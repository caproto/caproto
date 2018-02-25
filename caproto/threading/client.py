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

from collections import Iterable

import caproto as ca


class ThreadingClientException(Exception):
    ...


class DisconnectedError(ThreadingClientException):
    ...


AUTOMONITOR_MAXLENGTH = 65536
STALE_SEARCH_THRESHOLD = 10.0
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

        if not self.socket_to_id:
            self.stop()

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
    def __init__(self, *, log_level='ERROR'):
        self.log_level = log_level
        self.udp_sock = None
        self._search_lock = threading.RLock()

        self.search_results = {}  # map name to (time, address)
        self.unanswered_searches = {}  # map search id (cid) to name

        self.listeners = weakref.WeakSet()

        self.broadcaster = ca.Broadcaster(our_role=ca.CLIENT)
        self.broadcaster.log.setLevel(self.log_level)
        self.command_bundle_queue = queue.Queue()
        self.command_cond = threading.Condition()

        self.selector = SelectorThread()
        self.command_thread = threading.Thread(target=self.command_loop,
                                               daemon=True)
        self.command_thread.start()

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
                    if not self.registered and is_register:
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

    def register(self, *, wait=True, timeout=0.5, attempts=4):
        "Register this client with the CA Repeater."
        if self.registered:
            return

        if self.udp_sock is None:
            self.__create_sock()

        with self.command_cond:
            command = self.broadcaster.register('127.0.0.1')
            self.send(ca.EPICS_CA2_PORT, command)

        if wait:
            for attempts in range(attempts):
                with self.command_cond:
                    done = self.command_cond.wait_for(lambda: self.registered,
                                                      timeout)
                    self.send(ca.EPICS_CA2_PORT, command)
                if done:
                    break
            else:
                raise TimeoutError('Failed to register with the broadcaster')

    def search(self, name, *, wait=True, timeout=2):
        "Generate, process, and the transport a search request."
        if not self.registered:
            self.register()
        with self._search_lock:
            if name in self.search_results:
                address, timestamp = self.search_results[name]
                if (time.time() - timestamp) < STALE_SEARCH_THRESHOLD:
                    return address
                else:
                    # Discard any old search result for this name.
                    self.search_results.pop(name, None)

            ver_command, search_command = self.broadcaster.search(name)
            # Stash the search ID for recognizes the SearchResponse later.
            self.unanswered_searches[search_command.cid] = name
            self.send(ca.EPICS_CA1_PORT, ver_command, search_command)
        # Wait for the SearchResponse.
        if wait:
            with self.command_cond:
                result_found = lambda: name in self.search_results
                done = self.command_cond.wait_for(result_found, timeout)
            if not done:
                raise TimeoutError("No search result received for {}"
                                   "".format(name))
            address, timestamp = self.search_results[name]
            return address

    def received(self, bytes_recv, address):
        "Receive and process and next command broadcasted over UDP."
        commands = self.broadcaster.recv(bytes_recv, address)
        self.command_bundle_queue.put(commands)
        return 0

    def command_loop(self):
        while True:
            commands = self.command_bundle_queue.get()
            try:
                self.broadcaster.process_commands(commands)
            except ca.CaprotoError as ex:
                logger.warning('Broadcaster command error', exc_info=ex)
                continue

            with self.command_cond:
                for command in commands:
                    if isinstance(command, ca.VersionResponse):
                        # Check that the server version is one we can talk to.
                        if command.version <= 11:
                            logger.warning('Version response <= 11: %r',
                                           command)
                    if isinstance(command, ca.SearchResponse):
                        with self._search_lock:
                            name = self.unanswered_searches.get(command.cid,
                                                                None)
                            if name is not None:
                                self.search_results[name] = (
                                    ca.extract_address(command), time.time())
                                self.unanswered_searches.pop(command.cid)
                            else:
                                # This is a redundant response, which the spec
                                # tell us we must ignore.
                                pass
                    self.command_cond.notify_all()

    @property
    def registered(self):
        return self.broadcaster.registered

    def __del__(self):
        try:
            self.disconnect()
        except AttributeError:
            pass


