import collections
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

from collections import defaultdict

import caproto as ca
from .._constants import MAX_ID
from .._utils import batch_requests


class ThreadingClientException(Exception):
    ...


class DisconnectedError(ThreadingClientException):
    ...


AUTOMONITOR_MAXLENGTH = 65536
STALE_SEARCH_EXPIRATION = 10.0
TIMEOUT = 2
SEARCH_MAX_DATAGRAM_BYTES = (0xffff - 16)
EVENT_ADD_BATCH_MAX_BYTES = 2**16
RETRY_SEARCHES_PERIOD = 1
RESTART_SUBS_PERIOD = 0.1
STR_ENC = os.environ.get('CAPROTO_STRING_ENCODING', 'latin-1')


logger = logging.getLogger(__name__)


class SelectorThread:
    def __init__(self):
        self._running = False
        self.selector = selectors.DefaultSelector()

        self._socket_map_lock = threading.RLock()
        self.objects = weakref.WeakValueDictionary()
        self.id_to_socket = {}
        self.socket_to_id = {}

        self._register_sockets = set()
        self._unregister_sockets = set()
        self._object_id = 0

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

    def add_socket(self, socket, target_obj):
        with self._socket_map_lock:
            if socket in self.socket_to_id:
                raise ValueError('Socket already added')

            socket.setblocking(False)

            # assumption: only one socket per object
            self._object_id += 1
            self.objects[self._object_id] = target_obj
            self.id_to_socket[self._object_id] = socket
            self.socket_to_id[socket] = self._object_id
            weakref.finalize(target_obj,
                             lambda obj_id=self._object_id:
                             self._object_removed(obj_id))
            self._register_sockets.add(socket)

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
                self._register_sockets.remove(sock)
            else:
                self._unregister_sockets.add(sock)

    def _object_removed(self, obj_id):
        with self._socket_map_lock:
            if obj_id in self.id_to_socket:
                sock = self.id_to_socket.pop(obj_id)
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
                if self._unregister_sockets or self._register_sockets:
                    continue

                ready_ids = [self.socket_to_id[key.fileobj]
                             for key, mask in events]
                ready_objs = [(self.objects[obj_id], self.id_to_socket[obj_id])
                              for obj_id in ready_ids]

            for obj, sock in ready_objs:
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
                        self.remove_socket(sock)
                    continue

                if bytes_recv:
                    obj.received(bytes_recv, address)
                else:
                    # zero bytes received on a ready-to-read socket means it
                    # was disconnected
                    self.remove_socket(sock)


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

        self._id_counter = itertools.count(0)
        self.search_results = {}  # map name to (time, address)
        self.unanswered_searches = {}  # map search id (cid) to (name, queue)

        self.listeners = weakref.WeakSet()

        self.broadcaster = ca.Broadcaster(our_role=ca.CLIENT)
        self.broadcaster.log.setLevel(self.log_level)
        self.command_bundle_queue = queue.Queue()
        self.command_cond = threading.Condition()

        self.selector = SelectorThread()
        self.command_thread = threading.Thread(target=self.command_loop,
                                               daemon=True)
        self.command_thread.start()
        threading.Thread(target=self._retry_unanswered_searches,
                         daemon=True).start()

        # Register with the CA repeater.
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
            self.selector.remove_socket(self.udp_sock)
        self.selector.start()
        self.udp_sock = ca.bcast_socket()
        self.selector.add_socket(self.udp_sock, self)

    def add_listener(self, listener):
        self.listeners.add(listener)
        weakref.finalize(listener, self._listener_removed)

    def remove_listener(self, listener):
        try:
            self.listeners.remove(listener)
        except KeyError:
            pass
        finally:
            self._listener_removed()

    def _listener_removed(self):
        if not self.listeners:
            self.disconnect()

    def disconnect(self, *, wait=True, timeout=2):
        with self.command_cond:
            if self.udp_sock is not None:
                self.selector.remove_socket(self.udp_sock)

            self.search_results.clear()
            self.udp_sock = None
            self.broadcaster.disconnect()
            self._registration_last_sent = 0

            # if (wait and
            #         self.command_thread is not threading.current_thread()):
            #     self.command_thread.join()

    def send(self, port, *commands):
        """
        Process a command and transport it over the UDP socket.
        """
        with self.command_cond:
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
            use_cached_search = defaultdict([].copy)
            for name in names:
                try:
                    address = self.get_cached_search_result(name)
                except KeyError:
                    needs_search.append(name)
                else:
                    use_cached_search[address].append(name)

            for addr, pvs in use_cached_search.items():
                results_queue.put((address, pvs))

            # Generate search_ids and stash them on Context state so they can
            # be used to match SearchResponses with SearchRequests.
            search_ids = []
            for name in needs_search:
                search_id = new_id()
                search_ids.append(search_id)
                unanswered_searches[search_id] = (name, results_queue)

        logger.debug('Searching for %r PVs....', len(needs_search))
        requests = (ca.SearchRequest(name, search_id, 13)
                    for name, search_id in zip(needs_search, search_ids))
        for batch in batch_requests(requests, SEARCH_MAX_DATAGRAM_BYTES):
            self.send(ca.EPICS_CA1_PORT, ca.VersionRequest(0, 13), *batch)

    def received(self, bytes_recv, address):
        "Receive and process and next command broadcasted over UDP."
        commands = self.broadcaster.recv(bytes_recv, address)
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

            with self.command_cond:
                queues.clear()
                now = time.monotonic()
                for command in commands:
                    if isinstance(command, ca.VersionResponse):
                        # Check that the server version is one we can talk to.
                        if command.version <= 11:
                            logger.warning('Version response <= 11: %r',
                                           command)
                    elif isinstance(command, ca.SearchResponse):
                        cid = command.cid
                        with self._search_lock:
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
                                # (Entries expire after
                                # STALE_SEARCH_EXPIRATION.)
                                search_results[name] = (address, now)
                # Send the search results to the Contexts that asked for
                # them. This is probably more general than is has to be but
                # I'm playing it safe for now.
                for queue, names in queues.items():
                    queue.put((address, names))
                self.command_cond.notify_all()

    def _retry_unanswered_searches(self):
        while True:
            if self._should_attempt_registration():
                self._register()

            t = time.monotonic()
            items = list(self.unanswered_searches.items())
            requests = (ca.SearchRequest(name, search_id, 13)
                        for search_id, (name, _) in
                        items)

            for batch in batch_requests(requests, SEARCH_MAX_DATAGRAM_BYTES):
                self.send(ca.EPICS_CA1_PORT, ca.VersionRequest(0, 13), *batch)
            time.sleep(max(0, RETRY_SEARCHES_PERIOD - (time.monotonic() - t)))

    def __del__(self):
        try:
            self.disconnect()
        except AttributeError:
            pass


