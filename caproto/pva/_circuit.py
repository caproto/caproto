# A connection in caproto V3 is referred to as a VirtualCircuit. Let's just
# copy that nomenclature for now.
import logging
import typing
from typing import Dict, List, Optional, Sequence, Tuple, Type, Union

from .. import pva
from .._log import ComposableLogAdapter
from .._utils import ThreadsafeCounter
from ._core import SYS_ENDIAN
from ._data import FieldDescAndData, PVRequest
from ._functools_compat import singledispatchmethod
from ._messages import (AcknowledgeMarker, ApplicationCommand,
                        ChannelDestroyRequest, ChannelDestroyResponse,
                        ChannelFieldInfoRequest, ChannelFieldInfoResponse,
                        ChannelGetRequest, ChannelGetResponse,
                        ChannelMonitorRequest, ChannelMonitorResponse,
                        ChannelProcessRequest, ChannelProcessResponse,
                        ChannelPutGetRequest, ChannelPutGetResponse,
                        ChannelPutRequest, ChannelPutResponse,
                        ChannelRequestCancel, ChannelRequestDestroy,
                        ChannelRpcRequest, ChannelRpcResponse,
                        ConnectionValidatedResponse,
                        ConnectionValidationRequest,
                        ConnectionValidationResponse, CreateChannelRequest,
                        CreateChannelResponse, EndianSetting, Message,
                        MessageFlags, MessageHeaderBE, MessageHeaderLE,
                        MonitorSubcommand, SetByteOrder, SetMarker, Status,
                        Subcommand, _StatusOK, messages, read_from_bytestream)
from ._state import (ChannelState, CircuitState, MonitorRequestState,
                     RequestState, get_exception)
from ._utils import (CLEAR_SEGMENTS, CLIENT, DISCONNECTED, NEED_DATA, SERVER,
                     CaprotoError, CaprotoRuntimeError, ConnectionState, Role)

ChannelMessage = Union[
    CreateChannelRequest, CreateChannelResponse, ChannelFieldInfoRequest,
    ChannelFieldInfoResponse, ChannelDestroyRequest, ChannelDestroyResponse,
    ChannelGetRequest, ChannelGetResponse, ChannelMonitorRequest,
    ChannelMonitorResponse, ChannelPutRequest, ChannelPutResponse,
    ChannelProcessRequest, ChannelProcessResponse, ChannelPutGetRequest,
    ChannelPutGetResponse
]

Channel = typing.TypeVar('Channel', 'ServerChannel', 'ClientChannel')


