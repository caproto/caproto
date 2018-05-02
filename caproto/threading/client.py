import collections
import getpass
import itertools
import logging
import os
import queue
import socket
import threading
import time
import weakref
import selectors
import array
import fcntl
import errno
import termios
import inspect

from collections import defaultdict

import caproto as ca
from .._constants import (MAX_ID, STALE_SEARCH_EXPIRATION,
                          SEARCH_MAX_DATAGRAM_BYTES)
from .._utils import batch_requests, CaprotoError


def ensure_connected(func):
    def inner(self, *args, **kwargs):
        with self._in_use:
            self._usages += 1
            # If needed, reconnect. Do this inside the lock so that we don't
            # try to do this twice. (No other threads that need this lock
            # can proceed until the connection is ready anyway!)
            if self._idle or (self.circuit_manager and
                              self.circuit_manager.dead):
                self.context.reconnect(((self.name, self.priority),))
                reconnect = True
            else:
                reconnect = False
        try:
            self._wait_for_connection()
            if reconnect:
                def requests():
                    for sub in self.subscriptions:
                        command = sub.compose_command()
                        # compose_command() returns None if this
                        # Subscription is inactive (meaning there are no
                        # user callbacks attached). It will send an
                        # EventAddRequest on its own if/when the user does
                        # add any callbacks, so we can skip it here.
                        if command is not None:
                            yield command
                # Batching is probably overkill...unlikely to be very many
                # requests here....
                for batch in batch_requests(requests(),
                                            EVENT_ADD_BATCH_MAX_BYTES):
                    self.circuit_manager.send(*batch)
                self._idle = False
            result = func(self, *args, **kwargs)
        finally:
            with self._in_use:
                self._usages -= 1
                self._in_use.notify_all()
        return result
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
RETRY_SEARCHES_PERIOD = 1
RESTART_SUBS_PERIOD = 0.1
STR_ENC = os.environ.get('CAPROTO_STRING_ENCODING', 'latin-1')


logger = logging.getLogger(__name__)


class SelectorThread:
    def __init__(self, *, parent=None):
        self._running = False
        self.selector = selectors.DefaultSelector()

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
        return self._running

    def stop(self):
        self._running = False

    def start(self):
        if self._running:
            return

        self._running = True
        self.thread = threading.Thread(target=self, daemon=True)
        self.thread.start()

    def add_socket(self, sock, target_obj):
        with self._socket_map_lock:
            if sock in self.socket_to_id:
                raise ValueError('Socket already added')

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
            # logger.debug('Socket %s was added (obj %s)', sock, target_obj)

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
                # logger.debug('Socket %s was removed before it was added '
                #              '(obj = %s)', sock, obj)
                self._register_sockets.remove(sock)
            else:
                # logger.debug('Socket %s was removed '
                #              '(obj = %s)', sock, obj)
                self._unregister_sockets.add(sock)

    def _object_removed(self, obj_id):
        with self._socket_map_lock:
            if obj_id in self.id_to_socket:
                sock = self.id_to_socket.pop(obj_id)
                # logger.debug('Object ID %s was destroyed: removing %s', obj_id,
                #              sock)
                del self.socket_to_id[sock]
                self._unregister_sockets.add(sock)

    def __call__(self):
        '''Selector poll loop'''
        avail_buf = array.array('i', [0])
        while self._running:
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
                if fcntl.ioctl(sock, termios.FIONREAD, avail_buf) < 0:
                    continue

                bytes_available = avail_buf[0]

                try:
                    bytes_recv, address = sock.recvfrom(
                        max((4096, bytes_available)))
                except OSError as ex:
                    if ex.errno != errno.EAGAIN:
                        # register as a disconnection
                        # logger.error('Removing %s due to %s (%s)', obj, ex,
                        #              ex.errno)
                        self.remove_socket(sock)
                    continue

                # Let objects handle disconnection by returning a failure here
                if obj.received(bytes_recv, address) is ca.DISCONNECTED:
                    # logger.debug('Removing %s = %s due to receive failure',
                    #              sock, obj)
                    self.remove_socket(sock)

                    # TODO: consider adding specific DISCONNECTED instead of b''
                    # sent to disconnected sockets

        logger.debug('Selector loop exited')


