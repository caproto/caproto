# A connection in caproto V3 is referred to as a VirtualCircuit. Let's just
# copy that nomenclature for now.
import dataclasses
import logging
import typing

from .. import pva
from .._log import ComposableLogAdapter
from .._utils import ThreadsafeCounter
from ._core import SYS_ENDIAN
from ._messages import (AcknowledgeMarker, ApplicationCommands,
                        ChannelDestroyRequest, ChannelDestroyResponse,
                        ChannelFieldInfoRequest, ChannelFieldInfoResponse,
                        ChannelGetRequest, ChannelGetResponse,
                        ChannelMonitorRequest, ChannelMonitorResponse,
                        ChannelProcessRequest, ChannelProcessResponse,
                        ChannelPutGetRequest, ChannelPutGetResponse,
                        ChannelPutRequest, ChannelPutResponse,
                        ConnectionValidatedResponse,
                        ConnectionValidationRequest,
                        ConnectionValidationResponse, CreateChannelRequest,
                        CreateChannelResponse, EndianSetting, MessageBase,
                        MessageFlags, MessageHeaderBE, MessageHeaderLE,
                        MonitorSubcommands, SetByteOrder, SetMarker,
                        Subcommands, _StatusBase, messages,
                        read_from_bytestream)
# from ._pvrequest import PVRequestStruct
from ._state import ChannelState, CircuitState, RequestState, get_exception
from ._utils import (CLEAR_SEGMENTS, CLIENT, DISCONNECTED, NEED_DATA, SERVER,
                     CaprotoError, CaprotoRuntimeError, Role)


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
        self.states = CircuitState(self.channels)
        self._data = bytearray()
        self._segment_state = []
        self.channels_sid = {}  # map sid to Channel
        self._ioids = {}  # map ioid to Channel
        self.event_add_commands = {}  # map subscriptionid to EventAdd command
        # There are only used by the convenience methods, to auto-generate ids.
        self._channel_id_counter = ThreadsafeCounter(dont_clash_with=self.channels)
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

    def set_byte_order(self, endian_setting: EndianSetting) -> SetByteOrder:
        """
        Generate a valid :class:`SetByteOrder`.

        Returns
        -------
        SetByteOrder
        """
        return SetByteOrder(endian_setting)

    def acknowledge_marker(self) -> AcknowledgeMarker:
        """
        Generate a valid :class:`AcknowledgeMarker`.

        Returns
        -------
        AcknowledgeMarker
        """
        return AcknowledgeMarker()

    def validate_connection(self,
                            client_buffer_size: int,
                            client_registry_size: int,
                            connection_qos: int,
                            auth_nz: str = 'ca',
                            auth_args: dict = None,
                            ) -> ConnectionValidationResponse:
        """
        Generate a valid :class:`_ConnectionValidationResponse`.

        Parameters
        ----------
        client_buffer_size : int
            Client buffer size.

        client_registry_size : int
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
        cls = self.messages[ApplicationCommands.CONNECTION_VALIDATION]

        return cls(client_buffer_size=client_buffer_size,
                   client_registry_size=client_registry_size,
                   connection_qos=connection_qos,
                   auth_nz=auth_nz,
                   **(auth_args or {}),
                   )

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

    def send(self, *commands, extra: typing.Dict) -> typing.List[bytes]:
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
        buffers_to_send = []
        tags = {'their_address': self.address,
                'our_address': self.our_address,
                'direction': '--->>>',
                'role': repr(self.our_role)}
        tags.update(extra or {})
        for command in commands:
            self._process_command(self.our_role, command)
            self.log.debug("Serializing %r", command, extra=tags)

            if isinstance(command, (SetByteOrder, SetMarker, AcknowledgeMarker)):
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
                           pva.MessageFlags.FROM_CLIENT |
                           endian_flag),
                    command=command.ID,
                    payload_size=len(payload)
                )

                command.header = header
                buffers_to_send.append(memoryview(header))
                buffers_to_send.append(payload)

        return buffers_to_send

    def recv(self, *buffers
             ) -> typing.Generator[typing.Tuple[typing.List, int],
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

            if command is not NEED_DATA:
                self.log.debug("%d bytes -> %r", bytes_consumed, command)
                yield command, None
            else:
                self.log.debug("%d bytes are cached. Need more bytes to parse "
                               "next command.", len_data)
                yield command, num_bytes_needed

    def process_command(self, command: MessageBase):
        """
        Update internal state machine and raise if protocol is violated.

        Received commands should be passed through here before any additional
        processing by a server or client layer.
        """
        self._process_command(self.their_role, command)

    def _process_command(self, role: Role, command: MessageBase):
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
        if isinstance(command, (CreateChannelRequest, CreateChannelResponse,
                                ChannelFieldInfoRequest, ChannelFieldInfoResponse,
                                ChannelDestroyRequest, ChannelDestroyResponse,
                                ChannelGetRequest, ChannelGetResponse, ChannelMonitorRequest,
                                ChannelMonitorResponse, ChannelPutRequest, ChannelPutResponse,
                                ChannelProcessRequest, ChannelProcessResponse,
                                ChannelPutGetRequest, ChannelPutGetResponse)):
            if isinstance(command, CreateChannelRequest):
                for info in command.channels:
                    cid = info['id']
                    chan = self.channels[cid]
                    # TODO: only one supported now - also by C++ server, AFAIR
                    break
            else:
                try:
                    if hasattr(command, 'client_chid'):
                        cid = command.client_chid
                        chan = self.channels[cid]
                    elif hasattr(command, 'server_chid'):
                        chan = self.channels_sid[command.server_chid]
                    else:
                        ioid = command.ioid
                        chan = self._ioids[ioid]['channel']
                except KeyError:
                    err = get_exception(self.our_role, command)
                    raise err("Unknown ID")

            # Update the state machine of the pertinent Channel.  If this is
            # not a valid command, the state machine will raise here. Stash the
            # state transitions in a local var, run the callbacks at the end.
            transitions = chan.process_command(command)
            ioid_info = None

            try:
                ioid = command.ioid
            except AttributeError:
                ioid = None
            else:
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
                ioid_state.process_subcommand(command.subcommand)

            if isinstance(command, CreateChannelResponse):
                self.channels_sid[command.server_chid] = chan
            elif isinstance(command, ChannelFieldInfoRequest):
                ...
            elif isinstance(command, ChannelFieldInfoResponse):
                self._ioids.pop(ioid)
            elif isinstance(command, (ChannelGetRequest,
                                      ChannelMonitorRequest)):
                ...
            elif isinstance(command, ChannelPutResponse):
                if command.is_successful:
                    if command.subcommand == Subcommands.INIT:
                        interface = command.put_structure_if
                        self.cache.ioid_interfaces[ioid] = interface
                    elif command.subcommand == Subcommands.DEFAULT:
                        ...
            elif isinstance(command, ChannelGetResponse):
                if command.is_successful:
                    if command.subcommand == Subcommands.INIT:
                        interface = command.pv_structure_if
                        self.cache.ioid_interfaces[ioid] = interface
                    elif command.subcommand == Subcommands.GET:
                        ...
            elif isinstance(command, ChannelMonitorResponse):
                if command.subcommand == Subcommands.INIT:
                    if command.is_successful:
                        interface = command.pv_structure_if
                        self.cache.ioid_interfaces[ioid] = interface
                elif command.subcommand == Subcommands.DEFAULT:
                    ...

            if subcommand == Subcommands.DESTROY:
                self._ioids.pop(ioid)
                self.cache.ioid_interfaces.pop(ioid)

            # We are done. Run the Channel state change callbacks.
            for transition in transitions:
                chan.state_changed(*transition)
        else:
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

            if isinstance(command, _StatusBase) and command.has_message:
                self.log.debug(
                    'Command status returned %s (message=%s) (call tree=%s)',
                    command.name, command.message, command.call_tree
                )

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


class _BaseChannel:
    # Base class for ClientChannel and ServerChannel, which add convenience
    # methods for composing requests and repsonses, respectively. All of the
    # important code is here in the base class.
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
            self.field_info = command.field_if
            for line in self.field_info.summary().splitlines():
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
        create_cls = self.circuit.messages[ApplicationCommands.CREATE_CHANNEL]
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
            return
        cls = self.circuit.messages[ApplicationCommands.DESTROY_CHANNEL]
        return cls(client_chid=self.cid, server_chid=self.sid)

    def read_interface(self, *, ioid=None,
                       sub_field_name='') -> ChannelFieldInfoRequest:
        """
        Generate a valid :class:`ChannelFieldInfoRequest`.
        """

        if ioid is None:
            ioid = self.circuit.new_ioid()
        cls = self.circuit.messages[ApplicationCommands.GET_FIELD]
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
        pvrequest_if
        pvrequest

        Returns
        -------
        ChannelGetRequest
        """
        if ioid is None:
            ioid = self.circuit.new_ioid()

        cls = self.circuit.messages[ApplicationCommands.GET]
        return cls(server_chid=self.sid,
                   ioid=ioid,
                   subcommand=Subcommands.INIT,
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
        cls = self.circuit.messages[ApplicationCommands.GET]
        return cls(server_chid=self.sid,
                   ioid=ioid,
                   subcommand=Subcommands.GET,
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
        pvrequest_if
        pvrequest

        Returns
        -------
        ChannelMonitorRequest
        """
        if ioid is None:
            ioid = self.circuit.new_ioid()

        cls = self.circuit.messages[ApplicationCommands.MONITOR]
        return cls(server_chid=self.sid,
                   ioid=ioid,
                   subcommand=Subcommands.INIT,
                   pv_request=pvrequest,
                   )

    def subscribe_control(self, ioid, *, subcommand) -> ChannelMonitorRequest:
        """
        Generate a valid ...

        Parameters
        ----------
        ioid
        subcommand : MonitorSubcommands
            PIPELINE, START, STOP, DESTROY

        Returns
        -------
        ChannelMonitorRequest
        """
        assert subcommand in MonitorSubcommands
        cls = self.circuit.messages[ApplicationCommands.MONITOR]
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

        cls = self.circuit.messages[ApplicationCommands.PUT]
        return cls(server_chid=self.sid,
                   ioid=ioid,
                   subcommand=Subcommands.INIT,
                   pv_request=pvrequest,
                   )

    def write(self, ioid, interface, dataclass, bitset) -> ChannelPutRequest:
        """
        Generate a valid :class:`ChannelPutRequest`.
        """
        cls = self.circuit.messages[ApplicationCommands.PUT]
        if not isinstance(dataclass, dict):
            value = dataclasses.asdict(dataclass)

        if bitset is None:
            raise ValueError(
                'Must supply a bitset; if all fields are to '
                'be written BitSet({0}) may be used.'
            )

        put_data = {
            'data': value,
            'interface': interface,
            'bitset': bitset,
        }
        ret = cls(server_chid=self.sid,
                  ioid=ioid,
                  subcommand=Subcommands.DEFAULT,
                  put_data=put_data,
                  )
        return ret


class ServerChannel(_BaseChannel):
    """
    A server-side Channel.

    (TODO no server stuff yet)
    """

#    def create(self, native_data_type, native_data_count, sid):
#        """
#        Generate a valid :class:`CreateChanResponse`.
#
#        Parameters
#        ----------
#
#        Returns
#        -------
#        """
#
#    def create_fail(self):
#        """
#        Generate a valid :class:`CreateChFailResponse`.
#
#        Returns
#        -------
#        CreateChFailResponse
#        """
#
#    def read(self, data, ioid, data_type=None, data_count=None, status=1, *,
#             metadata=None):
#        """
#        Generate a valid :class:`ReadNotifyResponse`.
#
#        Parameters
#        ----------
#        data : tuple, ``numpy.ndarray``, ``array.array``, or bytes
#        ioid : integer
#
#        Returns
#        -------
#        """
#
#    def write(self, ioid, data_type=None, data_count=None, status=1):
#        """
#        Generate a valid :class:`WriteNotifyResponse`.
#
#        Parameters
#        ----------
#        ioid : integer
#
#        Returns
#        -------
#        """
#
#    def subscribe(self, data, subscriptionid, data_type=None,
#                  data_count=None, status_code=32, metadata=None):
#        """
#        Generate a valid :class:`EventAddResponse`.
#
#        Parameters
#        ----------
#
#        Returns
#        -------
#        """
#
#    def unsubscribe(self, subscriptionid, data_type=None):
#        """
#        Generate a valid :class:`EventCancelResponse`.
#
#        Parameters
#        ----------
#
#        Returns
#        -------
#        """
#
#    def disconnect(self):
#        """
#        Generate a valid :class:`ServerDisconnResponse`.
#
#        Returns
#        -------
#        ServerDisconnResponse
#        """
