import collections
import copy
import functools
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

from collections import Iterable, defaultdict

import caproto as ca
from .._constants import (DEFAULT_PROTOCOL_VERSION, MAX_ID)
from .._utils import batch_requests


class ThreadingClientException(Exception):
    ...


class DisconnectedError(ThreadingClientException):
    ...


AUTOMONITOR_MAXLENGTH = 65536
STALE_SEARCH_EXPIRATION = 10.0
TIMEOUT = 2
SEARCH_MAX_DATAGRAM_BYTES = (0xffff - 16)
RETRY_SEARCHES_PERIOD = 1
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

        self._register_sockets = []
        self._unregister_sockets = []
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
            self._register_sockets.append(socket)

    def remove_socket(self, sock):
        with self._socket_map_lock:
            if sock not in self.socket_to_id:
                return

            obj_id = self.socket_to_id.pop(sock)
            del self.id_to_socket[obj_id]
            obj = self.objects.pop(obj_id, None)
            if obj is not None:
                obj.received(b'', None)
            self._unregister_sockets.append(sock)

    def _object_removed(self, obj_id):
        with self._socket_map_lock:
            if obj_id in self.id_to_socket:
                sock = self.id_to_socket.pop(obj_id)
                del self.socket_to_id[sock]
                self._unregister_sockets.append(sock)

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
                    bytes_recv, address = sock.recvfrom(max((4096,
                                                             bytes_available)))
                except OSError as ex:
                    if ex.errno == errno.EAGAIN:
                        continue
                    bytes_recv, address = b'', None

                obj.received(bytes_recv, address)


class SharedBroadcaster:
    def __init__(self, *, log_level='ERROR', timeout=0.5, attempts=5):
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
        if self.udp_sock is None:
            self.__create_sock()

        with self.command_cond:
            command = self.broadcaster.register('127.0.0.1')
            self.send(ca.EPICS_CA2_PORT, command)

        for attempts in range(attempts):
            with self.command_cond:
                done = self.command_cond.wait_for(
                    lambda: self.broadcaster.registered, timeout)
                self.send(ca.EPICS_CA2_PORT, command)
            if done:
                break
        else:
            raise TimeoutError('Failed to register with the broadcaster')

    def new_id(self):
        # Return the next sequential unused id. Wrap back to 0 on overflow.
        # We need an id that is not currently used by _any_ Context that
        # searches using this Broadcaster. (In theory we could keep search IDs
        # separate from Channel IDs, but the CA spec says that they "SHOULD" be
        # the same ID.)
        while True:
            i = next(self._id_counter)
            for listener in self.listeners:  # 'listener' i.e. Context
                if i in listener.pvs:
                    continue
            if i == MAX_ID:
                self._id_counter = itertools.count(0)
                continue
            return i

    def __create_sock(self):
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
        if self.udp_sock is not None:
            self.selector.remove_socket(self.udp_sock)

        with self._search_lock:
            self.search_results.clear()
        self.udp_sock = None
        self.broadcaster.disconnect()

        # if wait and self.command_thread is not threading.current_thread():
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
                    is_register = isinstance(commands[0],
                                             ca.RepeaterRegisterRequest)
                    if not self.broadcaster.registered and is_register:
                        logger.debug('Specific IOC host/port designated in '
                                     'address list: %s:%s.  Repeater '
                                     'registration requirement ignored', host,
                                     specified_port)
                        with self.command_cond:
                            # TODO how does this work with multiple addresses
                            # listed?
                            response = ca.RepeaterConfirmResponse(
                                repeater_address='127.0.0.1')
                            response.sender_address = ('127.0.0.1',
                                                       ca.EPICS_CA1_PORT)
                            self.command_bundle_queue.put([response])
                            self.command_cond.notify_all()
                        continue
                    self.udp_sock.sendto(bytes_to_send, (host,
                                                         int(specified_port)))
                else:
                    self.udp_sock.sendto(bytes_to_send, (host, port))

    def search(self, results_queue, names, *, timeout=2):
        "Generate, process, and the transport a search request."
        new_id = self.new_id
        search_results = self.search_results
        unanswered_searches = self.unanswered_searches
        stale_search_expiration = STALE_SEARCH_EXPIRATION

        with self._search_lock:
            # We have have already searched for these names recently.
            # Filter `pv_names` down to a subset, `needs_search`.
            now = time.monotonic()
            needs_search = []
            use_cached_search = []
            for name in names:
                try:
                    # Raise KeyError if the result is missing or stale.
                    address, timestamp = search_results[name]
                    if now - timestamp > stale_search_expiration:
                        # Clean up expired result.
                        search_results.pop(name, None)
                        raise KeyError
                except KeyError:
                    needs_search.append(name)
                else:
                    use_cached_search.append(name)

            # TODO Resolve ones that do not need search as resolved.

            # Generate search_ids and stash them on Context state so they can
            # be used to match SearchResponses with SearchRequests.
            search_ids = []
            for name in needs_search:
                search_id = new_id()
                search_ids.append(search_id)
                unanswered_searches[search_id] = (name, results_queue)
        logger.debug("Searching for '%r' PVs...." % len(needs_search))
        requests = (ca.SearchRequest(name, search_id, 13)
                    for name, search_id in zip(needs_search, search_ids))
        for batch in batch_requests(requests, SEARCH_MAX_DATAGRAM_BYTES):
            self.send(ca.EPICS_CA1_PORT, ca.VersionRequest(0, 13), *batch)
        return search_ids

    def received(self, bytes_recv, address):
        "Receive and process and next command broadcasted over UDP."
        commands = self.broadcaster.recv(bytes_recv, address)
        self.command_bundle_queue.put(commands)
        return 0

    def command_loop(self):
        # Receive commands in 'bundles' (corresponding to the contents of one
        # UDP datagram). Match SearchResponses to their SearchRequests, and
        # put (address, (cid1, cid2, cid3, ...)) into a queue. The receiving
        # end of that queue is held by Context._process_search_results.

        # Save doing a 'self' lookup in the inner loop.
        search_results = self.search_results
        unanswered_searches = self.unanswered_searches

        while True:
            commands = self.command_bundle_queue.get()
            try:
                self.broadcaster.process_commands(commands)
            except ca.CaprotoError as ex:
                logger.warning('Broadcaster command error', exc_info=ex)
                continue

            with self.command_cond:
                queues = defaultdict(list)
                now = time.monotonic()
                for command in commands:
                    if isinstance(command, ca.VersionResponse):
                        # Check that the server version is one we can talk to.
                        if command.version <= 11:
                            logger.warning('Version response <= 11: %r',
                                           command)
                    if isinstance(command, ca.SearchResponse):
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
                                queues[queue].append(cid)
                                # Cache this to save time on future searches.
                                # (Entries expire after
                                # STALE_SEARCH_EXPIRATION.)
                                search_results[name] = (address, now)
                    # Send the search results to the Contexts that asked for
                    # them. This is probably more general than is has to be but
                    # I'm playing it safe for now.
                    for queue, cids in queues.items():
                        queue.put((address, cids))
                    self.command_cond.notify_all()

    def _retry_unanswered_searches(self):
        while True:
            t = time.monotonic()
            requests = (ca.SearchRequest(name, search_id, 13)
                        for search_id, (name, _) in
                        self.unanswered_searches.items())
            for batch in batch_requests(requests, SEARCH_MAX_DATAGRAM_BYTES):
                self.send(ca.EPICS_CA1_PORT, ca.VersionRequest(0, 13), *batch)
            time.sleep(max(0, RETRY_SEARCHES_PERIOD - (time.monotonic() - t)))

    def __del__(self):
        try:
            self.disconnect()
        except AttributeError:
            pass


