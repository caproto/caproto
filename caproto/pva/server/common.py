import copy
import logging
import sys
import time
import typing
import weakref
from collections import ChainMap, defaultdict, deque, namedtuple
from collections.abc import Iterable

import caproto as ca
import caproto.pva as pva
from caproto import (CaprotoKeyError, CaprotoNetworkError, CaprotoRuntimeError,
                     ChannelType, RemoteProtocolError,
                     get_environment_variables)

# If a Read[Notify]Request or EventAddRequest is received, wait for up to this
# long for the currently-processing Write[Notify]Request to finish.
WRITE_LOCK_TIMEOUT = 0.001


class DisconnectedCircuit(Exception):
    ...


class LoopExit(Exception):
    ...


class VirtualCircuit:
    def __init__(self, circuit, client, context):
        self.connected = True
        self.circuit = circuit  # a caproto.VirtualCircuit
        self.circuit.our_address = client.getsockname()
        self.log = circuit.log
        self.client = client
        self.context = context
        self.client_hostname = None
        self.client_username = None
        # The structure of self.subscriptions is:
        # {SubscriptionSpec: deque([Subscription, Subscription, ...]), ...}
        self.subscriptions = defaultdict(deque)
        self.most_recent_updates = {}
        # This dict is passed to the loggers.
        self._tags = {'their_address': self.circuit.address,
                      'our_address': self.circuit.our_address,
                      'direction': '<<<---',
                      'role': repr(self.circuit.our_role)}
        # Subclasses are expected to define:
        # self.QueueFull = ...
        # self.command_queue = ...
        # self.new_command_condition = ...
        # self.subscription_queue = ...
        # self.get_from_sub_queue = ...
        # self.events_on = ...
        # self.write_event = ...

    async def _on_disconnect(self):
        """Executed when disconnection detected"""
        if not self.connected:
            return

        self.connected = False
        # queue = self.context.subscription_queue
        # for sub_spec, subs in self.subscriptions.items():
        #     for sub in subs:
        #         self.context.subscriptions[sub_spec].remove(sub)
        #     # Does anything else on the Context still care about this sub_spec?
        #     # If not unsubscribe the Context's queue from the db_entry.
        #     if not self.context.subscriptions[sub_spec]:
        #         await sub_spec.db_entry.unsubscribe(queue, sub_spec)
        # self.subscriptions.clear()

    async def send(self, *commands):
        """
        Process a command and tranport it over the TCP socket for this circuit.
        """
        if self.connected:
            buffers_to_send = self.circuit.send(*commands)
            # send bytes over the wire using some caproto utilities
            async with self._raw_lock:
                await ca.async_send_all(buffers_to_send, self.client.sendmsg)

    async def recv(self):
        """
        Receive bytes over TCP and cache them in this circuit's buffer.
        """
        try:
            bytes_received = await self.client.recv(4096)
        except (ConnectionResetError, ConnectionAbortedError):
            bytes_received = []

        commands, _ = self.circuit.recv(bytes_received)
        for c in commands:
            try:
                await self.command_queue.put(c)
            except self.QueueFull:
                # This client is fast and we are not keeping up. Better to kill
                # the circuit (and let the client try again) than to let the
                # whole server be OOM-ed.
                self.log.warning(f"Circuit {self!r} has a large backlog of "
                                 f"received commands, evidently cannot keep "
                                 f"with a fast client. Disconnecting circuit "
                                 f"to avoid letting consume all available "
                                 f"memory.")
                await self._on_disconnect()
                raise DisconnectedCircuit()
        if not bytes_received:
            await self._on_disconnect()
            raise DisconnectedCircuit()

    def _get_ids_from_command(self, command):
        """Returns (cid, sid) given a command"""
        cid, sid = None, None
        if hasattr(command, 'sid'):
            sid = command.sid
            cid = self.circuit.channels_sid[sid].cid
        elif hasattr(command, 'cid'):
            cid = command.cid
            sid = self.circuit.channels[cid].sid

        return cid, sid

    async def _command_queue_iteration(self, command):
        """
        Coroutine which evaluates one item from the circuit command queue.

        1. Dispatch and validate through caproto.VirtualCircuit.process_command
            - Upon server failure, respond to the client with
              caproto.ErrorResponse
        2. Update Channel state if applicable.
        """
        try:
            self.circuit.process_command(command)
        except ca.RemoteProtocolError:
            cid, sid = self._get_ids_from_command(command)

            if cid is not None:
                try:
                    await self.send(ca.ServerDisconnResponse(cid=cid))
                except Exception:
                    self.log.exception(
                        "Client broke the protocol in a recoverable way, but "
                        "channel disconnection of cid=%d sid=%d failed.", cid,
                        sid)
                    raise LoopExit('Recoverable protocol error failure')
                else:
                    self.log.exception(
                        "Client broke the protocol in a recoverable way. "
                        "Disconnected channel cid=%d sid=%d but keeping the "
                        "circuit alive.", cid, sid)

                await self._wake_new_command()
                return
            else:
                self.log.exception(
                    "Client broke the protocol in an unrecoverable way.")
                # TODO: Kill the circuit.
                raise LoopExit('Unrecoverable protocol error')
        except Exception:
            self.log.exception('Circuit command queue evaluation failed')
            # Internal error - ignore for now
            return

        if command is ca.DISCONNECTED:
            raise DisconnectedCircuit

        try:
            response = await self._process_command(command)
            return response
        except Exception as ex:
            if not self.connected:
                if not isinstance(command, ca.ClearChannelRequest):
                    self.log.error('Server error after client '
                                   'disconnection: %s', command)
                raise LoopExit('Server error after client disconnection')

            cid, sid = self._get_ids_from_command(command)
            chan, _ = self._get_db_entry_from_command(command)
            self.log.exception(
                'Server failed to process command (%r): %s',
                chan.name, command)

            if cid is not None:
                error_message = f'Python exception: {type(ex).__name__} {ex}'
                return [ca.ErrorResponse(command, cid,
                                         status=ca.CAStatus.ECA_INTERNAL,
                                         error_message=error_message)
                        ]

    async def command_queue_loop(self):
        """Reference implementation of the command queue loop

        Note
        ----
        Assumes self.command_bundle_queue functions as an async queue with
        awaitable .get()

        Async library implementations can (and should) reimplement this.
        Coroutine which evaluates one item from the circuit command queue.
        """

        # The write_event will be cleared when a write is scheduled and set
        # when one completes.
        maybe_awaitable = self.write_event.set()
        # The curio backend makes this an awaitable thing.
        if maybe_awaitable is not None:
            await maybe_awaitable

        try:
            while True:
                command = await self.command_queue.get()
                response = await self._command_queue_iteration(command)
                if response is not None:
                    await self.send(*response)
                await self._wake_new_command()
        except DisconnectedCircuit:
            await self._on_disconnect()
            self.circuit.disconnect()
            await self.context.circuit_disconnected(self)
        except self.TaskCancelled:
            ...
        except LoopExit:
            ...

    def _get_db_entry_from_command(self, command):
        """Return a database entry from command, determined by the server id"""
        cid, sid = self._get_ids_from_command(command)
        chan = self.circuit.channels_sid[sid]
        db_entry = self.context[chan.name]
        return chan, db_entry

    async def _process_command(self, command):
        '''Process a command from a client, and return the server response'''
        tags = self._tags
        if command is ca.DISCONNECTED:
            raise DisconnectedCircuit()
        elif isinstance(command, ca.VersionRequest):
            to_send = [ca.VersionResponse(ca.DEFAULT_PROTOCOL_VERSION)]
        elif isinstance(command, ca.SearchRequest):
            pv_name = command.name
            try:
                self.context[pv_name]
            except KeyError:
                if command.reply == ca.DO_REPLY:
                    to_send = [
                        ca.NotFoundResponse(
                            version=ca.DEFAULT_PROTOCOL_VERSION,
                            cid=command.cid)
                    ]
                else:
                    to_send = []
            else:
                to_send = [
                    ca.SearchResponse(self.context.port, None, command.cid,
                                      ca.DEFAULT_PROTOCOL_VERSION)
                ]
        elif isinstance(command, ca.CreateChanRequest):
            pvname = command.name
            try:
                db_entry = self.context[pvname]
            except KeyError:
                self.log.debug('Client requested invalid channel name: %s',
                               pvname)
                to_send = [ca.CreateChFailResponse(cid=command.cid)]
            else:

                access = db_entry.check_access(self.client_hostname,
                                               self.client_username)

                modifiers = ca.parse_record_field(pvname).modifiers
                data_type = db_entry.data_type
                data_count = db_entry.max_length
                if ca.RecordModifiers.long_string in (modifiers or {}):
                    if data_type in (ChannelType.STRING, ):
                        data_type = ChannelType.CHAR
                        data_count = db_entry.long_string_max_length

                to_send = [ca.AccessRightsResponse(cid=command.cid,
                                                   access_rights=access),
                           ca.CreateChanResponse(data_type=data_type,
                                                 data_count=data_count,
                                                 cid=command.cid,
                                                 sid=self.circuit.new_channel_id()),
                           ]
        elif isinstance(command, ca.HostNameRequest):
            self.client_hostname = command.name
            to_send = []
        elif isinstance(command, ca.ClientNameRequest):
            self.client_username = command.name
            to_send = []
        elif isinstance(command, (ca.ReadNotifyRequest, ca.ReadRequest)):
            chan, db_entry = self._get_db_entry_from_command(command)
            try:
                data_type = command.data_type
            except ValueError:
                raise ca.RemoteProtocolError('Invalid data type')

            # If we are in the middle of processing a Write[Notify]Request,
            # allow a bit of time for that to (maybe) finish. Some requests
            # may take a long time, so give up rather quickly to avoid
            # introducing too much latency.
            await self.write_event.wait(timeout=WRITE_LOCK_TIMEOUT)

            read_data_type = data_type
            metadata, data = await db_entry.auth_read(
                self.client_hostname, self.client_username,
                read_data_type, user_address=self.circuit.address,
            )

            old_version = self.circuit.protocol_version < 13
            if command.data_count > 0 or old_version:
                data = data[:command.data_count]

            # If the timestamp feature is active swap the timestamp.
            # Information must copied because not all clients will have the
            # timestamp filter
            if chan.channel_filter.ts and command.data_type in ca.time_types:
                time_type = type(metadata)
                now = ca.TimeStamp.from_unix_timestamp(time.time())
                metadata = time_type(**ChainMap({'stamp': now},
                                                dict((field, getattr(metadata, field))
                                                     for field, _ in time_type._fields_)))
            notify = isinstance(command, ca.ReadNotifyRequest)
            data_count = db_entry.calculate_length(data)
            to_send = [chan.read(data=data, data_type=command.data_type,
                                 data_count=data_count, status=1,
                                 ioid=command.ioid, metadata=metadata,
                                 notify=notify)
                       ]
        elif isinstance(command, (ca.WriteRequest, ca.WriteNotifyRequest)):
            chan, db_entry = self._get_db_entry_from_command(command)
            client_waiting = isinstance(command, ca.WriteNotifyRequest)

            async def handle_write():
                '''Wait for an asynchronous caput to finish'''
                try:
                    write_status = await db_entry.auth_write(
                        self.client_hostname, self.client_username,
                        command.data, command.data_type, command.metadata,
                        user_address=self.circuit.address)
                except Exception as ex:
                    self.log.exception('Invalid write request by %s (%s): %r',
                                       self.client_username,
                                       self.client_hostname, command)
                    cid = self.circuit.channels_sid[command.sid].cid
                    response_command = ca.ErrorResponse(
                        command, cid,
                        status=ca.CAStatus.ECA_PUTFAIL,
                        error_message=('Python exception: {} {}'
                                       ''.format(type(ex).__name__, ex))
                    )
                    await self.send(response_command)
                else:
                    if client_waiting:
                        if write_status is None:
                            # errors can be passed back by exceptions, and
                            # returning none for write_status can just be
                            # considered laziness
                            write_status = True

                        response_command = chan.write(
                            ioid=command.ioid,
                            status=write_status,
                            data_count=db_entry.length
                        )
                        await self.send(response_command)
                finally:
                    maybe_awaitable = self.write_event.set()
                    # The curio backend makes this an awaitable thing.
                    if maybe_awaitable is not None:
                        await maybe_awaitable

            self.write_event.clear()
            await self._start_write_task(handle_write)
            to_send = []
        elif isinstance(command, ca.ClearChannelRequest):
            chan, db_entry = self._get_db_entry_from_command(command)
            await self._cull_subscriptions(
                db_entry,
                lambda sub: sub.channel == command.sid)
            to_send = [chan.clear()]
        elif isinstance(command, ca.EchoRequest):
            to_send = [ca.EchoResponse()]
        if isinstance(command, ca.Message):
            tags['bytesize'] = len(command)
            self.log.debug("%r", command, extra=tags)
        return to_send


