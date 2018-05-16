# A connection in caproto V3 is referred to as a VirtualCircuit. Let's just
# copy that nomenclature for now.

import itertools
import logging

from .introspection import summarize_field_info
from .const import SYS_ENDIAN, LITTLE_ENDIAN, BIG_ENDIAN
from .messages import (basic_types, DirectionFlag, ApplicationCommands, ControlCommands,
                       EndianSetting, read_from_bytestream, messages_grouped,
                       MessageHeaderBE, MessageHeaderLE, MessageTypeFlag,
                       EndianFlag, StatusType,
                       GetSubcommands,
                       )
from .messages import (Status, BeaconMessage, SetMarker, AcknowledgeMarker,
                       SetByteOrder, ConnectionValidationRequest,
                       ConnectionValidationResponse, Echo,
                       ConnectionValidatedResponse, SearchRequest,
                       SearchResponse, CreateChannelRequest,
                       CreateChannelResponse, ChannelGetRequest,
                       ChannelGetResponse, ChannelFieldInfoRequest,
                       ChannelFieldInfoResponse, ChannelDestroyRequest,
                       ChannelDestroyResponse)

from .state import (ChannelState, CircuitState, get_exception)
from .utils import (CLIENT, SERVER, NEED_DATA, DISCONNECTED,
                    CaprotoKeyError, CaprotoValueError, CaprotoRuntimeError,
                    CaprotoError,
                    )