class Context:
    "Wraps a Broadcaster, and cache of VirtualCircuits."
    def __init__(self, broadcaster, *, log_level='ERROR'):
        self.log_level = log_level
        self.broadcaster = broadcaster
        self.search_condition = threading.Condition()
        self.pv_state_lock = threading.RLock()
        self.circuit_managers = {}  # keyed on (address, priority)
        self.pvs = weakref.WeakValueDictionary()
        self.pvs_by_name_and_priority = weakref.WeakValueDictionary()
        self.selector = None
        self.broadcaster.add_listener(self)
        self._search_results_queue = queue.Queue()
        threading.Thread(target=self._process_search_results_loop,
                         daemon=True).start()
        self.selector = SelectorThread()
        self.selector.start()

    def get_pvs(self, *names, priority=0):
        """
        Return a list of PV objects.

        These objects may not be connected at first. Channel creation occurs on
        a background thread.
        """
        all_pvs = []
        search_pvs = []
        search_names = []
        for name in names:
            key = (name, priority)
            try:
                # Maybe the user has asked for a PV that we already made.
                pv = self.pvs_by_name_and_priority[key]
            except KeyError:
                pv = PV(name, priority, self)
                self.pvs_by_name_and_priority[key] = pv
                search_pvs.append(pv)
                search_names.append(name)
            all_pvs.append(pv)

        # Ask the Broadcaster to search for every PV for which we do not
        # already have an instance. It might already have a cached search
        # result, but that is the concern of broadcaster.search.
        with self.pv_state_lock:
            cids = self.broadcaster.search(self._search_results_queue,
                                           search_names)
            for cid, pv in zip(cids, search_pvs):
                self.pvs[cid] = pv
        return all_pvs

    def reconnect(self, cids):
        search_pvs = []
        search_names = []
        # We will reuse the same PV object but use a new cid.
        with self.pv_state_lock:
            for cid in cids:
                pv = self.pvs.pop(cid)
                pv.circuit_manager = None
                pv.channel = None
                search_pvs.append(pv)
                search_names.append(pv.name)
                # If there is a cached search result for this name, expire it.
                self.broadcaster.search_results.pop(pv.name, None)

            cids = self.broadcaster.search(self._search_results_queue,
                                           search_names)
            for cid, pv in zip(cids, search_pvs):
                self.pvs[cid] = pv

    def _process_search_results_loop(self):
        # Receive (address, (cid1, cid2, cid3, ...)). The sending side of this
        # queue is held by SharedBroadcaster.command_loop.
        while True:
            address, cids = self._search_results_queue.get()
            with self.pv_state_lock:
                # TODO Grouping by priority would be safer, but as implemented
                # currently it is safe to assume they all have the same
                # priority because get_pvs only takes one priority for the
                # whole batch.
                priority = self.pvs[cids[0]].priority

                # Get (make if necessary) a VirtualCircuitManager. This is
                # where TCP socket creation happens.
                vc_manager = self.get_circuit_manager(address, priority)
                circuit = vc_manager.circuit

                # Assign each PV a VirtualCircuitManager for managing a socket
                # and tracking circuit state, as well as a ClientChannel for
                # tracking channel state.
                channels = collections.deque()
                for cid in cids:
                    pv = self.pvs[cid]
                    pv.circuit_manager = vc_manager
                    chan = ca.ClientChannel(pv.name, circuit, cid=cid)
                    vc_manager.channels[cid] = chan
                    pv.channel = chan
                    channels.append(chan)

            # Notify PVs that they now have a circuit_manager. This will
            # un-block a wait() in the PV.wait_for_search() method.
            cond = self.search_condition
            with cond:
                cond.notify_all()

            # Initiate channel creation with the server.
            vc_manager.send(*(chan.create() for chan in channels))

    def get_circuit_manager(self, address, priority):
        """
        Return a VirtualCircuitManager for this address, priority. (It manages
        a caproto.VirtualCircuit and a TCP socket.)

        Make a new one if necessary.
        """
        vc_manager = self.circuit_managers.get((address, priority), None)
        if vc_manager is None:
            circuit = ca.VirtualCircuit(
                our_role=ca.CLIENT,
                address=address,
                priority=priority)
            vc_manager = VirtualCircuitManager(self, circuit, self.selector)
            vc_manager.circuit.log.setLevel(self.log_level)
            self.circuit_managers[(address, priority)] = vc_manager
        return vc_manager

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
                 '__weakref__')

    def __init__(self, context, circuit, selector, timeout=TIMEOUT):
        self.context = context
        self.circuit = circuit  # a caproto.VirtualCircuit
        self.channels = {}  # map cid to Channel
        self.ioids = {}  # map ioid to Channel
        self.subscriptions = {}  # map subscriptionid to Subscription
        self.new_command_cond = threading.Condition()
        self.socket = None
        self.selector = selector
        self.disconnected = False

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

    def send(self, *commands):
        with self.new_command_cond:
            # turn the crank on the caproto
            buffers_to_send = self.circuit.send(*commands)
            # send bytes over the wire

            gen = ca.incremental_buffer_list_slice(*buffers_to_send)
            # prime the generator
            gen.send(None)

            while buffers_to_send:
                try:
                    sent = self.socket.sendmsg(buffers_to_send)
                except BlockingIOError:
                    continue
                try:
                    buffers_to_send = gen.send(sent)
                except StopIteration:
                    # finished sending
                    break

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
                self.disconnect()
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

            self.new_command_cond.notify_all()

    def disconnect(self, *, wait=True, timeout=2.0):
        with self.new_command_cond:
            # Ensure that this method is idempotent.
            if self.disconnected:
                return
            self.disconnected = True
            # Update circuit state. This will be reflected on all PVs, which
            # continue to hold a reference to this disconnected circuit.
            circuit = self.circuit.disconnect()
            # Remove VirtualCircuitManager from Context.
            # This will cause all future calls to Context.get_circuit_manager()
            # to create a fresh VirtualCiruit and VirtualCircuitManager.
            key = (self.circuit.address, self.circuit.priority)
            self.context.circuit_managers.pop(key, None)

        # Kick off attempt to reconnect all PVs via fresh circuit(s).
        self.context.reconnect(collections.deque(self.channels))

        # Clean up the socket.
        sock = self.socket
        if sock is not None:
            self.selector.remove_socket(sock)
            try:
                sock.shutdown(socket.SHUT_WR)
                sock.close()
            except OSError:
                pass

    def __del__(self):
        try:
            self.disconnect()
        except AttributeError:
            pass


