import collections
import dataclasses
import enum
import logging
import typing
from collections import defaultdict, deque
from typing import Dict, Optional, Tuple, Type

import caproto as ca
import caproto.pva as pva
from caproto import (CaprotoNetworkError, CaprotoRuntimeError,
                     RemoteProtocolError, get_environment_variables)

from .._data import DataWithBitSet
from .._dataclass import get_pv_structure, pva_dataclass
from .._fields import BitSet
from .._functools_compat import singledispatchmethod
from .._messages import Message, MonitorSubcommand, Subcommand


class DisconnectedCircuit(Exception):
    ...


class LoopExit(Exception):
    ...


@pva_dataclass
class ServerStatus:
    running: bool = True
    caproto_version: str = str(ca.__version__)


class AuthOperation(enum.Enum):
    """
    Operations which allow for granular authorization on a per-PV basis.
    """
    read = enum.auto()
    read_interface = enum.auto()
    write = enum.auto()
    call = enum.auto()


@dataclasses.dataclass(frozen=True)
class SubscriptionSpec:
    '''
    Subscription specification used to key all subscription updates.

    Attributes
    ----------
    db_entry : DataWrapperInterface
        The database entry.

    bitset : BitSet
        The bitset to monitor.

    options : tuple
        Options for the monitor (tuple(options_dict.items()))
    '''
    db_entry: object
    bitset: BitSet
    options: tuple


@dataclasses.dataclass(frozen=True)
class Subscription:
    '''
    An individual subscription from a client.

    Attributes
    ----------
    spec : SubscriptionSpec
        The subscription specification information.

    circuit : VirtualCircuit
        The associated virtual circuit.

    channel : ServerChannel
        The associated channel.

    ioid : int
        The I/O identifier / request ID.
    '''
    spec: SubscriptionSpec
    circuit: 'VirtualCircuit'
    channel: pva.ServerChannel
    ioid: int


