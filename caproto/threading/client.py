# Regarding threads...
# The SharedBroadcaster has:
# - UDP socket SelectorThread
# - UDP command processing
# - forever retrying search requests for disconnected PV
# The Context has:
# - process search results
# - TCP socket SelectorThread
# - restart subscriptions
# The VirtualCircuit has:
# - ThreadPoolExecutor for processing user callbacks on read, write, subscribe
import array
import concurrent.futures
import errno
import functools
import getpass
import inspect
import itertools
import logging
import os
import selectors
import socket
import sys
import threading
import time
import weakref

from queue import Queue, Empty
from inspect import Parameter, Signature
from functools import partial
from collections import defaultdict, deque
import caproto as ca
from .._constants import (MAX_ID, STALE_SEARCH_EXPIRATION,
                          SEARCH_MAX_DATAGRAM_BYTES, RESPONSIVENESS_TIMEOUT)
from .._utils import (batch_requests, CaprotoError, ThreadsafeCounter,
                      socket_bytes_available, CaprotoTimeoutError,
                      CaprotoTypeError, CaprotoRuntimeError, CaprotoValueError,
                      CaprotoKeyError, CaprotoNetworkError)


print = partial(print, flush=True)


CIRCUIT_DEATH_ATTEMPTS = 3


class DeadCircuitError(CaprotoError):
    ...


def ensure_connected(func):
    @functools.wraps(func)
    def inner(self, *args, **kwargs):
        if isinstance(self, PV):
            pv = self
        elif isinstance(self, Subscription):
            pv = self.pv
        else:
            raise CaprotoTypeError("ensure_connected is intended to decorate "
                                   "methods of PV and Subscription.")
        # This `2` matches the default in read, write, wait_for_connection.
        raw_timeout = timeout = kwargs.get('timeout', 2)
        if timeout is not None:
            deadline = time.monotonic() + timeout
        with pv._in_use:
            pv._usages += 1
            # If needed, reconnect. Do this inside the lock so that we don't
            # try to do this twice. (No other threads that need this lock
            # can proceed until the connection is ready anyway!)
            if pv._idle:
                # The Context should have been maintaining a working circuit
                # for us while this was idle. We just need to re-create the
                # Channel.
                ready = pv.circuit_ready.wait(timeout=timeout)
                if not ready:
                    raise CaprotoTimeoutError(
                        f"{pv} could not connect within "
                        f"{float(raw_timeout):.3}-second timeout.")
                with pv.component_lock:
                    cm = pv.circuit_manager
                    cid = cm.circuit.new_channel_id()
                    chan = ca.ClientChannel(pv.name, cm.circuit, cid=cid)
                    cm.channels[cid] = chan
                    cm.pvs[cid] = pv
                    pv.circuit_manager.send(chan.create())
        try:
            for i in range(CIRCUIT_DEATH_ATTEMPTS):
                # On each iteration, subtract the time we already spent on any
                # previous attempts.
                if timeout is not None:
                    timeout = deadline - time.monotonic()
                ready = pv.channel_ready.wait(timeout=timeout)
                if not ready:
                    raise CaprotoTimeoutError(
                        f"{pv} could not connect within "
                        f"{float(raw_timeout):.3}-second timeout.")
                if timeout is not None:
                    timeout = deadline - time.monotonic()
                    kwargs['timeout'] = timeout
                self._idle = False
                cm = pv.circuit_manager
                try:
                    return func(self, *args, **kwargs)
                except DeadCircuitError:
                    # Something in func tried operate on the circuit after
                    # it died. The context will automatically build us a
                    # new circuit. Try again.
                    self.log.debug('Caught DeadCircuitError. '
                                   'Retrying %s.', func.__name__)
                    continue
                except TimeoutError:
                    # The circuit may have died after func was done calling
                    # methods on it but before we received some response we
                    # were expecting. The context will automatically build
                    # us a new circuit. Try again.
                    if cm.dead.is_set():
                        self.log.debug('Caught TimeoutError due to dead '
                                       'circuit. '
                                       'Retrying %s.', func.__name__)
                        continue
                    # The circuit is fine -- this is a real error.
                    raise

        finally:
            with pv._in_use:
                pv._usages -= 1
                pv._in_use.notify_all()
    return inner


class ThreadingClientException(CaprotoError):
    ...


class DisconnectedError(ThreadingClientException):
    ...


class ContextDisconnectedError(ThreadingClientException):
    ...


AUTOMONITOR_MAXLENGTH = 65536
TIMEOUT = 2
EVENT_ADD_BATCH_MAX_BYTES = 2**16
MIN_RETRY_SEARCHES_INTERVAL = 0.03
MAX_RETRY_SEARCHES_INTERVAL = 5
SEARCH_RETIREMENT_AGE = 8 * 60
RETRY_RETIRED_SEARCHES_INTERVAL = 60
RESTART_SUBS_PERIOD = 0.1
STR_ENC = os.environ.get('CAPROTO_STRING_ENCODING', 'latin-1')


class SelectorThread:
    """
    This is used internally by the Context and the VirtualCircuitManager.
    """
    def __init__(self, *, parent=None):
        self.thread = None  # set by the `start` method
        self._close_event = threading.Event()
        self.selector = selectors.DefaultSelector()

        if sys.platform == 'win32':
            # Empty select() list is problematic for windows
            dummy_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.selector.register(dummy_socket, selectors.EVENT_READ)

        self._socket_map_lock = threading.RLock()
        self.objects = weakref.WeakValueDictionary()
        self.id_to_socket = {}
        self.socket_to_id = {}

        self._register_sockets = set()
        self._unregister_sockets = set()
        self._object_id = 0

        if parent is not None:
            # Stop the selector if the parent goes out of scope
            self._parent = weakref.ref(parent, lambda obj: self.stop())

    @property
    def running(self):
        '''Selector thread is running'''
        return not self._close_event.is_set()

    def stop(self):
        self._close_event.set()

    def start(self):
        if self._close_event.is_set():
            raise CaprotoRuntimeError("Cannot be restarted once stopped.")
        self.thread = threading.Thread(target=self, daemon=True,
                                       name='selector')
        self.thread.start()

    def add_socket(self, sock, target_obj):
        with self._socket_map_lock:
            if sock in self.socket_to_id:
                raise CaprotoValueError('Socket already added')

            sock.setblocking(False)

            # assumption: only one sock per object
            self._object_id += 1
            self.objects[self._object_id] = target_obj
            self.id_to_socket[self._object_id] = sock
            self.socket_to_id[sock] = self._object_id
            weakref.finalize(target_obj,
                             lambda obj_id=self._object_id:
                             self._object_removed(obj_id))
            self._register_sockets.add(sock)
            # self.log.debug('Socket %s was added (obj %s)', sock, target_obj)

    def remove_socket(self, sock):
        with self._socket_map_lock:
            if sock not in self.socket_to_id:
                return
            obj_id = self.socket_to_id.pop(sock)
            del self.id_to_socket[obj_id]
            obj = self.objects.pop(obj_id, None)
            if obj is not None:
                obj.received(b'', None)

            if sock in self._register_sockets:
                # removed before it was even added...
                # self.log.debug('Socket %s was removed before it was added '
                #              '(obj = %s)', sock, obj)
                self._register_sockets.remove(sock)
            else:
                # self.log.debug('Socket %s was removed '
                #              '(obj = %s)', sock, obj)
                self._unregister_sockets.add(sock)

    def _object_removed(self, obj_id):
        with self._socket_map_lock:
            if obj_id in self.id_to_socket:
                sock = self.id_to_socket.pop(obj_id)
                # self.log.debug('Object ID %s was destroyed: removing %s', obj_id,
                #              sock)
                del self.socket_to_id[sock]
                self._unregister_sockets.add(sock)

    def __call__(self):
        '''Selector poll loop'''
        avail_buf = array.array('i', [0])
        while not self._close_event.is_set():
            with self._socket_map_lock:
                for sock in self._unregister_sockets:
                    self.selector.unregister(sock)
                self._unregister_sockets.clear()

                for sock in self._register_sockets:
                    self.selector.register(sock, selectors.EVENT_READ)
                self._register_sockets.clear()

            events = self.selector.select(timeout=0.1)
            with self._socket_map_lock:
                if self._unregister_sockets:
                    # some sockets may be affected here; try again
                    continue

                ready_ids = [self.socket_to_id[key.fileobj]
                             for key, mask in events]
                ready_objs = [(self.objects[obj_id], self.id_to_socket[obj_id])
                              for obj_id in ready_ids]

            for obj, sock in ready_objs:
                if sock in self._unregister_sockets:
                    continue

                # TODO: consider thread pool for recv and command_loop
                try:
                    bytes_available = socket_bytes_available(
                        sock, available_buffer=avail_buf)
                    bytes_recv, address = sock.recvfrom(bytes_available)
                except OSError as ex:
                    if ex.errno != errno.EAGAIN:
                        # register as a disconnection
                        # logger.error('Removing %s due to %s (%s)', obj, ex,
                        #              ex.errno)
                        self.remove_socket(sock)
                    continue

                # Let objects handle disconnection by returning a failure here
                if obj.received(bytes_recv, address) is ca.DISCONNECTED:
                    # self.log.debug('Removing %s = %s due to receive failure',
                    #              sock, obj)
                    self.remove_socket(sock)

                    # TODO: consider adding specific DISCONNECTED instead of b''
                    # sent to disconnected sockets


