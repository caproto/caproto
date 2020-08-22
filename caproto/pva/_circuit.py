# A connection in caproto V3 is referred to as a VirtualCircuit. Let's just
# copy that nomenclature for now.
import logging
import typing
from typing import Dict, List, Optional, Sequence, Tuple, Union

from .. import pva
from .._log import ComposableLogAdapter
from .._utils import ThreadsafeCounter
from ._core import SYS_ENDIAN
from ._data import DataWithBitSet, FieldDescAndData, PVRequest
from ._messages import (AcknowledgeMarker, ApplicationCommand,
                        ChannelDestroyRequest, ChannelDestroyResponse,
                        ChannelFieldInfoRequest, ChannelFieldInfoResponse,
                        ChannelGetRequest, ChannelGetResponse,
                        ChannelMonitorRequest, ChannelMonitorResponse,
                        ChannelProcessRequest, ChannelProcessResponse,
                        ChannelPutGetRequest, ChannelPutGetResponse,
                        ChannelPutRequest, ChannelPutResponse,
                        ChannelRequestCancel, ChannelRequestDestroy,
                        ConnectionValidatedResponse,
                        ConnectionValidationRequest,
                        ConnectionValidationResponse, CreateChannelRequest,
                        CreateChannelResponse, EndianSetting, Message,
                        MessageFlags, MessageHeaderBE, MessageHeaderLE,
                        MonitorSubcommand, SetByteOrder, SetMarker, Status,
                        Subcommand, _StatusOK, messages, read_from_bytestream)