class Context:
    "Wraps a Broadcaster, and cache of VirtualCircuits."
    __slots__ = ('broadcaster', 'circuits', 'log_level', 'selector',
                 '__weakref__')

    def __init__(self, broadcaster, *, log_level='ERROR'):
        self.log_level = log_level
        self.broadcaster = broadcaster
        self.circuits = {}  # map (address, priority) to VirtualCircuit
        self.selector = None

    def register(self):
        "Register this client with the CA Repeater."
        self.broadcaster.add_listener(self)
        self.broadcaster.register()

    def search(self, name):
        "Generate, process, and the transport a search request."
        return self.broadcaster.search(name)

    def get_circuit(self, address, priority):
        """
        Return a VirtualCircuit with this address, priority.

        Make a new one if necessary.
        """
        if self.selector is None:
            self.selector = SelectorThread()

        self.selector.start()

        circuit = self.circuits.get((address, priority), None)
        if circuit is None or not circuit.connected:
            circuit = VirtualCircuit(ca.VirtualCircuit(our_role=ca.CLIENT,
                                                       address=address,
                                                       priority=priority,
                                                       ),
                                     selector=self.selector)
            circuit.circuit.log.setLevel(self.log_level)
            self.circuits[(address, priority)] = circuit
        return circuit

    def create_channel(self, name, priority=0, *, wait=True, timeout=2):
        """
        Create a new channel.
        """
        address = self.broadcaster.search(name)

        circuit = self.get_circuit(address, priority)
        cid = circuit.circuit.new_channel_id()
        cachan = ca.ClientChannel(name, circuit.circuit, cid=cid)
        chan = circuit.channels[cid] = Channel(circuit, cachan)

        with circuit.new_command_cond:
            if circuit.circuit.states[ca.SERVER] is ca.IDLE:
                circuit.create_connection()
                circuit.send(cachan.version(),
                             cachan.host_name(),
                             cachan.client_name())
        cond = circuit.new_command_cond
        with cond:
            done = cond.wait_for(lambda: circuit.connected, timeout)
            if not done:
                raise TimeoutError("Circuit with server at {} did not "
                                   "connected within {}-second timeout."
                                   "".format(address, timeout))

        # do not need to lock here, take care of in send method
        circuit.send(cachan.create())

        if wait:
            chan.wait_for_connection()

        return chan

    def disconnect(self, *, wait=True, timeout=2):
        try:
            # disconnect any circuits we have
            for circ in list(self.circuits.values()):
                if circ.connected:
                    circ.disconnect(wait=wait, timeout=timeout)
        finally:
            # clear any state about circuits and search results
            self.circuits.clear()

            # disconnect the underlying state machine
            self.broadcaster.remove_listener(self)

    def __del__(self):
        try:
            self.disconnect(wait=False)
        except (KeyError, AttributeError):
            pass
            # clean-up on deletion is best effort...
            # TODO tacaswell


class VirtualCircuit:
    __slots__ = ('circuit', 'channels', 'ioids', 'subscriptionids',
                 'new_command_cond', 'socket', 'selector',
                 '__weakref__')

    def __init__(self, circuit, selector):
        self.circuit = circuit  # a caproto.VirtualCircuit
        self.channels = {}  # map cid to Channel
        self.ioids = {}  # map ioid to Channel
        self.subscriptionids = {}  # map subscriptionid to Channel
        self.new_command_cond = threading.Condition()
        self.socket = None

        self.selector = selector

    @property
    def connected(self):
        with self.new_command_cond:
            return self.circuit.states[ca.CLIENT] is ca.CONNECTED

    def create_connection(self):
        # TODO check removed
        # if self.sock_thread is not None:
        #     raise RuntimeError('trying to reuse a VC')
        self.socket = socket.create_connection(self.circuit.address)
        self.selector.add_socket(self.socket, self)

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
                # if we are here something else has triggered the
                # disconnect.
                pass
            elif isinstance(command, ca.ReadNotifyResponse):
                chan = self.ioids.pop(command.ioid)
                chan.process_read_notify(command)
            elif isinstance(command, ca.WriteNotifyResponse):
                chan = self.ioids.pop(command.ioid)
                chan.process_write_notify(command)
            elif isinstance(command, ca.EventAddResponse):
                chan = self.subscriptionids[command.subscriptionid]
                chan.process_subscription(command)
            elif isinstance(command, ca.EventCancelResponse):
                self.subscriptionids.pop(command.subscriptionid)

            self.new_command_cond.notify_all()

    def disconnect(self, *, wait=True, timeout=2.0):
        for cid, ch in list(self.channels.items()):
            ch.disconnect(wait=wait, timeout=timeout)
            self.channels.pop(cid)

        with self.new_command_cond:
            self.circuit.disconnect()
        sock = self.socket
        if sock is not None:
            self.selector.remove_socket(sock)
            try:
                sock.shutdown(socket.SHUT_WR)
                sock.close()
            except OSError:
                pass
            self.socket = None

        self.channels.clear()
        self.ioids.clear()

    def __del__(self):
        try:
            self.disconnect()
        except AttributeError:
            pass