class SharedBroadcaster:
    def __init__(self, *, registration_retry_time=10.0):
        '''
        A broadcaster client which can be shared among multiple Contexts

        Parameters
        ----------
        registration_retry_time : float, optional
            The time, in seconds, between attempts made to register with the
            repeater. Default is 10.
        '''
        self.environ = ca.get_environment_variables()
        self.ca_server_port = self.environ['EPICS_CA_SERVER_PORT']

        self.udp_sock = ca.bcast_socket()

        self._search_lock = threading.RLock()
        self._retry_unanswered_searches_thread = None
        # This Event ensures that we send a registration request before our
        # first search request.
        self._searching_enabled = threading.Event()
        # This Event lets us nudge the search thread when the user asks for new
        # PVs (via Context.get_pvs).
        self._search_now = threading.Event()

        self._id_counter = itertools.count(0)
        self.search_results = {}  # map name to (time, address)
        self.unanswered_searches = {}  # map search id (cid) to [name, queue, retirement_deadline]
        self.server_protocol_versions = {}  # map address to protocol version

        self.listeners = weakref.WeakSet()

        self.broadcaster = ca.Broadcaster(our_role=ca.CLIENT)
        self.log = self.broadcaster.log
        self.command_bundle_queue = Queue()
        self.last_beacon = {}
        self.last_beacon_interval = {}

        # an event to tear down and clean up the broadcaster
        self._close_event = threading.Event()

        self.selector = SelectorThread(parent=self)
        self.selector.add_socket(self.udp_sock, self)
        self.selector.start()

        self._command_thread = threading.Thread(target=self.command_loop,
                                                daemon=True, name='command')
        self._command_thread.start()

        self._check_for_unresponsive_servers_thread = threading.Thread(
            target=self._check_for_unresponsive_servers,
            daemon=True, name='check_for_unresponsive_servers')
        self._check_for_unresponsive_servers_thread.start()

        self._registration_retry_time = registration_retry_time
        self._registration_last_sent = 0

        try:
            # Always attempt registration on initialization, but allow failures
            self._register()
        except Exception:
            self.log.exception('Broadcaster registration failed on init')

    def _should_attempt_registration(self):
        'Whether or not a registration attempt should be tried'
        if self.udp_sock is None:
            return True

        if (self.broadcaster.registered or
                self._registration_retry_time is None):
            return False

        since_last_attempt = time.monotonic() - self._registration_last_sent
        if since_last_attempt < self._registration_retry_time:
            return False

        return True

    def _register(self):
        'Send a registration request to the repeater'
        self._registration_last_sent = time.monotonic()
        command = self.broadcaster.register()

        self.send(ca.EPICS_CA2_PORT, command)
        self._searching_enabled.set()

    def new_id(self):
        while True:
            i = next(self._id_counter)
            if i == MAX_ID:
                self._id_counter = itertools.count(0)
                continue
            return i

    def add_listener(self, listener):
        with self._search_lock:
            if self._retry_unanswered_searches_thread is None:
                self._retry_unanswered_searches_thread = threading.Thread(
                    target=self._retry_unanswered_searches, daemon=True,
                    name='retry')
                self._retry_unanswered_searches_thread.start()

            self.listeners.add(listener)

    def remove_listener(self, listener):
        try:
            self.listeners.remove(listener)
        except KeyError:
            pass
        if not self.listeners:
            self.disconnect()

    def disconnect(self, *, wait=True):
        if self.udp_sock is not None:
            self.selector.remove_socket(self.udp_sock)

        self._close_event.set()
        self.search_results.clear()
        self._registration_last_sent = 0
        self._searching_enabled.clear()
        self.broadcaster.disconnect()
        self.selector.stop()
        if wait:
            self._command_thread.join()
            self.selector.thread.join()
            self._retry_unanswered_searches_thread.join()

    def send(self, port, *commands):
        """
        Process a command and transport it over the UDP socket.
        """
        bytes_to_send = self.broadcaster.send(*commands)
        for host in ca.get_address_list():
            if ':' in host:
                host, _, port_as_str = host.partition(':')
                specified_port = int(port_as_str)
            else:
                specified_port = port
            try:
                self.broadcaster.log.debug(
                    'Sending %d bytes to %s:%d',
                    len(bytes_to_send), host, specified_port)
                self.udp_sock.sendto(bytes_to_send, (host, specified_port))
            except OSError as ex:
                raise CaprotoNetworkError(
                    f'{ex} while sending {len(bytes_to_send)} bytes to '
                    f'{host}:{specified_port}') from ex

    def get_cached_search_result(self, name, *,
                                 threshold=STALE_SEARCH_EXPIRATION):
        'Returns address if found, raises KeyError if missing or stale.'
        address, timestamp = self.search_results[name]
        # this block of code is only to re-fresh the time found on
        # any PVs.  If we can find any context which has any circuit which
        # has any channel talking to this PV name then it is not stale so
        # re-up the timestamp to now.
        if time.monotonic() - timestamp > threshold:
            # TODO this is very inefficient
            for context in self.listeners:
                for addr, cm in context.circuit_managers.items():
                    if cm.connected and name in cm.all_created_pvnames:
                        # A valid connection exists in one of our clients, so
                        # ignore the stale result status
                        self.search_results[name] = (address, time.monotonic())
                        # TODO verify that addr matches address
                        return address

            # Clean up expired result.
            self.search_results.pop(name, None)
            raise CaprotoKeyError(f'{name!r}: stale search result')

        return address

    def search(self, results_queue, names, *, timeout=2):
        """
        Search for PV names.

        The ``results_queue`` will receive ``(address, names)`` (the address of
        a server and a list of name(s) that it has) when results are received.

        If a cached result is already known, it will be put immediately into
        ``results_queue`` from this thread during this method's execution.

        If not, a SearchRequest will be sent from another thread. If necessary,
        the request will be re-sent periodically. When a matching response is
        received (by yet another thread) ``(address, names)`` will be put into
        the ``results_queue``.
        """
        if self._should_attempt_registration():
            self._register()

        new_id = self.new_id
        unanswered_searches = self.unanswered_searches

        with self._search_lock:
            # We have have already searched for these names recently.
            # Filter `pv_names` down to a subset, `needs_search`.
            needs_search = []
            use_cached_search = defaultdict(list)
            for name in names:
                try:
                    address = self.get_cached_search_result(name)
                except KeyError:
                    needs_search.append(name)
                else:
                    use_cached_search[address].append(name)

            for address, names in use_cached_search.items():
                results_queue.put((address, names))

            # Generate search_ids and stash them on Context state so they can
            # be used to match SearchResponses with SearchRequests.
            search_ids = []
            # Search requests that are past their retirement deadline with no
            # results will be searched for less frequently.
            retirement_deadline = time.monotonic() + SEARCH_RETIREMENT_AGE
            for name in needs_search:
                search_id = new_id()
                search_ids.append(search_id)
                # The value is a list because we mutate it to update the
                # retirement deadline sometimes.
                unanswered_searches[search_id] = [name, results_queue, retirement_deadline]
        self._search_now.set()

    def cancel(self, *names):
        """
        Cancel searches for these names.

        Parameters
        ----------
        *names : strings
            any number of PV names

        Any PV instances that were awaiting these results will be stuck until
        :meth:`get_pvs` is called again.
        """
        with self._search_lock:
            for search_id, item in list(self.unanswered_searches.items()):
                if item[0] in names:
                    del self.unanswered_searches[search_id]

    def search_now(self):
        """
        Force the Broadcaster to reissue all unanswered search requests now.

        Left to its own devices, the Broadcaster will do this at regular
        intervals automatically. This method is intended primarily for
        debugging and should not be needed in normal use.
        """
        self._search_now.set()

    def received(self, bytes_recv, address):
        "Receive and process and next command broadcasted over UDP."
        if bytes_recv:
            commands = self.broadcaster.recv(bytes_recv, address)
            if commands:
                self.command_bundle_queue.put(commands)
        return 0

    def command_loop(self):
        # Receive commands in 'bundles' (corresponding to the contents of one
        # UDP datagram). Match SearchResponses to their SearchRequests, and
        # put (address, (name1, name2, name3, ...)) into a queue. The receiving
        # end of that queue is held by Context._process_search_results.

        # Save doing a 'self' lookup in the inner loop.
        search_results = self.search_results
        server_protocol_versions = self.server_protocol_versions
        unanswered_searches = self.unanswered_searches
        queues = defaultdict(list)
        results_by_cid = deque(maxlen=1000)
        self.log.debug('Broadcaster command loop is running.')

        while not self._close_event.is_set():
            try:
                commands = self.command_bundle_queue.get(timeout=0.5)
            except Empty:
                # By restarting the loop, we will first check that we are not
                # supposed to shut down the thread before we go back to
                # waiting on the queue again.
                continue

            try:
                self.broadcaster.process_commands(commands)
            except ca.CaprotoError as ex:
                self.log.warning('Broadcaster command error', exc_info=ex)
                continue

            queues.clear()
            now = time.monotonic()
            for command in commands:
                if isinstance(command, ca.Beacon):
                    now = time.monotonic()
                    address = (command.address, command.server_port)
                    if address not in self.last_beacon:
                        # We made a new friend!
                        self.log.info("Watching Beacons from %s:%d",
                                      *address)
                        self._new_server_found()
                    else:
                        interval = now - self.last_beacon[address]
                        if interval < self.last_beacon_interval.get(address, 0) / 4:
                            # Beacons are arriving *faster*? The server at this
                            # address may have restarted.
                            self.log.info(
                                "Beacon anomaly: %s:%d may have restarted.",
                                *address)
                            self._new_server_found()
                        self.last_beacon_interval[address] = interval
                    self.last_beacon[address] = now
                elif isinstance(command, ca.VersionResponse):
                    # Per the specification, in CA < 4.11, VersionResponse does
                    # not include minor version number (it is always 0) and is
                    # interpreted as an echo command that carries no data.
                    # Version exchange is performed immediately after channel
                    # creation.
                    if command.version == 0:
                        self.log.warning(
                            "Server is speaking some protocol version "
                            "older than 4.11. It will not report a "
                            "specific version until a channel is created. "
                            "Quality of support is unknown.")

                elif isinstance(command, ca.SearchResponse):
                    cid = command.cid
                    try:
                        with self._search_lock:
                            name, queue, _ = unanswered_searches.pop(cid)
                    except KeyError:
                        # This is a redundant response, which the EPICS
                        # spec tells us to ignore. (The first responder
                        # to a given request wins.)
                        try:
                            _, name = next(r for r in results_by_cid if r[0] == cid)
                        except StopIteration:
                            continue
                        else:
                            if name in self.search_results:
                                accepted_address, _ = self.search_results[name]
                                new_address = ca.extract_address(command)
                                self.log.warning(
                                    "PV %s with cid %d found on multiple servers. "
                                    "Accepted address is %s:%d. "
                                    "Also found on %s:%d",
                                    name, cid, *accepted_address, *new_address)
                    else:
                        results_by_cid.append((cid, name))
                        address = ca.extract_address(command)
                        queues[queue].append(name)
                        # Cache this to save time on future searches.
                        # (Entries expire after STALE_SEARCH_EXPIRATION.)
                        self.log.debug('Found %s at %s:%d', name, *address)
                        search_results[name] = (address, now)
                        server_protocol_versions[address] = command.version
            # Send the search results to the Contexts that asked for
            # them. This is probably more general than is has to be but
            # I'm playing it safe for now.
            if queues:
                for queue, names in queues.items():
                    queue.put((address, names))

        self.log.debug('Broadcaster command loop has exited.')

    def _new_server_found(self):
        # Bring all the unanswered seraches out of retirement
        # to see if we have a new match.
        retirement_deadline = time.monotonic() + SEARCH_RETIREMENT_AGE
        with self._search_lock:
            for item in self.unanswered_searches.values():
                item[-1] = retirement_deadline

    def _check_for_unresponsive_servers(self):
        self.log.debug('Broadcaster check for unresponsive servers loop is running.')

        MARGIN = 1  # extra time (seconds) allowed between Beacons
        checking = dict()  # map address to deadline for check to resolve
        servers = defaultdict(weakref.WeakSet)  # map address to VirtualCircuitManagers
        last_heard = dict()  # map address to time of last response

        # Make locals to save getattr lookups in the loop.
        last_beacon = self.last_beacon
        listeners = self.listeners

        while not self._close_event.is_set():
            servers.clear()
            last_heard.clear()
            now = time.monotonic()

            # We are interested in identifying servers that we have not heard
            # from since some time cutoff in the past.
            cutoff = now - (self.environ['EPICS_CA_CONN_TMO'] + MARGIN)

            # Map each server address to VirtualCircuitManagers connected to
            # that address, across all Contexts ("listeners").
            for listener in listeners:
                for (address, _), circuit_manager in listener.circuit_managers.items():
                    servers[address].add(circuit_manager)

            # When is the last time we heard from each server, either via a
            # Beacon or from TCP packets related to user activity or any
            # circuit?
            for address, circuit_managers in servers.items():
                last_tcp_receipt = (cm.last_tcp_receipt for cm in circuit_managers)
                last_heard[address] = max((last_beacon.get(address, 0),
                                           *last_tcp_receipt))

                # If is has been too long --- and if we aren't already checking
                # on this server --- try to prompt a response over TCP by
                # sending an EchoRequest.
                if last_heard[address] < cutoff and address not in checking:
                    # Record that we are checking on this address and set a
                    # deadline for a response.
                    checking[address] = now + RESPONSIVENESS_TIMEOUT
                    self.log.debug(
                        "Missed Beacons from %s:%d. Sending EchoRequest to "
                        "check that server is responsive.", *address)
                    # Send on all circuits. One might be less backlogged
                    # with queued commands than the others and thus able to
                    # respond faster. In the majority of cases there will only
                    # be one circuit per server anyway, so this is a minor
                    # distinction.
                    for circuit_manager in circuit_managers:
                        try:
                            circuit_manager.send(ca.EchoRequest())
                        except Exception:
                            # Send failed. Server is likely dead, but we'll
                            # catch that shortly; no need to handle it
                            # specially here.
                            pass

            # Check to see if any of our ongoing checks have resolved or
            # failed to resolve within the allowed response window.
            for address, deadline in list(checking.items()):
                if last_heard[address] > cutoff:
                    # It's alive!
                    checking.pop(address)
                elif deadline < now:
                    # No circuit connected to the server at this address has
                    # sent Beacons or responded to the EchoRequest. We assume
                    # it is unresponsive. The EPICS specification says the
                    # behavior is undefined at this point. We choose to
                    # disconnect all circuits from that server so that PVs can
                    # attempt to connect to a new server, such as a failover
                    # backup.
                    for circuit_manager in servers[address]:
                        if circuit_manager.connected:
                            circuit_manager.log.warning(
                                "Server at %s:%d is unresponsive. "
                                "Disconnecting circuit manager %r. PVs will "
                                "automatically begin attempting to reconnect "
                                "to a responsive server.",
                                *address, circuit_manager)
                            circuit_manager.disconnect()
                    checking.pop(address)
                # else:
                #     # We are still waiting to give the server time to respond
                #     # to the EchoRequest.
            time.sleep(0.5)

        self.log.debug('Broadcaster check for unresponsive servers loop has exited.')

    def _retry_unanswered_searches(self):
        """
        Periodically (re-)send a SearchRequest for all unanswered searches.

        """
        # Each time new searches are added, the self._search_now Event is set,
        # and we reissue *all* unanswered searches.
        #
        # We then frequently retry the unanswered searches that are younger
        # than SEARCH_RETIREMENT_AGE, backing off from an interval of
        # MIN_RETRY_SEARCHES_INTERVAL to MAX_RETRY_SEARCHES_INTERVAL. The
        # interval is reset to MIN_RETRY_SEARCHES_INTERVAL each time new
        # searches are added.
        #
        # For the searches older than SEARCH_RETIREMENT_AGE, we adopt a slower
        # period to minimize network traffic. We only resend every
        # RETRY_RETIRED_SEARCHES_INTERVAL or, again, whenever new searches
        # are added.
        self.log.debug('Broadcaster search-retry thread has started.')
        time_to_check_on_retirees = time.monotonic() + RETRY_RETIRED_SEARCHES_INTERVAL
        interval = MIN_RETRY_SEARCHES_INTERVAL
        while not self._close_event.is_set():
            try:
                self._searching_enabled.wait(0.5)
            except TimeoutError:
                # Here we go check on self._close_event before waiting again.
                continue

            t = time.monotonic()

            # filter to just things that need to go out
            def _construct_search_requests(items):
                for search_id, it in items:
                    yield ca.SearchRequest(it[0], search_id,
                                           ca.DEFAULT_PROTOCOL_VERSION)

            with self._search_lock:
                if t >= time_to_check_on_retirees:
                    items = list(self.unanswered_searches.items())
                    time_to_check_on_retirees += RETRY_RETIRED_SEARCHES_INTERVAL
                else:
                    # Skip over searches that haven't gotten any results in
                    # SEARCH_RETIREMENT_AGE.
                    items = list((search_id, it)
                                 for search_id, it in self.unanswered_searches.items()
                                 if (it[-1] > t))
            requests = _construct_search_requests(items)

            if not self._searching_enabled.is_set():
                continue

            if items:
                self.log.debug('Sending %d SearchRequests', len(items))

            version_req = ca.VersionRequest(0, ca.DEFAULT_PROTOCOL_VERSION)
            for batch in batch_requests(requests,
                                        SEARCH_MAX_DATAGRAM_BYTES - len(version_req)):
                self.send(self.ca_server_port,
                          version_req,
                          *batch)

            wait_time = max(0, interval - (time.monotonic() - t))
            # Double the interval for the next loop.
            interval = min(2 * interval, MAX_RETRY_SEARCHES_INTERVAL)
            if self._search_now.wait(wait_time):
                # New searches have been requested. Reset the interval between
                # subseqent searches and force a check on the "retirees".
                time_to_check_on_retirees = t
                interval = MIN_RETRY_SEARCHES_INTERVAL
            self._search_now.clear()

        self.log.debug('Broadcaster search-retry thread has exited.')

    def __del__(self):
        try:
            self.disconnect()
            self.selector = None
        except AttributeError:
            pass