class SharedBroadcaster:
    def __init__(self, *, log_level='ERROR', registration_retry_time=10.0):
        '''
        A broadcaster client which can be shared among multiple clients

        Parameters
        ----------
        log_level : str, optional
            The log level to use
        registration_retry_time : float, optional
            The time, in seconds, between attempts made to register with the
            repeater
        '''
        self.log_level = log_level
        self.udp_sock = None
        self._search_lock = threading.RLock()
        self._retry_thread = None
        self._retries_enabled = threading.Event()

        self._id_counter = itertools.count(0)
        self.search_results = {}  # map name to (time, address)
        self.unanswered_searches = {}  # map search id (cid) to (name, queue)

        self.listeners = weakref.WeakSet()

        self.broadcaster = ca.Broadcaster(our_role=ca.CLIENT)
        self.broadcaster.log.setLevel(self.log_level)
        self.command_bundle_queue = queue.Queue()
        self.command_cond = threading.Condition()

        self.selector = SelectorThread(parent=self)
        self.command_thread = threading.Thread(target=self.command_loop,
                                               daemon=True)
        self.command_thread.start()

        self._registration_retry_time = registration_retry_time
        self._registration_last_sent = 0

        # When no listeners exist, automatically disconnect the broadcaster
        self.disconnect_thread = None
        self._disconnect_timer = None

        try:
            # Always attempt registration on initialization, but allow failures
            self._register()
        except Exception as ex:
            logger.exception('Broadcaster registration failed on init')

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
        if self.udp_sock is None:
            self._create_sock()

        self._registration_last_sent = time.monotonic()
        command = self.broadcaster.register()

        with self.command_cond:
            self.send(ca.EPICS_CA2_PORT, command)
            self._retries_enabled.set()

    def new_id(self):
        while True:
            i = next(self._id_counter)
            if i == MAX_ID:
                self._id_counter = itertools.count(0)
                continue
            return i

    def _create_sock(self):
        # UDP socket broadcasting to CA servers
        if self.udp_sock is not None:
            udp_sock, self.udp_sock = self.udp_sock, None
            self.selector.remove_socket(udp_sock)

        self.selector.start()
        self.udp_sock = ca.bcast_socket()
        self.selector.add_socket(self.udp_sock, self)

    def add_listener(self, listener):
        with self._search_lock:
            if self._retry_thread is None:
                self._retry_thread = threading.Thread(
                    target=self._retry_unanswered_searches, daemon=True)
                self._retry_thread.start()

            self.listeners.add(listener)
            weakref.finalize(listener, self._listener_removed)

    def remove_listener(self, listener):
        try:
            self.listeners.remove(listener)
        except KeyError:
            pass
        finally:
            self._listener_removed()

    def _disconnect_wait(self):
        while len(self.listeners) == 0:
            self._disconnect_timer -= 1
            if self._disconnect_timer == 0:
                logger.debug('Unused broadcaster, disconnecting')
                self.disconnect()
                break
            time.sleep(1.0)

        self.disconnect_thread = None

    def _listener_removed(self):
        with self._search_lock:
            if not self.listeners:
                self._disconnect_timer = 30
                if self.disconnect_thread is None:
                    self.disconnect_thread = threading.Thread(
                        target=self._disconnect_wait, daemon=True)
                    self.disconnect_thread.start()

    def disconnect(self, *, wait=True, timeout=2):
        with self.command_cond:
            if self.udp_sock is not None:
                self.selector.remove_socket(self.udp_sock)

            self.search_results.clear()
            self._registration_last_sent = 0
            self._retries_enabled.clear()
            self.udp_sock = None
            self.broadcaster.disconnect()

    def send(self, port, *commands):
        """
        Process a command and transport it over the UDP socket.
        """
        bytes_to_send = self.broadcaster.send(*commands)
        for host in ca.get_address_list():
            if ':' in host:
                host, _, specified_port = host.partition(':')
                self.udp_sock.sendto(bytes_to_send, (host,
                                                     int(specified_port)))
            else:
                self.udp_sock.sendto(bytes_to_send, (host, port))

    def get_cached_search_result(self, name, *,
                                 threshold=STALE_SEARCH_EXPIRATION):
        'Returns address if found, raises KeyError if missing or stale.'
        address, timestamp = self.search_results[name]
        if time.monotonic() - timestamp > threshold:
            # TODO this is very inefficient
            for context in self.listeners:
                for addr, cm in context.circuit_managers.items():
                    if cm.connected and name in cm.all_created_pvnames:
                        # A valid connection exists in one of our clients, so
                        # ignore the stale result status
                        self.search_results[name] = (address, time.monotonic())
                        return address

            # Clean up expired result.
            self.search_results.pop(name, None)
            raise KeyError(f'{name!r}: stale search result')

        return address

    def search(self, results_queue, names, *, timeout=2):
        "Generate, process, and the transport a search request."
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

            for addr, names in use_cached_search.items():
                results_queue.put((address, names))

            # Generate search_ids and stash them on Context state so they can
            # be used to match SearchResponses with SearchRequests.
            search_ids = []
            for name in needs_search:
                search_id = new_id()
                search_ids.append(search_id)
                unanswered_searches[search_id] = (name, results_queue)

        if not needs_search:
            return

        logger.debug('Searching for %r PVs....', len(needs_search))
        requests = (ca.SearchRequest(name, search_id, 13)
                    for name, search_id in zip(needs_search, search_ids))
        for batch in batch_requests(requests, SEARCH_MAX_DATAGRAM_BYTES):
            self.send(ca.EPICS_CA1_PORT, ca.VersionRequest(0, 13), *batch)

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
        unanswered_searches = self.unanswered_searches
        queues = defaultdict(list)

        while True:
            commands = self.command_bundle_queue.get()

            try:
                self.broadcaster.process_commands(commands)
            except ca.CaprotoError as ex:
                logger.warning('Broadcaster command error', exc_info=ex)
                continue

            queues.clear()
            now = time.monotonic()
            for command in commands:
                if isinstance(command, ca.VersionResponse):
                    # Check that the server version is one we can talk to.
                    if command.version <= 11:
                        logger.warning('Version response <= 11: %r', command)
                elif isinstance(command, ca.SearchResponse):
                    cid = command.cid
                    try:
                        name, queue = unanswered_searches.pop(cid)
                    except KeyError:
                        # This is a redundant response, which the EPICS
                        # spec tells us to ignore. (The first responder
                        # to a given request wins.)
                        pass
                    else:
                        address = ca.extract_address(command)
                        queues[queue].append(name)
                        # Cache this to save time on future searches.
                        # (Entries expire after STALE_SEARCH_EXPIRATION.)
                        logger.debug('Found %s at %s', name, address)
                        search_results[name] = (address, now)
            # Send the search results to the Contexts that asked for
            # them. This is probably more general than is has to be but
            # I'm playing it safe for now.
            if queues:
                for queue, names in queues.items():
                    queue.put((address, names))

                with self.command_cond:
                    self.command_cond.notify_all()

    def _retry_unanswered_searches(self):
        logger.debug('Search-retry thread started.')
        while True:  # self.listeners:
            try:
                self._retries_enabled.wait(0.5)
            except TimeoutError:
                continue

            t = time.monotonic()
            items = list(self.unanswered_searches.items())
            requests = (ca.SearchRequest(name, search_id, 13)
                        for search_id, (name, _) in
                        items)

            if not self._retries_enabled.is_set():
                continue

            if items:
                logger.debug('Retrying searches for %d PVs', len(items))

            for batch in batch_requests(requests,
                                        SEARCH_MAX_DATAGRAM_BYTES):
                self.send(ca.EPICS_CA1_PORT, ca.VersionRequest(0, 13), *batch)

            time.sleep(max(0, RETRY_SEARCHES_PERIOD - (time.monotonic() - t)))

        logger.debug('Search-retry thread exiting.')

    def __del__(self):
        try:
            self.disconnect()
            self.selector = None
        except AttributeError:
            pass