from ._state import ChannelState, CircuitState, RequestState, get_exception
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
        self._ioids = {}  # map ioid to Channel
        # is ioids at the right level? should it be per channel?
        self.event_add_commands = {}  # map subscriptionid to EventAdd command
        # There are only used by the convenience methods, to auto-generate ids.
        if our_role is CLIENT:
            self._channel_id_counter = ThreadsafeCounter(
                dont_clash_with=self.channels
            )
        else:
            self._channel_id_counter = ThreadsafeCounter(
                dont_clash_with=self.channels_sid
            )
        self._ioid_counter = ThreadsafeCounter(dont_clash_with=self._ioids)
        self._sub_counter = ThreadsafeCounter(dont_clash_with=self.event_add_commands)
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

    def send(self, *commands,
             extra: Optional[Dict] = None) -> List[Union[bytes, memoryview]]:
        """
        Convert one or more high-level Commands into buffers of bytes that may
        be broadcast together in one TCP packet. Update our internal
        state machine.

        Parameters
        ----------
        *commands :
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
        for command in commands:
            self.log.debug("Serializing %r", command, extra=tags)

            if self.our_role == CLIENT:
                role_flag = pva.MessageFlags.FROM_CLIENT
            else:
                role_flag = pva.MessageFlags.FROM_SERVER

            if isinstance(command, (SetByteOrder, SetMarker, AcknowledgeMarker)):
                # Control messages handled here
                command.flags = command.flags | role_flag
                buffers_to_send.append(memoryview(command))
            else:
                if command._ENDIAN == pva.LITTLE_ENDIAN:
                    header_cls = MessageHeaderLE
                    endian_flag = pva.MessageFlags.LITTLE_ENDIAN
                else:
                    header_cls = MessageHeaderBE
                    endian_flag = pva.MessageFlags.BIG_ENDIAN

                payload = memoryview(command.serialize(cache=self.cache))
                header = header_cls(
                    flags=(pva.MessageFlags.APP_MESSAGE |
                           role_flag | endian_flag),
                    command=command.ID,
                    payload_size=len(payload)
                )

                command.header = header
                buffers_to_send.append(header)
                buffers_to_send.append(payload)

            self._process_command(self.our_role, command)

        return buffers_to_send

    def recv(self, *buffers
             ) -> typing.Generator[Tuple[Union[Message, ConnectionState],
                                         Optional[int]],
                                   None, None]:
        """
        Parse commands from buffers received over TCP.

        When the caller is ready to process the commands, each command should
        first be passed to :meth:`VirtualCircuit.process_command` to validate
        it against the protocol and update the VirtualCircuit's state.

        Parameters
        ----------
        *buffers :
            any number of bytes-like buffers

        Yields
        ------
        command : Message
            The command/message.

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
            command, self._data, bytes_consumed = decoded

            if isinstance(self._data, memoryview):
                self._data = bytearray(self._data)

            if segmented is CLEAR_SEGMENTS:
                self._segment_state.clear()
            elif segmented is not None:
                self._segment_state.append(segmented)
                continue

            if command is NEED_DATA:
                self.log.debug(
                    "%d bytes are cached. Need %d more bytes to parse next "
                    "command.", len_data, num_bytes_needed)
                break

            self.log.debug("%d bytes -> %r", bytes_consumed, command)
            yield command, None

    def process_command(self, command: Message):
        """
        Update internal state machine and raise if protocol is violated.

        Received commands should be passed through here before any additional
        processing by a server or client layer.
        """
        self._process_command(self.their_role, command)

    def _get_channel_from_command(self, command: ChannelMessage) -> Channel:
        """
        Get the :class:`Channel` instance associated with the given command.

        Parameters
        ----------
        command : Message
        """
        cid = getattr(command, 'client_chid', None)
        if cid is not None:
            return self.channels[cid]

        sid = getattr(command, 'server_chid', None)
        if sid is not None:
            return self.channels_sid[sid]

        ioid = getattr(command, 'ioid', None)
        if ioid is None:
            err = get_exception(self.our_role, command)
            raise err('Unable to determine channel information')

        return self._ioids[ioid]['channel']

    def _process_channel_creation(self, role: Role,
                                  command: CreateChannelRequest):
        """
        Separately process channel creation, as it may possibly work on more
        than one channel at a time.
        """
        channels = []

        for request in command.channels:
            cid = request['id']
            try:
                chan = self.channels[cid]
            except KeyError:
                chan = self.create_channel(request['channel_name'], cid=cid)
                channels.append((request, chan))

        for request, chan in channels:
            transitions = chan.process_command(command)
            self.channels[request['id']] = chan
            for transition in transitions:
                chan.state_changed(*transition)

    def _process_channel_command(self, role: Role, command: ChannelMessage):
        """
        Process a command related to a channel.

        Parameters
        ----------
        role : ``CLIENT`` or ``SERVER``
        command : Message
        """
        if isinstance(command, CreateChannelRequest):
            return self._process_channel_creation(role, command)

        try:
            chan = self._get_channel_from_command(command)
        except KeyError:
            err = get_exception(self.our_role, command)
            raise err("Unknown ID")

        # Update the state machine of the pertinent Channel.  If this is not a
        # valid command, the state machine will raise here. Stash the state
        # transitions in a local var, run the callbacks at the end.
        transitions = chan.process_command(command)
        ioid_info = None

        ioid = getattr(command, 'ioid', None)
        if ioid is not None:
            try:
                ioid_info = self._ioids[ioid]
            except KeyError:
                monitor = isinstance(command, (ChannelMonitorRequest,
                                               ChannelMonitorResponse))
                ioid_info = dict(
                    channel=chan,
                    state=RequestState(monitor)
                )
                self._ioids[ioid] = ioid_info

        subcommand = getattr(command, 'subcommand', None)

        if subcommand is not None:
            ioid_state = ioid_info['state']
            ioid_state.process_subcommand(subcommand)

        if isinstance(command, CreateChannelResponse):
            self.channels_sid[command.server_chid] = chan
        elif isinstance(command, ChannelFieldInfoRequest):
            ...
        elif isinstance(command, ChannelFieldInfoResponse):
            ...
        elif isinstance(command, (ChannelGetRequest,
                                  ChannelMonitorRequest)):
            ...
        elif isinstance(command, ChannelPutResponse):
            if command.status.is_successful:
                if command.subcommand == Subcommand.INIT:
                    interface = command.put_structure_if
                    self.cache.ioid_interfaces[ioid] = interface
                elif command.subcommand == Subcommand.DEFAULT:
                    ...
        elif isinstance(command, ChannelGetResponse):
            if command.status.is_successful:
                if command.subcommand == Subcommand.INIT:
                    interface = command.pv_structure_if
                    self.cache.ioid_interfaces[ioid] = interface
                elif command.subcommand == Subcommand.GET:
                    ...
        elif isinstance(command, ChannelMonitorResponse):
            if command.subcommand == Subcommand.INIT:
                if command.status.is_successful:
                    interface = command.pv_structure_if
                    self.cache.ioid_interfaces[ioid] = interface
            elif command.subcommand == Subcommand.DEFAULT:
                ...

        if (isinstance(command, ChannelRequestDestroy) or
                subcommand == Subcommand.DESTROY):
            self._ioids.pop(ioid)
            self.cache.ioid_interfaces.pop(ioid)

        # We are done. Run the Channel state change callbacks.
        for transition in transitions:
            chan.state_changed(*transition)

    def _process_command(self, role: Role, command: Message):
        """
        All commands go through here.

        Parameters
        ----------
        role : ``CLIENT`` or ``SERVER``
        command : Message
        """
        if command is DISCONNECTED:
            self.states.disconnect()
            return

        # Filter for Commands that are pertinent to a specific Channel, as
        # opposed to the Circuit as a whole:
        if isinstance(command, CreateChannelRequest):
            return self._process_channel_creation(role, command)

        if isinstance(command, (CreateChannelResponse,
                                ChannelFieldInfoRequest, ChannelFieldInfoResponse,
                                ChannelDestroyRequest, ChannelDestroyResponse,
                                ChannelGetRequest, ChannelGetResponse, ChannelMonitorRequest,
                                ChannelMonitorResponse, ChannelPutRequest, ChannelPutResponse,
                                ChannelProcessRequest, ChannelProcessResponse,
                                ChannelPutGetRequest, ChannelPutGetResponse,
                                ChannelRequestDestroy, ChannelRequestCancel)):
            return self._process_channel_command(role, command)

        if any((hasattr(command, 'server_chid'),
                hasattr(command, 'client_chid'),
                hasattr(command, 'ioid'))):
            raise RuntimeError(f'Channel-specific command fell through: '
                               f'TODO {command}')

        # Otherwise, this Command affects the state of this circuit, not a
        # specific Channel.
        if isinstance(command, SetByteOrder):
            fixed = (command.byte_order_setting == EndianSetting.use_server_byte_order)
            if self.our_role == SERVER:
                self.our_order = command.byte_order
                self.their_order = None
                self.fixed_recv_order = None
                self.messages = messages[(self.our_order,
                                          MessageFlags.FROM_SERVER)]
            else:
                self.our_order = command.byte_order
                self.their_order = command.byte_order
                self.fixed_recv_order = (self.their_order if fixed else None)
                if fixed:
                    self.log.debug('Using fixed byte order for server messages'
                                   ': %s', self.fixed_recv_order.name)
                else:
                    self.log.debug('Using byte order from individual messages.')
                self.messages = messages[(self.our_order,
                                          MessageFlags.FROM_CLIENT)]
        elif isinstance(command, ConnectionValidationRequest):
            ...
        elif isinstance(command, ConnectionValidationResponse):
            ...
        elif isinstance(command, ConnectionValidatedResponse):
            ...

        status = getattr(command, 'status', None)
        if status is not None and (status.message or status.call_tree):
            self.log.debug('Command %s status: %s', type(command).__name__,
                           status)

        # Run the circuit's state machine.
        self.states.process_command_type(self.our_role, command)
        self.states.process_command_type(self.their_role, command)

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
            command=AcknowledgeMarker.ID,
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
        if data is not None:
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
        self.access_rights = None
        self.ioid_interfaces = {}

    @property
    def subscriptions(self):
        """
        Get cached EventAdd commands for this channel's active subscriptions.
        """
        return {k: v for k, v in self.circuit.event_add_commands.items()
                if v.sid == self.sid}

    def state_changed(self, role, old_state, new_state, command):
        '''State changed callback for subclass usage'''
        pass

    def process_command(self, command):
        if isinstance(command, CreateChannelResponse):
            self.sid = command.server_chid
        elif isinstance(command, ChannelFieldInfoResponse):
            field_info = getattr(command.field_if, '_pva_struct_',
                                 command.field_if)
            for line in field_info.summary().splitlines():
                self.circuit.log.debug('[%s] %s', self.name, line)

        transitions = []
        for role in (self.circuit.our_role, self.circuit.their_role):
            initial_state = self.states[role]
            try:
                self.states.process_command_type(role, command)
            except CaprotoError as ex:
                ex.channel = self
                raise

            new_state = self.states[role]
            # Assemble arguments needed by state_changed, to be called later.
            if initial_state is not new_state:
                transition = (role, initial_state, new_state, command)
                transitions.append(transition)
        return transitions