class Context:
    """
    Encapsulates the state and connections of a client

    Parameters
    ----------
    broadcaster : SharedBroadcaster, optional
        If None is specified, a fresh one is instantiated.
    host_name : string, optional
        uses value of ``socket.gethostname()`` by default
    client_name : string, optional
        uses value of ``getpass.getuser()`` by default
    max_workers : integer, optional
        Number of worker threaders *per VirtualCircuit* for executing user
        callbacks. Default is 1. For any number of workers, workers will
        receive updates in the order which they are received from the server.
        That is, work on each update will *begin* in sequential order.
        Work-scheduling internal to the user callback is outside caproto's
        control. If the number of workers is set to greater than 1, the work on
        each update may not *finish* in a deterministic order. For example, if
        workers are writing lines into a file, the only way to guarantee that
        the lines are ordered properly is to use only one worker. If ordering
        matters for your application, think carefully before increasing this
        value from 1.
    """
    def __init__(self, broadcaster=None, *,
                 host_name=None, client_name=None, max_workers=1):
        if broadcaster is None:
            broadcaster = SharedBroadcaster()
        self.broadcaster = broadcaster
        if host_name is None:
            host_name = socket.gethostname()
        self.host_name = host_name
        if client_name is None:
            client_name = getpass.getuser()
        self.max_workers = max_workers
        self.client_name = client_name
        self.log = logging.getLogger(f'caproto.ctx.{id(self)}')
        self.pv_cache_lock = threading.RLock()
        self.circuit_managers = {}  # keyed on ((host, port), priority)
        self._lock_during_get_circuit_manager = threading.RLock()
        self.pvs = {}  # (name, priority) -> pv
        # name -> set of pvs  --- with varied priority
        self.pvs_needing_circuits = defaultdict(set)
        self.broadcaster.add_listener(self)
        self._search_results_queue = Queue()
        # an event to close and clean up the whole context
        self._close_event = threading.Event()
        self.subscriptions_lock = threading.RLock()
        self.subscriptions_to_activate = defaultdict(set)
        self.activate_subscriptions_now = threading.Event()

        self._process_search_results_thread = threading.Thread(
            target=self._process_search_results_loop,
            daemon=True, name='search')
        self._process_search_results_thread.start()

        self._activate_subscriptions_thread = threading.Thread(
            target=self._activate_subscriptions,
            daemon=True, name='activate_subscriptions')
        self._activate_subscriptions_thread.start()

        self.selector = SelectorThread(parent=self)
        self.selector.start()
        self._user_disconnected = False

    def __repr__(self):
        return (f"<Context "
                f"searches_pending={len(self.broadcaster.unanswered_searches)} "
                f"circuits={len(self.circuit_managers)} "
                f"pvs={len(self.pvs)} "
                f"idle={len([1 for pv in self.pvs.values() if pv._idle])}>")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.disconnect(wait=True)

    def get_pvs(self, *names, priority=0, connection_state_callback=None,
                access_rights_callback=None):
        """
        Return a list of PV objects.

        These objects may not be connected at first. Channel creation occurs on
        a background thread.

        PVs are uniquely defined by their name and priority. If a PV with the
        same name and priority is requested twice, the same (cached) object is
        returned. Any callbacks included here are added to added alongside any
        existing ones.

        Parameters
        ----------
        *names : strings
            any number of PV names
        priority : integer
            Used by the server to triage subscription responses when under high
            load. 0 is lowest; 99 is highest.
        connection_state_callback : callable
            Expected signature: ``f(pv, state)`` where ``pv`` is the instance
            of ``PV`` whose state has changed and ``state`` is a string
        access_rights_callback : callable
            Expected signature: ``f(pv, access_rights)`` where ``pv`` is the
            instance of ``PV`` whose state has changed and ``access_rights`` is
            a member of the caproto ``AccessRights`` enum

        """
        if self._user_disconnected:
            raise ContextDisconnectedError("This Context is no longer usable.")
        pvs = []  # list of all PV objects to return
        names_to_search = []  # subset of names that we need to search for
        for name in names:
            with self.pv_cache_lock:
                try:
                    pv = self.pvs[(name, priority)]
                    new_instance = False
                except KeyError:
                    pv = PV(name, priority, self, connection_state_callback,
                            access_rights_callback)
                    names_to_search.append(name)
                    self.pvs[(name, priority)] = pv
                    self.pvs_needing_circuits[name].add(pv)
                    new_instance = True

            if not new_instance:
                if connection_state_callback is not None:
                    pv.connection_state_callback.add_callback(
                        connection_state_callback)
                if access_rights_callback is not None:
                    pv.access_rights_callback.add_callback(
                        access_rights_callback)

            pvs.append(pv)

        # TODO: potential bug?
        # if callback is quick, is there a chance downstream listeners may
        # never receive notification?

        # Ask the Broadcaster to search for every PV for which we do not
        # already have an instance. It might already have a cached search
        # result, but that is the concern of broadcaster.search.
        if names_to_search:
            self.broadcaster.search(self._search_results_queue,
                                    names_to_search)
        return pvs

    def reconnect(self, keys):
        # We will reuse the same PV object but use a new cid.
        names = []
        pvs = []

        for key in keys:
            with self.pv_cache_lock:
                pv = self.pvs[key]
            pvs.append(pv)
            name, _ = key
            names.append(name)
            # If there is a cached search result for this name, expire it.
            self.broadcaster.search_results.pop(name, None)
            with self.pv_cache_lock:
                self.pvs_needing_circuits[name].add(pv)

        self.broadcaster.search(self._search_results_queue, names)

    def _process_search_results_loop(self):
        # Receive (address, (name1, name2, ...)). The sending side of this
        # queue is held by SharedBroadcaster.command_loop.
        self.log.debug('Context search-results processing loop has '
                       'started.')
        while not self._close_event.is_set():
            try:
                address, names = self._search_results_queue.get(timeout=0.5)
            except Empty:
                # By restarting the loop, we will first check that we are not
                # supposed to shut down the thread before we go back to
                # waiting on the queue again.
                continue

            channels_grouped_by_circuit = defaultdict(list)
            # Assign each PV a VirtualCircuitManager for managing a socket
            # and tracking circuit state, as well as a ClientChannel for
            # tracking channel state.
            for name in names:
                # There could be multiple PVs with the same name and
                # different priority. That is what we are looping over
                # here. There could also be NO PVs with this name that need
                # a circuit, because we could be receiving a duplicate
                # search response (which we are supposed to ignore).
                with self.pv_cache_lock:
                    pvs = self.pvs_needing_circuits.pop(name, set())
                for pv in pvs:
                    # Get (make if necessary) a VirtualCircuitManager. This
                    # is where TCP socket creation happens.
                    cm = self.get_circuit_manager(address, pv.priority)
                    circuit = cm.circuit

                    pv.circuit_manager = cm
                    # TODO: NOTE: we are not following the suggestion to
                    # use the same cid as in the search. This simplifies
                    # things between the broadcaster and Context.
                    cid = cm.circuit.new_channel_id()
                    chan = ca.ClientChannel(name, circuit, cid=cid)
                    cm.channels[cid] = chan
                    cm.pvs[cid] = pv
                    channels_grouped_by_circuit[cm].append(chan)
                    pv.circuit_ready.set()

            # Initiate channel creation with the server.
            for cm, channels in channels_grouped_by_circuit.items():
                commands = [chan.create() for chan in channels]
                try:
                    cm.send(*commands)
                except Exception:
                    if cm.dead.is_set():
                        self.log.debug("Circuit died while we were trying "
                                       "to create the channel. We will "
                                       "keep attempting this until it "
                                       "works.")
                        # When the Context creates a new circuit, we will end
                        # up here again. No big deal.
                        continue
                    raise

        self.log.debug('Context search-results processing thread has exited.')

    def get_circuit_manager(self, address, priority):
        """
        Return a VirtualCircuitManager for this address, priority. (It manages
        a caproto.VirtualCircuit and a TCP socket.)

        Make a new one if necessary.
        """
        with self._lock_during_get_circuit_manager:
            cm = self.circuit_managers.get((address, priority), None)
            if cm is None or cm.dead.is_set():
                version = self.broadcaster.server_protocol_versions[address]
                circuit = ca.VirtualCircuit(
                    our_role=ca.CLIENT,
                    address=address,
                    priority=priority,
                    protocol_version=version)
                cm = VirtualCircuitManager(self, circuit, self.selector)
                self.circuit_managers[(address, priority)] = cm
            return cm

    def _activate_subscriptions(self):
        while not self._close_event.is_set():
            t = time.monotonic()
            with self.subscriptions_lock:
                items = list(self.subscriptions_to_activate.items())
                self.subscriptions_to_activate.clear()
            for cm, subs in items:
                def requests():
                    "Yield EventAddRequest commands."
                    for sub in subs:
                        command = sub.compose_command()
                        # compose_command() returns None if this
                        # Subscription is inactive (meaning there are no
                        # user callbacks attached). It will send an
                        # EventAddRequest on its own if/when the user does
                        # add any callbacks, so we can skip it here.
                        if command is not None:
                            yield command

                for batch in batch_requests(requests(),
                                            EVENT_ADD_BATCH_MAX_BYTES):
                    try:
                        cm.send(*batch)
                    except Exception:
                        if cm.dead.is_set():
                            self.log.debug("Circuit died while we were "
                                           "trying to activate "
                                           "subscriptions. We will "
                                           "keep attempting this until it "
                                           "works.")
                        # When the Context creates a new circuit, we will
                        # end up here again. No big deal.
                        break

            wait_time = max(0, (RESTART_SUBS_PERIOD -
                                (time.monotonic() - t)))
            self.activate_subscriptions_now.wait(wait_time)
            self.activate_subscriptions_now.clear()

        self.log.debug('Context restart-subscriptions thread exiting')

    def disconnect(self, *, wait=True):
        self._user_disconnected = True
        try:
            self._close_event.set()
            # disconnect any circuits we have
            circuits = list(self.circuit_managers.values())
            total_circuits = len(circuits)
            disconnected = False
            for idx, circuit in enumerate(circuits, 1):
                if circuit.connected:
                    self.log.debug('Disconnecting circuit %d/%d: %s',
                                   idx, total_circuits, circuit)
                    circuit.disconnect()
                    disconnected = True
            if disconnected:
                self.log.debug('All circuits disconnected')
        finally:
            # Remove from Broadcaster.
            self.broadcaster.remove_listener(self)

            # clear any state about circuits and search results
            self.log.debug('Clearing circuit managers')
            self.circuit_managers.clear()

            # disconnect the underlying state machine
            self.broadcaster.remove_listener(self)

            self.log.debug("Stopping SelectorThread of the context")
            self.selector.stop()

            if wait:
                self._process_search_results_thread.join()
                self._activate_subscriptions_thread.join()
                self.selector.thread.join()

            self.log.debug('Context disconnection complete')

    def __del__(self):
        try:
            self.disconnect(wait=False)
        except Exception:
            ...
        finally:
            self.selector = None
            self.broadcaster = None
            self.circuit_managers = None