class Context:
    "Wraps Broadcaster and a cache of VirtualCircuits"
    def __init__(self, broadcaster, *,
                 host_name=None, client_name=None,
                 log_level='DEBUG'):
        self.broadcaster = broadcaster
        if host_name is None:
            host_name = socket.gethostname()
        self.host_name = host_name
        if client_name is None:
            client_name = getpass.getuser()
        self.client_name = client_name
        self.log_level = log_level
        self.search_condition = threading.Condition()
        self.pv_state_lock = threading.RLock()
        self.resuscitated_pvs = []
        self.circuit_managers = {}  # keyed on address
        self.pvs = {}  # (name, priority) -> pv
        # name -> set of pvs  --- with varied priority
        self.pvs_needing_circuits = defaultdict(set)
        self.broadcaster.add_listener(self)
        self._search_results_queue = queue.Queue()
        logger.debug('Context: start process search results loop')
        self._search_thread = threading.Thread(
            target=self._process_search_results_loop,
            daemon=True)
        self._search_thread.start()

        logger.debug('Context: start restart_subscriptions loop')
        self._restart_sub_thread = threading.Thread(
            target=self._restart_subscriptions,
            daemon=True)
        self._restart_sub_thread.start()

        self.selector = SelectorThread(parent=self)
        self.selector.start()
        self._user_disconnected = False

    def get_pvs(self, *names, priority=0, connection_state_callback=None):
        """
        Return a list of PV objects.

        These objects may not be connected at first. Channel creation occurs on
        a background thread.
        """
        if self._user_disconnected:
            raise ContextDisconnectedError("This Context is no longer usable.")
        pvs = []  # list of all PV objects to return
        names_to_search = []  # subset of names that we need to search for
        with self.pv_state_lock:
            for name in names:
                try:
                    pv = self.pvs[(name, priority)]
                except KeyError:
                    pv = PV(name, priority, self, connection_state_callback)
                    self.pvs[(name, priority)] = pv
                    self.pvs_needing_circuits[name].add(pv)
                    names_to_search.append(name)
                else:
                    # Re-using a PV instance. Add a new connection state callback,
                    # if necessary:
                    logger.debug('Reusing PV instance for %r', name)
                    if connection_state_callback:
                        pv.connection_state_callback.add_callback(
                            connection_state_callback)

                pvs.append(pv)

        # TODO: potential bug?
        # if callback is quick, is there a chance downstream listeners may
        # never receive notification?

        # Ask the Broadcaster to search for every PV for which we do not
        # already have an instance. It might already have a cached search
        # result, but that is the concern of broadcaster.search.
        self.broadcaster.search(self._search_results_queue, names_to_search)
        return pvs

    def reconnect(self, keys):
        # We will reuse the same PV object but use a new cid.
        names = []
        pvs = []
        with self.pv_state_lock:
            for key in keys:
                pv = self.pvs[key]
                pv.circuit_manager = None
                pv.channel = None
                pvs.append(pv)
                name, _ = key
                names.append(name)
                self.pvs_needing_circuits[name].add(pv)
                # If there is a cached search result for this name, expire it.
                self.broadcaster.search_results.pop(name, None)

            self.resuscitated_pvs.extend(
                [pv for pv in pvs if pv.subscriptions])

        self.broadcaster.search(self._search_results_queue, names)

    def _process_search_results_loop(self):
        # Receive (address, (name1, name2, ...)). The sending side of this
        # queue is held by SharedBroadcaster.command_loop.
        while True:
            address, names = self._search_results_queue.get()
            channels = collections.deque()
            with self.pv_state_lock:
                # Assign each PV a VirtualCircuitManager for managing a socket
                # and tracking circuit state, as well as a ClientChannel for
                # tracking channel state.
                for name in names:
                    # There could be multiple PVs with the same name and
                    # different priority. That is what we are looping over
                    # here. There could also be NO PVs with this name that need
                    # a circuit, because we could be receiving a duplicate
                    # search response (which we are supposed to ignore).
                    for pv in self.pvs_needing_circuits.pop(name, set()):
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
                        pv.channel = chan
                        channels.append(chan)

            # Notify PVs that they now have a circuit_manager. This will
            # un-block a wait() in the PV.wait_for_search() method.
            with self.search_condition:
                self.search_condition.notify_all()

            # Initiate channel creation with the server.
            cm.send(*(chan.create() for chan in channels))

    def get_circuit_manager(self, address, priority):
        """
        Return a VirtualCircuitManager for this address, priority. (It manages
        a caproto.VirtualCircuit and a TCP socket.)

        Make a new one if necessary.
        """
        cm = self.circuit_managers.get((address, priority), None)
        if cm is None or cm.dead:
            circuit = ca.VirtualCircuit(our_role=ca.CLIENT, address=address,
                                        priority=priority)
            cm = VirtualCircuitManager(self, circuit, self.selector)
            cm.circuit.log.setLevel(self.log_level)
            self.circuit_managers[(address, priority)] = cm
        return cm

    def _restart_subscriptions(self):
        while True:
            t = time.monotonic()
            ready = defaultdict(list)
            with self.pv_state_lock:
                pvs = list(self.resuscitated_pvs)
                self.resuscitated_pvs.clear()
                for pv in pvs:
                    if pv.connected:
                        ready[pv.circuit_manager].append(pv)
                    else:
                        self.resuscitated_pvs.append(pv)

            for cm, pvs in ready.items():
                def requests():
                    "Yield EventAddRequest commands."
                    for pv in pvs:
                        for sub in pv.subscriptions:
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
                    cm.send(*batch)

            time.sleep(max(0, RESTART_SUBS_PERIOD - (time.monotonic() - t)))

    def disconnect(self, *, wait=True, timeout=2):
        self._user_disconnected = True
        try:
            # disconnect any circuits we have
            circuits = list(self.circuit_managers.values())
            total_circuits = len(circuits)
            for idx, circuit in enumerate(circuits, 1):
                if circuit.connected:
                    logger.debug('Disconnecting circuit %d/%d: %s',
                                 idx, total_circuits, circuit)
                    circuit.disconnect(wait=wait, timeout=timeout)
                    logger.debug('... Circuit %d disconnect complete.', idx)
                else:
                    logger.debug('Circuit %d/%d was already disconnected: %s',
                                 idx, total_circuits, circuit)
            logger.debug('All circuits disconnected')
        finally:
            # clear any state about circuits and search results
            logger.debug('Clearing circuit managers')
            self.circuit_managers.clear()

            # disconnect the underlying state machine
            logger.debug('Removing Context from the broadcaster')
            self.broadcaster.remove_listener(self)

            logger.debug('Disconnection complete')

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
    __slots__ = ('context', 'circuit', 'channels', 'ioids', 'subscriptions',
                 '_user_disconnected', 'new_command_cond', 'socket',
                 'selector', 'pvs', 'all_created_pvnames', 'callback_queue',
                 'callback_thread',
                 '__weakref__')

    def __init__(self, context, circuit, selector, timeout=TIMEOUT):
        self.context = context
        self.circuit = circuit  # a caproto.VirtualCircuit
        self.channels = {}  # map cid to Channel
        self.pvs = {}  # map cid to PV
        self.ioids = {}  # map ioid to Channel
        self.subscriptions = {}  # map subscriptionid to Subscription
        self.new_command_cond = threading.Condition()
        self.socket = None
        self.selector = selector
        self._user_disconnected = False
        self.callback_queue = queue.Queue()
        self.callback_thread = threading.Thread(target=self._callback_loop,
                                                daemon=True)
        self.callback_thread.start()

        # keep track of all PV names that are successfully connected to within
        # this circuit. This is to be cleared upon disconnection:
        self.all_created_pvnames = []

        # Connect.
        with self.new_command_cond:
            if self.connected:
                return
            if self.circuit.states[ca.SERVER] is ca.IDLE:
                self.socket = socket.create_connection(self.circuit.address)
                self.selector.add_socket(self.socket, self)
                self.send(ca.VersionRequest(self.circuit.priority, 13),
                          ca.HostNameRequest(self.context.host_name),
                          ca.ClientNameRequest(self.context.client_name))
            else:
                raise RuntimeError("Cannot connect. States are {} "
                                   "".format(self.circuit.states))
            if not self.new_command_cond.wait_for(lambda: self.connected,
                                                  timeout):
                raise TimeoutError("Circuit with server at {} did not "
                                   "connected within {}-second timeout."
                                   "".format(self.circuit.address, timeout))

    def __repr__(self):
        return (f"<VirtualCircuitManager circuit={self.circuit} "
                f"pvs={len(self.pvs)} ioids={len(self.ioids)} "
                f"subscriptions={len(self.subscriptions)}>")

    def _callback_loop(self):
        while True:
            t0, sub, command = self.callback_queue.get()
            if sub is ca.DISCONNECTED:
                break

            dt = time.monotonic() - t0
            logger.debug('Executing callback (dt=%.1f ms): %s %s',
                         dt * 1000., sub, command)

            sub.process(command)

    @property
    def connected(self):
        return self.circuit.states[ca.CLIENT] is ca.CONNECTED

    @property
    def dead(self):
        return self.socket is None

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
        commands, num_bytes_needed = self.circuit.recv(bytes_recv)

        for c in commands:
            self._process_command(c)

        if not bytes_recv:
            # Tell the selector to remove our socket
            return ca.DISCONNECTED
        return num_bytes_needed

    def _process_command(self, command):
        try:
            self.circuit.process_command(command)
        except ca.CaprotoError as ex:
            if hasattr(ex, 'channel'):
                channel = ex.channel
                logger.warning('Invalid command %s for Channel %s in state %s',
                               command, channel, channel.states,
                               exc_info=ex)
                # channel exceptions are not fatal
                return
            else:
                logger.error('Invalid command %s for VirtualCircuit %s in '
                             'state %s', command, self, self.circuit.states,
                             exc_info=ex)
                # circuit exceptions are fatal; exit the loop
                self.disconnect()
                return

        with self.new_command_cond:
            if command is ca.DISCONNECTED:
                self._disconnected()
            elif isinstance(command, ca.ReadNotifyResponse):
                chan = self.ioids.pop(command.ioid)
                chan.process_read_notify(command)
            elif isinstance(command, ca.WriteNotifyResponse):
                chan = self.ioids.pop(command.ioid)
                chan.process_write_notify(command)
            elif isinstance(command, ca.EventAddResponse):
                sub = self.subscriptions[command.subscriptionid]
                self.callback_queue.put((time.monotonic(), sub, command))
            elif isinstance(command, ca.EventCancelResponse):
                self.subscriptions.pop(command.subscriptionid)
            elif isinstance(command, ca.CreateChanResponse):
                pv = self.pvs[command.cid]
                chan = self.channels[command.cid]
                pv.connection_state_changed('connected', chan)
                self.all_created_pvnames.append(pv.name)
            elif isinstance(command, (ca.ServerDisconnResponse,
                                      ca.ClearChannelResponse)):
                pv = self.pvs[command.cid]
                pv.connection_state_changed('disconnected', None)
                # NOTE: pv remains valid until server goes down
            self.new_command_cond.notify_all()

    def _disconnected(self):
        with self.new_command_cond:
            logger.debug('Entered VCM._disconnected')
            # Ensure that this method is idempotent.
            self.all_created_pvnames.clear()
            for pv in self.pvs.values():
                pv.connection_state_changed('disconnected', None)
            # Update circuit state. This will be reflected on all PVs, which
            # continue to hold a reference to this disconnected circuit.
            self.circuit.disconnect()
            # Remove VirtualCircuitManager from Context.
            # This will cause all future calls to Context.get_circuit_manager()
            # to create a fresh VirtualCiruit and VirtualCircuitManager.
            self.context.circuit_managers.pop(self.circuit.address, None)
            self.callback_queue.put((time.monotonic(), ca.DISCONNECTED, None))

        if not self._user_disconnected:
            # If the user didn't request disconnection, kick off attempt to
            # reconnect all PVs via fresh circuit(s).
            logger.debug('VCM: Attempting reconnection')
            self.context.reconnect(((chan.name, chan.circuit.priority)
                                    for chan in self.channels.values()))

        # Clean up the socket if it has not yet been cleared:
        sock = self.socket
        if sock is not None:
            self.selector.remove_socket(sock)
            try:
                sock.shutdown(socket.SHUT_WR)
                sock.close()
            except OSError:
                pass

    def disconnect(self, *, wait=True, timeout=2.0):
        self._user_disconnected = True
        self._disconnected()
        if self.socket is None:
            return

        sock, self.socket = self.socket, None
        try:
            sock.shutdown(socket.SHUT_WR)
        except OSError as ex:
            pass

        if wait:
            states = self.circuit.states

            def is_disconnected():
                return states[ca.CLIENT] is ca.DISCONNECTED

            with self.new_command_cond:
                done = self.new_command_cond.wait_for(is_disconnected, timeout)

            if not done:
                # TODO: this may actually happen due to a long backlog of
                # incoming data, but may not be critical to wait for...
                raise TimeoutError(f"Server did not respond to disconnection "
                                   f"attempt within {timeout}-second timeout."
                                   )

            logger.debug('Circuit manager disconnected')

    def __del__(self):
        try:
            self.disconnect()
        except AttributeError:
            pass