from .serialization import SerializeCache
from .._utils import ThreadsafeCounter


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
        May be used by the server to prioritize requests when under high
        load. Lowest priority is 0; highest is 99.
    """
    def __init__(self, our_role, address):
        self.our_role = our_role
        if our_role is CLIENT:
            self.their_role = SERVER
            abbrev = 'cli'  # just for logger
        else:
            self.their_role = CLIENT
            abbrev = 'srv'
        self.address = address
        self.channels = {}  # map cid to Channel
        logger_name = f"{abbrev}.{address[0]}:{address[1]}"
        self.log = logging.getLogger(logger_name)
        self.states = CircuitState(self.channels)
        self._data = bytearray()
        self.channels_sid = {}  # map sid to Channel
        self._ioids = {}  # map ioid to Channel
        self.event_add_commands = {}  # map subscriptionid to EventAdd command
        # There are only used by the convenience methods, to auto-generate ids.
        self._channel_id_counter = ThreadsafeCounter()
        self._ioid_counter = ThreadsafeCounter()
        self._sub_counter = ThreadsafeCounter()
        # A fixed byte order, required by the server
        self.our_order = SYS_ENDIAN
        self.their_order = None
        self.fixed_recv_order = None
        self.messages = None
        self.cache = SerializeCache(ours={}, theirs={},
                                    user_types=basic_types.copy(),  # TODO
                                    ioid_interfaces={})

    def set_byte_order(self):
        """
        Generate a valid :class:`SetByteOrder`.

        Parameters
        ----------

        Returns
        -------
        SetByteOrder
        """
        return SetByteOrder()

    def acknowledge_marker(self):
        """
        Generate a valid :class:`AcknowledgeMarker`.

        Parameters
        ----------

        Returns
        -------
        AcknowledgeMarker
        """
        return AcknowledgeMarker()

    def validate_connection(self, client_buffer_size, client_registry_size,
                            connection_qos, auth_nz=''):
        """
        Generate a valid :class:`_ConnectionValidationResponse`.

        Parameters
        ----------
        client_buffer_size : int
            Client buffer size
        client_registry_size : int
            Client registry size
        connection_qos  : int
            Connection QOS
        auth_nz  : str, optional
            Authorization string

        Returns
        -------
        AuthorizationResponse
        """
        cls = self.messages[ApplicationCommands.CONNECTION_VALIDATION]
        return cls(client_buffer_size=client_buffer_size,
                   client_registry_size=client_registry_size,
                   connection_qos=connection_qos,
                   auth_nz=auth_nz)

    @property
    def host(self):
        '''Peer host name'''
        return self.address[0]

    @property
    def port(self):
        '''Port number'''
        return self.address[1]

    def __repr__(self):
        return (f"<VirtualCircuit host={self.host} port={self.port} "
                f"our_role={self.our_role}> logger_name={self.log.name}>")

    def __eq__(self, other):
        return hash(self) == hash(other)

    def __hash__(self):
        return hash((self.address, self.our_role))

    def send(self, *commands):
        """
        Convert one or more high-level Commands into buffers of bytes that may
        be broadcast together in one TCP packet. Update our internal
        state machine.

        Parameters
        ----------
        *commands :
            any number of :class:`Message` objects

        Returns
        -------
        buffers_to_send : list
            list of buffers to send over a socket
        """
        buffers_to_send = []
        for command in commands:
            self._process_command(self.our_role, command)
            self.log.debug("Serializing %r", command)

            if isinstance(command, (SetByteOrder, SetMarker, AcknowledgeMarker)):
                buffers_to_send.append(memoryview(command))
            else:
                header_cls = (MessageHeaderLE
                              if command._ENDIAN == LITTLE_ENDIAN
                              else MessageHeaderBE)

                payload = memoryview(command.serialize(cache=self.cache))
                header = header_cls(message_type=MessageTypeFlag.APP_MESSAGE,
                                    direction=DirectionFlag.FROM_CLIENT,
                                    endian=command._ENDIAN,
                                    command=command.ID,
                                    payload_size=len(payload)
                                    )

                command.header = header

                buffers_to_send.append(memoryview(header))
                buffers_to_send.append(payload)

        return buffers_to_send

    def recv(self, *buffers):
        """
        Parse commands from buffers received over TCP.

        When the caller is ready to process the commands, each command should
        first be passed to :meth:`VirtualCircuit.process_command` to validate
        it against the protocol and update the VirtualCircuit's state.

        Parameters
        ----------
        *buffers :
            any number of bytes-like buffers

        Returns
        -------
        ``(commands, num_bytes_needed)``
        """
        total_received = sum(len(byteslike) for byteslike in buffers)
        if total_received == 0:
            self.log.debug('Zero-length recv; sending disconnect notification')
            yield DISCONNECTED, None
            return

        self.log.debug("Received %d bytes.", total_received)
        self._data += b''.join(buffers)

        while True:
            res = read_from_bytestream(self._data, self.their_role,
                                       byte_order=self.fixed_recv_order,
                                       cache=self.cache)
            (self._data, command, bytes_consumed, num_bytes_needed) = res
            len_data = len(self._data)  # just for logging
            if type(command) is not NEED_DATA:
                self.log.debug("%d bytes -> %r", bytes_consumed, command)
                yield command, None
            else:
                self.log.debug("%d bytes are cached. Need more bytes to parse "
                               "next command.", len_data)
                yield command, num_bytes_needed

    def process_command(self, command):
        """
        Update internal state machine and raise if protocol is violated.

        Received commands should be passed through here before any additional
        processing by a server or client layer.
        """
        self._process_command(self.their_role, command)

    def _process_command(self, role, command):
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
                                ChannelGetRequest, ChannelGetResponse)):
            if isinstance(command, CreateChannelRequest):
                print(command.channels)
                for info in [command.channels]:
                    cid = info['id']
                    chan = self.channels[cid]
                    # TODO: only one supported now - also by C++ server, AFAIR
                    break
            else:
                if hasattr(command, 'client_chid'):
                    cid = command.client_chid
                    chan = self.channels[cid]
                elif hasattr(command, 'server_chid'):
                    chan = self.channels_sid[command.server_chid]
                else:
                    ioid = command.ioid
                    chan = self._ioids[ioid]

            # Update the state machine of the pertinent Channel.
            # If this is not a valid command, the state machine will raise
            # here. Stash the state transitions in a local var and run the
            # callbacks at the end.
            transitions = chan.process_command(command)

            if isinstance(command, CreateChannelResponse):
                self.channels_sid[command.server_chid] = chan
            elif isinstance(command, ChannelFieldInfoRequest):
                self._ioids[command.ioid] = chan
            elif isinstance(command, ChannelFieldInfoResponse):
                self._ioids.pop(command.ioid)
            elif isinstance(command, ChannelGetRequest):
                ioid = command.ioid
                self._ioids[command.ioid] = chan
            elif isinstance(command, ChannelGetResponse):
                ioid = command.ioid
                if command.subcommand == GetSubcommands.INIT:
                    interface = command.pv_structure_if
                    self.cache.ioid_interfaces[ioid] = interface
                elif command.subcommand == GetSubcommands.GET:
                    ...
                elif command.subcommand == GetSubcommands.DESTROY:
                    self._ioids.pop(ioid)
                    self.cache.ioid_interfaces.pop(ioid)

            # We are done. Run the Channel state change callbacks.
            for transition in transitions:
                chan.state_changed(*transition)
        else:
            # Otherwise, this Command affects the state of this circuit, not a
            # specific Channel.
            if isinstance(command, SetByteOrder):
                fixed = (command.byte_order_setting ==
                         EndianSetting.use_server_byte_order)
                if self.our_role == SERVER:
                    self.our_order = command.byte_order
                    self.their_order = None
                    self.fixed_recv_order = None
                    self.messages = messages_grouped[
                        (self.our_order, DirectionFlag.FROM_SERVER)]
                else:
                    self.our_order = command.byte_order
                    self.their_order = command.byte_order
                    self.fixed_recv_order = (self.their_order if fixed else None)
                    if fixed:
                        self.log.debug('Using fixed byte order for server messages'
                                       ': %s', self.fixed_recv_order.name)
                    else:
                        self.log.debug('Using byte order from individual messages.')
                    self.messages = messages_grouped[
                        (self.our_order, DirectionFlag.FROM_CLIENT)]
            elif isinstance(command, ConnectionValidationRequest):
                ...
            elif isinstance(command, ConnectionValidationResponse):
                ...
            elif isinstance(command, ConnectionValidatedResponse):
                ...

            if isinstance(command, Status):
                status = StatusType(command.status_type)
                if status == StatusType.OK:
                    ...
                else:
                    self.log.debug('Command status returned %s (message=%s) '
                                   '(call tree=%s)',
                                   status.name, command.message,
                                   command.call_tree)

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
        while True:
            i = self._channel_id_counter()
            if i not in self.channels:
                return i

    def new_subscriptionid(self):
        """
        This is used by the convenience methods to obtain an unused integer ID.
        It does not update any important state.
        """
        # Return the next sequential unused id. Wrap back to 0 on overflow.
        while True:
            i = self._sub_counter()
            if i not in self.event_add_commands:
                return i

    def new_ioid(self):
        """
        This is used by the convenience methods to obtain an unused integer ID.
        It does not update any important state.
        """
        # Return the next sequential unused id. Wrap back to 0 on overflow.
        while True:
            i = self._ioid_counter()
            if i not in self._ioids:
                return i


class _BaseChannel:
    # Base class for ClientChannel and ServerChannel, which add convenience
    # methods for composing requests and repsponses, respectively. All of the
    # important code is here in the base class.
    def __init__(self, name, circuit, cid=None):
        self.endian = None  # TODO
        self.name = name
        self.circuit = circuit
        if cid is None:
            cid = self.circuit.new_channel_id()
        self.cid = cid
        self.circuit.channels[self.cid] = self
        self.states = ChannelState(self.circuit.states)
        # These will be set when the circuit processes CreateChanResponse.
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
            for depth, info in summarize_field_info(
                    self.field_info, user_types=self.circuit.cache.user_types,
                    values=None):
                self.circuit.log.debug('[%s]%s%s', self.name, '    ' * depth,
                                       info)
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
    (2) A VirtualCircuit processes a CreateChanRequest that refers to a cid
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

    def create(self):
        """
        Generate a valid :class:`CreateChanRequest`.

        Returns
        -------
        CreateChanRequest
        """
        create_cls = self.circuit.messages[ApplicationCommands.CREATE_CHANNEL]
        return create_cls(count=1, channels={'id': self.cid,
                                             'channel_name': self.name})

    def disconnect(self):
        """
        Generate a valid :class:`ClearChannelRequest`.

        Returns
        -------
        ClearChannelRequest
        """
        if self.sid is None:
            return
        cls = self.circuit.messages[ApplicationCommands.DESTROY_CHANNEL]
        return cls(client_chid=self.cid, server_chid=self.sid)

    def read_interface(self, *, ioid=None, sub_field_name=''):
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

    def read_init(self, *, ioid=None, pvrequest_if=None, pvrequest=None):
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
        # if pvrequest_if is None:
        # TODO
        pvrequest_if = 'field(value)'
        pvrequest = dict(field=dict(value=None))

        if ioid is None:
            ioid = self.circuit.new_ioid()

        cls = self.circuit.messages[ApplicationCommands.GET]
        return cls(server_chid=self.sid,
                   ioid=ioid,
                   subcommand=GetSubcommands.INIT,
                   pv_request_if=pvrequest_if,
                   pv_request=pvrequest,
                   )

    def read(self, ioid, interface):
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
                   subcommand=GetSubcommands.GET,
                   interface=dict(pv_data=interface),
                   )

    def write(self, data, data_type=None, data_count=None, metadata=None):
        """
        Generate a valid :class:`WriteNotifyRequest`.

        Parameters
        ----------
        data : tuple, ``numpy.ndarray``, ``array.array``, or bytes
        metadata : ``ctypes.BigEndianStructure`` or tuple
            Status and control metadata for the values

        Returns
        -------
        WriteNotifyRequest
        """


class ServerChannel(_BaseChannel):
    """
    A server-side Channel.

    Parameters
    ----------
    name : string
        Channnel name (PV)
    circuit : VirtualCircuit
    cid : integer, optional
    protocol_version : integer, optional
        Default is ``DEFAULT_PROTOCOL_VERSION``.
    """

    def create(self, native_data_type, native_data_count, sid):
        """
        Generate a valid :class:`CreateChanResponse`.

        Parameters
        ----------
        native_data_type : a :class:`DBR_TYPE` or its designation integer ID
            Default Channel Access data type.
        native_data_count : integer
            Default number of values
        sid : integer
            server-allocated sid

        Returns
        -------
        CreateChanResponse
        """
        command = CreateChanResponse(native_data_type, native_data_count,
                                     self.cid, sid)
        return command

    def create_fail(self):
        """
        Generate a valid :class:`CreateChFailResponse`.

        Returns
        -------
        CreateChFailResponse
        """
        command = CreateChFailResponse(self.cid)
        return command

    def read(self, data, ioid, data_type=None, data_count=None, status=1, *,
             metadata=None):
        """
        Generate a valid :class:`ReadNotifyResponse`.

        Parameters
        ----------
        data : tuple, ``numpy.ndarray``, ``array.array``, or bytes
        ioid : integer
        data_type : a :class:`DBR_TYPE` or its designation integer ID, optional
            Requested Channel Access data type. Default is the channel's
            native data type, which can be checked in the Channel's attribute
            :attr:`native_data_type`.
        data_count : integer, optional
            Requested number of values. Default is the channel's native data
            count, which can be checked in the Channel's attribute
            :attr:`native_data_count`.
        status : integer, optional
            Default is 1 (success).
        metadata : ``ctypes.BigEndianStructure`` or tuple
            Status and control metadata for the values

        Returns
        -------
        ReadNotifyResponse
        """
        data_type, data_count = self._fill_defaults(data_type, data_count)
        command = ReadNotifyResponse(data, data_type, data_count, status,
                                     ioid, metadata=metadata)
        return command

    def write(self, ioid, data_type=None, data_count=None, status=1):
        """
        Generate a valid :class:`WriteNotifyResponse`.

        Parameters
        ----------
        ioid : integer
        data_type : a :class:`DBR_TYPE` or its designation integer ID, optional
            Requested Channel Access data type. Default is the channel's
            native data type, which can be checked in the Channel's attribute
            :attr:`native_data_type`.
        data_count : integer, optional
            Requested number of values. Default is the channel's native data
            count, which can be checked in the Channel's attribute
            :attr:`native_data_count`.
        status : integer, optional
            Default is 1 (success).

        Returns
        -------
        WriteNotifyResponse
        """
        data_type, data_count = self._fill_defaults(data_type, data_count)
        command = WriteNotifyResponse(data_type, data_count, status, ioid)
        return command

    def subscribe(self, data, subscriptionid, data_type=None,
                  data_count=None, status_code=32, metadata=None):
        """
        Generate a valid :class:`EventAddResponse`.

        Parameters
        ----------
        data : tuple, ``numpy.ndarray``, ``array.array``, or bytes
        subscriptionid : integer
        data_type : a :class:`DBR_TYPE` or its designation integer ID, optional
            Requested Channel Access data type. Default is the channel's
            native data type, which can be checked in the Channel's attribute
            :attr:`native_data_type`.
        data_count : integer, optional
            Requested number of values. Default is the channel's native data
            count, which can be checked in the Channel's attribute
            :attr:`native_data_count`.
        status_code : integer, optional
            Default is 32 (???).
        metadata : ``ctypes.BigEndianStructure`` or tuple
            Status and control metadata for the values

        Returns
        -------
        EventAddResponse
        """
        # TODO It's unclear what the status_code means here.
        data_type, data_count = self._fill_defaults(data_type, data_count)
        command = EventAddResponse(data, data_type, data_count, status_code,
                                   subscriptionid, metadata=metadata)
        return command

    def unsubscribe(self, subscriptionid, data_type=None):
        """
        Generate a valid :class:`EventCancelResponse`.

        Parameters
        ----------
        subscriptionid : integer
        data_type : a :class:`DBR_TYPE` or its designation integer ID, optional
            Requested Channel Access data type. Default is the channel's
            native data type, which can be checked in the Channel's attribute
            :attr:`native_data_type`.

        Returns
        -------
        EventCancelResponse
        """
        data_type, _ = self._fill_defaults(data_type, None)
        command = EventCancelResponse(data_type, self.sid, subscriptionid)
        return command

    def disconnect(self):
        """
        Generate a valid :class:`ServerDisconnResponse`.

        Returns
        -------
        ServerDisconnResponse
        """
        command = ServerDisconnResponse(self.cid)
        return command