class Channel:
    """Wraps a VirtualCircuit and a caproto.ClientChannel."""
    __slots__ = ('circuit', 'channel', 'last_reading', 'monitoring_tasks',
                 '_callback', '_read_notify_callback', 'command_bundle_queue',
                 '_write_notify_callback', '_pc_callbacks')

    def __init__(self, circuit, channel):
        self.circuit = circuit  # a VirtualCircuit
        self.channel = channel  # a caproto.ClientChannel
        self.last_reading = None
        self.monitoring_tasks = {}  # maps subscriptionid to curio.Task
        self._callback = None  # user func to call when subscriptions are run
        self._read_notify_callback = None  # func to call on ReadNotifyResponse
        self._write_notify_callback = None  # func to call on WriteNotifyResponse
        self._pc_callbacks = {}

    @property
    def connected(self):
        with self.circuit.new_command_cond:
            return self.channel.states[ca.CLIENT] is ca.CONNECTED

    def register_user_callback(self, func):
        """
        Func to be called when a subscription receives a new EventAdd command.

        This function will be called by a Task in the main thread. If ``func``
        needs to do CPU-intensive or I/O-related work, it should execute that
        work in a separate thread of process.
        """
        if inspect.ismethod(func):
            self._callback = weakref.WeakMethod(func, self._callback_cleared)
        else:
            self._callback = weakref.ref(func, self._callback_cleared)

    def _callback_cleared(self, ref):
        self._callback = None

    def process_subscription(self, event_add_command):
        if self._callback is None:
            return

        user_callback = self._callback()
        if user_callback is not None:
            try:
                user_callback(event_add_command)
            except Exception as ex:
                print(ex)

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

    def wait_for_connection(self, *, timeout=2):
        """Wait for this Channel to be connected, ready to use.

        The method ``Context.create_channel`` spawns an asynchronous task to
        initialize the connection in the fist place. This method waits for it
        to complete.
        """
        if self.connected:
            return
        cond = self.circuit.new_command_cond
        with cond:
            done = cond.wait_for(lambda: self.connected, timeout)
        if not done:
            raise TimeoutError("Server at {} did not respond to attempt "
                               "to create channel named {} within {}-second "
                               "timeout."
                               "".format(self.circuit.address,
                                         self.channel.name,
                                         timeout))

    def disconnect(self, *, wait=True, timeout=2):
        "Disconnect this Channel."
        with self.circuit.new_command_cond:
            if self.connected:
                try:
                    self.circuit.send(self.channel.disconnect())
                except OSError:
                    # the socket is dead-dead, return
                    return
            else:
                return
        if wait:
            is_closed = lambda: self.channel.states[ca.CLIENT] is ca.CLOSED
            cond = self.circuit.new_command_cond
            with cond:
                done = cond.wait_for(is_closed, timeout)
            if not done:
                raise TimeoutError("Server at {} did not respond to attempt "
                                   "to close channel named {} within {}-second"
                                   " timeout."
                                   "".format(self.circuit.address, self.name,
                                             timeout))

    def read(self, *args, timeout=2, **kwargs):
        """Request a fresh reading, wait for it, return it and stash it.

        The most recent reading is always available in the ``last_reading``
        attribute.
        """
        # need this lock because the socket thread could be trying to
        # update this channel due to an incoming message
        with self.circuit.new_command_cond:
            command = self.channel.read(*args, **kwargs)
        # Stash the ioid to match the response to the request.
        ioid = command.ioid
        self.circuit.ioids[ioid] = self
        # do not need lock here, happens in send
        self.circuit.send(command)
        has_reading = lambda: ioid not in self.circuit.ioids
        cond = self.circuit.new_command_cond
        with cond:
            done = cond.wait_for(has_reading, timeout)
        if not done:
            raise TimeoutError("Server at {} did not respond to attempt "
                               "to read channel named {} within {}-second "
                               "timeout."
                               "".format(self.circuit.address,
                                         self.name, timeout))
        return self.last_reading

    def write(self, *args, wait=True, cb=None, timeout=2, **kwargs):
        "Write a new value and await confirmation from the server."
        with self.circuit.new_command_cond:
            command = self.channel.write(*args, **kwargs)
        # Stash the ioid to match the response to the request.
        ioid = command.ioid
        self.circuit.ioids[ioid] = self
        if cb is not None:
            self._pc_callbacks[ioid] = cb
        # do not need to lock this, locking happens in circuit command
        self.circuit.send(command)
        has_reading = lambda: ioid not in self.circuit.ioids
        cond = self.circuit.new_command_cond
        with cond:
            done = cond.wait_for(has_reading, timeout)
        if not done:
            raise TimeoutError("Server at {} did not respond to attempt "
                               "to write to channel named {} within {}-second "
                               "timeout."
                               "".format(self.circuit.address,
                                         self.name, timeout))
        return self.last_reading

    def subscribe(self, *args, **kwargs):
        "Start a new subscription and spawn an async task to receive readings."
        command = self.channel.subscribe(*args, **kwargs)
        # Stash the subscriptionid to match the response to the request.
        self.circuit.subscriptionids[command.subscriptionid] = self
        self.circuit.send(command)
        # TODO verify it worked before returning?
        return command.subscriptionid

    def unsubscribe(self, subscriptionid, *args, **kwargs):
        "Cancel a subscription and await confirmation from the server."
        self.circuit.send(self.channel.unsubscribe(subscriptionid))
        # TODO verify it worked before returning?