class VirtualCircuitManager:
    """
    Encapsulates a VirtualCircuit, a TCP socket, and additional state

    This object should never be instantiated directly by user code. It is used
    internally by the Context. Its methods may be touched by user code, but
    this is rarely necessary.
    """
    __slots__ = ('context', 'circuit', 'channels', 'ioids', '_ioid_counter',
                 'subscriptions', '_ready', 'log',
                 'socket', 'selector', 'pvs', 'all_created_pvnames',
                 'dead', 'process_queue', 'processing',
                 '_subscriptionid_counter', 'user_callback_executor',
                 'last_tcp_receipt', '__weakref__')

    def __init__(self, context, circuit, selector, timeout=TIMEOUT):
        self.context = context
        self.circuit = circuit  # a caproto.VirtualCircuit
        self.log = circuit.log
        self.channels = {}  # map cid to Channel
        self.pvs = {}  # map cid to PV
        self.ioids = {}  # map ioid to Channel and info dict
        self.subscriptions = {}  # map subscriptionid to Subscription
        self.socket = None
        self.selector = selector
        self.user_callback_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=self.context.max_workers,
            thread_name_prefix='user-callback-executor')
        self.last_tcp_receipt = None
        # keep track of all PV names that are successfully connected to within
        # this circuit. This is to be cleared upon disconnection:
        self.all_created_pvnames = []
        self.dead = threading.Event()
        self._ioid_counter = ThreadsafeCounter()
        self._subscriptionid_counter = ThreadsafeCounter()
        self._ready = threading.Event()

        # Connect.
        if self.circuit.states[ca.SERVER] is ca.IDLE:
            self.socket = socket.create_connection(self.circuit.address)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.selector.add_socket(self.socket, self)
            self.send(ca.VersionRequest(self.circuit.priority,
                                        ca.DEFAULT_PROTOCOL_VERSION),
                      ca.HostNameRequest(self.context.host_name),
                      ca.ClientNameRequest(self.context.client_name))
        else:
            raise CaprotoRuntimeError("Cannot connect. States are {} "
                                      "".format(self.circuit.states))
        # Old versions of the protocol do not send a VersionResponse at TCP
        # connection time, so set this Event manually rather than waiting for
        # it to be set by receipt of a VersionResponse.
        if self.context.broadcaster.server_protocol_versions[self.circuit.address] < 12:
            self._ready.set()
        ready = self._ready.wait(timeout=timeout)
        if not ready:
            host, port = self.circuit.address
            raise CaprotoTimeoutError(f"Circuit with server at {host}:{port} "
                                      f"did not connect within "
                                      f"{float(timeout):.3}-second timeout.")

    def __repr__(self):
        return (f"<VirtualCircuitManager circuit={self.circuit} "
                f"pvs={len(self.pvs)} ioids={len(self.ioids)} "
                f"subscriptions={len(self.subscriptions)}>")

    @property
    def connected(self):
        return self.circuit.states[ca.CLIENT] is ca.CONNECTED

    def _socket_send(self, buffers_to_send):
        'Send a list of buffers over the socket'
        try:
            return self.socket.sendmsg(buffers_to_send)
        except BlockingIOError:
            raise ca.SendAllRetry()

    def send(self, *commands):
        # Turn the crank: inform the VirtualCircuit that these commands will
        # be send, and convert them to buffers.
        buffers_to_send = self.circuit.send(*commands)
        # Send bytes over the wire using some caproto utilities.
        ca.send_all(buffers_to_send, self._socket_send)

    def received(self, bytes_recv, address):
        """Receive and process and next command from the virtual circuit.

        This will be run on the recv thread"""
        self.last_tcp_receipt = time.monotonic()
        commands, num_bytes_needed = self.circuit.recv(bytes_recv)

        for c in commands:
            self._process_command(c)

        if not bytes_recv:
            # Tell the selector to remove our socket
            return ca.DISCONNECTED
        return num_bytes_needed

    def events_off(self):
        """
        Suspend updates to all subscriptions on this circuit.

        This may be useful if the server produces updates faster than the
        client can processs them.
        """
        self.send(ca.EventsOffRequest())

    def events_on(self):
        """
        Reactive updates to all subscriptions on this circuit.
        """
        self.send(ca.EventsOnRequest())

    def _process_command(self, command):
        try:
            self.circuit.process_command(command)
        except ca.CaprotoError as ex:
            if hasattr(ex, 'channel'):
                channel = ex.channel
                self.log.warning('Invalid command %s for Channel %s in state %s',
                                 command, channel, channel.states,
                                 exc_info=ex)
                # channel exceptions are not fatal
                return
            else:
                self.log.error('Invalid command %s for VirtualCircuit %s in '
                               'state %s', command, self, self.circuit.states,
                               exc_info=ex)
                # circuit exceptions are fatal; exit the loop
                self.disconnect()
                return

        if command is ca.DISCONNECTED:
            self._disconnected()
        elif isinstance(command, (ca.VersionResponse,)):
            assert self.connected  # double check that the state machine agrees
            self._ready.set()
        elif isinstance(command, (ca.ReadNotifyResponse,
                                  ca.ReadResponse,
                                  ca.WriteNotifyResponse)):
            ioid_info = self.ioids.pop(command.ioid)
            deadline = ioid_info['deadline']
            if deadline is not None and time.monotonic() > deadline:
                self.log.warn("Ignoring late response with ioid=%d because "
                              "it arrived %.3f seconds after the deadline "
                              "specified by the timeout.", command.ioid,
                              time.monotonic() - deadline)
                return

            event = ioid_info.get('event')
            if event is not None:
                # If PV.read() or PV.write() are waiting on this response,
                # they hold a reference to ioid_info. We will use that to
                # provide the response to them and then set the Event that they
                # are waiting on.
                ioid_info['response'] = command
                event.set()
            callback = ioid_info.get('callback')
            if callback is not None:
                self.user_callback_executor.submit(callback, command)

        elif isinstance(command, ca.EventAddResponse):
            try:
                sub = self.subscriptions[command.subscriptionid]
            except KeyError:
                # This subscription has been removed. We assume that this
                # response was in flight before the server processed our
                # unsubscription.
                pass
            else:
                # This method submits jobs to the Contexts's
                # ThreadPoolExecutor for user callbacks.
                sub.process(command)
        elif isinstance(command, ca.AccessRightsResponse):
            pv = self.pvs[command.cid]
            pv.access_rights_changed(command.access_rights)
        elif isinstance(command, ca.EventCancelResponse):
            ...
        elif isinstance(command, ca.CreateChanResponse):
            pv = self.pvs[command.cid]
            chan = self.channels[command.cid]
            self.all_created_pvnames.append(pv.name)
            with pv.component_lock:
                pv.channel = chan
                pv.channel_ready.set()
            pv.connection_state_changed('connected', chan)
        elif isinstance(command, (ca.ServerDisconnResponse,
                                  ca.ClearChannelResponse)):
            pv = self.pvs[command.cid]
            pv.connection_state_changed('disconnected', None)
            # NOTE: pv remains valid until server goes down
        elif isinstance(command, ca.EchoResponse):
            # The important effect here is that it will have updated
            # self.last_tcp_receipt when the bytes flowed through
            # self.received.
            ...
        else:
            self.log.debug('other command %s', command)

    def _disconnected(self):
        # Ensure that this method is idempotent.
        if self.dead.is_set():
            return
        self.log.debug('Virtual circuit with address %s:%d has disconnected.',
                       *self.circuit.address)
        # Update circuit state. This will be reflected on all PVs, which
        # continue to hold a reference to this disconnected circuit.
        self.circuit.disconnect()
        for pv in self.pvs.values():
            pv.channel_ready.clear()
            pv.circuit_ready.clear()
        self.dead.set()
        for ioid_info in self.ioids.values():
            # Un-block any calls to PV.read() or PV.write() that are waiting on
            # responses that we now know will never arrive. They will check on
            # circuit health and raise appropriately.
            event = ioid_info.get('event')
            if event is not None:
                event.set()

        self.all_created_pvnames.clear()
        for pv in self.pvs.values():
            pv.connection_state_changed('disconnected', None)
        # Remove VirtualCircuitManager from Context.
        # This will cause all future calls to Context.get_circuit_manager()
        # to create a fresh VirtualCiruit and VirtualCircuitManager.
        self.context.circuit_managers.pop(self.circuit.address, None)

        # Clean up the socket if it has not yet been cleared:
        sock, self.socket = self.socket, None
        if sock is not None:
            self.selector.remove_socket(sock)
            try:
                sock.shutdown(socket.SHUT_WR)
                sock.close()
            except OSError:
                pass

        # Kick off attempt to reconnect all PVs via fresh circuit(s).
        self.log.debug('Kicking off reconnection attempts for %d PVs '
                       'disconnected from %s:%d....',
                       len(self.channels), *self.circuit.address)
        self.context.reconnect(((chan.name, chan.circuit.priority)
                                for chan in self.channels.values()))

        self.log.debug("Shutting down ThreadPoolExecutor for user callbacks")
        self.user_callback_executor.shutdown()

    def disconnect(self):
        self._disconnected()
        if self.socket is None:
            return

        sock, self.socket = self.socket, None
        try:
            sock.shutdown(socket.SHUT_WR)
        except OSError:
            pass
        self.log.debug('Circuit manager disconnected by user')

    def __del__(self):
        try:
            self.disconnect()
        except AttributeError:
            pass


