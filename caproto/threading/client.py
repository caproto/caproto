# There are 7 threads plus one callback-processing thread per VirtualCircuit

# UDP socket selector
# TCP socket selector
# UDP command processing
# forever retrying search requests for disconnected PV
# handle disconnection
# process search results
# restart subscriptions
import getpass
import itertools
import logging
import os
from queue import Queue, Empty
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
from inspect import Parameter, Signature
from functools import partial
from collections import defaultdict
import caproto as ca
from .._constants import (MAX_ID, STALE_SEARCH_EXPIRATION,
                          SEARCH_MAX_DATAGRAM_BYTES)
from .._utils import batch_requests, CaprotoError, ThreadsafeCounter

print = partial(print, flush=True)


def master_lock(func):
    """
    Apply to a lock during an instance method's execution.

    This expects the instance to have an attribute named `master_lock`.
    """
    counter = itertools.count()

    def inner(self, *args, **kwargs):
        next(counter)
        with self.master_lock:
            ret = func(self, *args, **kwargs)
            return ret
    return inner


def ensure_connected(func):
    def inner(self, *args, **kwargs):
        with self._in_use:
            self._usages += 1
            # If needed, reconnect. Do this inside the lock so that we don't
            # try to do this twice. (No other threads that need this lock
            # can proceed until the connection is ready anyway!)
            with self.master_lock:
                if self._idle or (self.circuit_manager and
                                  self.circuit_manager.dead):
                    self.context.reconnect(((self.name, self.priority),))
                    reconnect = True
                else:
                    reconnect = False
            # Do not bother notifying the self._in_use condition because we
            # have *increased* the usages here. It will be notified below,
            # inside the `finally` block, when we decrease the usages.
        try:
            self._wait_for_connection()
            if reconnect:
                def requests():
                    for sub in self.subscriptions.values():
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
                with self.master_lock:
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
        self.thread = None  # set by the `start` method
        self._close_event = threading.Event()
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
        return not self._close_event.is_set()

    def stop(self):
        self._close_event.set()

    def start(self):
        if self._close_event.is_set():
            raise RuntimeError("Cannot be restarted once stopped.")
        self.thread = threading.Thread(target=self, daemon=True,
                                       name='selector')
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
        self._retry_unanswered_searches_thread = None
        self._retries_enabled = threading.Event()

        self._id_counter = itertools.count(0)
        self.search_results = {}  # map name to (time, address)
        self.unanswered_searches = {}  # map search id (cid) to (name, queue)

        self.listeners = weakref.WeakSet()

        self.broadcaster = ca.Broadcaster(our_role=ca.CLIENT)
        self.broadcaster.log.setLevel(self.log_level)
        self.command_bundle_queue = Queue()
        self.command_cond = threading.Condition()

        # an event to tear down and clean up the broadcaster
        self._close_event = threading.Event()
        self.selector = SelectorThread(parent=self)

        self.selector.start()
        self.command_thread = threading.Thread(target=self.command_loop,
                                               daemon=True, name='command')
        self.command_thread.start()

        self._registration_retry_time = registration_retry_time
        self._registration_last_sent = 0

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

        self.udp_sock = ca.bcast_socket()
        self.selector.add_socket(self.udp_sock, self)

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

    def disconnect(self, *, wait=True, timeout=2):
        with self.command_cond:
            if self.udp_sock is not None:
                self.selector.remove_socket(self.udp_sock)

            self._close_event.set()
            self.search_results.clear()
            self._registration_last_sent = 0
            self._retries_enabled.clear()
            self.udp_sock = None
            self.broadcaster.disconnect()
            self.selector.stop()

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

        while not self._close_event.is_set():
            try:
                commands = self.command_bundle_queue.get(timeout=1)
            except Empty:
                # By restarting the loop, we will first check that we are not
                # supposed to shut down the thread before we go back to
                # waiting on the queue again.
                continue

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

        logger.debug('Broadcaster command loop exiting')

    def _retry_unanswered_searches(self):
        logger.debug('Search-retry thread started.')
        while not self._close_event.is_set():
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

            wait_time = max(0, RETRY_SEARCHES_PERIOD - (time.monotonic() - t))
            self._close_event.wait(wait_time)

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
        self.pv_cache_lock = threading.RLock()
        self.master_lock = threading.RLock()
        self.resuscitated_pvs = []
        self.circuit_managers = {}  # keyed on address
        self.pvs = {}  # (name, priority) -> pv
        # name -> set of pvs  --- with varied priority
        self.pvs_needing_circuits = defaultdict(set)
        self.broadcaster.add_listener(self)
        self._search_results_queue = Queue()

        # an event to close and clean up the whole context
        self._close_event = threading.Event()

        logger.debug('Context: start process search results loop')
        self._process_search_results_thread = threading.Thread(
            target=self._process_search_results_loop,
            daemon=True, name='search')
        self._process_search_results_thread.start()

        logger.debug('Context: start restart_subscriptions loop')
        self._restart_sub_thread = threading.Thread(
            target=self._restart_subscriptions,
            daemon=True, name='restart_subscriptions')
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
        for name in names:

            with self.pv_cache_lock:
                try:
                    pv = self.pvs[(name, priority)]
                    new_instance = False
                except KeyError:
                    pv = PV(name, priority, self, connection_state_callback)
                    names_to_search.append(name)
                    self.pvs[(name, priority)] = pv
                    self.pvs_needing_circuits[name].add(pv)
                    new_instance = True

            if not new_instance and connection_state_callback:
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

        for key in keys:
            with self.pv_cache_lock:
                pv = self.pvs[key]
            pv.circuit_manager = None
            pv.channel = None
            pvs.append(pv)
            name, _ = key
            names.append(name)
            # If there is a cached search result for this name, expire it.
            self.broadcaster.search_results.pop(name, None)
            with self.pv_cache_lock:
                self.pvs_needing_circuits[name].add(pv)
            with self.pv_cache_lock:
                self.resuscitated_pvs.extend(
                    [pv for pv in pvs if pv.subscriptions])

        self.broadcaster.search(self._search_results_queue, names)

    def _process_search_results_loop(self):
        # Receive (address, (name1, name2, ...)). The sending side of this
        # queue is held by SharedBroadcaster.command_loop.
        while not self._close_event.is_set():
            try:
                address, names = self._search_results_queue.get(timeout=1)
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

            # Notify PVs that they now have a circuit_manager. This will
            # un-block a wait() in the PV.wait_for_search() method.
            with self.search_condition:
                self.search_condition.notify_all()

            # Initiate channel creation with the server.
            for cm, channels in channels_grouped_by_circuit.items():
                commands = [chan.create() for chan in channels]
                cm.send(*commands)

        logger.debug('Process search results thread exiting')

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
        while not self._close_event.is_set():
            with self.master_lock:
                t = time.monotonic()
                ready = defaultdict(list)
                with self.pv_cache_lock:
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
                            subs = pv.subscriptions
                            cm_subs_cache = pv.circuit_manager.subscriptions
                            for sub in list(subs.values()):
                                # the old subscription is dead, remove it
                                if sub.subscriptionid is not None:
                                    cm_subs_cache.pop(sub.subscriptionid, None)
                                # this will add the subscription into our self.subscriptions
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

                wait_time = max(0, (RESTART_SUBS_PERIOD -
                                    (time.monotonic() - t)))
                self._close_event.wait(wait_time)

        logger.debug('Restart subscriptions thread exiting')

    def disconnect(self, *, wait=True, timeout=2):
        self._user_disconnected = True
        try:
            self._close_event.set()
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

            logger.debug("Stopping Context's SelectorThread")
            self.selector.stop()

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
    __slots__ = ('context', 'circuit', 'channels', 'ioids', '_ioid_counter',
                 'subscriptions', '_user_disconnected', 'new_command_cond',
                 'socket', 'selector', 'pvs', 'all_created_pvnames',
                 'callback_queue', 'callback_thread', '_torn_down',
                 'process_queue', 'processing', 'master_lock',
                 '__weakref__')

    def __init__(self, context, circuit, selector, timeout=TIMEOUT):
        self.context = context
        self.circuit = circuit  # a caproto.VirtualCircuit
        self.channels = {}  # map cid to Channel
        self.pvs = {}  # map cid to PV
        self.ioids = {}  # map ioid to Channel and info dict
        self.subscriptions = {}  # map subscriptionid to Subscription
        self.new_command_cond = threading.Condition()
        self.socket = None
        self.selector = selector
        self._user_disconnected = False
        self.callback_queue = Queue()
        self.callback_thread = threading.Thread(target=self._callback_loop,
                                                daemon=True, name='vcm_cb')
        self.callback_thread.start()
        self.master_lock = threading.RLock()
        # keep track of all PV names that are successfully connected to within
        # this circuit. This is to be cleared upon disconnection:
        self.all_created_pvnames = []
        self._torn_down = False
        self._ioid_counter = ThreadsafeCounter()

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
        while not self.context._close_event.is_set():
            t0, sub, command = self.callback_queue.get()
            if sub is ca.DISCONNECTED:
                break

            dt = time.monotonic() - t0
            logger.debug('Executing callback (dt=%.1f ms): %s %s',
                         dt * 1000., sub, command)

            sub.process(command)

        logger.debug('Callback loop exiting')

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
            elif isinstance(command, (ca.ReadNotifyResponse,
                                      ca.WriteNotifyResponse)):
                ioid_info = self.ioids.pop(command.ioid)
                deadline = ioid_info['deadline']
                if deadline is not None and time.monotonic() > deadline:
                    logger.warn(f"ignoring late response with "
                                f"ioid={command.ioid} because it arrived "
                                f"{time.monotonic() - ioid_info['deadline']} "
                                f"seconds after the deadline specified by the "
                                f"timeout."
                                )
                else:
                    chan = ioid_info['channel']
                    if isinstance(command, ca.WriteNotifyResponse):
                        chan.process_write_notify(command)
                    else:
                        chan.process_read_notify(command)
                    callback = ioid_info.get('callback')
                    if callback is not None:
                        try:
                            callback(command)
                        except Exception as ex:
                            logger.exception('ioid callback failed')

                event = ioid_info['event']
                # If PV.read() or PV.write() are waiting on this response,
                # they hold a reference to ioid_info. We will use that to
                # provide the response to them and then set the Event that they
                # are waiting on.
                ioid_info['response'] = command
                if event is not None:
                    event.set()

            elif isinstance(command, ca.EventAddResponse):
                try:
                    sub = self.subscriptions[command.subscriptionid]
                except KeyError:
                    # This subscription has been removed. We assume that this
                    # response was in flight before the server processed our
                    # unsubscription.
                    pass
                else:
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
            else:
                logger.debug('other command %s', command)
            self.new_command_cond.notify_all()

    @master_lock
    def _disconnected(self):
        print("DISCONNECTED")
        # Ensure that this method is idempotent.
        if self._torn_down:
            return
        self._torn_down = True

        logger.debug('Entered VCM._disconnected')
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

        # Clean up the socket if it has not yet been cleared:
        sock, self.socket = self.socket, None
        if sock is not None:
            self.selector.remove_socket(sock)
            try:
                sock.shutdown(socket.SHUT_WR)
                sock.close()
            except OSError:
                pass

        if not self._user_disconnected:
            # If the user didn't request disconnection, kick off attempt to
            # reconnect all PVs via fresh circuit(s).
            logger.debug('VCM: Attempting reconnection')
            self.context.reconnect(((chan.name, chan.circuit.priority)
                                    for chan in self.channels.values()))

    @master_lock
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
    __slots__ = ('name', 'priority', 'context', '_circuit_manager', '_channel',
                 '_read_notify_callback',
                 'subscriptions', 'command_bundle_queue', '_component_lock',
                 '_write_notify_callback', '_idle', '_in_use', '_usages',
                 'connection_state_callback', 'master_lock', '__weakref__')

    def __init__(self, name, priority, context, connection_state_callback):
        """
        These must be instantiated by a Context, never directly.
        """
        self.master_lock = threading.RLock()
        self.name = name
        self.priority = priority
        self.context = context
        # Use this lock whenever we touch circuit_manager or channel.
        self._component_lock = threading.RLock()
        self.connection_state_callback = CallbackHandler(self)

        if connection_state_callback is not None:
            self.connection_state_callback.add_callback(
                connection_state_callback)

        self._circuit_manager = None
        self._channel = None
        self.subscriptions = {}
        self._read_notify_callback = None  # called on ReadNotifyResponse
        self._write_notify_callback = None  # called on WriteNotifyResponse
        self._idle = False
        self._in_use = threading.Condition()
        self._usages = 0

    @property
    def circuit_manager(self):
        with self._component_lock:
            return self._circuit_manager

    @circuit_manager.setter
    def circuit_manager(self, val):
        with self._component_lock:
            self._circuit_manager = val

    @property
    def channel(self):
        with self._component_lock:
            return self._channel

    @channel.setter
    def channel(self, val):
        with self._component_lock:
            self._channel = val

    def connection_state_changed(self, state, channel):
        logger.debug('%s Connection state changed %s %s', self.name, state,
                     channel)
        # PV is responsible for updating its channel attribute.
        self.channel = channel

        self.connection_state_callback.process(self, state)

    @master_lock
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
        with self._component_lock:
            channel = self.channel
            if channel is None:
                return False
            return channel.states[ca.CLIENT] is ca.CONNECTED

    def process_read_notify(self, read_notify_command):
        if self._read_notify_callback is None:
            return
        else:
            try:
                return self._read_notify_callback(read_notify_command)
            except Exception as ex:
                print(ex)

    def process_write_notify(self, write_notify_command):
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

    @master_lock
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
    def read(self, wait=True, callback=None, timeout=2, data_type=None,
             data_count=None):
        """Request a fresh reading.

        Can do one or both of:
        - Block while waiting for the response, and return it.
        - Pass the response to callback, with or without blocking.

        Parameters
        ----------
        wait : boolean
            If True (default) block until a matching WriteNotifyResponse is
            received from the server. Raises TimeoutError if that response is
            not received within the time specified by the `timeout` parameter.
        callback : callable or None
            Called with the WriteNotifyResponse as its argument when received.
        timeout : number or None
            Number of seconds to wait before raising TimeoutError. Default is
            2.
        data_type : a ChannelType or corresponding integer ID, optional
            Requested Channel Access data type. Default is the channel's
            native data type, which can be checked in the Channel's attribute
            :attr:`native_data_type`.
        data_count : integer, optional
            Requested number of values. Default is the channel's native data
            count, which can be checked in the Channel's attribute
            :attr:`native_data_count`.
        """
        # need this lock because the socket thread could be trying to
        # update this channel due to an incoming message
        if not self.connected:
            raise DisconnectedError()

        ioid = self.circuit_manager._ioid_counter()
        command = self.channel.read(ioid=ioid,
                                    data_type=data_type,
                                    data_count=data_count)
        # Stash the ioid to match the response to the request.

        event = threading.Event()
        ioid_info = dict(channel=self, event=event)
        if callback is not None:
            ioid_info['callback'] = callback

        self.circuit_manager.ioids[ioid] = ioid_info

        deadline = time.monotonic() + timeout if timeout is not None else None
        ioid_info['deadline'] = deadline
        # TODO: circuit_manager can be removed from underneath us here
        self.circuit_manager.send(command)

        # The circuit_manager will put a reference to the response into
        # ioid_info and then set event.
        if not event.wait(timeout=timeout):
            raise TimeoutError(
                f"Server at {self.circuit_manager.circuit.address} did "
                f"not respond to attempt to read channel named "
                f"{self.name!r} within {timeout}-second timeout."
            )

        return ioid_info['response']

    @ensure_connected
    def write(self, data, wait=True, callback=None, timeout=2, use_notify=None,
              data_type=None, data_count=None):
        """
        Write a new value. Optionally, request confirmation from the server.

        Can do one or both of:
        - Block while waiting for the response, and return it.
        - Pass the response to callback, with or without blocking.

        Parameters
        ----------
        data : Iterable
            values to write
        wait : boolean
            If True (default) block until a matching WriteNotifyResponse is
            received from the server. Raises TimeoutError if that response is
            not received within the time specified by the `timeout` parameter.
        callback : callable or None
            Called with the WriteNotifyResponse as its argument when received.
        timeout : number or None
            Number of seconds to wait before raising TimeoutError. Default is
            2.
        use_notify : boolean or None
            If None (default), set to True if wait=True or callback is set.
            Can be manually set to True or False. Will raise ValueError if set
            to False while wait=True or callback is set.
        data_type : a ChannelType or corresponding integer ID, optional
            Requested Channel Access data type. Default is the channel's
            native data type, which can be checked in the Channel's attribute
            :attr:`native_data_type`.
        data_count : integer, optional
            Requested number of values. Default is the channel's native data
            count, which can be checked in the Channel's attribute
            :attr:`native_data_count`.
        """
        if use_notify is None:
            use_notify = (wait or callback is not None)
        ioid = self.circuit_manager._ioid_counter()
        command = self.channel.write(data,
                                     ioid=ioid,
                                     use_notify=use_notify,
                                     data_type=data_type,
                                     data_count=data_count)
        if not use_notify:
            if wait or callback is not None:
                raise ValueError("Must set use_notify=True in order to use "
                                 "`wait` or `callback` because, without a "
                                 "notification of 'put-completion' from the "
                                 "server, there is nothing to wait on or to "
                                 "trigger a callback.")
            self.circuit_manager.send(command)
            return

        event = threading.Event()
        ioid_info = dict(channel=self, event=event)
        if callback is not None:
            ioid_info['callback'] = callback

        self.circuit_manager.ioids[ioid] = ioid_info

        deadline = time.monotonic() + timeout if timeout is not None else None
        ioid_info['deadline'] = deadline
        # do not need to lock this, locking happens in circuit command
        self.circuit_manager.send(command)
        if not wait:
            return

        # The circuit_manager will put a reference to the response into
        # ioid_info and then set event.
        if not event.wait(timeout=timeout):
            raise TimeoutError(
                f"Server at {self.circuit_manager.circuit.address} did "
                f"not respond to attempt to write to channel named "
                f"{self.name!r} within {timeout}-second timeout. The ioid of "
                f"the expected response is {ioid}."
            )
        return ioid_info['response']

    @master_lock
    def subscribe(self, *args, **kwargs):
        "Start a new subscription to which user callback may be added."
        # A Subscription is uniquely identified by the Signature created by its
        # args and kwargs.
        key = tuple(SUBSCRIBE_SIG.bind(*args, **kwargs).arguments.items())
        try:
            sub = self.subscriptions[key]
        except KeyError:
            sub = Subscription(self, args, kwargs)
            self.subscriptions[key] = sub
        # The actual EPICS messages will not be sent until the user adds
        # callbacks via sub.add_callback(user_func).
        return sub

    @master_lock
    def unsubscribe_all(self):
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
        self._callback_lock = threading.RLock()
        self.master_lock = threading.RLock()

    @master_lock
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
            ref = weakref.ref(func, removed)

        with self._callback_lock:
            self.callbacks[cb_id] = ref
        return cb_id

    @master_lock
    def remove_callback(self, cb_id):
        with self._callback_lock:
            self.callbacks.pop(cb_id, None)

    @master_lock
    def process(self, *args, **kwargs):

        to_remove = []
        with self._callback_lock:
            callbacks = list(self.callbacks.items())

        for cb_id, ref in callbacks:
            callback = ref()
            if callback is None:
                to_remove.append(cb_id)
                continue

            try:
                callback(*args, **kwargs)
            except Exception as ex:
                print(ex)

        with self._callback_lock:
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

    def __repr__(self):
        return f"<Subscription to {self.pv.name!r}, id={self.subscriptionid}>"

    @master_lock
    def _subscribe(self):
        """This is called automatically after the first callback is added.
        """
        # some contorions employed to reuse the ensure_connected decorator here
        ensure_connected(lambda self: None)(self.pv)
        with self._callback_lock:
            command = self.compose_command()  # None if there are no callbacks
        has_callbacks = command is not None
        if has_callbacks:
            self.pv.circuit_manager.send(command)
        return has_callbacks

    @master_lock
    def compose_command(self):
        "This is used by the Context to re-subscribe in bulk after dropping."
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

    @master_lock
    def clear(self):
        """
        Remove all callbacks.
        """
        with self._callback_lock:
            for cb_id in list(self.callbacks):
                self.remove_callback(cb_id)
        # Once self.callbacks is empty, self.remove_callback calls
        # self._unsubscribe for us.

    @master_lock
    def _unsubscribe(self):
        """
        This is automatically called if the number of callbacks goes to 0.
        """
        with self._callback_lock:
            if self.subscriptionid is None:
                # Already unsubscribed.
                return
            subscriptionid = self.subscriptionid
            self.subscriptionid = None

            self.most_recent_response = None
        chan = self.pv.channel
        if chan and chan.states[ca.CLIENT] is ca.CONNECTED:
            try:
                command = self.pv.channel.unsubscribe(subscriptionid)
            except ca.CaprotoKeyError:
                pass
            else:
                self.pv.circuit_manager.send(command)

    @master_lock
    def process(self, *args, **kwargs):
        # TODO here i think we can decouple PV update rates and callback
        # handling rates, if desirable, to not bog down performance.
        # As implemented below, updates are blocking further messages from
        # the CA servers from processing. (-> ThreadPool, etc.)

        super().process(*args, **kwargs)
        self.most_recent_response = (args, kwargs)

    @master_lock
    def add_callback(self, func):
        cb_id = super().add_callback(func)
        with self._callback_lock:
            if self.subscriptionid is None:
                # This is the first callback. Set up a subscription, which
                # should elicit a response from the server soon giving the
                # current value to this func (and any other funcs added in the
                # mean time).
                self._subscribe()
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

    @master_lock
    def remove_callback(self, cb_id):
        with self._callback_lock:
            super().remove_callback(cb_id)
            if not self.callbacks:
                # Go dormant.
                self._unsubscribe()

    def __del__(self):
        self.clear()


# The signature of caproto._circuit.ClientChannel.subscribe, which is used to
# resolve the (args, kwargs) of a Subscription into a unique key.
SUBSCRIBE_SIG = Signature([
    Parameter('data_type', Parameter.POSITIONAL_OR_KEYWORD, default=None),
    Parameter('data_count', Parameter.POSITIONAL_OR_KEYWORD, default=None),
    Parameter('low', Parameter.POSITIONAL_OR_KEYWORD, default=0),
    Parameter('high', Parameter.POSITIONAL_OR_KEYWORD, default=0),
    Parameter('to', Parameter.POSITIONAL_OR_KEYWORD, default=0),
    Parameter('mask', Parameter.POSITIONAL_OR_KEYWORD, default=None)])