class VirtualCircuit:
    """
    An object encapulating the state of one CA client--server connection.

    It is a companion to a TCP socket managed by the user. All data
    received over the socket should be passed to :meth:`recv`. Any data sent
    over the socket should first be passed through :meth:`send`.

    Parameters
    ----------
    our_role : CLIENT or SERVER
    address : tuple
        ``(host, port)`` as a string and an integer respectively
    priority : integer or None
        QOS priority
    """
    def __init__(self, our_role, address, priority):
        self.log = logging.getLogger('caproto.circ')
        self.our_role = our_role
        if our_role is CLIENT:
            self.their_role = SERVER
        else:
            self.their_role = CLIENT
        self.our_address = None
        self.address = address
        self._priority = None
        self.channels = {}  # map cid to Channel
        self.channels_sid = {}  # map sid to Channel
        self.states = CircuitState(self.channels)
        self._data = bytearray()
        self._segment_state = []
        self.ioids = {}  # map ioid to Channel

        # There are only used by the convenience methods, to auto-generate ids.
        if our_role is CLIENT:
            self._channel_id_counter = ThreadsafeCounter(
                dont_clash_with=self.channels
            )
        else:
            self._channel_id_counter = ThreadsafeCounter(
                dont_clash_with=self.channels_sid
            )
        self._ioid_counter = ThreadsafeCounter(dont_clash_with=self.ioids)
        self._sub_counter = ThreadsafeCounter()
        # A fixed byte order, required by the server
        self.our_order = SYS_ENDIAN
        self.their_order = None
        self.fixed_recv_order = None
        self.messages = None
        if priority is not None:
            self.priority = priority
        self.cache = pva.CacheContext()

    @property
    def priority(self):
        return self._priority

    @priority.setter
    def priority(self, priority):
        if self._priority is not None:
            raise CaprotoRuntimeError('Cannot update priority after already set')

        # A server-side circuit does not get to know its priority until after
        # instantiation, so we need a setter.
        self._priority = priority

    @property
    def host(self) -> str:
        '''Peer host name'''
        return self.address[0]

    @property
    def port(self) -> int:
        '''Port number'''
        return self.address[1]

    def __repr__(self):
        return (f"<VirtualCircuit host={self.host} port={self.port} "
                f"our_role={self.our_role}> logger_name={self.log.name}>")

    def __eq__(self, other):
        return hash(self) == hash(other)

    def __hash__(self):
        return hash((self.address, self.our_role))

    def send(self, *messages,
             extra: Optional[Dict] = None) -> List[Union[bytes, memoryview]]:
        """
        Convert one or more high-level Commands into buffers of bytes that may
        be broadcast together in one TCP packet. Update our internal
        state machine.

        Parameters
        ----------
        *messages :
            any number of :class:`Message` objects

        extra : dict or None
            Used for logging purposes. This is merged into the ``extra``
            parameter passed to the logger to provide information like ``'pv'``
            to the logger.

        Returns
        -------
        buffers_to_send : list
            list of buffers to send over a socket
        """
        buffers_to_send: List[Union[bytes, memoryview]] = []
        tags = {'their_address': self.address,
                'our_address': self.our_address,
                'direction': '--->>>',
                'role': repr(self.our_role)}
        tags.update(extra or {})
        for message in messages:
            self.log.debug("Serializing %r", message, extra=tags)

            if self.our_role == CLIENT:
                role_flag = pva.MessageFlags.FROM_CLIENT
            else:
                role_flag = pva.MessageFlags.FROM_SERVER

            if isinstance(message, (SetByteOrder, SetMarker, AcknowledgeMarker)):
                # Control messages handled here
                message.flags = message.flags | role_flag
                buffers_to_send.append(memoryview(message))
            else:
                if message._ENDIAN == pva.LITTLE_ENDIAN:
                    header_cls = MessageHeaderLE
                    endian_flag = pva.MessageFlags.LITTLE_ENDIAN
                else:
                    header_cls = MessageHeaderBE
                    endian_flag = pva.MessageFlags.BIG_ENDIAN

                payload = memoryview(message.serialize(cache=self.cache))
                header = header_cls(
                    flags=(pva.MessageFlags.APP_MESSAGE |
                           role_flag | endian_flag),
                    command=message.ID,
                    payload_size=len(payload)
                )

                message.header = header
                buffers_to_send.append(header)
                buffers_to_send.append(payload)

            self._process_message(message, self.our_role)

            # Run the circuit's state machine.
            self.states.process_command_type(self.our_role, message)
            self.states.process_command_type(self.their_role, message)

        return buffers_to_send

    def recv(self, *buffers
             ) -> typing.Generator[Tuple[Union[Message, ConnectionState],
                                         Optional[int]],
                                   None, None]:
        """
        Parse messages from buffers received over TCP.

        When the caller is ready to process the messages, each message should
        first be passed to :meth:`VirtualCircuit.process_command` to validate
        it against the protocol and update the VirtualCircuit's state.

        Parameters
        ----------
        *buffers :
            any number of bytes-like buffers

        Yields
        ------
        message : Message
            The message/message.

        num_bytes_needed : int
            Number of bytes needed for the next message.
        """
        total_received = sum(len(byteslike) for byteslike in buffers)
        if total_received == 0:
            self.log.debug('Zero-length recv; sending disconnect notification')
            yield DISCONNECTED, None
            return

        self.log.debug("Received %d bytes.", total_received)
        self._data += b''.join(buffers)

        while True:
            decoded, num_bytes_needed, segmented = read_from_bytestream(
                self._data, self.their_role, segment_state=self._segment_state,
                byte_order=self.fixed_recv_order, cache=self.cache)

            len_data = len(self._data)
            message, self._data, bytes_consumed = decoded

            if isinstance(self._data, memoryview):
                self._data = bytearray(self._data)

            if segmented is CLEAR_SEGMENTS:
                self._segment_state.clear()
            elif segmented is not None:
                self._segment_state.append(segmented)
                continue

            if message is NEED_DATA:
                self.log.debug(
                    "%d bytes are cached. Need %d more bytes to parse next "
                    "message.", len_data, num_bytes_needed)
                break

            self.log.debug("%d bytes -> %r", bytes_consumed, message)
            yield message, None

    def process_command(self, message: Message):
        """
        Update internal state machine and raise if protocol is violated.

        **Received** messages should be passed through here before any
        additional processing by a server or client layer.
        """
        if message is DISCONNECTED:
            self.states.disconnect()
            return

        self._process_message(message, self.their_role)

        status = getattr(message, 'status', None)
        if status is not None and (status.message or status.call_tree):
            self.log.debug('Command %s status: %s', type(message).__name__,
                           status)

        # Run the circuit's state machine.
        self.states.process_command_type(self.our_role, message)
        self.states.process_command_type(self.their_role, message)

    def _get_channel_from_message(self, message: ChannelMessage) -> Channel:
        """
        Get the :class:`Channel` instance associated with the given message.

        Parameters
        ----------
        message : Message
        """
        cid = getattr(message, 'client_chid', None)
        if cid is not None:
            return self.channels[cid]

        sid = getattr(message, 'server_chid', None)
        if sid is not None:
            return self.channels_sid[sid]

        ioid = getattr(message, 'ioid', None)
        if ioid is not None:
            return self.ioids[ioid]['channel']

        raise get_exception(self.our_role, message)(
            'Unable to determine channel information'
        )

    @singledispatchmethod
    def _process_message(self, message: Message, role: Role):
        """
        Single dispatch method for all messages.

        Parameters
        ----------
        message : Message
            The message to process.

        role : ``CLIENT`` or ``SERVER``
            The role of the sender.
        """
        # Filter for Commands that are pertinent to a specific Channel, as
        # opposed to the Circuit as a whole:
        if any((hasattr(message, 'server_chid'),
                hasattr(message, 'client_chid'),
                hasattr(message, 'ioid'))):
            raise RuntimeError(f'Channel-specific message fell through: '
                               f'TODO {message}')
        self.log.warning('Unhandled message in circuit: %s (%s)', message,
                         role)

    @_process_message.register
    def _(self, message: SetByteOrder, role: Role):
        fixed = (message.byte_order_setting == EndianSetting.use_server_byte_order)
        if self.our_role == SERVER:
            self.our_order = message.byte_order
            self.their_order = None
            self.fixed_recv_order = None
            self.messages = messages[(self.our_order,
                                      MessageFlags.FROM_SERVER)]
        else:
            self.our_order = message.byte_order
            self.their_order = message.byte_order
            self.fixed_recv_order = (self.their_order if fixed else None)
            if fixed:
                self.log.debug('Using fixed byte order for server messages'
                               ': %s', self.fixed_recv_order.name)
            else:
                self.log.debug('Using byte order from individual messages.')
            self.messages = messages[(self.our_order,
                                      MessageFlags.FROM_CLIENT)]

    @_process_message.register(ConnectionValidationRequest)
    @_process_message.register(ConnectionValidationResponse)
    @_process_message.register(ConnectionValidatedResponse)
    def _(self, message, role: Role):
        ...

    @_process_message.register
    def _process_channel_creation(self, message: CreateChannelRequest,
                                  role: Role):
        """
        Separately process channel creation, as it may possibly work on more
        than one channel at a time.
        """
        channels = []

        for request in message.channels:
            cid = request['id']
            try:
                chan = self.channels[cid]
            except KeyError:
                chan = self.create_channel(request['channel_name'], cid=cid)
                channels.append((request, chan))

        for request, channel in channels:
            # transitions = channel.process_command(message)
            channel.process_command(message, role)
            self.channels[request['id']] = channel
            # for transition in transitions:
            #     chan.state_changed(*transition)

    @_process_message.register(ChannelDestroyRequest)
    @_process_message.register(ChannelDestroyResponse)
    @_process_message.register(ChannelFieldInfoRequest)
    @_process_message.register(ChannelFieldInfoResponse)
    @_process_message.register(ChannelGetRequest)
    @_process_message.register(ChannelGetResponse)
    @_process_message.register(ChannelRpcRequest)
    @_process_message.register(ChannelRpcResponse)
    @_process_message.register(ChannelMonitorRequest)
    @_process_message.register(ChannelMonitorResponse)
    @_process_message.register(ChannelPutRequest)
    @_process_message.register(ChannelPutResponse)
    @_process_message.register(ChannelRequestCancel)
    @_process_message.register(ChannelRequestDestroy)
    @_process_message.register(CreateChannelResponse)
    def _(self, message, role: Role):
        channel = self._get_channel_from_message(message)
        channel.process_command(message, role)

    def disconnect(self):
        """
        Notify all channels on this circuit that they are disconnected.

        Clients should call this method when a TCP connection is lost.
        """
        return DISCONNECTED

    def new_channel_id(self):
        "Return a valid value for a cid or sid."
        # Return the next sequential unused id. Wrap back to 0 on overflow.
        return self._channel_id_counter()

    def new_subscriptionid(self):
        """
        This is used by the convenience methods to obtain an unused integer ID.
        It does not update any important state.
        """
        # Return the next sequential unused id. Wrap back to 0 on overflow.
        return self._sub_counter()

    def new_ioid(self):
        """
        This is used by the convenience methods to obtain an unused integer ID.
        It does not update any important state.
        """
        # Return the next sequential unused id. Wrap back to 0 on overflow.
        return self._ioid_counter()

    def set_byte_order(self, endian_setting: EndianSetting) -> SetByteOrder:
        """
        Generate a valid :class:`SetByteOrder`.

        Returns
        -------
        SetByteOrder
        """
        return SetByteOrder(
            endian_setting,
            flags=pva.MessageFlags.CONTROL_MESSAGE,
        )

    def acknowledge_marker(self) -> AcknowledgeMarker:
        """
        Generate a valid :class:`AcknowledgeMarker`.

        Returns
        -------
        AcknowledgeMarker
        """
        return AcknowledgeMarker(
            flags=pva.MessageFlags.APP_MESSAGE,
            message=AcknowledgeMarker.ID,
            payload_size=0,
        )

    def create_channel(self, name: str, cid: int = None) -> Channel:
        """
        Create a ClientChannel or ServerChannel, depending on the role.

        Parameters
        ----------
        name : str
            The channel name.

        cid : int
            The client channel ID.
        """
        cls = {CLIENT: ClientChannel,
               SERVER: ServerChannel}[self.our_role]
        return cls(name, self, cid=cid)