class PV:
    """
    Represents one PV, specified by a name and priority.

    This object may exist prior to connection and persists across any
    subsequent re-connections.

    This object should never be instantiated directly by user code; rather it
    should be created by calling the ``get_pvs`` method on a ``Context``
    object.
    """
    __slots__ = ('name', 'priority', 'context', '_circuit_manager', '_channel',
                 'circuit_ready', 'channel_ready',
                 'access_rights_callback', 'subscriptions',
                 'command_bundle_queue', 'component_lock', '_idle', '_in_use',
                 '_usages', 'connection_state_callback', 'log',
                 '__weakref__')

    def __init__(self, name, priority, context, connection_state_callback,
                 access_rights_callback):
        """
        These must be instantiated by a Context, never directly.
        """
        self.name = name
        self.priority = priority
        self.context = context
        self.log = logging.getLogger(f'caproto.ch.{name}.{priority}')
        # Use this lock whenever we touch circuit_manager or channel.
        self.component_lock = threading.RLock()
        self.circuit_ready = threading.Event()
        self.channel_ready = threading.Event()
        self.connection_state_callback = CallbackHandler(self)
        self.access_rights_callback = CallbackHandler(self)

        if connection_state_callback is not None:
            self.connection_state_callback.add_callback(
                connection_state_callback)

        if access_rights_callback is not None:
            self.access_rights_callback.add_callback(
                access_rights_callback)

        self._circuit_manager = None
        self._channel = None
        self.subscriptions = {}
        self._idle = False
        self._in_use = threading.Condition()
        self._usages = 0

    @property
    def circuit_manager(self):
        return self._circuit_manager

    @circuit_manager.setter
    def circuit_manager(self, val):
        with self.component_lock:
            self._circuit_manager = val

    @property
    def channel(self):
        return self._channel

    @channel.setter
    def channel(self, val):
        with self.component_lock:
            self._channel = val

    def access_rights_changed(self, rights):
        self.access_rights_callback.process(self, rights)

    def connection_state_changed(self, state, channel):
        self.log.info('%s connection state changed to %s.', self.name, state)
        self.connection_state_callback.process(self, state)
        if state == 'disconnected':
            for sub in self.subscriptions.values():
                with sub.callback_lock:
                    if sub.callbacks:
                        sub.needs_reactivation = True
        if state == 'connected':
            cm = self.circuit_manager
            ctx = cm.context
            with ctx.subscriptions_lock:
                for sub in self.subscriptions.values():
                    with sub.callback_lock:
                        if sub.needs_reactivation:
                            ctx.subscriptions_to_activate[cm].add(sub)
                            sub.needs_reactivation = False

    def __repr__(self):
        if self._idle:
            state = "(idle)"
        elif self.circuit_manager is None or self.circuit_manager.dead.is_set():
            state = "(searching....)"
        else:
            state = (f"address={self.circuit_manager.circuit.address}, "
                     f"circuit_state="
                     f"{self.circuit_manager.circuit.states[ca.CLIENT]}")
            if self.connected:
                state += f", channel_state={self.channel.states[ca.CLIENT]}"
            else:
                state += " (creating...)"
        return f"<PV name={self.name!r} priority={self.priority} {state}>"

    @property
    def connected(self):
        channel = self.channel
        if channel is None:
            return False
        return channel.states[ca.CLIENT] is ca.CONNECTED

    def wait_for_search(self, *, timeout=2):
        """
        Wait for this PV to be found.

        This does not wait for the PV's Channel to be created; it merely waits
        for an address (and a VirtualCircuit) to be assigned.

        Parameters
        ----------
        timeout : float
            Seconds before a CaprotoTimeoutError is raised. Default is 2.
        """
        if not self.circuit_ready.wait(timeout=timeout):
            raise CaprotoTimeoutError("No servers responded to a search for a "
                                      "channel named {!r} within {:.3}-second "
                                      "timeout."
                                      "".format(self.name, float(timeout)))

    @ensure_connected
    def wait_for_connection(self, *, timeout=2):
        pass

    def go_idle(self):
        """Request to clear this Channel to reduce load on client and server.

        A new Channel will be automatically, silently created the next time any
        method requiring a connection is called. Thus, this saves some memory
        in exchange for making the next request a bit slower, as it has to
        redo the handshake with the server first.

        If there are any subscriptions with callbacks, this request will be
        ignored. If the PV is in the process of connecting, this request will
        be ignored.  If there are any actions in progress (read, write) this
        request will be processed when they are complete.
        """
        for sub in self.subscriptions.values():
            if sub.callbacks:
                return
        with self._in_use:
            if not self.channel_ready.is_set():
                return
            # Wait until no other methods that employ @self.ensure_connected
            # are in process.
            self._in_use.wait_for(lambda: self._usages == 0)
            # No other threads are using the connection, and we are holding the
            # self._in_use Condition's lock, so we can safely close the
            # connection. The next thread to acquire the lock will re-connect
            # after it acquires the lock.
            try:
                self.channel_ready.clear()
                self.circuit_manager.send(self.channel.clear())
            except OSError:
                # the socket is dead-dead, do nothing
                ...
            self._idle = True

    @ensure_connected
    def read(self, *, wait=True, callback=None, timeout=2, data_type=None,
             data_count=None, notify=True):
        """Request a fresh reading.

        Can do one or both of:
        - Block while waiting for the response, and return it.
        - Pass the response to callback, with or without blocking.

        Parameters
        ----------
        wait : boolean
            If True (default) block until a matching response is
            received from the server. Raises CaprotoTimeoutError if that
            response is not received within the time specified by the `timeout`
            parameter.
        callback : callable or None
            Called with the response as its argument when received.
        timeout : number or None
            Number of seconds to wait before raising CaprotoTimeoutError.
            Default is 2.
        data_type : {'native', 'status', 'time', 'graphic', 'control'} or ChannelType or int ID, optional
            Request specific data type or a class of data types, matched to the
            channel's native data type. Default is Channel's native data type.
        data_count : integer, optional
            Requested number of values. Default is the channel's native data
            count.
        notify: boolean, optional
            Send a ``ReadNotifyRequest`` instead of a ``ReadRequest``. True by
            default.
        """
        cm, chan = self._circuit_manager, self._channel
        ioid = cm._ioid_counter()
        command = chan.read(ioid=ioid, data_type=data_type,
                            data_count=data_count, notify=notify)
        # Stash the ioid to match the response to the request.

        event = threading.Event()
        ioid_info = dict(event=event)
        if callback is not None:
            ioid_info['callback'] = callback

        cm.ioids[ioid] = ioid_info

        deadline = time.monotonic() + timeout if timeout is not None else None
        ioid_info['deadline'] = deadline
        cm.send(command)
        self.log.debug("%r: %r", self.name, command)
        if not wait:
            return

        # The circuit_manager will put a reference to the response into
        # ioid_info and then set event.
        if not event.wait(timeout=timeout):
            if cm.dead.is_set():
                # This circuit has died sometime during this function call.
                # The exception raised here will be caught by
                # @ensure_connected, which will retry the function call a
                # in hopes of getting a working circuit until our `timeout` has
                # been used up.
                raise DeadCircuitError()
            host, port = cm.circuit.address
            raise CaprotoTimeoutError(
                f"Server at {host}:{port} did "
                f"not respond to attempt to read channel named "
                f"{self.name!r} within {float(timeout):.3}-second timeout. "
                f"The ioid of the expected response is {ioid}."
            )

        self.log.debug("%r: %r", self.name, ioid_info['response'])
        return ioid_info['response']

    @ensure_connected
    def write(self, data, *, wait=True, callback=None, timeout=2,
              notify=None, data_type=None, data_count=None):
        """
        Write a new value. Optionally, request confirmation from the server.

        Can do one or both of:
        - Block while waiting for the response, and return it.
        - Pass the response to callback, with or without blocking.

        Parameters
        ----------
        data : str, int, or float or any Iterable of these
            Value(s) to write.
        wait : boolean
            If True (default) block until a matching WriteNotifyResponse is
            received from the server. Raises CaprotoTimeoutError if that
            response is not received within the time specified by the `timeout`
            parameter.
        callback : callable or None
            Called with the WriteNotifyResponse as its argument when received.
        timeout : number or None
            Number of seconds to wait before raising CaprotoTimeoutError.
            Default is 2.
        notify : boolean or None
            If None (default), set to True if wait=True or callback is set.
            Can be manually set to True or False. Will raise ValueError if set
            to False while wait=True or callback is set.
        data_type : {'native', 'status', 'time', 'graphic', 'control'} or ChannelType or int ID, optional
            Write specific data type or a class of data types, matched to the
            channel's native data type. Default is Channel's native data type.
        data_count : integer, optional
            Requested number of values. Default is the channel's native data
            count.
        """
        cm, chan = self._circuit_manager, self._channel
        if notify is None:
            notify = (wait or callback is not None)
        ioid = cm._ioid_counter()
        command = chan.write(data, ioid=ioid, notify=notify,
                             data_type=data_type, data_count=data_count)
        if notify:
            event = threading.Event()
            ioid_info = dict(event=event)
            if callback is not None:
                ioid_info['callback'] = callback

            cm.ioids[ioid] = ioid_info

            deadline = time.monotonic() + timeout if timeout is not None else None
            ioid_info['deadline'] = deadline
            # do not need to lock this, locking happens in circuit command
            cm.send(command)
            self.log.debug("%r: %r", self.name, command)
        else:
            if wait or callback is not None:
                raise CaprotoValueError("Must set notify=True in order to use "
                                        "`wait` or `callback` because, without a "
                                        "notification of 'put-completion' from the "
                                        "server, there is nothing to wait on or to "
                                        "trigger a callback.")
            cm.send(command)
            self.log.debug("%r: %r", self.name, command)

        if not wait:
            return

        # The circuit_manager will put a reference to the response into
        # ioid_info and then set event.
        if not event.wait(timeout=timeout):
            if cm.dead.is_set():
                # This circuit has died sometime during this function call.
                # The exception raised here will be caught by
                # @ensure_connected, which will retry the function call a
                # in hopes of getting a working circuit until our `timeout` has
                # been used up.
                raise DeadCircuitError()
            host, port = cm.circuit.address
            raise CaprotoTimeoutError(
                f"Server at {host}:{port} did "
                f"not respond to attempt to write to channel named "
                f"{self.name!r} within {float(timeout):.3}-second timeout. "
                f"The ioid of the expected response is {ioid}."
            )
        self.log.debug("%r: %r", self.name, ioid_info['response'])
        return ioid_info['response']

    def subscribe(self, data_type=None, data_count=None,
                  low=0.0, high=0.0, to=0.0, mask=None):
        """
        Start a new subscription to which user callback may be added.

        Parameters
        ----------
        data_type : {'native', 'status', 'time', 'graphic', 'control'} or ChannelType or int ID, optional
            Request specific data type or a class of data types, matched to the
            channel's native data type. Default is Channel's native data type.
        data_count : integer, optional
            Requested number of values. Default is the channel's native data
            count.
        low, high, to : float, optional
            deprecated by Channel Access, not yet implemented by caproto
        mask :  SubscriptionType, optional
            Subscribe to selective updates.

        Returns
        -------
        subscription : Subscription

        Examples
        --------

        Define a subscription.

        >>> sub = pv.subscribe()

        Add a user callback. The subscription will be transparently activated
        (i.e. an ``EventAddRequest`` will be sent) when the first user callback
        is added.

        >>> sub.add_callback(my_func)

        Multiple callbacks may be added to the same subscription.

        >>> sub.add_callback(another_func)

        See the docstring for :class:`Subscription` for more.
        """
        # A Subscription is uniquely identified by the Signature created by its
        # args and kwargs.
        bound = SUBSCRIBE_SIG.bind(data_type, data_count, low, high, to, mask)
        key = tuple(bound.arguments.items())
        try:
            sub = self.subscriptions[key]
        except KeyError:
            sub = Subscription(self,
                               data_type, data_count,
                               low, high, to, mask)
            self.subscriptions[key] = sub
        # The actual EPICS messages will not be sent until the user adds
        # callbacks via sub.add_callback(user_func).
        return sub

    def unsubscribe_all(self):
        "Clear all subscriptions. (Remove all user callbacks from them.)"
        for sub in self.subscriptions.values():
            sub.clear()

    # def __hash__(self):
    #     return id((self.context, self.circuit_manager, self.name))