class Context:
    "Wraps Broadcaster + cache of VirtualCircuits of a single priority"
    def __init__(self, broadcaster, *, priority=0, log_level='DEBUG'):
        self.log_level = log_level
        self.broadcaster = broadcaster
        self.search_condition = threading.Condition()
        self.pv_state_lock = threading.RLock()
        self.resuscitated_pvs = []
        self.circuit_managers = {}  # keyed on address
        self.pvs = {}
        self.cids = {}  # cid -> pv
        self.priority = priority
        self.broadcaster.add_listener(self)
        self._search_results_queue = queue.Queue()
        threading.Thread(target=self._process_search_results_loop,
                         daemon=True).start()
        threading.Thread(target=self._restart_subscriptions,
                         daemon=True).start()
        self.selector = SelectorThread()
        self.selector.start()

    def get_pvs(self, *names, connection_state_callback=None):
        """
        Return a list of PV objects.

        These objects may not be connected at first. Channel creation occurs on
        a background thread.
        """
        all_pvs = []
        search_pvs = {}
        for name in names:
            try:
                pv = self.pvs[name]
            except KeyError:
                pv = PV(name, self, connection_state_callback)
                self.pvs[name] = pv
            else:
                # Re-using a PV instance. Add a new connection state callback,
                # if necessary:
                if connection_state_callback:
                    logger.debug('Re-using PV instance for %r', name)
                    pv.connection_state_callback.add_callback(
                        connection_state_callback)

            if not pv.connected:
                search_pvs[name] = pv

            all_pvs.append(pv)

        # TODO: potential bug?
        # if callback is quick, is there a chance downstream listeners may
        # never receive notification?

        # Ask the Broadcaster to search for every PV for which we do not
        # already have an instance. It might already have a cached search
        # result, but that is the concern of broadcaster.search.
        with self.pv_state_lock:
            search_pvnames = list(search_pvs.keys())
            self.broadcaster.search(self._search_results_queue, search_pvnames)
            self.pvs.update(**search_pvs)
        return all_pvs

    def reconnect(self, names):
        search_pvs = {}
        # We will reuse the same PV object but use a new cid.
        with self.pv_state_lock:
            for name in names:
                pv = self.pvs[name]
                # if pv.channel is not None:
                #     self.pvs.pop(name, None)
                pv.circuit_manager = None
                pv.channel = None
                search_pvs[name] = pv
                # If there is a cached search result for this name, expire it.
                self.broadcaster.search_results.pop(name, None)

            search_pvnames = list(search_pvs.keys())
            self.broadcaster.search(self._search_results_queue, search_pvnames)
            with self.pv_state_lock:
                self.pvs.update(**search_pvs)
                self.resuscitated_pvs.extend(
                    [pv for name, pv in search_pvs.items()
                     if pv.subscriptions]
                )

    def _process_search_results_loop(self):
        # Receive (address, (cid1, cid2, cid3, ...)). The sending side of this
        # queue is held by SharedBroadcaster.command_loop.
        while True:
            address, names = self._search_results_queue.get()
            with self.pv_state_lock:
                # Get (make if necessary) a VirtualCircuitManager. This is
                # where TCP socket creation happens.
                vc_manager = self.get_circuit_manager(address)
                circuit = vc_manager.circuit

                # Assign each PV a VirtualCircuitManager for managing a socket
                # and tracking circuit state, as well as a ClientChannel for
                # tracking channel state.
                channels = collections.deque()
                for name in names:
                    pv = self.pvs[name]
                    pv.circuit_manager = vc_manager

                    # TODO: NOTE: we are not following the suggestion to use
                    # the same cid as in the search. This simplifies things
                    # between the broadcaster and Context.
                    cid = self.broadcaster.new_id()
                    chan = ca.ClientChannel(name, circuit, cid=cid)
                    vc_manager.channels[cid] = chan
                    vc_manager.pvs[cid] = pv
                    pv.channel = chan
                    channels.append(chan)

            # Notify PVs that they now have a circuit_manager. This will
            # un-block a wait() in the PV.wait_for_search() method.
            cond = self.search_condition
            with cond:
                cond.notify_all()

            # Initiate channel creation with the server.
            vc_manager.send(*(chan.create() for chan in channels))

    def get_circuit_manager(self, address):
        """
        Return a VirtualCircuitManager for this address. (It manages a
        caproto.VirtualCircuit and a TCP socket.)

        Make a new one if necessary.
        """
        vc_manager = self.circuit_managers.get(address, None)
        if vc_manager is None:
            circuit = ca.VirtualCircuit(our_role=ca.CLIENT, address=address,
                                        priority=self.priority)
            vc_manager = VirtualCircuitManager(self, circuit, self.selector)
            vc_manager.circuit.log.setLevel(self.log_level)
            self.circuit_managers[address] = vc_manager
        return vc_manager

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
            for vc_manager, pvs in ready.items():
                def requests():
                    for pv in pvs:
                        yield from pv._resubscribe()

                for batch in batch_requests(requests(),
                                            EVENT_ADD_BATCH_MAX_BYTES):
                    vc_manager.send(*batch)
            time.sleep(max(0, RESTART_SUBS_PERIOD - (time.monotonic() - t)))

    def disconnect(self, *, wait=True, timeout=2):
        try:
            # disconnect any circuits we have
            for circ in list(self.circuit_managers.values()):
                if circ.connected:
                    circ.disconnect(wait=wait, timeout=timeout)
        finally:
            # clear any state about circuits and search results
            self.circuit_managers.clear()

            # disconnect the underlying state machine
            self.broadcaster.remove_listener(self)

    def __del__(self):
        try:
            self.disconnect(wait=False)
            self.selector.stop()
        except (KeyError, AttributeError):
            pass
            # clean-up on deletion is best effort...
            # TODO tacaswell