class VirtualCircuit:
    """
    The base VirtualCircuit class.

    Servers are expected to subclass from this, including additional
    attributes, noted in the Attributes section.

    Attributes
    ----------
    QueueFull : class
        Must be implemented in the subclass.  (TODO details)

    message_queue : QueueInterface
        Must be implemented in the subclass.

    subscription_queue : QueueInterface
        Must be implemented in the subclass.

    get_from_sub_queue : method
        Must be implemented in the subclass.

    _start_write_task : method
        Must be implemented in the subclass.
    """

    context: 'Context'
    connected: bool
    circuit: pva.ServerVirtualCircuit
    log: logging.Logger
    client: object  # socket or similar (TODO socket interface)
    most_recent_updates: Dict
    _tags: Dict[str, str]
    subscriptions: typing.DefaultDict[SubscriptionSpec,
                                      typing.Deque[Subscription]]

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

    async def _start_write_task(self, handle_write):
        """
        Start a write handler, and return the task.

        Must be implemented by the subclass, and must return a cancellable task
        instance (API like asyncio, currently).
        """
        raise NotImplementedError()

    async def _on_disconnect(self):
        """Executed when disconnection detected"""
        if not self.connected:
            return

        self.connected = False
        queue = self.context.subscription_queue
        for sub_spec, subs in self.subscriptions.items():
            for sub in subs:
                self.context.subscriptions[sub_spec].remove(sub)
                await sub_spec.db_entry.unsubscribe(queue, sub)

            if not self.context.subscriptions[sub_spec]:
                self.context.subscriptions.pop(sub_spec)
        self.subscriptions.clear()

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
        except OSError:
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
            self.log.debug("%r", message, extra=self._tags)
            self.circuit.process_command(message)
        except RemoteProtocolError:
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

        if message is pva.DISCONNECTED:
            raise DisconnectedCircuit()

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
                chan.name, message
            )

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

    async def subscription_queue_loop(self):
        """
        Subscription queue loop.

        This is the final spot where we ship updates off to the client.
        """
        def cull_messages(messages):
            """
            Ensure at the last possible moment that we don't send responses for
            Subscriptions that have been canceled at some time after the
            response was queued.
            """
            all_subscription_ids = set(
                sub.ioid
                for subs in self.subscriptions.values()
                for sub in subs
            )
            return (
                message for message in messages
                if message.ioid in all_subscription_ids
            )

        while True:
            try:
                ref = await self.subscription_queue.get()
                # ref = await self.get_from_sub_queue(timeout=ca.HIGH_LOAD_TIMEOUT)
                # message = ref()  # TODO: weakref
                await self.send(*cull_messages([ref]))
            except self.TaskCancelled:
                break
            except DisconnectedCircuit:
                await self._on_disconnect()
                self.circuit.disconnect()
                await self.context.circuit_disconnected(self)
                break
            except Exception:
                self.log.exception('Subscription update send failure %s',
                                   locals().get('message', '(no message)'))

    async def message_queue_loop(self):
        """Reference implementation of the message queue loop

        Note
        ----
        Assumes self.message_bundle_queue functions as an async queue with
        awaitable .get()

        Async library implementations can (and should) reimplement this.
        Coroutine which evaluates one item from the circuit message queue.
        """

        await self._newly_connected()

        try:
            while True:
                message = await self.message_queue.get()
                response = await self._message_queue_iteration(message)
                if response is not None:
                    await self.send(*response)
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
        chan = self.circuit._get_channel_from_message(message)
        db_entry = self.context[chan.name]
        return chan, db_entry

    @singledispatchmethod
    async def _process_message(self, message):
        # Fall-through for non-registered items
        if message is pva.DISCONNECTED:
            raise DisconnectedCircuit()

        self.log.error("Unhandled %r", message, extra=self._tags)
        return []

    @_process_message.register
    async def _(self, message: pva.ConnectionValidationResponse):
        self.authorization_info.update(**{
            'method': message.auth_nz,
            'data': message.data.data,
        })
        return [self.circuit.validated_connection()]

    @_process_message.register
    async def _(self, message: pva.SearchRequest):
        ...
        # TODO message.channels -> searchreply
        return []

    @_process_message.register
    async def _(self, message: pva.CreateChannelRequest):
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
        return to_send

    @_process_message.register
    async def _(self, message: pva.ChannelFieldInfoRequest):
        chan, db_entry = self._get_db_entry_from_message(message)
        data = await db_entry.authorize(
            operation=AuthOperation.read_interface,
            authorization=self.authorization_info,
        )

        data = await db_entry.read(None)
        return [chan.read_interface(ioid=message.ioid, interface=data)]

    @_process_message.register
    async def _(self, message: pva.ChannelGetRequest):
        subcommand = Subcommand(message.subcommand)
        chan, db_entry = self._get_db_entry_from_message(message)
        ioid_info = self.circuit.ioids[message.ioid]
        response: pva.ChannelGetResponse

        if Subcommand.INIT in subcommand:
            try:
                await db_entry.authorize(
                    AuthOperation.read,
                    authorization=self.authorization_info,
                    request=message.pv_request,
                )
                data = await db_entry.read(
                    request=message.pv_request,
                )
            except Exception as ex:
                self.log.exception('Message response failure %s (%s)',
                                   message, subcommand)
                response = chan.read(
                    ioid=message.ioid, interface=None,
                    status=pva.Status.create_error(
                        message=f'{ex.__class__.__name__}: {ex}',
                    ),
                )
            else:
                ioid_info['pv_request'] = message.pv_request
                ioid_info['interface'] = data

                response = chan.read(ioid=message.ioid, interface=data)
                ioid_info['init_request'] = message
                # Reusable response message for this ioid:
                ioid_info['response'] = response
            return [response]

        if Subcommand.GET in subcommand or subcommand == Subcommand.DEFAULT:
            # NOTE: we'll only get here if INIT succeeded, where the
            # authentication happens

            data = await db_entry.read(
                ioid_info['init_request'].pv_request
            )

            pv_data = DataWithBitSet(data=data,
                                     bitset=BitSet({0}),  # TODO
                                     )

            # TODO: check if interface has changed
            response = ioid_info['response']
            if subcommand == Subcommand.GET:
                response.to_get(pv_data=pv_data)
            else:
                response.to_default(pv_data=pv_data)
            return [response]

    @_process_message.register
    async def _(self, message: pva.ChannelPutRequest):
        subcommand = Subcommand(message.subcommand)
        chan, db_entry = self._get_db_entry_from_message(message)
        ioid_info = self.circuit.ioids[message.ioid]
        response: pva.ChannelPutResponse

        if Subcommand.INIT in subcommand:
            try:
                interface = await db_entry.authorize(
                    AuthOperation.write,
                    request=message.pv_request,
                    authorization=self.authorization_info,
                )
            except Exception as ex:
                self.log.exception('Message response failure %s (%s)',
                                   message, subcommand)
                interface = None
                status = pva.Status.create_error(
                    message=f'{ex.__class__.__name__}: {ex}',
                )
            else:
                status = pva.Status.create_success()

            response = chan.write(
                ioid=message.ioid,
                status=status,
                put_structure_if=interface,
            )

            ioid_info['pv_request'] = message.pv_request
            ioid_info['interface'] = interface
            ioid_info['response'] = response
            ioid_info['write_task'] = None
            return [response.to_init(put_structure_if=interface)]

        if Subcommand.GET in subcommand:
            # This is pretty much a pva-get, using the pvrequest from the
            # put_init
            response = ioid_info['response']
            try:
                pv_request = ioid_info['pv_request']
                read_data = await db_entry.read(pv_request)
                data = DataWithBitSet(
                    data=read_data,
                    bitset=BitSet({0}),  # TODO
                )
            except Exception as ex:
                self.log.exception('Message response failure %s (%s)',
                                   message, subcommand)
                response.status = pva.Status.create_error(
                    message=f'{ex.__class__.__name__}: {ex}',
                )
                data = None
            else:
                response.status = pva.Status.create_success()

            return [response.to_get(data=data)]

        if subcommand == Subcommand.DEFAULT or subcommand == Subcommand.DESTROY:
            async def handle_write():
                try:
                    response = ioid_info['response']
                    await db_entry.write(message.put_data)
                except self.TaskCancelled:
                    self.log.debug(
                        'Write request by %s(%s) cancelled: %s => %r',
                        self.authorization_info['method'],
                        self.authorization_info['data'],
                        chan.name,
                        message.put_data.data,
                    )
                    response.status = pva.Status.create_error(
                        message='Cancelled',
                    )
                except Exception as ex:
                    self.log.exception(
                        'Write request by %s(%s) failed: %r',
                        self.authorization_info['method'],
                        self.authorization_info['data'],
                        message)
                    response.status = pva.Status.create_error(
                        message=f'{ex.__class__.__name__}: {ex}',
                    )
                else:
                    response.status = pva.Status.create_success()
                finally:
                    ioid_info['write_task'] = None

                await self.send(response.to_default())

            ioid_info['write_task'] = await self._start_write_task(handle_write)

    @_process_message.register
    async def _(self, message: pva.ChannelMonitorRequest):
        subcommand = MonitorSubcommand(message.subcommand)
        chan, db_entry = self._get_db_entry_from_message(message)
        ioid_info = self.circuit.ioids[message.ioid]
        response: pva.ChannelMonitorResponse

        if subcommand == MonitorSubcommand.INIT:
            try:
                data = await db_entry.authorize(
                    AuthOperation.read,
                    authorization=self.authorization_info,
                    request=message.pv_request,
                )
                bitset, options = message.pv_request.to_bitset_and_options(
                    data
                )
                spec = SubscriptionSpec(
                    db_entry=db_entry, bitset=bitset, options=tuple(options.items())
                )
                sub = Subscription(
                    circuit=self, channel=chan, spec=spec, ioid=message.ioid
                )
            except Exception as ex:
                self.log.exception('Message response failure %s (%s)',
                                   message, subcommand)
                response = chan.subscribe(
                    ioid=message.ioid, interface=None,
                    status=pva.Status.create_error(
                        message=f'{ex.__class__.__name__}: {ex}',
                    ),
                )
            else:
                response = chan.subscribe(ioid=message.ioid, interface=data)
                ioid_info['pv_request'] = message.pv_request
                ioid_info['interface'] = data
                ioid_info['init_request'] = message
                # Reusable response message for this ioid:
                ioid_info['response'] = response
                ioid_info['sub'] = sub
                ioid_info['monitor_state'] = MonitorSubcommand.INIT
                ioid_info['pipeline_count'] = None

            return [response]

        if MonitorSubcommand.START in subcommand:
            if ioid_info['monitor_state'] in {MonitorSubcommand.INIT,
                                              MonitorSubcommand.STOP}:
                sub: Subscription = ioid_info['sub']
                data = await db_entry.subscribe(
                    queue=self.context.subscription_queue,
                    sub=sub,
                )
                self.subscriptions[sub.spec].append(sub)
                self.context.subscriptions[sub.spec].append(sub)
                ioid_info['monitor_state'] = MonitorSubcommand.START

                # It's not impossible this send could happen -after- an update
                response = ioid_info['response']
                response.to_default(
                    pv_data=pva.DataWithBitSet(
                        bitset=BitSet(sub.spec.bitset),
                        interface=get_pv_structure(data),
                        data=data
                    ),
                    overrun_bitset=BitSet({})
                )
                return [response]

        if MonitorSubcommand.PIPELINE in subcommand:
            # TODO: need to track the number of monitors that happen
            ...

        has_destroy = MonitorSubcommand.DESTROY in subcommand
        if subcommand in {MonitorSubcommand.STOP} or has_destroy:
            if ioid_info['monitor_state'] in {MonitorSubcommand.START}:
                await db_entry.unsubscribe(
                    queue=self.context.subscription_queue,
                    sub=ioid_info['sub'],
                )
                ioid_info['monitor_state'] = MonitorSubcommand.STOP
            self.subscriptions[sub.spec].remove(sub)
            self.context.subscriptions[sub.spec].remove(sub)

    @_process_message.register
    async def _(self, message: pva.ChannelRpcRequest):
        subcommand = Subcommand(message.subcommand)
        chan, db_entry = self._get_db_entry_from_message(message)
        ioid_info = self.circuit.ioids[message.ioid]

        response: pva.ChannelRpcResponse

        if subcommand == Subcommand.INIT:
            try:
                await db_entry.authorize(
                    AuthOperation.call,
                    authorization=self.authorization_info,
                    request=message.pv_request,
                )
            except Exception as ex:
                self.log.exception('Message response failure %s (%s)',
                                   message, subcommand)
                response = chan.rpc(
                    ioid=message.ioid,
                    status=pva.Status.create_error(
                        message=f'{ex.__class__.__name__}: {ex}',
                    ),
                )
            else:
                ioid_info['pv_request'] = message.pv_request
                response = chan.rpc(ioid=message.ioid)
                ioid_info['init_request'] = message
                # Reusable response message for this ioid:
                ioid_info['response'] = response
            return [response]

        if subcommand == Subcommand.DEFAULT or subcommand == Subcommand.DESTROY:
            response = ioid_info['response']
            try:
                pv_response = await db_entry.call(
                    request=ioid_info['init_request'].pv_request,
                    data=message.pv_data,
                )
            except Exception as ex:
                self.log.exception('Message response failure %s (%s)',
                                   message, subcommand)
                response.to_default(
                    pv_response=None,
                    status=pva.Status.create_error(
                        message=f'{ex.__class__.__name__}: {ex}',
                    )
                )
            else:
                response.to_default(
                    pv_response=pva.FieldDescAndData(data=pv_response),
                    status=pva.Status.create_success(),
                )

            return [response]

    @_process_message.register
    async def _(self, message: pva.ChannelDestroyRequest):
        """This is a request to destroy a **channel**."""
        # TODO: cleanup
        chan, db_entry = self._get_db_entry_from_message(message)
        return [chan.disconnect()]

    @_process_message.register
    async def _(self, message: pva.ChannelRequestDestroy):
        """This is a request to destroy a **request**."""
        chan, db_entry = self._get_db_entry_from_message(message)
        ioid_info = self.circuit.ioids[message.ioid]

        task = ioid_info.pop('write_task', None)
        if task is not None:
            task.cancel()

        return []

    @_process_message.register
    async def _(self, message: pva.ChannelRequestCancel):
        # TODO: this layer should handle canceling the operation
        chan, db_entry = self._get_db_entry_from_message(message)
        ioid_info = self.circuit.ioids[message.ioid]

        task = ioid_info.pop('write_task', None)
        if task is not None:
            task.cancel()

        return []

    @_process_message.register
    async def _(self, message: pva.EchoRequest):
        return [pva.EchoResponse()]


