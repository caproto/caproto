import logging
import typing
from collections import defaultdict, deque
from typing import Dict, Tuple

import caproto as ca
import caproto.pva as pva
from caproto import (CaprotoNetworkError, CaprotoRuntimeError,
                     RemoteProtocolError, get_environment_variables)

from .._data import DataWithBitSet
from .._dataclass import pva_dataclass
from .._messages import Message, Subcommand

# If a Read[Notify]Request or EventAddRequest is received, wait for up to this
# long for the currently-processing Write[Notify]Request to finish.
WRITE_LOCK_TIMEOUT = 0.001


class DisconnectedCircuit(Exception):
    ...


class LoopExit(Exception):
    ...


@pva_dataclass
class ServerStatus:
    running: bool = True
    caproto_version: str = str(ca.__version__)


class VirtualCircuit:
    context: 'Context'
    connected: bool
    circuit: pva.ServerVirtualCircuit
    log: logging.Logger
    client: object  # socket or similar (TODO socket interface)
    client_hostname: str
    client_username: str
    subscriptions: defaultdict
    most_recent_updates: Dict
    _tags: Dict[str, str]

    def __init__(self,
                 circuit: pva.ServerVirtualCircuit,
                 client,
                 context: 'Context'
                 ):
        self.connected = True
        self.circuit = circuit  # a caproto.pva.ServerVirtualCircuit
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
        self._tags = {
            'their_address': self.circuit.address,
            'our_address': self.circuit.our_address,
            'direction': '<<<---',
            'role': repr(self.circuit.our_role),
        }
        self.authorization_info = {}
        # Subclasses are expected to define:
        # self.QueueFull = ...
        # self.message_queue = ...
        # self.new_message_condition = ...
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

    async def send(self, *messages):
        """
        Process a message and tranport it over the TCP socket for this circuit.
        """
        if self.connected:
            buffers_to_send = self.circuit.send(*messages, extra=self._tags)
            # send bytes over the wire using some caproto utilities
            async with self._raw_lock:
                await ca.async_send_all(buffers_to_send, self.client.sendmsg)

    async def recv(self):
        """
        Receive bytes over TCP and append them to this circuit's buffer.
        """
        try:
            bytes_received = await self.client.recv(4096)
        except (ConnectionResetError, ConnectionAbortedError):
            bytes_received = []

        for message, bytes_consumed in self.circuit.recv(bytes_received):
            try:
                await self.message_queue.put(message)
            except self.QueueFull:
                # This client is fast and we are not keeping up. Better to kill
                # the circuit (and let the client try again) than to let the
                # whole server be OOM-ed.
                self.log.warning(
                    "Circuit %r has a large backlog of received messages, "
                    "evidently cannot keep up with a fast client. Disconnecting"
                    " circuit to avoid letting consume all available memory.",
                    self
                )
                await self._on_disconnect()
                raise DisconnectedCircuit()

        if not bytes_received:
            await self._on_disconnect()
            raise DisconnectedCircuit()

    def _get_ids_from_message(self, message: Message) -> Tuple[int, int]:
        """Returns (client_chid, server_chid) given a message"""
        server_chid = getattr(message, 'server_chid', None)
        client_chid = getattr(message, 'server_chid', None)
        if server_chid is not None and client_chid is None:
            client_chid = self.circuit.channels_sid[server_chid].client_chid
        elif client_chid is not None and server_chid is None:
            server_chid = self.circuit.channels[client_chid].server_chid

        return client_chid, server_chid

    async def _message_queue_iteration(self, message):
        """
        Coroutine which evaluates one item from the circuit message queue.

        1. Dispatch and validate through caproto.pva.VirtualCircuit.process_message
            - Upon server failure, respond to the client with
              caproto.ErrorResponse
        2. Update Channel state if applicable.
        """
        try:
            self.circuit.process_command(message)
        except ca.RemoteProtocolError:
            client_chid, server_chid = self._get_ids_from_message(message)

            if client_chid is not None:
                try:
                    raise
                    # await self.send(ca.ServerDisconnResponse(client_chid=client_chid))
                except Exception:
                    self.log.exception(
                        "Client broke the protocol in a recoverable way, but "
                        "channel disconnection of client_chid=%d server_chid=%d failed.", client_chid,
                        server_chid)
                    raise LoopExit('Recoverable protocol error failure')
                else:
                    self.log.exception(
                        "Client broke the protocol in a recoverable way. "
                        "Disconnected channel client_chid=%d server_chid=%d but keeping the "
                        "circuit alive.", client_chid, server_chid)

                await self._wake_new_message()
                return
            else:
                self.log.exception(
                    "Client broke the protocol in an unrecoverable way.")
                # TODO: Kill the circuit.
                raise LoopExit('Unrecoverable protocol error')
        except Exception:
            self.log.exception('Circuit message queue evaluation failed')
            # Internal error - ignore for now
            return

        if message is ca.DISCONNECTED:
            raise DisconnectedCircuit

        try:
            response = await self._process_message(message)
            return response
        except Exception:
            if not self.connected:
                if not isinstance(message, pva.ChannelDestroyRequest):
                    self.log.exception(
                        'Server error after client disconnection: %s', message
                    )
                raise LoopExit('Server error after client disconnection')

            client_chid, server_chid = self._get_ids_from_message(message)
            chan, _ = self._get_db_entry_from_message(message)
            self.log.exception(
                'Server failed to process message (%r): %s',
                chan.name, message)

            # if client_chid is not None:
            #     error_message = f'Python exception: {type(ex).__name__} {ex}'
            #     return [
            #         pva.todo(message, client_chid, status=ca.CAStatus.ECA_INTERNAL,
            #                              error_message=error_message)
            #             ]
            raise

    async def _newly_connected(self):
        """
        Just connected to the client.  Send an authentication request.
        """
        byte_order = self.circuit.set_byte_order(
            pva.EndianSetting.use_server_byte_order
        )

        req = self.circuit.validate_connection(
            buffer_size=32767,
            registry_size=32767,
            authorization_options=self.context.authentication_methods
        )
        await self.send(byte_order, req)

    async def message_queue_loop(self):
        """Reference implementation of the message queue loop

        Note
        ----
        Assumes self.message_bundle_queue functions as an async queue with
        awaitable .get()

        Async library implementations can (and should) reimplement this.
        Coroutine which evaluates one item from the circuit message queue.
        """

        # The write_event will be cleared when a write is scheduled and set
        # when one completes.
        maybe_awaitable = self.write_event.set()
        # The curio backend makes this an awaitable thing.
        if maybe_awaitable is not None:
            await maybe_awaitable

        await self._newly_connected()

        try:
            while True:
                message = await self.message_queue.get()
                response = await self._message_queue_iteration(message)
                if response is not None:
                    await self.send(*response)
                await self._wake_new_message()
        except DisconnectedCircuit:
            await self._on_disconnect()
            self.circuit.disconnect()
            await self.context.circuit_disconnected(self)
        except self.TaskCancelled:
            ...
        except LoopExit:
            ...

    def _get_db_entry_from_message(self, message):
        """Return a database entry from message, determined by the server id"""
        chan = self.circuit._get_channel_from_command(message)
        db_entry = self.context[chan.name]
        return chan, db_entry

    async def _process_message(self, message):
        '''Process a message from a client, and return the server response'''
        tags = self._tags
        if message is ca.DISCONNECTED:
            raise DisconnectedCircuit()

        to_send = []
        if isinstance(message, pva.ConnectionValidationResponse):
            message = typing.cast(pva.ConnectionValidationResponse, message)
            message: pva.ConnectionValidationResponse  # TODO: cast insufficient?
            self.authorization_info.update(**{
                'method': message.auth_nz,
                'data': message.data.data,
            })
            to_send = [
                self.circuit.validated_connection()
            ]
        elif isinstance(message, pva.SearchRequest):
            ...
            # TODO message.channels -> searchreply
        elif isinstance(message, pva.CreateChannelRequest):
            to_send = []
            for info in message.channels:
                try:
                    cid = info['id']
                    name = info['channel_name']
                    chan = self.circuit.channels[cid]
                except KeyError:
                    self.log.debug('Client requested invalid channel name: %s',
                                   name)
                    to_send.append(
                        chan.create(
                            sid=0,
                            status=pva.Status.create_error(
                                message=f'Invalid channel name {name}',
                            ),
                        )
                    )
                else:
                    to_send.append(
                        chan.create(sid=self.circuit.new_channel_id())
                    )

        elif isinstance(message, pva.ChannelFieldInfoRequest):
            chan, db_entry = self._get_db_entry_from_message(message)
            ioid_info = self.circuit._ioids[message.ioid]
            chan = ioid_info['channel']

            data = await db_entry.auth_read_interface(
                authorization=self.authorization_info)

            data = await db_entry.read(None)
            to_send = [
                chan.read_interface(ioid=message.ioid, interface=data)
            ]
        elif isinstance(message, pva.ChannelGetRequest):
            message = typing.cast(pva.ChannelGetRequest, message)
            message: pva.ChannelGetRequest
            chan, db_entry = self._get_db_entry_from_message(message)
            ioid_info = self.circuit._ioids[message.ioid]
            chan = ioid_info['channel']
            subcommand = message.subcommand
            if subcommand == Subcommand.INIT:
                try:
                    data = await db_entry.auth_read(
                        message.pv_request, authorization=self.authorization_info)
                except Exception as ex:
                    to_send = [
                        chan.read(
                            ioid=message.ioid, interface=None,
                            status=pva.Status.create_error(
                                message=f'{ex.__class__.__name__}: {ex}',
                            ),
                        )
                    ]
                else:
                    ioid_info['pv_request'] = message.pv_request
                    ioid_info['interface'] = data

                    response = chan.read(ioid=message.ioid, interface=data)
                    ioid_info['init_request'] = message
                    # Reusable response message for this ioid:
                    ioid_info['response'] = response
                    to_send = [response]
            elif (subcommand == Subcommand.GET or subcommand == Subcommand.DEFAULT):
                # NOTE: we'll only get here if INIT succeeded, where the
                # authentication happens

                # TODO: check if interface has changed
                response = ioid_info['response']

                data = await db_entry.read(
                    ioid_info['init_request'].pv_request
                )

                to_send = [
                    response.as_subcommand(
                        message.subcommand,
                        pv_data=DataWithBitSet(
                            data=data,
                            bitset=pva.BitSet({0}),  # TODO
                        ),
                    )
                ]
        elif isinstance(message, pva.ChannelPutRequest):
            message = typing.cast(pva.ChannelPutRequest, message)
            message: pva.ChannelPutRequest

            chan, db_entry = self._get_db_entry_from_message(message)
            ioid_info = self.circuit._ioids[message.ioid]
            chan = ioid_info['channel']
            subcommand = message.subcommand

            if subcommand == Subcommand.INIT:
                try:
                    interface = await db_entry.auth_write(
                        message.pv_request,
                        authorization=self.authorization_info
                    )
                except Exception as ex:
                    interface = None
                    status = pva.Status.create_error(
                        message=f'{ex.__class__.__name__}: {ex}',
                    )
                else:
                    status = pva.Status.create_success()

                ioid_info['pv_request'] = message.pv_request
                ioid_info['interface'] = interface

                to_send = [
                    chan.write_init(
                        ioid=message.ioid,
                        interface=interface,
                        status=status
                    )
                ]
            elif subcommand == Subcommand.GET:
                # This is pretty much a pva-get, using the pvrequest from the
                # put_init
                try:
                    pv_request = ioid_info['pv_request']
                    read_data = await db_entry.read(pv_request)
                    data = DataWithBitSet(
                        data=read_data,
                        bitset=pva.BitSet({0}),  # TODO
                    )
                except Exception as ex:
                    status = pva.Status.create_error(
                        message=f'{ex.__class__.__name__}: {ex}',
                    )
                    data = None
                else:
                    status = pva.Status.create_success()

                to_send = [chan.write_get(ioid=message.ioid, data=data,
                                          status=status)]
            elif subcommand == Subcommand.DEFAULT:
                # TODO: check if interface has changed
                data = message.put_data
                # ioid_info['interface']
                try:
                    await db_entry.write(data)
                except Exception as ex:
                    status = pva.Status.create_error(
                        message=f'{ex.__class__.__name__}: {ex}',
                    )
                else:
                    status = pva.Status.create_success()
                to_send = [chan.write(ioid=message.ioid, status=status)]
                to_send[0].subcommand = Subcommand(subcommand)
        elif isinstance(message, pva.ChannelRequestDestroy):
            # Handled by the circuit
            ...
        elif isinstance(message, pva.ChannelRequestCancel):
            # TODO: this layer should handle canceling the operation
            ...
        elif isinstance(message, pva.EchoRequest):
            to_send = [pva.EchoResponse()]

        if isinstance(message, pva.Message):
            self.log.debug("%r", message, extra=tags)

        return to_send