class ClientVirtualCircuit(VirtualCircuit):
    def validate_connection(self,
                            buffer_size: int,
                            registry_size: int,
                            connection_qos: int,
                            auth_nz: str = 'ca',
                            data=None,
                            ) -> ConnectionValidationResponse:
        """
        Generate a valid :class:`_ConnectionValidationResponse`.

        Parameters
        ----------
        buffer_size : int
            Client buffer size.

        registry_size : int
            Client registry size.

        connection_qos  : int
            Connection QOS value.

        auth_nz  : str, optional
            Authorization string, defaults to 'ca'.  Caller must confirm that
            the server supports the given authorization method prior to
            specifying it.

        Returns
        -------
        ConnectionValidationResponse
        """
        cls = self.messages[ApplicationCommand.CONNECTION_VALIDATION]
        data = FieldDescAndData(data=data)

        return cls(client_buffer_size=buffer_size,
                   client_registry_size=registry_size,
                   connection_qos=connection_qos,
                   auth_nz=auth_nz,
                   data=data,
                   )


class ServerVirtualCircuit(VirtualCircuit):
    def __init__(self, our_role, address, priority):
        super().__init__(our_role, address, priority)
        # TODO rethink?
        self.messages = messages[(self.our_order,
                                  MessageFlags.FROM_SERVER)]

    def validate_connection(self,
                            buffer_size: int,
                            registry_size: int,
                            authorization_options: Sequence,
                            ) -> ConnectionValidationRequest:
        """
        Generate a valid :class:`_ConnectionValidationRequest`.

        Parameters
        ----------
        buffer_size : int
            Server buffer size.

        registry_size : int
            Server registry size.

        authorization_options  : Sequence
            Authorization options, such as 'ca' or 'anonymous'.

        Returns
        -------
        ConnectionValidationRequest
        """
        cls = self.messages[ApplicationCommand.CONNECTION_VALIDATION]
        return cls(server_buffer_size=buffer_size,
                   server_registry_size=registry_size,
                   auth_nz=authorization_options,
                   )

    def validated_connection(self) -> ConnectionValidatedResponse:
        """Generate a valid :class:`_ConnectionValidatedResponse`."""
        cls = self.messages[ApplicationCommand.CONNECTION_VALIDATED]
        return cls()