class Context(typing.Mapping):
    # subscription_queue: 'QueueInterface'
    port: Optional[int]
    # TODO

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

        self.subscription_queue = None
        self.subscriptions = defaultdict(deque)

    async def _core_broadcaster_loop(self, udp_sock):
        while True:
            try:
                bytes_received, address = await udp_sock.recvfrom(4096 * 16)
            except OSError:
                self.log.exception('UDP server recvfrom error')
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
        """
        Reference broadcaster queue loop implementation

        Note
        ----
        Assumes self.message_bundle_queue functions as an async queue with
        awaitable .get()

        Async library implementations can (and should) reimplement this.
        """
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
        saw_empty_channel_list = False
        for message in messages:
            if isinstance(message, pva.SearchRequest):
                if len(message.channels) == 0:
                    # This is apparently a special "I'm looking for servers"
                    # message
                    saw_empty_channel_list = True

                for channel in message.channels:
                    try:
                        channel['id']
                        name = channel['channel_name']
                        self[name]
                    except KeyError:
                        ...
                    else:
                        found_pv_to_cid[name] = channel['id']

        if found_pv_to_cid or saw_empty_channel_list:
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
        if self.environ.get('CAPROTO_PVA_BEACON_DISABLE', '') == '1':
            self.log.warning('Beacons disabled for debugging purposes')
            return

        self.log.debug('Will send beacons to %r',
                       [f'{h}:{p}' for h, p in self.beacon_socks.keys()])

        # "RECOMMENDED" by the PVA spec (~15Hz at startup)
        MIN_BEACON_PERIOD = 0.07
        BEACON_BACKOFF = 2
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
        """Notification from circuit that its connection has closed"""
        self.circuits.discard(circuit)

    async def _bind_tcp_sockets_with_consistent_port_number(self, make_socket):
        """
        Find a random port number that is free on all `self.interfaces`, and
        get a bound TCP socket with that port number on each interface. The
        argument `make_socket` is expected to be a coroutine with the signature
        `make_socket(interface, port)` that does whatever library-specific
        incantation is necessary to return a bound socket or raise an IOError.
        """
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
            raise CaprotoRuntimeError(
                'No available ports and/or bind failed'
            ) from stashed_ex
        return port, tcp_sockets

    async def tcp_handler(self, client, addr):
        """Handler for each new TCP client to the server"""
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

    @property
    def startup_methods(self):
        """Notify all instances of the server startup."""
        return {
            name: instance.server_startup
            for name, instance in self.pvdb.items()
            if getattr(instance, 'server_startup', None) is not None
        }

    @property
    def shutdown_methods(self):
        """Notify all instances of the server shutdown."""
        return {
            name: instance.server_shutdown
            for name, instance in self.pvdb.items()
            if getattr(instance, 'server_shutdown', None) is not None
        }

    async def subscription_queue_loop(self):
        """
        Reference implementation of the subscription queue loop.

        Note
        ----
        Assumes self.subscription-queue functions as an async queue with
        awaitable .get()

        Async library implementations can (and should) reimplement this
        coroutine which evaluates one item from the circuit command queue.
        """
        while True:
            # This queue receives updates that match the SubscriptionSpec of
            # one or more subscriptions.
            item = await self.subscription_queue.get()
            try:
                await self._subscription_queue_iteration(**item)
            except Exception:
                self.log.exception(
                    'Subscription publishing failed for %s',
                    item.get('sub', None)
                )
                raise  # TODO: remove

    async def _subscription_queue_iteration(
            self, sub: Subscription, interface, data, bitset: BitSet):
        """
        Called on every item from the Context subscription queue.
        """
        circuit = sub.circuit
        cls: Type[pva.ChannelMonitorResponse] = circuit.circuit.messages[
            pva.ApplicationCommand.MONITOR
        ]

        monitor_update = cls(ioid=sub.ioid).to_default(
            pv_data=pva.DataWithBitSet(
                bitset=bitset,
                interface=get_pv_structure(interface),  # TODO
                data=data
            ),
            overrun_bitset=BitSet({})
        )
        try:
            await circuit.subscription_queue.put(monitor_update)
        except circuit.QueueFull:
            # We have hit the overall max for subscription backlog.
            circuit.log.warning(
                "Critically high EventAddResponse load. Dropping all "
                "queued responses on this circuit."
            )
            circuit.subscription_queue.clear()
            # TODO
            # circuit.unexpired_updates.clear()