class ClientChannel(_BaseChannel):
    """An object encapsulating the state of the EPICS Channel on a Client.

    A ClientChannel may be created in one of two ways:
    (1) The user instantiates a ClientChannel with a name, server address,
    and optional cid. The server address is used to assign the ClientChannel to
    a VirtualCircuit. If no cid is given, a unique one is allocated by the
    VirtualCircuit.
    (2) A VirtualCircuit processes a CreateChannelRequest that refers to a cid
    that it has not yet seen. A ClientChannel will be automatically
    instantiated with the name and cid indicated that command and the address
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
            raise ValueError('Server ID unavailable')

        cls = self.circuit.messages[ApplicationCommand.DESTROY_CHANNEL]
        return cls(client_chid=self.cid, server_chid=self.sid)

    def read_interface(self, *, ioid=None,
                       sub_field_name='') -> ChannelFieldInfoRequest:
        """
        Generate a valid :class:`ChannelFieldInfoRequest`.
        """

        if ioid is None:
            ioid = self.circuit.new_ioid()
        cls = self.circuit.messages[ApplicationCommand.GET_FIELD]
        return cls(server_chid=self.sid,
                   ioid=ioid,
                   sub_field_name=sub_field_name,
                   )

    def read_init(self, *, ioid=None,
                  pvrequest: str = 'field()'
                  ) -> ChannelGetRequest:
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

        cls = self.circuit.messages[ApplicationCommand.GET]
        if not isinstance(pvrequest, PVRequest):
            pvrequest = PVRequest(data=pvrequest)

        return cls(server_chid=self.sid,
                   ioid=ioid,
                   subcommand=Subcommand.INIT,
                   pv_request=pvrequest,
                   )

    def read(self, ioid, interface) -> ChannelGetRequest:
        """
        Generate a valid :class:`ChannelGetRequest`.

        Parameters
        ----------
        ioid

        Returns
        -------
        ChannelGetRequest
        """
        # TODO state machine for get requests?
        cls = self.circuit.messages[ApplicationCommand.GET]
        return cls(server_chid=self.sid,
                   ioid=ioid,
                   subcommand=Subcommand.GET,  # DEFAULT is acceptable too
                   interface=dict(pv_data=interface),
                   )

    def subscribe_init(self, *,
                       ioid=None,
                       pvrequest: str = 'field(value)',
                       queue_size=None) -> ChannelMonitorRequest:
        """
        Generate a valid :class:`...`.

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

        cls = self.circuit.messages[ApplicationCommand.MONITOR]
        return cls(server_chid=self.sid,
                   ioid=ioid,
                   subcommand=Subcommand.INIT,
                   pv_request=pvrequest,
                   )

    def subscribe_control(self, ioid, *, subcommand) -> ChannelMonitorRequest:
        """
        Generate a valid ...

        Parameters
        ----------
        ioid
        subcommand : MonitorSubcommand
            PIPELINE, START, STOP, DESTROY

        Returns
        -------
        ChannelMonitorRequest
        """
        assert subcommand in MonitorSubcommand
        cls = self.circuit.messages[ApplicationCommand.MONITOR]
        return cls(server_chid=self.sid,
                   ioid=ioid,
                   subcommand=subcommand,
                   )

    def write_init(self, *,
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
        return cls(server_chid=self.sid,
                   ioid=ioid,
                   subcommand=Subcommand.INIT,
                   pv_request=pvrequest,
                   )

    def write(self, ioid, data, bitset, *, interface=None) -> ChannelPutRequest:
        """
        Generate a valid :class:`ChannelPutRequest`.
        """
        cls = self.circuit.messages[ApplicationCommand.PUT]
        if bitset is None:
            raise ValueError(
                # TODO; should be determined based on the keys provided
                'Must supply a bitset; if all fields are to '
                'be written BitSet({0}) may be used.'
            )

        ret = cls(server_chid=self.sid,
                  ioid=ioid,
                  subcommand=Subcommand.DEFAULT,
                  put_data=DataWithBitSet(data=data,
                                          interface=interface,
                                          bitset=bitset),
                  )
        return ret


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

    def read_init(self, ioid, interface, *,
                  status: Status = _StatusOK,
                  ) -> ChannelGetResponse:
        """
        Generate a valid :class:`ChannelGetResponse`.

        Parameters
        ----------
        ioid

        Returns
        -------
        ChannelGetResponse
        """
        cls = self.circuit.messages[ApplicationCommand.GET]
        return cls(ioid=ioid,
                   subcommand=Subcommand.INIT,
                   pv_structure_if=interface,
                   status=status,
                   )

    def read(self, ioid, data,
             status: Status = _StatusOK,
             ) -> ChannelGetResponse:
        """
        Generate a valid :class:`ChannelGetResponse`.

        Parameters
        ----------
        ioid

        Returns
        -------
        ChannelGetResponse
        """
        # TODO state machine for subcommand requests?
        cls = self.circuit.messages[ApplicationCommand.GET]
        return cls(ioid=ioid,
                   subcommand=Subcommand.GET,  # DEFAULT is acceptable too
                   pv_data=data,
                   status=status,
                   )