class _BaseChannel:
    # Base class for ClientChannel and ServerChannel, which add convenience
    # methods for composing requests and responses, respectively.
    def __init__(self, name, circuit, cid=None):
        tags = {'pv': name,
                'their_address': circuit.address,
                'role': repr(circuit.our_role)}
        self.log = ComposableLogAdapter(logging.getLogger('caproto.ch'), tags)
        self.endian = None  # TODO
        self.name = name
        self.circuit = circuit
        if cid is None:
            cid = self.circuit.new_channel_id()
        self.cid = cid
        self.circuit.channels[self.cid] = self
        self.states = ChannelState(self.circuit.states)
        # These will be set when the circuit processes CreateChannelResponse..
        self.interface = None
        self.sid = None
        self.ioids = {}
        # self.access_rights = None

    @property
    def subscriptions(self):
        """
        Get cached EventAdd messages for this channel's active subscriptions.
        """

    def state_changed(self, role, old_state, new_state, message):
        '''State changed callback for subclass usage'''
        pass

    def process_command(self, message: ChannelMessage, role: Role):
        # Update the state machine of the pertinent Channel.  If this is
        # not a valid message, the state machine will raise here. Stash the
        # state transitions in a local var, run the callbacks at the end.
        ioid_info = self._ioid_info_from_message(message)
        subcommand = getattr(message, 'subcommand', None)
        if subcommand is not None and ioid_info is not None:
            ioid_state = ioid_info['state']
            ioid_state.process_subcommand(subcommand)

        self._process_message(message, role, ioid_info)

        if (role == Role.SERVER and subcommand and Subcommand.DESTROY in Subcommand(subcommand)):
            # Only destroy when the server acknowledges it
            self._destroy_ioid(ioid_info)

        transitions = []
        for role in (self.circuit.our_role, self.circuit.their_role):
            initial_state = self.states[role]
            try:
                self.states.process_command_type(role, message)
            except CaprotoError as ex:
                ex.channel = self
                raise

            new_state = self.states[role]
            # Assemble arguments needed by state_changed, to be called later.
            if initial_state is not new_state:
                transition = (role, initial_state, new_state, message)
                transitions.append(transition)

        # We are done. Run the Channel state change callbacks.
        for transition in transitions:
            self.state_changed(*transition)
        return transitions

    @singledispatchmethod
    def _process_message(self, message, role: Role, ioid_info: dict):
        self.circuit.log.warning(
            'Unhandled channel message %s role=%s ioid_info=%s',
            message, role, ioid_info
        )

    @_process_message.register
    def _(self, message: CreateChannelRequest, role: Role, ioid_info: dict):
        ...

    @_process_message.register
    def _(self, message: ChannelFieldInfoResponse, role: Role, ioid_info: dict):
        field_info = getattr(message.field_if, '_pva_struct_',
                             message.field_if)
        for line in field_info.summary().splitlines():
            self.circuit.log.debug('[%s] %s', self.name, line)

    def _ioid_info_from_message(self, message: ChannelMessage) -> Optional[Dict]:
        ioid = getattr(message, 'ioid', None)
        if ioid is None:
            return

        try:
            return self.ioids[ioid]
        except KeyError:
            ...

        if isinstance(message, (ChannelMonitorRequest, ChannelMonitorResponse)):
            state_class = MonitorRequestState
        else:
            state_class = RequestState

        ioid_info = dict(
            channel=self,
            state=state_class(message.__class__.__name__),
            ioid=ioid,
        )

        self.ioids[ioid] = ioid_info
        self.circuit.ioids[ioid] = ioid_info
        return ioid_info

    @_process_message.register(ChannelDestroyRequest)
    @_process_message.register(ChannelDestroyResponse)
    @_process_message.register(ChannelFieldInfoRequest)
    @_process_message.register(ChannelFieldInfoResponse)
    @_process_message.register(ChannelGetRequest)
    @_process_message.register(ChannelRpcRequest)
    @_process_message.register(ChannelRpcResponse)
    @_process_message.register(ChannelMonitorRequest)
    @_process_message.register(ChannelPutRequest)
    def _(self, message, role: Role, ioid_info: dict):
        ...
        # Nothing to do here

    @_process_message.register
    def _(self, message: CreateChannelResponse, role: Role, ioid_info: dict):
        self.sid = message.server_chid
        self.circuit.channels_sid[message.server_chid] = self

    @_process_message.register
    def _(self, message: ChannelPutResponse, role: Role, ioid_info: dict):
        if message.status.is_successful:
            subcommand = Subcommand(message.subcommand)
            if Subcommand.INIT in subcommand:
                interface = message.put_structure_if
                self.circuit.cache.ioid_interfaces[message.ioid] = interface

    @_process_message.register
    def _(self, message: ChannelGetResponse, role: Role, ioid_info: dict):
        if message.status.is_successful:
            subcommand = Subcommand(message.subcommand)
            if Subcommand.INIT in subcommand:
                interface = message.pv_structure_if
                self.circuit.cache.ioid_interfaces[message.ioid] = interface

    @_process_message.register
    def _(self, message: ChannelMonitorResponse, role: Role, ioid_info: dict):
        subcommand = MonitorSubcommand(message.subcommand)
        if MonitorSubcommand.INIT in subcommand:
            if message.status.is_successful:
                interface = message.pv_structure_if
                self.circuit.cache.ioid_interfaces[message.ioid] = interface

    @_process_message.register
    def _(self, message: ChannelRequestCancel, role: Role, ioid_info: dict):
        ...
        # TODO?

    @_process_message.register
    def _(self, message: ChannelRequestDestroy, role: Role, ioid_info: dict):
        self._destroy_ioid(ioid_info)

    def _destroy_ioid(self, ioid_info: dict):
        """Destroy an I/O request id given its info dictionary."""
        ioid = ioid_info['ioid']

        self.ioids.pop(ioid)
        # May not have been successful:
        self.circuit.cache.ioid_interfaces.pop(ioid, None)