def ensure_connection(func):
    # TODO get timeout default from func signature
    @functools.wraps(func)
    def inner(self, *args, **kwargs):
        self.wait_for_connection(timeout=kwargs.get('timeout', None))
        return func(self, *args, **kwargs)
    return inner


class PVContext(Context):
    def __init__(self, broadcaster=None, *, log_level='ERROR'):
        if broadcaster is None:
            broadcaster = SharedBroadcaster()
        super().__init__(broadcaster=broadcaster, log_level=log_level)

        if not self.broadcaster.registered:
            self.register()

    def get_pv(self, pvname, *args, **kwargs):
        # TODO add PV cache to this class
        return PV(pvname, *args, context=self, **kwargs)


class PV:
    """Epics Process Variable

    A PV encapsulates an Epics Process Variable.

    The primary interface methods for a pv are to get() and put() is value::

      >>> p = PV(pv_name)  # create a pv object given a pv name
      >>> p.get()          # get pv value
      >>> p.put(val)       # set pv to specified value.

    Additional important attributes include::

      >>> p.pvname         # name of pv
      >>> p.value          # pv value (can be set or get)
      >>> p.char_value     # string representation of pv value
      >>> p.count          # number of elements in array pvs
      >>> p.type           # EPICS data type: 'string','double','enum','long',..
"""

    _fmtsca = "<PV '%(pvname)s', count=%(count)i, type=%(typefull)s, access=%(access)s>"
    _fmtarr = "<PV '%(pvname)s', count=%(count)i/%(nelm)i, type=%(typefull)s, access=%(access)s>"
    _fields = ('pvname',  'value',  'char_value',  'status',  'ftype',  'chid',
               'host', 'count', 'access', 'write_access', 'read_access',
               'severity', 'timestamp', 'posixseconds', 'nanoseconds',
               'precision', 'units', 'enum_strs',
               'upper_disp_limit', 'lower_disp_limit', 'upper_alarm_limit',
               'lower_alarm_limit', 'lower_warning_limit',
               'upper_warning_limit', 'upper_ctrl_limit', 'lower_ctrl_limit')
    _default_context = None

    def __init__(self, pvname, callback=None, form='time',
                 verbose=False, auto_monitor=False, count=None,
                 connection_callback=None,
                 connection_timeout=None, *, context=None):
        # TODO
        # - connection_callback
        # - connection_timeout
        self.chid = None

        if context is None:
            context = self._default_context
        if context is None:
            raise RuntimeError("must have a valid context")
        self._context = context
        self.pvname = pvname.strip()
        self.form = form.lower()
        self.verbose = verbose
        self.auto_monitor = auto_monitor
        self.ftype = None
        self.connection_timeout = connection_timeout
        self.dflt_count = count
        self._subid = None

        if self.connection_timeout is None:
            self.connection_timeout = 1

        self._args = {}.fromkeys(self._fields)
        self._args['pvname'] = self.pvname
        self._args['count'] = count
        self._args['nelm'] = -1
        self._args['type'] = 'unknown'
        self._args['typefull'] = 'unknown'
        self._args['access'] = 'unknown'
        self.connection_callbacks = []

        if connection_callback is not None:
            self.connection_callbacks = [connection_callback]

        self.callbacks = {}
        self._conn_started = False

        if isinstance(callback, (tuple, list)):
            for i, thiscb in enumerate(callback):
                if hasattr(thiscb, '__call__'):
                    self.callbacks[i] = (thiscb, {})

        elif hasattr(callback, '__call__'):
            self.callbacks[0] = (callback, {})

        # DIFF
        # not handling lazy connecting, pyepics is
        self._context.search(self.pvname)
        self.wait_for_connection(form=form, count=count)

    @property
    def connected(self):
        return self.chid is not None and self.chid.connected

    def force_connect(self, pvname=None, chid=None, conn=True, **kws):
        # not quite sure what this is for in pyepics, probably should
        # be an arias for reconnect?
        ...

    def wait_for_connection(self, timeout=None, *, form=None, count=None):
        """wait for a connection that started with connect() to finish
        Returns
        -------
        connected : bool
            If the PV is connected when this method returns
        """
        # TODO
        # - check if there is a form or count on the object we should respect
        # - do something with the timeout value
        if self.connected:
            return

        self.chid = self._context.create_channel(self.pvname)

        self._args['type'] = ca.ChannelType(self.chid.channel.native_data_type)
        self._args['typefull'] = ca.promote_type(self.type,
                                                 use_time=(form == 'time'),
                                                 use_ctrl=(form != 'time'))
        self._args['nelm'] = self.chid.channel.native_data_count
        self._args['count'] = self.chid.channel.native_data_count

        # yeah... enum.Flag would be nice here
        self._args['write_access'] = (self.chid.channel.access_rights & 2) == 2
        self._args['read_access'] = (self.chid.channel.access_rights & 1) == 1

        access_strs = ('no access', 'read-only', 'write-only', 'read/write')
        self._args['access'] = access_strs[self.chid.channel.access_rights]

        self.chid.register_user_callback(self.__on_changes)

        if self.auto_monitor is None:
            mcount = count if count is not None else self._args['count']
            self.auto_monitor = mcount < AUTOMONITOR_MAXLENGTH

        if self.auto_monitor:
            self._subid = self.chid.subscribe(data_type=self.typefull,
                                              data_count=count)

        self._cb_count = iter(itertools.count())

        # todo move to async connect logic
        for cb in self.connection_callbacks:
            cb(pvname=self.pvname, conn=True, pv=self)

    def connect(self, timeout=None):
        """check that a PV is connected, forcing a connection if needed

        Returns
        -------
        connected : bool
            If the PV is connected when this method returns
        """
        self.wait_for_connection(timeout=timeout)

    def reconnect(self):
        "try to reconnect PV"
        self.disconnect()
        return self.wait_for_connection()

    @ensure_connection
    def get(self, *, count=None, as_string=False, as_numpy=True,
            timeout=None, with_ctrlvars=False, use_monitor=True):
        """returns current value of PV.

        Parameters
        ----------
        count : int, optional
             explicitly limit count for array data
        as_string : bool, optional
            flag(True/False) to get a string representation
            of the value.
        as_numpy : bool, optional
            use numpy array as the return type for array data.
        timeout : float, optional
            maximum time to wait for value to be received.
            (default = 0.5 + log10(count) seconds)
        use_monitor : bool, optional
            use value from latest monitor callback (True, default)
            or to make an explicit CA call for the value.

        Returns
        -------
        val : Object
            The value, the type is dependent on the underlying PV
        """
        # TODO
        # - timeout
        # - with_ctrlvars

        if count is None:
            count = self.dflt_count
        dt = self.typefull
        if not as_string and self.typefull in ca.char_types:
            re_map = {ca.ChannelType.CHAR: ca.ChannelType.INT,
                      ca.ChannelType.CTRL_CHAR: ca.ChannelType.CTRL_INT,
                      ca.ChannelType.TIME_CHAR: ca.ChannelType.TIME_INT,
                      ca.ChannelType.STS_CHAR: ca.ChannelType.STS_INT}
            dt = re_map[self.typefull]
            # TODO if you want char arrays not as_string
            # force no-monitor rather than
            use_monitor = False

        # trigger going out to got data from network
        if ((not use_monitor) or
            (self._subid is None) or
            (self._args['value'] is None) or
            (count is not None and
             count > len(self._args['value']))):
            command = self.chid.read(data_type=dt,
                                     data_count=count)
            self.__ingest_read_response_command(command)

        info = self._args

        if (as_string and (self.typefull in ca.char_types) or
                self.typefull in ca.string_types):
            return info['char_value']
        elif as_string and self.typefull in ca.enum_types:
            enum_strs = self.enum_strs
            ret = []
            for r in info['value']:
                try:
                    ret.append(enum_strs[r])
                except IndexError:
                    ret.append('')
            if len(ret) == 1:
                ret, = ret
            return ret

        elif not as_numpy:
            return list(info['value'])
        return info['value']

    def __ingest_read_response_command(self, command):
        info = self._parse_dbr_metadata(command.metadata)
        info['value'] = command.data

        ret = info['value']
        if self.typefull in ca.char_types:
            ret = ret.tobytes().partition(b'\x00')[0].decode(STR_ENC)
            info['char_value'] = ret
        elif self.typefull in ca.string_types:
            ret = [v.decode(STR_ENC).strip() for v in ret]
            if len(ret) == 1:
                ret = ret[0]
            info['char_value'] = ret

        self._args.update(**info)

    @ensure_connection
    def put(self, value, *, wait=False, timeout=30.0,
            use_complete=False, callback=None, callback_data=None):
        """set value for PV, optionally waiting until the processing is
        complete, and optionally specifying a callback function to be run
        when the processing is complete.
        """
        # TODO
        # - wait
        # - timeout
        # - put complete (use_complete, callback, callback_data)
        # API
        # consider returning futures instead of storing state on the PV object
        if callback_data is None:
            callback_data = ()
        if self._args['typefull'] in ca.enum_types:
            if isinstance(value, str):
                try:
                    value = self.enum_strs.index(value)
                except ValueError:
                    raise ValueError('{} is not in Enum ({}'.format(
                        value, self.enum_strs))

        if isinstance(value, str) or not isinstance(value, Iterable):
            value = (value, )

        if isinstance(value[0], str):
            value = tuple(v.encode(STR_ENC) for v in value)

        def run_callback(cmd):
            callback(*callback_data)
        cb = run_callback if callback is not None else None
        ret = self.value
        self.chid.write(value, wait=wait, cb=cb, timeout=timeout)
        return ret if wait else None

    @ensure_connection
    def get_ctrlvars(self, timeout=5, warn=True):
        "get control values for variable"
        dtype = ca.promote_type(self.type, use_ctrl=True)
        command = self.chid.read(data_type=dtype, timeout=timeout)
        info = self._parse_dbr_metadata(command.metadata)
        info['value'] = command.data
        self._args.update(**info)
        return info

    @ensure_connection
    def get_timevars(self, timeout=5, warn=True):
        "get time values for variable"
        dtype = ca.promote_type(self.type, use_time=True)
        command = self.chid.read(data_type=dtype, timeout=timeout)
        info = self._parse_dbr_metadata(command.metadata)
        info['value'] = command.data
        self._args.update(**info)

    def _parse_dbr_metadata(self, dbr_data):
        ret = {}

        arg_map = {'status': 'status',
                   'severity': 'severity',
                   'precision': 'precision',
                   'units': 'units',
                   'upper_disp_limit': 'upper_disp_limit',
                   'lower_disp_limit': 'lower_disp_limit',
                   'upper_alarm_limit': 'upper_alarm_limit',
                   'upper_warning_limit': 'upper_warning_limit',
                   'lower_warning_limit': 'lower_warning_limit',
                   'lower_alarm_limit': 'lower_alarm_limit',
                   'upper_ctrl_limit': 'upper_ctrl_limit',
                   'lower_ctrl_limit': 'lower_ctrl_limit',
                   'strs': 'enum_strs',
                   # 'secondsSinceEpoch': 'posixseconds',
                   # 'nanoSeconds': 'nanoseconds',
                   }

        for attr, arg in arg_map.items():
            if hasattr(dbr_data, attr):
                ret[arg] = getattr(dbr_data, attr)

        if ret.get('enum_strs', None):
            ret['enum_strs'] = tuple(k.value.decode(STR_ENC) for
                                     k in ret['enum_strs'] if k.value)

        if hasattr(dbr_data, 'nanoSeconds'):
            ret['posixseconds'] = dbr_data.secondsSinceEpoch
            ret['nanoseconds'] = dbr_data.nanoSeconds
            timestamp = ca.epics_timestamp_to_unix(dbr_data.secondsSinceEpoch,
                                                   dbr_data.nanoSeconds)
            ret['timestamp'] = timestamp

        if 'units' in ret:
            ret['units'] = ret['units'].decode(STR_ENC)

        return ret

    def __on_changes(self, command):
        """internal callback function: do not overwrite!!
        To have user-defined code run when the PV value changes,
        use add_callback()
        """
        self.__ingest_read_response_command(command)
        self.run_callbacks()

    def run_callbacks(self):
        """run all user-defined callbacks with the current data

        Normally, this is to be run automatically on event, but
        it is provided here as a separate function for testing
        purposes.
        """
        for index in sorted(list(self.callbacks.keys())):
            self.run_callback(index)

    def run_callback(self, index):
        """run a specific user-defined callback, specified by index,
        with the current data
        Note that callback functions are called with keyword/val
        arguments including:
             self._args  (all PV data available, keys = __fields)
             keyword args included in add_callback()
             keyword 'cb_info' = (index, self)
        where the 'cb_info' is provided as a hook so that a callback
        function  that fails may de-register itself (for example, if
        a GUI resource is no longer available).
        """
        try:
            fcn, kwargs = self.callbacks[index]
        except KeyError:
            return
        kwd = copy.copy(self._args)
        kwd.update(kwargs)
        kwd['cb_info'] = (index, self)
        if hasattr(fcn, '__call__'):
            fcn(**kwd)

    def add_callback(self, callback, *, index=None, run_now=False,
                     with_ctrlvars=True, **kw):
        """add a callback to a PV.  Optional keyword arguments
        set here will be preserved and passed on to the callback
        at runtime.

        Note that a PV may have multiple callbacks, so that each
        has a unique index (small integer) that is returned by
        add_callback.  This index is needed to remove a callback."""
        if not callable(callback):
            raise ValueError()
        if self._subid is None:
            self._subid = self.chid.subscribe(data_type=self.typefull,
                                              data_count=self.dflt_count)
        if index is not None:
            raise ValueError("why do this")
        index = next(self._cb_count)
        self.callbacks[index] = (callback, kw)

        if with_ctrlvars and self.connected:
            self.get_ctrlvars()
        if run_now:
            self.get(as_string=True)
            if self.connected:
                self.run_callback(index)
        return index

    def remove_callback(self, index):
        """remove a callback by index"""
        self.callbacks.pop(index, None)

    def clear_callbacks(self):
        "clear all callbacks"
        self.callbacks = {}

    def __getval(self):
        "get value"
        return self.get()

    def __setval(self, val):
        "put-value"
        return self.put(val)

    value = property(__getval, __setval, None, "value property")

    @property
    def char_value(self):
        "character string representation of value"
        return self._getarg('char_value')

    @property
    def status(self):
        "pv status"
        return self._getarg('status')

    @property
    def type(self):
        "pv type"
        return self._args['type']

    @property
    def typefull(self):
        "pv type"
        return self._args['typefull']

    @property
    def host(self):
        "pv host"
        return self.chid.channel.host_name().name.decode(STR_ENC)

    @property
    def count(self):
        """count (number of elements). For array data and later EPICS versions,
        this is equivalent to the .NORD field.  See also 'nelm' property"""
        if self._args['count'] is not None:
            return self._args['count']
        else:
            return self._getarg('count')

    @property
    def nelm(self):
        """native count (number of elements).
        For array data this will return the full array size (ie, the
        .NELM field).  See also 'count' property"""
        if self._getarg('count') == 1:
            return 1
        return self.chid.channel.native_data_count

    @property
    def read_access(self):
        "read access"
        return self._getarg('read_access')

    @property
    def write_access(self):
        "write access"
        return self._getarg('write_access')

    @property
    def access(self):
        "read/write access as string"
        return self._getarg('access')

    @property
    def severity(self):
        "pv severity"
        return self._getarg('severity')

    @property
    def timestamp(self):
        "timestamp of last pv action"
        return self._getarg('timestamp')

    @property
    def posixseconds(self):
        """integer seconds for timestamp of last pv action
        using POSIX time convention"""
        return self._getarg('posixseconds')

    @property
    def nanoseconds(self):
        "integer nanoseconds for timestamp of last pv action"
        return self._getarg('nanoseconds')

    @property
    def precision(self):
        "number of digits after decimal point"
        return self._getarg('precision')

    @property
    def units(self):
        "engineering units for pv"
        return self._getarg('units')

    @property
    def enum_strs(self):
        "list of enumeration strings"
        return self._getarg('enum_strs')

    @property
    def upper_disp_limit(self):
        "limit"
        return self._getarg('upper_disp_limit')

    @property
    def lower_disp_limit(self):
        "limit"
        return self._getarg('lower_disp_limit')

    @property
    def upper_alarm_limit(self):
        "limit"
        return self._getarg('upper_alarm_limit')

    @property
    def lower_alarm_limit(self):
        "limit"
        return self._getarg('lower_alarm_limit')

    @property
    def lower_warning_limit(self):
        "limit"
        return self._getarg('lower_warning_limit')

    @property
    def upper_warning_limit(self):
        "limit"
        return self._getarg('upper_warning_limit')

    @property
    def upper_ctrl_limit(self):
        "limit"
        return self._getarg('upper_ctrl_limit')

    @property
    def lower_ctrl_limit(self):
        "limit"
        return self._getarg('lower_ctrl_limit')

    @property
    def info(self):
        "info string"
        return self._getinfo()

    @property
    def put_complete(self):
        "returns True if a put-with-wait has completed"
        True

    def _getinfo(self):
        "get information paragraph"
        self.get_ctrlvars()
        out = []
        xtype = self._args['typefull']
        mod_map = {'enum': ca.enum_types,
                   'status': ca.status_types,
                   'time': ca.time_types,
                   'control': ca.control_types,
                   'native': ca.native_types}
        mod = next(k for k, v in mod_map.items() if xtype in v)
        nt_type = ca.native_type(xtype)
        fmt = '%i'

        if nt_type in (ca.ChannelType.FLOAT, ca.ChannelType.DOUBLE):
            fmt = '%g'
        elif nt_type in (ca.ChannelType.CHAR, ca.ChannelType.STRING):
            fmt = '%s'

        # self._set_charval(self._args['value'], call_ca=False)
        out.append("== %s  (%s) ==" % (self.pvname, ca.DBR_TYPES[xtype].__name__))
        if self.count == 1:
            val = self._args['value']
            out.append('   value      = %s' % fmt % val)
        else:
            ext = {True: '...', False: ''}[self.count > 10]
            elems = range(min(5, self.count))
            try:
                aval = [fmt % self._args['value'][i] for i in elems]
            except TypeError:
                aval = ('unknown',)
            out.append("   value      = array  [%s%s]" % (",".join(aval), ext))
        for nam in ('char_value', 'count', 'nelm', 'type', 'units',
                    'precision', 'host', 'access',
                    'status', 'severity', 'timestamp',
                    'posixseconds', 'nanoseconds',
                    'upper_ctrl_limit', 'lower_ctrl_limit',
                    'upper_disp_limit', 'lower_disp_limit',
                    'upper_alarm_limit', 'lower_alarm_limit',
                    'upper_warning_limit', 'lower_warning_limit'):
            if hasattr(self, nam):
                att = getattr(self, nam)
                if att is not None:
                    if nam == 'timestamp':
                        def fmt_time(tstamp=None):
                            "simple formatter for time values"
                            if tstamp is None:
                                tstamp = time.time()
                            tstamp, frac = divmod(tstamp, 1)
                            return "%s.%5.5i" % (time.strftime("%Y-%m-%d %H:%M:%S",
                                                               time.localtime(tstamp)),
                                                 round(1.e5*frac))

                        att = "%.3f (%s)" % (att, fmt_time(att))
                    elif nam == 'char_value':
                        att = "'%s'" % att
                    if len(nam) < 12:
                        out.append('   %.11s= %s' % (nam+' '*12, str(att)))
                    else:
                        out.append('   %.20s= %s' % (nam+' '*20, str(att)))
        if xtype == 'enum':  # list enum strings
            out.append('   enum strings: ')
            for index, nam in enumerate(self.enum_strs):
                out.append("       %i = %s " % (index, nam))

        if len(self.chid.channel.subscriptions) > 0:
            msg = 'PV is internally monitored'
            out.append('   %s, with %i user-defined callbacks:' %
                       (msg, len(self.callbacks)))
            if len(self.callbacks) > 0:
                for nam in sorted(self.callbacks.keys()):
                    cback = self.callbacks[nam][0]
                    out.append('      {!r}'.format(cback))
        else:
            out.append('   PV is NOT internally monitored')
        out.append('=============================')
        return '\n'.join(out)

    def _getarg(self, arg):
        "wrapper for property retrieval"
        if self._args['value'] is None:
            self.get()
        if self._args[arg] is None and self.connected:
            if arg in ('status', 'severity', 'timestamp',
                       'posixseconds', 'nanoseconds'):
                self.get_timevars(timeout=1, warn=False)
            else:
                self.get_ctrlvars(timeout=1, warn=False)
        return self._args.get(arg, None)

    def __repr__(self):
        "string representation"

        if self.connected:
            if self.count == 1:
                return self._fmtsca % self._args
            else:
                return self._fmtarr % self._args
        else:
            return "<PV '%s': not connected>" % self.pvname

    def __eq__(self, other):
        "test for equality"
        return False

    def disconnect(self):
        "disconnect PV"
        if self.connected:
            self.chid.disconnect()

    def __del__(self):
        if self.connected:
            self.chid.disconnect(wait=False)