class Context:
    def __init__(self, pvdb, interfaces=None):
        if interfaces is None:
            interfaces = ca.get_server_address_list(
                protocol=ca.Protocol.PVAccess)
        self.interfaces = interfaces
        self.udp_socks = {}  # map each interface to a UDP socket for searches
        self.beacon_socks = {}  # map each interface to a UDP socket for beacons
        self.pvdb = pvdb
        self.log = logging.getLogger('caproto.ctx')

        self.addresses = []
        self.circuits = set()

        self.subscriptions = defaultdict(deque)
        # Map Subscription to {'before': last_update, 'after': last_update}
        # to silence duplicates for Subscriptions that use edge-triggered sync
        # Channel Filter.
        self.last_sync_edge_update = defaultdict(lambda: defaultdict(dict))
        self.last_dead_band = {}
        self.beacon_count = 0

        self.environ = get_environment_variables()

        # pva_server_port: the default tcp/udp port from the environment
        self.pva_server_port = self.environ['EPICS_PVAS_SERVER_PORT']
        self.pva_broadcast_port = self.environ['EPICS_PVAS_BROADCAST_PORT']
        self.broadcaster = pva.Broadcaster(
            our_role=ca.SERVER,
            broadcast_port=self.pva_broadcast_port,
            server_port=self.pva_server_port
        )
        # the specific tcp port in use by this server
        self.port = None

        self.log.debug(
            'EPICS_PVA_SERVER_PORT set to %d. This is the UDP port to be used'
            'for searches.'
        )

    @property
    def pvdb_with_fields(self):
        'Dynamically generated each time - use sparingly'
        # TODO is static generation sufficient?
        pvdb = {}
        for name, instance in self.pvdb.items():
            pvdb[name] = instance
            if hasattr(instance, 'fields'):
                # Note that we support PvpropertyData along with ChannelData
                # instances here (which may not have fields)
                for field_name, field in instance.fields.items():
                    pvdb[f'{name}.{field_name}'] = field
        return pvdb

    async def _core_broadcaster_loop(self, udp_sock):
        while True:
            try:
                bytes_received, address = await udp_sock.recvfrom(4096 * 16)
                print('loop', bytes_received, address)
            except ConnectionResetError:
                self.log.exception('UDP server connection reset')
                await self.async_layer.library.sleep(0.1)
                continue
            if bytes_received:
                await self._broadcaster_recv_datagram(bytes_received, address)

    async def _broadcaster_recv_datagram(self, bytes_received, address):
        try:
            commands = self.broadcaster.recv(bytes_received, address)
        except RemoteProtocolError:
            self.log.exception('Broadcaster received bad packet')
        else:
            await self.command_bundle_queue.put((address, commands))

    async def broadcaster_queue_loop(self):
        '''Reference broadcaster queue loop implementation

        Note
        ----
        Assumes self.command_bundle_queue functions as an async queue with
        awaitable .get()

        Async library implementations can (and should) reimplement this.
        '''
        while True:
            try:
                addr, commands = await self.command_bundle_queue.get()
                await self._broadcaster_queue_iteration(addr, commands)
            except self.TaskCancelled:
                break
            except Exception as ex:
                self.log.exception('Broadcaster command queue evaluation failed',
                                   exc_info=ex)
                continue

    def __iter__(self):
        # Implemented to support __getitem__ below
        return iter(self.pvdb)

    def __getitem__(self, pvname):
        return self.pvdb[pvname]

    async def _broadcaster_queue_iteration(self, addr, commands):
        self.broadcaster.process_commands(commands)
        found_pv_to_cid = {}
        for command in commands:
            if isinstance(command, pva.SearchRequest):
                for channel in command.channels:
                    try:
                        name = channel['channel_name']
                        id_ = channel['id']
                        known_pv = self[name] is not None
                    except KeyError:
                        ...
                    else:
                        found_pv_to_cid[name] = channel['id']

        if found_pv_to_cid:
            search_replies = [
                self.broadcaster.search_response(
                    pv_to_cid=found_pv_to_cid,
                )
            ]
            bytes_to_send = self.broadcaster.send(*search_replies)
            # TODO: why send this back on all sockets?
            for udp_sock in self.udp_socks.values():
                try:
                    await udp_sock.sendto(bytes_to_send, addr)
                except OSError as exc:
                    host, port = addr
                    raise CaprotoNetworkError(f"Failed to send to {host}:{port}") from exc

    async def broadcast_beacon_loop(self):
        self.log.debug('Will send beacons to %r',
                       [f'{h}:{p}' for h, p in self.beacon_socks.keys()])
        MIN_BEACON_PERIOD = 0.02  # "RECOMMENDED" by the CA spec
        BEACON_BACKOFF = 2  # "RECOMMENDED" by the CA spec
        max_beacon_period = self.environ['EPICS_PVAS_BEACON_PERIOD']
        beacon_period = MIN_BEACON_PERIOD
        server_status = None
        while True:
            for address, (interface, sock) in self.beacon_socks.items():
                try:
                    ...
                    # beacon = self.broadcaster.beacon(
                    #     flags=0, server_status=server_status)
                    # bytes_to_send = self.broadcaster.send(beacon)
                    # await sock.send(bytes_to_send)
                except IOError:
                    self.log.exception(
                        "Failed to send beacon to %r. Try setting "
                        "EPICS_PVAS_AUTO_BEACON_ADDR_LIST=no and "
                        "EPICS_PVAS_BEACON_ADDR_LIST=<addresses>.", address)
            self.beacon_count += 1
            if beacon_period < max_beacon_period:
                beacon_period = min(max_beacon_period,
                                    beacon_period * BEACON_BACKOFF)
            await self.async_layer.library.sleep(beacon_period)

    async def circuit_disconnected(self, circuit):
        '''Notification from circuit that its connection has closed'''
        self.circuits.discard(circuit)

    @property
    def startup_methods(self):
        'Notify all ChannelData instances of the server startup'
        return {name: instance.server_startup
                for name, instance in self.pvdb_with_fields.items()
                if hasattr(instance, 'server_startup') and
                instance.server_startup is not None}

    @property
    def shutdown_methods(self):
        'Notify all ChannelData instances of the server shutdown'
        return {name: instance.server_shutdown
                for name, instance in self.pvdb.items()
                if hasattr(instance, 'server_shutdown') and
                instance.server_shutdown is not None}

    async def _bind_tcp_sockets_with_consistent_port_number(self, make_socket):
        # Find a random port number that is free on all self.interfaces,
        # and get a bound TCP socket with that port number on each
        # interface. The argument `make_socket` is expected to be a coroutine
        # with the signature `make_socket(interface, port)` that does whatever
        # library-specific incantation is necessary to return a bound socket or
        # raise an IOError.
        tcp_sockets = {}  # maps interface to bound socket
        stashed_ex = None
        for port in ca.random_ports(100, try_first=self.pva_server_port):
            try:
                for interface in self.interfaces:
                    s = await make_socket(interface, port)
                    tcp_sockets[interface] = s
            except IOError as ex:
                stashed_ex = ex
                for s in tcp_sockets.values():
                    s.close()
                tcp_sockets.clear()
            else:
                break
        else:
            raise CaprotoRuntimeError('No available ports and/or bind failed') from stashed_ex
        return port, tcp_sockets

    async def tcp_handler(self, client, addr):
        '''Handler for each new TCP client to the server'''
        cavc = ca.VirtualCircuit(ca.SERVER, addr, None)
        circuit = self.CircuitClass(cavc, client, self)
        self.circuits.add(circuit)
        self.log.info('Connected to new client at %s:%d (total: %d).', *addr,
                      len(self.circuits))

        await circuit.run()

        try:
            while True:
                try:
                    await circuit.recv()
                except DisconnectedCircuit:
                    await self.circuit_disconnected(circuit)
                    break
        except KeyboardInterrupt as ex:
            self.log.debug('TCP handler received KeyboardInterrupt')
            raise self.ServerExit() from ex
        self.log.info('Disconnected from client at %s:%d (total: %d).', *addr,
                      len(self.circuits))

    def stop(self):
        ...