class PV:
    """Wraps a VirtualCircuit and a caproto.ClientChannel."""
    __slots__ = ('name', 'priority', 'context', 'circuit_manager', 'channel',
                 'last_reading', '_read_notify_callback',
                 'command_bundle_queue', '_write_notify_callback',
                 '_pc_callbacks', '__weakref__')
    def __init__(self, name, priority, context):
        """
        These must be instantiated by a Context, never directly.
        """
        self.name = name
        self.priority = priority
        self.context = context
        self.circuit_manager = None
        self.channel = None
        self.last_reading = None
        self._read_notify_callback = None  # func to call on ReadNotifyResponse
        self._write_notify_callback = None  # func to call on WriteNotifyResponse
        self._pc_callbacks = {}

    def __repr__(self):
        if self.circuit_manager is None:
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
        if self.circuit_manager is None:
            self.wait_for_search()
        cond = self.circuit_manager.new_command_cond
        with cond:
            if self.connected:
                return
            done = cond.wait_for(lambda: self.connected, timeout)
        if not done:
            raise TimeoutError("Server at {} did not respond to attempt "
                               "to create channel named {!r} within {}-second "
                               "timeout."
                               "".format(self.circuit_manager.address,
                                         self.name,
                                         timeout))

    def disconnect(self, *, wait=True, timeout=2):
        "Disconnect this Channel."
        with self.circuit_manager.new_command_cond:
            if self.connected:
                try:
                    self.circuit_manager.send(self.channel.disconnect())
                except OSError:
                    # the socket is dead-dead, return
                    return
            else:
                return
        if wait:
            is_closed = lambda: self.channel.states[ca.CLIENT] is ca.CLOSED
            cond = self.circuit_manager.new_command_cond
            with cond:
                done = cond.wait_for(is_closed, timeout)
            if not done:
                raise TimeoutError("Server at {} did not respond to attempt "
                                   "to close channel named {} within {}-second"
                                   " timeout."
                                   "".format(self.circuit_manager.address,
                                             self.name,
                                             timeout))

    def read(self, *args, timeout=2, **kwargs):
        """Request a fresh reading, wait for it, return it and stash it.

        The most recent reading is always available in the ``last_reading``
        attribute.
        """
        # need this lock because the socket thread could be trying to
        # update this channel due to an incoming message
        with self.circuit_manager.new_command_cond:
            command = self.channel.read(*args, **kwargs)
        # Stash the ioid to match the response to the request.
        ioid = command.ioid
        self.circuit_manager.ioids[ioid] = self
        # do not need lock here, happens in send
        self.circuit_manager.send(command)
        has_reading = lambda: ioid not in self.circuit_manager.ioids
        cond = self.circuit_manager.new_command_cond
        with cond:
            done = cond.wait_for(has_reading, timeout)
        if not done:
            raise TimeoutError("Server at {} did not respond to attempt "
                               "to read channel named {} within {}-second "
                               "timeout."
                               "".format(self.circuit_manager.circuit.address,
                                         self.name, timeout))
        return self.last_reading

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
        has_reading = lambda: ioid not in self.circuit_manager.ioids
        cond = self.circuit_manager.new_command_cond
        with cond:
            done = cond.wait_for(has_reading, timeout)
        if not done:
            raise TimeoutError("Server at {} did not respond to attempt "
                               "to write to channel named {} within {}-second "
                               "timeout."
                               "".format(self.circuit_manager.address,
                                         self.name, timeout))
        return self.last_reading

    def subscribe(self, *args, **kwargs):
        "Start a new subscription and spawn an async task to receive readings."
        command = self.channel.subscribe(*args, **kwargs)
        # Stash the subscriptionid to match the response to the request.
        sub = Subscription(self, command)
        self.circuit_manager.subscriptions[command.subscriptionid] = sub
        self.circuit_manager.send(command)
        # TODO verify it worked before returning?
        return sub

    def unsubscribe(self, subscriptionid, *args, **kwargs):
        "Cancel a subscription and await confirmation from the server."
        self.circuit_manager.send(self.channel.unsubscribe(subscriptionid))
        # TODO verify it worked before returning?


class Subscription:
    def __init__(self, pv, command):
        self.pv = pv
        self.command = command
        self.callbacks = weakref.WeakSet()

    def add_callback(self, func):
        self.callbacks.add(func)

    def process(self, command):
        for callback in self.callbacks:
            try:
                callback(command)
            except Exception as ex:
                print(ex)

    def unsubscribe(self):
        self.pv.unsubscribe(self.command.subscriptionid)