class CallbackHandler:
    def __init__(self, pv):
        # NOTE: not a WeakValueDictionary or WeakSet as PV is unhashable...
        self.callbacks = {}
        self.pv = pv
        self._callback_id = 0
        self.callback_lock = threading.RLock()

    def add_callback(self, func):

        def removed(_):
            self.remove_callback(cb_id)  # defined below inside the lock

        if inspect.ismethod(func):
            ref = weakref.WeakMethod(func, removed)
        else:
            # TODO: strong reference to non-instance methods?
            ref = weakref.ref(func, removed)

        with self.callback_lock:
            cb_id = self._callback_id
            self._callback_id += 1
            self.callbacks[cb_id] = ref
        return cb_id

    def remove_callback(self, token):
        with self.callback_lock:
            self.callbacks.pop(token, None)

    def process(self, *args, **kwargs):
        """
        This is a fast operation that submits jobs to the Context's
        ThreadPoolExecutor and then returns.
        """
        to_remove = []
        with self.callback_lock:
            callbacks = list(self.callbacks.items())

        for cb_id, ref in callbacks:
            callback = ref()
            if callback is None:
                to_remove.append(cb_id)
                continue

            self.pv.circuit_manager.user_callback_executor.submit(
                callback, *args, **kwargs)

        with self.callback_lock:
            for remove_id in to_remove:
                self.callbacks.pop(remove_id, None)