class VirtualCircuitManager:
    __slots__ = ('context', 'circuit', 'channels', 'ioids', 'subscriptions',
                 'disconnected', 'new_command_cond', 'socket', 'selector',
                 'pvs', 'all_created_pvnames', '__weakref__')

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
        self.disconnected = False

        # keep track of all PV names that are successfully connected to within
        # this circuit. This is to be cleared upon disconnection:
        self.all_created_pvnames = []

        # Connect.
        cond = self.new_command_cond
        with cond:
            if self.connected:
                return
            if self.circuit.states[ca.SERVER] is ca.IDLE:
                self.socket = socket.create_connection(self.circuit.address)
                self.selector.add_socket(self.socket, self)
                self.send(ca.VersionRequest(self.circuit.priority, 13),
                          ca.HostNameRequest('foo'),
                          ca.ClientNameRequest('bar'))
            else:
                raise RuntimeError("Cannot connect. States are {} "
                                   "".format(self.circuit.states))
            if not cond.wait_for(lambda: self.connected, timeout):
                raise TimeoutError("Circuit with server at {} did not "
                                   "connected within {}-second timeout."
                                   "".format(self.circuit.address, timeout))

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
        with self.new_command_cond:
            # turn the crank on the caproto
            buffers_to_send = self.circuit.send(*commands)

            # send bytes over the wire using some caproto utilities
            ca.send_all(buffers_to_send, self._socket_send)

    def received(self, bytes_recv, address):
        """Receive and process and next command from the virtual circuit.

        This will be run on the recv thread"""
        commands, num_bytes_needed = self.circuit.recv(bytes_recv)

        for c in commands:
            self._process_command(c)

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
                sub.process(command)
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
            # Ensure that this method is idempotent.
            if self.disconnected:
                return
            self.disconnected = True
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

        # Kick off attempt to reconnect all PVs via fresh circuit(s).

        self.context.reconnect([chan.name for chan in self.channels.values()])

        # Clean up the socket.
        sock = self.socket
        if sock is not None:
            self.selector.remove_socket(sock)
            try:
                sock.shutdown(socket.SHUT_WR)
                sock.close()
            except OSError:
                pass

    def disconnect(self, *, wait=True, timeout=2.0):
        if self.disconnected or self.socket is None:
            return

        sock, self.socket = self.socket, None
        try:
            sock.shutdown(socket.SHUT_WR)
        except OSError as ex:
            pass

        # self.selector.remove_socket(sock)
        if wait:
            cond = self.new_command_cond
            with cond:
                if self.disconnected:
                    return
                done = cond.wait_for(lambda: self.disconnected, timeout)

            if not done:
                # TODO: this may actually happen due to a long backlog of
                # incoming data, but may not be critical to wait for...
                raise TimeoutError(f"Server did not respond to disconnection "
                                   f"attempt within {timeout}-second timeout."
                                   )

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
                 '_write_notify_callback', '_user_disconnected',
                 'connection_state_callback', '_pc_callbacks', '__weakref__')

    def __init__(self, name, context, connection_state_callback):
        """
        These must be instantiated by a Context, never directly.
        """
        self.name = name
        self.priority = context.priority
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
        self._user_disconnected = False

    def connection_state_changed(self, state, channel):
        logger.debug('%s Connection state changed %s %s %s %d', self.name, state,
                     channel, hex(id(self)),
                     len(self.connection_state_callback.callbacks))
        if state == 'disconnected':
            logger.debug('%s channel reset', self.name)

        # PV is responsible for updating its channel attribute.
        self.channel = channel

        self.connection_state_callback.process(self, state)

    def __repr__(self):
        if self._user_disconnected:
            state = "(disconnected by user)"
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
        return f"<PV name={repr(self.name)} priority={self.priority} {state}>"

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
        cond = self.context.search_condition
        with cond:
            if self.circuit_manager is not None:
                return
            done = cond.wait_for(lambda: self.circuit_manager is not None,
                                 timeout)
        if not done:
            raise TimeoutError("No servers responded to a search for a "
                               "channel named {!r} within {}-second "
                               "timeout."
                               "".format(self.name, timeout))

    def wait_for_connection(self, *, timeout=2):
        """Wait for this Channel to be connected, ready to use.

        The method ``Context.create_channel`` spawns an asynchronous task to
        initialize the connection in the fist place. This method waits for it
        to complete.
        """
        # TODO: old docstring
        if self.circuit_manager is None:
            self.wait_for_search(timeout=timeout)
        cond = self.circuit_manager.new_command_cond
        with cond:
            if self.connected:
                return
            done = cond.wait_for(lambda: self.connected, timeout)
        if not done:
                raise TimeoutError(
                    f"Server at {self.circuit_manager.circuit.address} did "
                    f"not respond to attempt to create channel named "
                    f"{self.name!r} within {timeout}-second timeout."
                )

    def disconnect(self, *, wait=True, timeout=2):
        "Disconnect this Channel."
        self._user_disconnected = True

        # TODO
        self.connection_state_callback.callbacks.clear()

        with self.circuit_manager.new_command_cond:
            if not self.connected:
                return

            try:
                self.circuit_manager.send(self.channel.disconnect())
            except OSError:
                # the socket is dead-dead, return
                return

        if wait:
            def is_closed():
                return self.channel is None

            cond = self.circuit_manager.new_command_cond
            with cond:
                done = cond.wait_for(is_closed, timeout)
            if not done:
                raise TimeoutError(
                    f"Server at {self.circuit_manager.circuit.address} did "
                    f"not respond to attempt to close channel named "
                    f"{self.name!r} within {timeout}-second timeout."
                )

    def reconnect(self, *, timeout=2):
        if self.connected:
            # Try disconnecting first, but reconnect even if that fails.
            try:
                self.disconnect()
            except Exception:
                pass
        self._user_disconnected = False
        self.context.reconnect((self.name, ))
        self.wait_for_connection(timeout=timeout)
        self.circuit_manager.send(*self._resubscribe())

    def _resubscribe(self):
        for sub in self.subscriptions:
            command = self.channel.subscribe(*sub.sub_args, **sub.sub_kwargs)
            # Update Subscription object with new id.
            subscriptionid = command.subscriptionid
            sub.subscriptionid = subscriptionid
            # Let the circuit_manager match future responses to this request.
            self.circuit_manager.subscriptions[subscriptionid] = sub
            yield command

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

        cond = self.circuit_manager.new_command_cond
        with cond:
            done = cond.wait_for(has_reading, timeout)
        if not done:
            raise TimeoutError(
                f"Server at {self.circuit_manager.circuit.address} did "
                f"not respond to attempt to read channel named "
                f"{self.name!r} within {timeout}-second timeout."
            )
        return self.last_reading

    def write(self, *args, wait=True, cb=None, timeout=2, **kwargs):
        "Write a new value and await confirmation from the server."
        if not self.connected:
            raise DisconnectedError()

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

        cond = self.circuit_manager.new_command_cond
        with cond:
            done = cond.wait_for(has_reading, timeout)
        if not done:
            raise TimeoutError(
                f"Server at {self.circuit_manager.circuit.address} did "
                f"not respond to attempt to write to channel named "
                f"{self.name!r} within {timeout}-second timeout."
            )
        return self.last_writing

    def subscribe(self, *args, **kwargs):
        "Start a new subscription and spawn an async task to receive readings."
        if not self.connected:
            raise DisconnectedError()

        command = self.channel.subscribe(*args, **kwargs)
        subscriptionid = command.subscriptionid
        sub = Subscription(self, subscriptionid, args, kwargs)
        # Let the circuit_manager match future responses to this request.
        self.circuit_manager.subscriptions[subscriptionid] = sub
        # Stash this in case we need to re-connect later.
        self.subscriptions.append(sub)
        self.circuit_manager.send(command)
        # TODO verify it worked before returning?
        return sub

    def unsubscribe(self, subscriptionid, *args, **kwargs):
        "Cancel a subscription and await confirmation from the server."
        self.circuit_manager.send(self.channel.unsubscribe(subscriptionid))
        sub, = [sub for sub in self.subscriptions
                if sub.subscriptionid == subscriptionid]
        self.subscriptions.remove(sub)
        # TODO verify it worked before returning?

    # def __hash__(self):
    #     return id((self.context, self.circuit_manager, self.name))


class CallbackHandler:
    def __init__(self, pv):
        # NOTE: not a WeakValueDictionary or WeakSet as PV is unhashable...
        self.callbacks = {}
        self.pv = pv
        self._callback_id = 0

    def add_callback(self, func):
        # TODO thread safety, not just weakmethods
        cb_id = self._callback_id
        self._callback_id += 1

        def removed(_):
             self.remove_callback(cb_id)

        ref = weakref.WeakMethod(func, removed)

        self.callbacks[cb_id] = ref

    def remove_callback(self, cb_id):
        self.callbacks.pop(cb_id, None)

    def process(self, *args, **kwargs):
        to_remove = []
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
            self._callbacks.pop(remove_id, None)


class Subscription(CallbackHandler):
    def __init__(self, pv, subscriptionid, sub_args, sub_kwargs):
        super().__init__(pv)

        self.subscriptionid = subscriptionid
        # These will be used by the PV to re-subscribe if we need to reconnect.
        self.sub_args = sub_args
        self.sub_kwargs = sub_kwargs
        self._unsubscribed = False

    def unsubscribe(self):
        self.pv.unsubscribe(self.subscriptionid)

    def __del__(self):
        if not self._unsubscribed:
            self.unsubscribe()