class ClientChannel(_BaseChannel):
    """An object encapsulating the state of the EPICS Channel on a Client.

    A ClientChannel may be created in one of two ways:
    (1) The user instantiates a ClientChannel with a name, server address,
    and optional cid. The server address is used to assign the ClientChannel to
    a VirtualCircuit. If no cid is given, a unique one is allocated by the
    VirtualCircuit.
    (2) A VirtualCircuit processes a CreateChannelRequest that refers to a cid
    that it has not yet seen. A ClientChannel will be automatically
    instantiated with the name and cid indicated that message and the address
    of that VirtualCircuit. It can be accessed in the circuit's
    ``channels`` attribute.

    Parameters
    ----------
    name : string
        Channnel name (PV)
    circuit : VirtualCircuit
    cid : integer, optional
    """

    def create(self) -> CreateChannelRequest:
        """
        Generate a valid :class:`CreateChannelRequest`.

        Returns
        -------
        CreateChannelRequest
        """
        create_cls = self.circuit.messages[ApplicationCommand.CREATE_CHANNEL]
        return create_cls(
            count=1,
            channels=[{'id': self.cid, 'channel_name': self.name}]
        )

    def disconnect(self) -> ChannelDestroyRequest:
        """
        Generate a valid :class:`ChannelDestroyRequest`.

        Returns
        -------
        ChannelDestroyRequest
        """
        if self.sid is None:
            raise RuntimeError('Server ID unavailable')

        cls = self.circuit.messages[ApplicationCommand.DESTROY_CHANNEL]
        return cls(client_chid=self.cid, server_chid=self.sid)

    def read_interface(self, *, ioid=None,
                       sub_field_name='') -> ChannelFieldInfoRequest:
        """
        Generate a valid :class:`ChannelFieldInfoRequest`.
        """

        if self.sid is None:
            raise RuntimeError('Server ID unavailable')

        if ioid is None:
            ioid = self.circuit.new_ioid()
        cls = self.circuit.messages[ApplicationCommand.GET_FIELD]
        return cls(server_chid=self.sid,
                   ioid=ioid,
                   sub_field_name=sub_field_name,
                   )

    def read(self, *, ioid=None, pvrequest: str = 'field()') -> ChannelGetRequest:
        """
        Generate a valid :class:`ChannelGetRequest`.

        Parameters
        ----------
        ioid
        pvrequest

        Returns
        -------
        ChannelGetRequest
        """
        if ioid is None:
            ioid = self.circuit.new_ioid()

        cls = typing.cast(Type[ChannelGetRequest],
                          self.circuit.messages[ApplicationCommand.GET])
        if not isinstance(pvrequest, PVRequest):
            pvrequest = PVRequest(data=pvrequest)

        instance = cls(server_chid=self.sid, ioid=ioid)
        instance.to_init(pv_request=pvrequest)
        return instance

    def rpc(self, *, ioid=None, pvrequest: str = 'field()') -> ChannelRpcRequest:
        """
        Generate a valid :class:`ChannelRpcRequest`.

        Parameters
        ----------
        ioid
        pvrequest

        Returns
        -------
        ChannelRpcRequest
        """
        if ioid is None:
            ioid = self.circuit.new_ioid()

        if not isinstance(pvrequest, PVRequest):
            pvrequest = PVRequest(data=pvrequest)

        cls: Type[ChannelRpcRequest] = self.circuit.messages[ApplicationCommand.RPC]
        instance = cls(server_chid=self.sid, ioid=ioid)
        instance.to_init(pv_request=pvrequest)
        return instance

    def subscribe(self, *,
                  ioid=None,
                  pvrequest: str = 'field(value)',
                  queue_size=None) -> ChannelMonitorRequest:
        """
        Generate a valid :class:`ChannelMonitorRequest`.

        Parameters
        ----------
        ioid
        pvrequest

        Returns
        -------
        ChannelMonitorRequest
        """
        if ioid is None:
            ioid = self.circuit.new_ioid()

        if not isinstance(pvrequest, PVRequest):
            pvrequest = PVRequest(data=pvrequest)

        cls: Type[ChannelMonitorRequest] = self.circuit.messages[ApplicationCommand.MONITOR]

        return cls(server_chid=self.sid, ioid=ioid).to_init(
            pv_request=pvrequest,
            queue_size=queue_size or 0,
        )

    def write(self, *,
              ioid: int = None,
              pvrequest: str = 'field(value)',
              queue_size=None) -> ChannelPutRequest:
        """
        Generate a valid :class:`ChannelPutRequest` (INIT).

        Parameters
        ----------
        ioid : int, optional
            The I/O identifier.  Generated if needed.
        """
        if ioid is None:
            ioid = self.circuit.new_ioid()

        if not isinstance(pvrequest, PVRequest):
            pvrequest = PVRequest(data=pvrequest)

        cls = self.circuit.messages[ApplicationCommand.PUT]
        instance: ChannelPutRequest = cls(server_chid=self.sid, ioid=ioid)
        return instance.to_init(pv_request=pvrequest)

    def cancel(self, ioid: int) -> ChannelRequestCancel:
        """
        Generate a valid :class:`ChannelRequestCancel`.

        Parameters
        ----------
        ioid : int, optional
            The I/O identifier.
        """
        cls = self.circuit.messages[ApplicationCommand.CANCEL_REQUEST]
        instance: ChannelRequestCancel = cls(server_chid=self.sid, ioid=ioid)
        return instance