class DataWrapperBase:
    """
    A base class to wrap dataclasses and support caproto-pva's server API.

    Parameters
    ----------
    name : str
        The associated name of the data.

    data : PvaStruct
        The dataclass holding the data.
    """

    _sub_queues: typing.DefaultDict[typing.FrozenSet[int], typing.Deque]

    def __init__(self, name: str, data):
        self.data = data
        self.name = name

        # This is a dict keyed on queues that will receive subscription
        # updates, where each queue belongs to a Context.
        self._sub_queues = collections.defaultdict(collections.deque)

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} name={self.name}>'

    async def authorize(self,
                        operation: AuthOperation, *,
                        authorization,
                        request=None):
        """
        Authenticate `operation`, given `authorization` information.

        In the event of successful authorization, a dataclass defining the data
        contained here must be returned.

        In the event of a failed authorization, `AuthenticationError` or
        similar should be raised.

        Returns
        -------
        data

        Raises
        ------
        AuthenticationError
        """
        return self.data

    async def read(self, request):
        """A bare ``read`` (``get``) implementation."""
        return self.data

    async def write(self, update: pva.DataWithBitSet):
        """A bare ``write`` (``put``) implementation."""
        await self.commit(update.data)

    async def call(self, request: pva.PVRequest, data: pva.FieldDescAndData):
        """A bare ``call`` (``RPC``) implementation."""

    async def subscribe(self, queue, sub: Subscription):
        """
        Add a subscription from the server.

        It is unlikely this would need customization in a subclass.

        Parameters
        ----------
        queue : QueueInterface
            The queue to send updates to.

        sub : Subscription
            Subscription information.

        Returns
        -------
        data
        """
        self._sub_queues[sub.spec.bitset].append((sub, queue))
        return self.data

    async def unsubscribe(self, queue, sub: Subscription):
        """
        Remove an already-added subscription.

        It is unlikely this would need customization in a subclass.

        Parameters
        ----------
        queue : QueueInterface
            The queue used for subscriptions.

        sub : Subscription
            Subscription information.
        """
        self._sub_queues[sub.spec.bitset].remove((sub, queue))
        if not self._sub_queues[sub.spec.bitset]:
            self._sub_queues.pop(sub.spec.bitset)

    async def commit(self, changes: dict):
        """
        Commit `changes` to the local dataclass and publish monitors.

        It is unlikely this would need customization in a subclass.

        Parameters
        ----------
        changes : dict
            A nested dictionary of key to value, indicating changes to be
            made to the underlying data.
        """
        changed_bitset = pva.fill_dataclass(self.data, changes)
        # And publish indicating which bits of information have changed:
        await self._publish(changed_bitset)

    async def _publish(self, changed_bitset: BitSet):
        """
        Publish already-committed changes.

        It is unlikely this would need customization in a subclass.

        Parameters
        ----------
        changed_bitset : BitSet
            This indicates which fields have changed.
        """
        # A misplaced description regarding subscription flow:
        # Data written and .commit() called ->
        #   -> _publish
        #      Based on what parts changed
        #   -> Context.subscription_queue
        #      Create monitor update message
        #   -> VirtualCircuit.subscription_queue
        #      Potentially batch messages, remove unsubscribed items
        #   -> Ship remaining messages to client

        data = None

        for frozen_bitset, queues in self._sub_queues.items():
            matched_bitset = changed_bitset & frozen_bitset
            if matched_bitset:
                if data is None:
                    # Only create the dict if actually needed
                    data = dataclasses.asdict(self.data)
                    # TODO/FIXME/BUG: numpy arrays will be shallow copied

                for sub, queue in queues:
                    # if request matches change
                    # TODO: respect options here?
                    item = dict(
                        sub=sub,
                        bitset=matched_bitset,
                        data=data,
                        interface=self.data
                    )
                    await queue.put(item)