class PV:
    """Wraps a VirtualCircuit and a caproto.ClientChannel."""
    __slots__ = ('name', 'priority', 'context', 'circuit_manager', 'channel',
                 'last_reading', 'last_writing', '_read_notify_callback',
                 'subscriptions', 'command_bundle_queue',
                 '_write_notify_callback', '_idle', '_in_use', '_usages',
                 'connection_state_callback', '_pc_callbacks', '__weakref__')

    def __init__(self, name, priority, context, connection_state_callback):
        """
        These must be instantiated by a Context, never directly.
        """
        self.name = name
        self.priority = priority
        self.context = context
        self.connection_state_callback = CallbackHandler(self)

        if connection_state_callback is not None:
            self.connection_state_callback.add_callback(
                connection_state_callback)

        self.circuit_manager = None
        self.channel = None
        self.last_reading = None
        self.last_writing = None
        self.subscriptions = []
        self._read_notify_callback = None  # called on ReadNotifyResponse
        self._write_notify_callback = None  # called on WriteNotifyResponse
        self._pc_callbacks = {}
        self._idle = False
        self._in_use = threading.Condition()
        self._usages = 0

    def connection_state_changed(self, state, channel):
        logger.debug('%s Connection state changed %s %s', self.name, state,
                     channel)
        # PV is responsible for updating its channel attribute.
        self.channel = channel

        self.connection_state_callback.process(self, state)

    def __repr__(self):
        if self._idle:
            state = "(idle)"
        elif self.circuit_manager is None:
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

    def process_read_notify(self, read_notify_command):
        self.last_reading = read_notify_command

        if self._read_notify_callback is None:
            return
        else:
            try:
                return self._read_notify_callback(read_notify_command)
            except Exception as ex:
                print(ex)

    def process_write_notify(self, write_notify_command):
        self.last_writing = write_notify_command

        pc_cb = self._pc_callbacks.pop(write_notify_command.ioid, None)
        if pc_cb is not None:
            try:
                pc_cb(write_notify_command)
            except Exception as ex:
                print(ex)
        if self._write_notify_callback is None:
            return
        else:
            try:
                return self._write_notify_callback(write_notify_command)
            except Exception as ex:
                print(ex)

    def wait_for_search(self, *, timeout=2):
        """
        Wait for this PV to be found.

        This does not wait for the PV's Channel to be created; it merely waits
        for an address (and a VirtualCircuit) to be assigned.

        Parameters
        ----------
        timeout : float
            Seconds before a TimeoutError is raised. Default is 2.
        """
        search_cond = self.context.search_condition
        with search_cond:
            if self.circuit_manager is not None:
                return
            done = search_cond.wait_for(
                lambda: self.circuit_manager is not None,
                timeout)
        if not done:
            raise TimeoutError("No servers responded to a search for a "
                               "channel named {!r} within {}-second "
                               "timeout."
                               "".format(self.name, timeout))

    @ensure_connected
    def wait_for_connection(self, *, timeout=2):
        self._wait_for_connection(timeout=timeout)

    def _wait_for_connection(self, *, timeout=2):
        """
        Wait for this PV to be connected, ready to use.

        Parameters
        ----------
        timeout : float
            Seconds before a TimeoutError is raised. Default is 2.
        """
        if self.circuit_manager is None:
            self.wait_for_search(timeout=timeout)
        with self.circuit_manager.new_command_cond:
            if self.connected:
                return
            done = self.circuit_manager.new_command_cond.wait_for(
                lambda: self.connected, timeout)
        if not done:
                raise TimeoutError(
                    f"Server at {self.circuit_manager.circuit.address} did "
                    f"not respond to attempt to create channel named "
                    f"{self.name!r} within {timeout}-second timeout."
                )

    def go_idle(self):
        """Request to clear this Channel to reduce load on client and server.

        A new Channel will be automatically, silently created the next time any
        method requiring a connection is called. Thus, this saves some memory
        in exchange for making the next request a bit slower, as it has to
        redo the handshake with the server first.

        If there are any active subscriptions, this request will be ignored. If
        the PV is in the process of connecting, this request will be ignored.
        If there are any actions in progress (read, write) this request will be
        processed when they are complete.
        """
        if self.subscriptions:
            return
        if not self.circuit_manager:
            return

        with self._in_use:
            # Wait until no other methods that employ @self.ensure_connected
            # are in process.
            self._in_use.wait_for(lambda: self._usages == 0)
            # No other threads are using the connection, and we are holding the
            # self._in_use Condition's lock, so we can safely close the
            # connection. The next thread to acquire the lock will re-connect
            # after it acquires the lock.
            with self.circuit_manager.new_command_cond:
                if not self.connected:
                    return

            try:
                self.circuit_manager.send(self.channel.disconnect())
            except OSError:
                # the socket is dead-dead, do nothing
                ...
            self._idle = True

    @ensure_connected
    def read(self, *args, timeout=2, **kwargs):
        """Request a fresh reading, wait for it, return it and stash it.

        The most recent reading is always available in the ``last_reading``
        attribute.
        """
        # need this lock because the socket thread could be trying to
        # update this channel due to an incoming message
        if not self.connected:
            raise DisconnectedError()

        with self.circuit_manager.new_command_cond:
            command = self.channel.read(*args, **kwargs)
        # Stash the ioid to match the response to the request.
        ioid = command.ioid
        self.circuit_manager.ioids[ioid] = self
        # TODO: circuit_manager can be removed from underneath us here
        self.circuit_manager.send(command)

        def has_reading():
            return ioid not in self.circuit_manager.ioids

        with self.circuit_manager.new_command_cond:
            done = self.circuit_manager.new_command_cond.wait_for(has_reading,
                                                                  timeout)
        if not done:
            raise TimeoutError(
                f"Server at {self.circuit_manager.circuit.address} did "
                f"not respond to attempt to read channel named "
                f"{self.name!r} within {timeout}-second timeout."
            )
        return self.last_reading

    @ensure_connected
    def write(self, *args, wait=True, cb=None, timeout=2, **kwargs):
        "Write a new value and await confirmation from the server."
        with self.circuit_manager.new_command_cond:
            command = self.channel.write(*args, **kwargs)
        # Stash the ioid to match the response to the request.
        ioid = command.ioid
        self.circuit_manager.ioids[ioid] = self
        if cb is not None:
            self._pc_callbacks[ioid] = cb
        # do not need to lock this, locking happens in circuit command
        self.circuit_manager.send(command)
        if not wait:
            return

        def has_reading():
            return ioid not in self.circuit_manager.ioids

        with self.circuit_manager.new_command_cond:
            done = self.circuit_manager.new_command_cond.wait_for(has_reading,
                                                                  timeout)
        if not done:
            raise TimeoutError(
                f"Server at {self.circuit_manager.circuit.address} did "
                f"not respond to attempt to write to channel named "
                f"{self.name!r} within {timeout}-second timeout."
            )
        return self.last_writing

    @ensure_connected
    def subscribe(self, *args, **kwargs):
        "Start a new subscription to which user callback may be added."
        sub = Subscription(self, args, kwargs)
        self.subscriptions.append(sub)
        # The actual EPICS messages will not be sent until the user adds
        # callbacks via sub.add_callback(user_func).
        return sub

    # def __hash__(self):
    #     return id((self.context, self.circuit_manager, self.name))