class ServerChannel(_BaseChannel):
    """
    A server-side Channel.

    """

    def create(self,
               sid: int,
               *,
               status=_StatusOK,
               ) -> CreateChannelResponse:
        """
        Generate a valid :class:`CreateChannelResponse`.

        Parameters
        ----------
        sid : int
            The server channel ID.

        status : Status
            Status information.

        Returns
        -------
        CreateChannelResponse
        """
        create_cls = self.circuit.messages[ApplicationCommand.CREATE_CHANNEL]
        return create_cls(
            client_chid=self.cid,
            server_chid=sid,
            status=status,
        )

    def read_interface(self, ioid, interface, *,
                       status=_StatusOK
                       ) -> ChannelFieldInfoResponse:
        """
        Generate a valid :class:`ChannelFieldInfoResponse`.
        """
        cls = self.circuit.messages[ApplicationCommand.GET_FIELD]
        return cls(ioid=ioid,
                   status=status,
                   interface=interface,
                   )

    def read(self, ioid, interface, *,
             status: Status = _StatusOK,
             ) -> ChannelGetResponse:
        """
        Generate a valid :class:`ChannelGetResponse`.

        Parameters
        ----------
        ioid : int
            The operation ID.

        interface : FieldDesc or dataclass
            The interface or dataclass containing data.

        status : Status
            Status information.

        Returns
        -------
        ChannelGetResponse
        """
        cls = self.circuit.messages[ApplicationCommand.GET]
        return cls(ioid=ioid, status=status).to_init(
            pv_structure_if=interface
        )

    def write(self, ioid, put_structure_if, *,
              status: Status = _StatusOK) -> ChannelPutResponse:
        """
        Generate a valid :class:`ChannelPutResponse`.

        Parameters
        ----------
        ioid : int
            The operation ID.

        put_structure_if : FieldDesc or dataclass
            The interface or dataclass containing data.

        status : Status
            Status information.

        Returns
        -------
        ChannelPutResponse
        """
        cls = typing.cast(Type[ChannelPutResponse],
                          self.circuit.messages[ApplicationCommand.PUT])
        return cls(ioid=ioid, status=status).to_init(
            put_structure_if=put_structure_if
        )

    def disconnect(self) -> ChannelDestroyResponse:
        """
        Generate a valid :class:`ChannelDestroyResponse`.

        Returns
        -------
        ChannelDestroyResponse
        """
        cls = self.circuit.messages[ApplicationCommand.DESTROY_CHANNEL]
        return cls(client_chid=self.cid, server_chid=self.sid)

    def subscribe(self, ioid, interface, *,
                  status=_StatusOK,
                  ) -> ChannelMonitorResponse:
        """
        Generate a valid :class:`ChannelMonitorResponse`.

        Parameters
        ----------
        ioid : int
            The operation ID.

        status : Status
            Status information.

        interface : FieldDesc or dataclass
            The interface or dataclass containing data.

        Returns
        -------
        ChannelMonitorResponse
        """
        cls: Type[ChannelMonitorResponse] = self.circuit.messages[ApplicationCommand.MONITOR]
        return cls(ioid=ioid).to_init(status=status, pv_structure_if=interface)

    def rpc(self, ioid, *, status: Status = _StatusOK) -> ChannelRpcResponse:
        """
        Generate a valid :class:`ChannelRpcResponse`.

        Parameters
        ----------
        ioid : int
            The operation ID.

        status : Status
            Status information.

        Returns
        -------
        ChannelRpcResponse
        """
        cls: Type[ChannelRpcResponse] = self.circuit.messages[ApplicationCommand.RPC]
        return cls(ioid=ioid).to_init(status=status)