_dflt_context = None


def get_pv(pvname, *args, **kwargs):
    global _dflt_context
    if _dflt_context is None:
        _dflt_context = PVContext()

    return _dflt_context.get_pv(pvname)


def caput(pvname, value, wait=False, timeout=60):
    """caput(pvname, value, wait=False, timeout=60)
    simple put to a pv's value.
       >>> caput('xx.VAL',3.0)

    to wait for pv to complete processing, use 'wait=True':
       >>> caput('xx.VAL',3.0,wait=True)
    """
    thispv = get_pv(pvname, connect=True)
    if thispv.connected:
        return thispv.put(value, wait=wait, timeout=timeout)


def caget(pvname, as_string=False, count=None, as_numpy=True,
          use_monitor=False, timeout=5.0):
    """caget(pvname, as_string=False)
    simple get of a pv's value..
       >>> x = caget('xx.VAL')

    to get the character string representation (formatted double,
    enum string, etc):
       >>> x = caget('xx.VAL', as_string=True)

    to get a truncated amount of data from an array, you can specify
    the count with
       >>> x = caget('MyArray.VAL', count=1000)
    """
    start_time = time.time()
    thispv = get_pv(pvname, timeout=timeout, connect=True)
    if thispv.connected:
        if as_string:
            thispv.get_ctrlvars()
        timeout -= (time.time() - start_time)
        val = thispv.get(count=count, timeout=timeout,
                         use_monitor=use_monitor,
                         as_string=as_string,
                         as_numpy=as_numpy)

        return val


def cainfo(pvname, print_out=True):
    """cainfo(pvname,print_out=True)

    return printable information about pv
       >>>cainfo('xx.VAL')

    will return a status report for the pv.

    If print_out=False, the status report will be printed,
    and not returned.
    """
    thispv = get_pv(pvname, connect=True)
    if thispv.connected:
        thispv.get()
        thispv.get_ctrlvars()
        if print_out:
            print(thispv.info)
        else:
            return thispv.info