class Subscription(CallbackHandler):
    """
    Represents one subscription, specified by a PV and configurational parameters

    It may fan out to zero, one, or multiple user-registered callback
    functions.

    This object should never be instantiated directly by user code; rather
    it should be made by calling the ``subscribe()`` method on a ``PV`` object.
    """
    def __init__(self, pv, data_type, data_count, low, high, to, mask):
        super().__init__(pv)
        # Stash everything, but do not send any EPICS messages until the first
        # user callback is attached.
        self.data_type = data_type
        self.data_count = data_count
        self.low = low
        self.high = high
        self.to = to
        self.mask = mask
        self.subscriptionid = None
        self.most_recent_response = None
        self.needs_reactivation = False

    @property
    def log(self):
        return self.pv.log

    def __repr__(self):
        return f"<Subscription to {self.pv.name!r}, id={self.subscriptionid}>"

    @ensure_connected
    def _subscribe(self, timeout=2):
        """This is called automatically after the first callback is added.
        """
        cm = self.pv.circuit_manager
        ctx = cm.context
        with ctx.subscriptions_lock:
            ctx.subscriptions_to_activate[cm].add(self)
        ctx.activate_subscriptions_now.set()

    @ensure_connected
    def compose_command(self, timeout=2):
        "This is used by the Context to re-subscribe in bulk after dropping."
        with self.callback_lock:
            if not self.callbacks:
                return None
            cm, chan = self.pv._circuit_manager, self.pv._channel
            subscriptionid = cm._subscriptionid_counter()
            command = chan.subscribe(data_type=self.data_type,
                                     data_count=self.data_count, low=self.low,
                                     high=self.high, to=self.to,
                                     mask=self.mask,
                                     subscriptionid=subscriptionid)
            subscriptionid = command.subscriptionid
            self.subscriptionid = subscriptionid
        # The circuit_manager needs to know the subscriptionid so that it can
        # route responses to this request.
        cm.subscriptions[subscriptionid] = self
        return command

    def clear(self):
        """
        Remove all callbacks.
        """
        with self.callback_lock:
            for cb_id in list(self.callbacks):
                self.remove_callback(cb_id)
        # Once self.callbacks is empty, self.remove_callback calls
        # self._unsubscribe for us.

    def _unsubscribe(self, timeout=2):
        """
        This is automatically called if the number of callbacks goes to 0.
        """
        with self.callback_lock:
            if self.subscriptionid is None:
                # Already unsubscribed.
                return
            subscriptionid = self.subscriptionid
            self.subscriptionid = None
            self.most_recent_response = None
        self.pv.circuit_manager.subscriptions.pop(subscriptionid, None)
        chan = self.pv.channel
        if chan and chan.states[ca.CLIENT] is ca.CONNECTED:
            try:
                command = self.pv.channel.unsubscribe(subscriptionid)
            except ca.CaprotoKeyError:
                pass
            else:
                self.pv.circuit_manager.send(command)

    def process(self, command):
        # TODO here i think we can decouple PV update rates and callback
        # handling rates, if desirable, to not bog down performance.
        # As implemented below, updates are blocking further messages from
        # the CA servers from processing. (-> ThreadPool, etc.)

        super().process(command)
        self.log.debug("%r: %r", self.pv.name, command)
        self.most_recent_response = command

    def add_callback(self, func):
        """
        Add a callback to receive responses.

        Parameters
        ----------
        func : callable
            Expected signature: ``func(response)``

        Returns
        -------
        token : int
            Integer token that can be passed to :meth:`remove_callback`.
        """
        with self.callback_lock:
            was_empty = not self.callbacks
            cb_id = super().add_callback(func)
            most_recent_response = self.most_recent_response
        if was_empty:
            # This is the first callback. Set up a subscription, which
            # should elicit a response from the server soon giving the
            # current value to this func (and any other funcs added in the
            # mean time).
            self._subscribe()
        else:
            # This callback is piggy-backing onto an existing subscription.
            # Send it the most recent response, unless we are still waiting
            # for that first response from the server.
            if most_recent_response is not None:
                try:
                    func(most_recent_response)
                except Exception:
                    self.log.exception(
                        "Exception raised during processing most recent "
                        "response %r with new callback %r",
                        most_recent_response, func)

        return cb_id

    def remove_callback(self, token):
        """
        Remove callback using token that was returned by :meth:`add_callback`.

        Parameters
        ----------

        token : integer
            Token returned by :meth:`add_callback`.
        """
        with self.callback_lock:
            super().remove_callback(token)
            if not self.callbacks:
                # Go dormant.
                self._unsubscribe()
                self.most_recent_response = None
                self.needs_reactivation = False

    def __del__(self):
        try:
            self.clear()
        except TimeoutError:
            pass