class Context(typing.Mapping):
    def __init__(self, pvdb, interfaces=None):
        if interfaces is None:
            interfaces = ca.get_server_address_list(
                protocol=ca.Protocol.PVAccess)
        self.interfaces = interfaces
        self.udp_socks = {}  # map each interface to a UDP socket for searches
        self.beacon_socks = {}  # map each interface to a UDP socket for beacons
        self.pvdb = pvdb
        self.log = logging.getLogger('caproto.pva.ctx')

        self.addresses = []
        self.circuits = set()
        self.authentication_methods = {'anonymous', 'ca'}

        self.subscriptions = defaultdict(deque)
        # Map Subscription to {'before': last_update, 'after': last_update}
        # to silence duplicates for Subscriptions that use edge-triggered sync
        # Channel Filter.
        self.last_sync_edge_update = defaultdict(lambda: defaultdict(dict))
        self.last_dead_band = {}
        self.environ = get_environment_variables()

        # pva_server_port: the default tcp/udp port from the environment
        self.pva_server_port = self.environ['EPICS_PVAS_SERVER_PORT']
        self.pva_broadcast_port = self.environ['EPICS_PVAS_BROADCAST_PORT']
        self.broadcaster = pva.Broadcaster(
            our_role=ca.SERVER,
            broadcast_port=self.pva_broadcast_port,
            server_port=None,  # TBD
        )
        # the specific tcp port in use by this server
        self.port = None

        self.log.debug(
            'EPICS_PVA_SERVER_PORT set to %d. This is the UDP port to be used'
            'for searches.'
        )

    async def _core_broadcaster_loop(self, udp_sock):
        while True:
            try:
                bytes_received, address = await udp_sock.recvfrom(4096 * 16)
            except ConnectionResetError:
                self.log.exception('UDP server connection reset')
                await self.async_layer.library.sleep(0.1)
                continue
            if bytes_received:
                await self._broadcaster_recv_datagram(bytes_received, address)

    async def _broadcaster_recv_datagram(self, bytes_received, address):
        try:
            messages = self.broadcaster.recv(bytes_received, address)
        except RemoteProtocolError:
            self.log.exception('Broadcaster received bad packet')
        else:
            await self.message_bundle_queue.put((address, messages))

    async def broadcaster_queue_loop(self):
        '''
        Reference broadcaster queue loop implementation

        Note
        ----
        Assumes self.message_bundle_queue functions as an async queue with
        awaitable .get()

        Async library implementations can (and should) reimplement this.
        '''
        while True:
            try:
                addr, messages = await self.message_bundle_queue.get()
                await self._broadcaster_queue_iteration(addr, messages)
            except self.TaskCancelled:
                break
            except Exception as ex:
                self.log.exception('Broadcaster message queue evaluation failed',
                                   exc_info=ex)
                continue

    def __iter__(self):
        # Implemented to support __getitem__ below
        return iter(self.pvdb)

    def __getitem__(self, pvname):
        return self.pvdb[pvname]

    def __len__(self):
        return len(self.pvdb)

    async def _broadcaster_queue_iteration(self, addr, messages):
        self.broadcaster.process_commands(messages)
        found_pv_to_cid = {}
        for message in messages:
            if isinstance(message, pva.SearchRequest):
                for channel in message.channels:
                    try:
                        channel['id']
                        name = channel['channel_name']
                        self[name]
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
        return

        self.log.debug('Will send beacons to %r',
                       [f'{h}:{p}' for h, p in self.beacon_socks.keys()])
        MIN_BEACON_PERIOD = 0.02  # "RECOMMENDED" by the CA spec
        BEACON_BACKOFF = 2  # "RECOMMENDED" by the CA spec
        max_beacon_period = self.environ['EPICS_PVAS_BEACON_PERIOD']
        beacon_period = MIN_BEACON_PERIOD
        server_status = ServerStatus()
        while True:
            beacon = self.broadcaster.beacon(server_status=server_status)
            bytes_to_send = self.broadcaster.send(beacon)
            for address, (interface, sock) in self.beacon_socks.items():
                try:
                    await sock.send(bytes_to_send)
                except IOError:
                    self.log.exception(
                        "Failed to send beacon to %r. Try setting "
                        "EPICS_PVAS_AUTO_BEACON_ADDR_LIST=no and "
                        "EPICS_PVAS_BEACON_ADDR_LIST=<addresses>.", address
                    )

            if beacon_period < max_beacon_period:
                beacon_period = min(max_beacon_period,
                                    beacon_period * BEACON_BACKOFF)
            await self.async_layer.library.sleep(beacon_period)

    async def circuit_disconnected(self, circuit):
        '''Notification from circuit that its connection has closed'''
        self.circuits.discard(circuit)

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
        cavc = pva.ServerVirtualCircuit(ca.SERVER, addr, None)
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