class CallbackHandler:
    def __init__(self, pv):
        # NOTE: not a WeakValueDictionary or WeakSet as PV is unhashable...
        self.callbacks = {}
        self.pv = pv
        self._callback_id = 0
        self._callback_lock = threading.RLock()

    def add_callback(self, func):
        # TODO thread safety
        cb_id = self._callback_id
        self._callback_id += 1

        def removed(_):
            self.remove_callback(cb_id)

        if inspect.ismethod(func):
            ref = weakref.WeakMethod(func, removed)
        else:
            # TODO: strong reference to non-instance methods?
            def ref():
                return func
        with self._callback_lock:
            self.callbacks[cb_id] = ref
        return cb_id

    def remove_callback(self, cb_id):
        with self._callback_lock:
            self.callbacks.pop(cb_id, None)

    def process(self, *args, **kwargs):

        to_remove = []
        with self._callback_lock:
            for cb_id, ref in self.callbacks.items():
                try:
                    callback = ref()
                except TypeError:
                    to_remove.append(cb_id)
                    continue

                try:
                    callback(*args, **kwargs)
                except Exception as ex:
                    print(ex)

            for remove_id in to_remove:
                self.callbacks.pop(remove_id, None)


class Subscription(CallbackHandler):
    def __init__(self, pv, sub_args, sub_kwargs):
        super().__init__(pv)
        # Stash everything, but do not send any EPICS messages until the first
        # user callback is attached.
        self.sub_args = sub_args
        self.sub_kwargs = sub_kwargs
        self.subscriptionid = None
        self.most_recent_response = None

    def subscribe(self):
        """This is called automatically after the first callback is added.

        This can also be called by the user to re-activate a Subscription that
        has been previously unsubscribed.

        If this is called by the user when no callbacks are attached, nothing
        is done. The return value indicates whether a subscription was sent.
        """
        with self._callback_lock:
            # Ensure we are not already subscribed. Multiple calls to
            # unsubscribe() are idempotent, so this is always safe to do.
            self.unsubscribe()
            command = self.compose_command()  # None if there are no callbacks
        has_callbacks = command is not None
        if has_callbacks:
            self.pv.circuit_manager.send(command)
        return has_callbacks

    def compose_command(self):
        "This is used by the Context to re-subscribe after connection loss."
        with self._callback_lock:
            if not self.callbacks:
                return None
            command = self.pv.channel.subscribe(*self.sub_args,
                                                **self.sub_kwargs)
            subscriptionid = command.subscriptionid
            self.subscriptionid = subscriptionid
        # The circuit_manager needs to know the subscriptionid so that it can
        # route responses to this request.
        self.pv.circuit_manager.subscriptions[subscriptionid] = self
        return command

    def unsubscribe(self):
        # TODO This should be called automatically if all user callbacks have
        # been removed.
        with self._callback_lock:
            if self.subscriptionid is None:
                # Already unsubscribed.
                return
            self.pv.unsubscribe(self.subscriptionid)
            self.subscriptionid = None
            self.most_recent_response = None
            self.circuit_manager.send(self.channel.unsubscribe(subscriptionid))

    def process(self, *args, **kwargs):
        # TODO here i think we can decouple PV update rates and callback
        # handling rates, if desirable, to not bog down performance.
        # As implemented below, updates are blocking further messages from
        # the CA servers from processing. (-> ThreadPool, etc.)

        with self._callback_lock:
            if self.callbacks:
                super().process(*args, **kwargs)
                self.most_recent_response = (args, kwargs)

    def add_callback(self, func):
        cb_id = super().add_callback(func)
        with self._callback_lock:
            if not self.subscriptionid:
                # This is the first callback. Set up a subscription, which
                # should elicit a response from the server soon giving the
                # current value to this func (and any other funcs added in the
                # mean time).
                self.subscribe()
            else:
                # This callback is piggy-backing onto an existing subscription.
                # Send it the most recent response, unless we are still waiting
                # for that first response from the server.
                if self.most_recent_response is not None:
                    args, kwargs = self.most_recent_response
                    try:
                        func(*args, **kwargs)
                    except Exception as ex:
                        print(ex)

        return cb_id

    def __del__(self):
        if not self.subscriptionid:
            self.unsubscribe()