class Batch:
    """
    Accumulate requests and then issue them all in batch.

    Parameters
    ----------
    timeout : number or None
        Number of seconds to wait before ignoring late responses. Default
        is 2.

    Examples
    --------
    Read some PVs in batch and stash the readings in a dictionary as they
    come in.

    >>> results = {}
    >>> def stash_result(name, response):
    ...     results[name] = response.data
    ...
    >>> with Batch() as b:
    ...     for pv in pvs:
    ...         b.read(pv, functools.partial(stash_result, pv.name))
    ...     # The requests are sent upon exiting this 'with' block.
    ...

    The ``results`` dictionary will be populated as responses come in.
    """
    def __init__(self, timeout=2):
        self.timeout = timeout
        self._commands = defaultdict(list)  # map each circuit to commands
        self._ioid_infos = []

    def __enter__(self):
        return self

    def read(self, pv, callback, data_type=None, data_count=None):
        """Request a fresh reading as part of a batched request.

        Notice that, unlike :meth:`PV.read`, the callback is required. (There
        is no other way to get the result back from a batched read.)

        Parameters
        ----------
        pv : PV
        callback : callable
            Expected signature: ``f(response)``
        data_type : {'native', 'status', 'time', 'graphic', 'control'} or ChannelType or int ID, optional
            Request specific data type or a class of data types, matched to the
            channel's native data type. Default is Channel's native data type.
        data_count : integer, optional
            Requested number of values. Default is the channel's native data
            count.
        """
        ioid = pv.circuit_manager._ioid_counter()
        command = pv.channel.read(ioid=ioid,
                                  data_type=data_type,
                                  data_count=data_count,
                                  notify=True)
        self._commands[pv.circuit_manager].append(command)
        # Stash the ioid to match the response to the request.
        ioid_info = dict(callback=callback)
        pv.circuit_manager.ioids[ioid] = ioid_info
        self._ioid_infos.append(ioid_info)

    def write(self, pv, data, callback=None, data_type=None, data_count=None):
        """Write a new value as part of a batched request.

        Parameters
        ----------
        pv : PV
        data : str, int, or float or any Iterable of these
            Value(s) to write.
        callback : callable
            Expected signature: ``f(response)``
        data_type : {'native', 'status', 'time', 'graphic', 'control'} or ChannelType or int ID, optional
            Request specific data type or a class of data types, matched to the
            channel's native data type. Default is Channel's native data type.
        data_count : integer, optional
            Requested number of values. Default is the channel's native data
            count.
        """
        ioid = pv.circuit_manager._ioid_counter()
        command = pv.channel.write(data=data,
                                   ioid=ioid,
                                   data_type=data_type,
                                   data_count=data_count,
                                   notify=callback is not None)
        self._commands[pv.circuit_manager].append(command)
        if callback:
            # Stash the ioid to match the response to the request.
            ioid_info = dict(callback=callback)
            pv.circuit_manager.ioids[ioid] = ioid_info
            self._ioid_infos.append(ioid_info)

    def __exit__(self, exc_type, exc_value, traceback):
        timeout = self.timeout
        deadline = time.monotonic() + timeout if timeout is not None else None
        for ioid_info in self._ioid_infos:
            ioid_info['deadline'] = deadline
        for circuit_manager, commands in self._commands.items():
            circuit_manager.send(*commands)


# The signature of caproto._circuit.ClientChannel.subscribe, which is used to
# resolve the (args, kwargs) of a Subscription into a unique key.
SUBSCRIBE_SIG = Signature([
    Parameter('data_type', Parameter.POSITIONAL_OR_KEYWORD, default=None),
    Parameter('data_count', Parameter.POSITIONAL_OR_KEYWORD, default=None),
    Parameter('low', Parameter.POSITIONAL_OR_KEYWORD, default=0),
    Parameter('high', Parameter.POSITIONAL_OR_KEYWORD, default=0),
    Parameter('to', Parameter.POSITIONAL_OR_KEYWORD, default=0),
    Parameter('mask', Parameter.POSITIONAL_OR_KEYWORD, default=None)])
