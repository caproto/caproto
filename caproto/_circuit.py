# This module defines classes that encapsulate key abstractions in
# Channel Access: Channels and VirtualCircuits. Each VirtualCircuit is a
# companion to a TCP socket managed by a higher-level client or server
# implementation, updating its state in response to incoming and outgoing TCP
# bytestreams. Each Channel belongs to a circuit, and tracks state particular
# to that Channel. A ClientChannel provides convenience methods for composing
# Requests; a ServerChannel provides convenience methods for composing
# Responses.
import itertools
import logging
import collections

from ._commands import (AccessRightsResponse, CreateChFailResponse,
                        ClearChannelRequest, ClearChannelResponse,
                        ClientNameRequest, CreateChanRequest,
                        CreateChanResponse, EventAddRequest, EventAddResponse,
                        EventCancelRequest, EventCancelResponse,
                        HostNameRequest, ReadNotifyRequest, ReadNotifyResponse,
                        SearchResponse, ServerDisconnResponse,
                        VersionRequest, VersionResponse, WriteNotifyRequest,
                        WriteNotifyResponse, WriteRequest,
                        read_from_bytestream,)
from ._state import (ChannelState, CircuitState, get_exception)
from ._utils import (CLIENT, SERVER, NEED_DATA, DISCONNECTED, CaprotoKeyError,
                     CaprotoValueError, CaprotoRuntimeError, CaprotoError,
                     )
from ._dbr import (SubscriptionType, )
from ._constants import (DEFAULT_PROTOCOL_VERSION, MAX_ID)


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
    def __init__(self, our_role, address, priority):
        self.our_role = our_role
        if our_role is CLIENT:
            self.their_role = SERVER
            abbrev = 'cli'  # just for logger
        else:
            self.their_role = CLIENT
            abbrev = 'srv'
        self.address = address
        self.priority = priority
        self.channels = {}  # map cid to Channel
        logger_name = f"{abbrev}.{address[0]}:{address[1]}.{priority}"
        self.log = logging.getLogger(logger_name)
        self.states = CircuitState(self.channels)
        self._data = bytearray()
        self.channels_sid = {}  # map sid to Channel
        self._ioids = {}  # map ioid to Channel
        self.event_add_commands = {}  # map subscriptionid to EventAdd command
        # There are only used by the convenience methods, to auto-generate ids.
        self._channel_id_counter = itertools.count(0)
        self._ioid_counter = itertools.count(0)
        self._sub_counter = itertools.count(0)
        if priority is None and self.our_role is CLIENT:
            raise CaprotoRuntimeError("Client-side VirtualCircuit requires a "
                                      "non-None priority at initialization "
                                      "time.")

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

    @property
    def key(self):
        if self.priority is None:
            raise CaprotoRuntimeError("This VirtualCircuit has not received a "
                                      "VersionRequest and does not know its "
                                      "priority. Therefore, it does not yet "
                                      "have a key.")
        return self.address, self.priority  # a unique identifier

    def __eq__(self, other):
        return hash(self) == hash(other)

    def __hash__(self):
        return hash((self.address, self.priority, self.our_role))

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
            buffers_to_send.append(memoryview(command.header))
            buffers_to_send.extend(command.buffers)
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
        commands = collections.deque()
        if total_received == 0:
            self.log.debug('Zero-length recv; sending disconnect notification')
            commands.append(DISCONNECTED)
            return commands, 0

        self.log.debug("Received %d bytes.", total_received)
        self._data += b''.join(buffers)

        while True:
            (self._data,
             command,
             num_bytes_needed) = read_from_bytestream(self._data,
                                                      self.their_role)
            len_data = len(self._data)  # just for logging
            if type(command) is not NEED_DATA:
                self.log.debug("%d bytes -> %r", len(command), command)
                commands.append(command)
            else:
                self.log.debug("%d bytes are cached. Need more bytes to parse "
                               "next command.", len_data)
                break
        return commands, num_bytes_needed

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
        if isinstance(command, (ClearChannelRequest, ClearChannelResponse,
                                CreateChanRequest, CreateChanResponse,
                                CreateChFailResponse, AccessRightsResponse,
                                ReadNotifyRequest, ReadNotifyResponse,
                                WriteNotifyRequest, WriteNotifyResponse,
                                WriteRequest,
                                EventAddRequest, EventAddResponse,
                                EventCancelRequest, EventCancelResponse,
                                ServerDisconnResponse,)):
            # Identify which Channel this Command is referring to. We have to
            # do this in one of a couple different ways depenending on the
            # Command.
            if isinstance(command, (ReadNotifyRequest, WriteNotifyRequest,
                                    WriteRequest, EventAddRequest)):
                # Identify the Channel based on its sid.
                sid = command.sid
                try:
                    chan = self.channels_sid[sid]
                except KeyError:
                    err = get_exception(self.our_role, command)
                    raise err("Unknown Channel sid {!r}".format(command.sid))
            elif isinstance(command, (ReadNotifyResponse,
                                      WriteNotifyResponse)):
                # Identify the Channel based on its ioid.
                try:
                    chan = self._ioids[command.ioid]
                except KeyError:
                    err = get_exception(self.our_role, command)
                    raise err("Unknown Channel ioid {!r}".format(command.ioid))
            elif isinstance(command, (EventAddResponse, EventCancelRequest,
                                      EventCancelResponse)):
                # Identify the Channel based on its subscriptionid
                try:
                    event_add = self.event_add_commands[command.subscriptionid]
                except KeyError:
                    err = get_exception(self.our_role, command)
                    raise err("Unrecognized subscriptionid {!r}"
                              "".format(command.subscriptionid))
                chan = self.channels_sid[event_add.sid]
            elif isinstance(command, CreateChanRequest):
                # A Channel instance for this cid may already exist.
                try:
                    chan = self.channels[command.cid]
                except KeyError:
                    _class = {CLIENT: ClientChannel,
                              SERVER: ServerChannel}[self.our_role]
                    chan = _class(command.name, self, command.cid)
            else:
                # In all other cases, the Command gives us a cid.
                cid = command.cid
                chan = self.channels[cid]

            # Do some additional validation on commands related to an existing
            # subscription.
            if isinstance(command, (EventAddResponse, EventCancelRequest,
                                    EventCancelResponse)):
                # Verify data_type matches the one in the original request.
                event_add = self.event_add_commands[command.subscriptionid]
                if event_add.data_type != command.data_type:
                    err = get_exception(self.our_role, command)
                    raise err("The data_type in {!r} does not match the "
                              "data_type in the original EventAddRequest "
                              "for this subscriptionid, {!r}."
                              "".format(command, event_add.data_type))
            if isinstance(command, (EventAddResponse,)):
                # Verify data_count matches the one in the original request.
                # NOTE The docs say that EventCancelRequest should echo the
                # original data_count too, but in fact it seems to be 0.
                event_add = self.event_add_commands[command.subscriptionid]
                if (event_add.data_count > 0 and
                        event_add.data_count != command.data_count):
                    err = get_exception(self.our_role, command)
                    raise err("The data_count in {!r} does not match the "
                              "data_count in the original EventAddRequest "
                              "for this subscriptionid, {!r}."
                              "".format(command, event_add.data_count))
            if isinstance(command, (EventCancelRequest, EventCancelResponse)):
                # Verify sid matches the one in the original request.
                event_add = self.event_add_commands[command.subscriptionid]
                if event_add.sid != command.sid:
                    err = get_exception(self.our_role, command)
                    raise err("The sid in {!r} does not match the sid in "
                              "in the original EventAddRequest for this "
                              "subscriptionid, {!r}."
                              "".format(command, event_add.sid))

            # Update the state machine of the pertinent Channel.
            # If this is not a valid command, the state machine will raise
            # here. Stash the state transitions in a local var and run the
            # callbacks at the end.
            transitions = chan.process_command(command)

            # If we got this far, the state machine has validated this Command.
            # Update other Channel and Circuit state.
            if isinstance(command, AccessRightsResponse):
                chan.access_rights = command.access_rights
            elif isinstance(command, CreateChanResponse):
                chan.sid = command.sid
                self.channels_sid[chan.sid] = chan
            elif isinstance(command, ClearChannelResponse):
                self.channels_sid.pop(chan.sid)
                self.channels.pop(chan.cid)
            elif isinstance(command, (ReadNotifyRequest, WriteNotifyRequest)):
                # Stash the ioid for later reference.
                self._ioids[command.ioid] = chan
            elif isinstance(command, EventAddRequest):
                # We will use the info in this command later to validate that
                # {EventAddResponse, EventCancelRequest, EventCancelResponse}
                # send or received in the future are valid.
                self.event_add_commands[command.subscriptionid] = command
            elif isinstance(command, EventCancelResponse):
                self.event_add_commands.pop(command.subscriptionid)

            # We are done. Run the Channel state change callbacks.
            for transition in transitions:
                chan.state_changed(*transition)

        # Otherwise, this Command affects the state of this circuit, not a
        # specific Channel. Run the circuit's state machine.
        else:
            self.states.process_command_type(self.our_role, type(command))
            self.states.process_command_type(self.their_role, type(command))

        if isinstance(command, VersionRequest):
            if self.priority is None:
                self.priority = command.priority
            elif self.priority != command.priority:
                err = get_exception(self.our_role, command)
                raise err("priority {} does not match previously set priority "
                          "of {} for this circuit".format(command.priority,
                                                          self.priority))

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
            i = next(self._channel_id_counter)
            if i in self.channels:
                continue
            if i == MAX_ID:
                self._channel_id_counter = itertools.count(0)
                continue
            return i

    def new_subscriptionid(self):
        """
        This is used by the convenience methods to obtain an unused integer ID.
        It does not update any important state.
        """
        # Return the next sequential unused id. Wrap back to 0 on overflow.
        while True:
            i = next(self._sub_counter)
            if i in self.event_add_commands:
                continue
            if i == MAX_ID:
                self._sub_counter = itertools.count(0)
                continue
            return i

    def new_ioid(self):
        """
        This is used by the convenience methods to obtain an unused integer ID.
        It does not update any important state.
        """
        # Return the next sequential unused id. Wrap back to 0 on overflow.
        while True:
            i = next(self._ioid_counter)
            if i in self._ioids:
                continue
            if i == MAX_ID:
                self._ioid_counter = itertools.count(0)
                continue
            return i


class _BaseChannel:
    # Base class for ClientChannel and ServerChannel, which add convenience
    # methods for composing requests and repsponses, respectively. All of the
    # important code is here in the base class.
    def __init__(self, name, circuit, cid=None,
                 protocol_version=DEFAULT_PROTOCOL_VERSION):
        self.protocol_version = protocol_version
        self.name = name
        self.circuit = circuit
        if cid is None:
            cid = self.circuit.new_channel_id()
        self.cid = cid
        self.circuit.channels[self.cid] = self
        self.states = ChannelState(self.circuit.states)
        # These will be set when the circuit processes CreateChanResponse.
        self.native_data_type = None
        self.native_data_count = None
        self.sid = None
        self.access_rights = None

    @property
    def subscriptions(self):
        """
        Get cached EventAdd commands for this channel's active subscriptions.
        """
        return {k: v for k, v in self.circuit.event_add_commands.items()
                if v.sid == self.sid}

    def _fill_defaults(self, data_type, data_count):
        # Boilerplate used in many convenience methods:
        # Replace `None` default arg with actual default value.
        if data_type is None:
            data_type = self.native_data_type
        if data_count is None:
            data_count = 0
        return data_type, data_count

    def state_changed(self, role, old_state, new_state, command):
        '''State changed callback for subclass usage'''
        pass

    def process_command(self, command):
        if isinstance(command, CreateChanResponse):
            self.native_data_type = command.data_type
            self.native_data_count = command.data_count

        transitions = []
        for role in (self.circuit.our_role, self.circuit.their_role):
            initial_state = self.states[role]
            try:
                self.states.process_command_type(role, type(command))
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
    priority, and optional cid. The server address and priority are used to
    assign the ClientChannel to a VirtualCircuit. If no cid is given, a unique
    one is allocated by the VirtualCircuit.
    (2) A VirtualCircuit processes a CreateChanRequest that refers to a cid
    that it has not yet seen. A ClientChannel will be automatically
    instantiated with the name and cid indicated that command and the address
    and priority of that VirtualCircuit. It can be accessed in the circuit's
    ``channels`` attribute.

    Parameters
    ----------
    name : string
        Channnel name (PV)
    circuit : VirtualCircuit
    cid : integer, optional
    protocol_version : integer, optional
        Default is ``DEFAULT_PROTOCOL_VERSION``.
    """
    def version(self):
        """
        Generate a valid :class:`VersionRequest`.

        Parameters
        ----------
        priority : integer, optional
            May be used by the server to prioritize requests when under high
            load. Lowest priority is 0; highest is 99. Default is 0.

        Returns
        -------
        VersionRequest
        """
        command = VersionRequest(version=self.protocol_version,
                                 priority=self.circuit.priority)
        return command

    def host_name(self, host_name):
        """
        Generate a valid :class:`HostNameRequest`.

        Parameters
        ----------
        host_name : string

        Returns
        -------
        HostNameRequest
        """
        command = HostNameRequest(host_name)
        return command

    def client_name(self, client_name):
        """
        Generate a valid :class:`ClientNameRequest`.

        Parameters
        ----------
        client_name : string, optional
            defaults to output of ``getpass.getuser()``

        Returns
        -------
        ClientNameRequest
        """
        command = ClientNameRequest(client_name)
        return command

    def create(self):
        """
        Generate a valid :class:`CreateChanRequest`.

        Returns
        -------
        CreateChanRequest
        """
        command = CreateChanRequest(self.name, self.cid,
                                    self.protocol_version)
        return command

    def disconnect(self):
        """
        Generate a valid :class:`ClearChannelRequest`.

        Returns
        -------
        ClearChannelRequest
        """
        command = ClearChannelRequest(self.sid, self.cid)
        return command

    def read(self, data_type=None, data_count=None, ioid=None):
        """
        Generate a valid :class:`ReadNotifyRequest`.

        Parameters
        ----------
        data_type : a ChannelType or corresponding integer ID, optional
            Requested Channel Access data type. Default is the channel's
            native data type, which can be checked in the Channel's attribute
            :attr:`native_data_type`.
        data_count : integer, optional
            Requested number of values. Default is the channel's native data
            count, which can be checked in the Channel's attribute
            :attr:`native_data_count`.

        Returns
        -------
        ReadNotifyRequest
        """
        data_type, data_count = self._fill_defaults(data_type, data_count)
        if ioid is None:
            ioid = self.circuit.new_ioid()
        command = ReadNotifyRequest(data_type, data_count, self.sid, ioid)
        return command

    def write(self, data, data_type=None, data_count=None, metadata=None, ioid=None,
              use_notify=True):
        """
        Generate a valid :class:`WriteNotifyRequest`.

        Parameters
        ----------
        data : tuple, ``numpy.ndarray``, ``array.array``, or bytes
        data_type : a ChannelType or corresponding integer ID, optional
            Requested Channel Access data type. Default is the channel's
            native data type, which can be checked in the Channel's attribute
            :attr:`native_data_type`.
        data_count : integer, optional
            Requested number of values. Default is the channel's native data
            count, which can be checked in the Channel's attribute
            :attr:`native_data_count`.
        metadata : ``ctypes.BigEndianStructure`` or tuple
            Status and control metadata for the values

        Returns
        -------
        WriteNotifyRequest
        """
        data_type, data_count = self._fill_defaults(data_type, data_count)
        if data_count == 0:
            data_count = len(data)
        if ioid is None:
            ioid = self.circuit.new_ioid()

        # TODO: change use_notify default value; may break tests
        if use_notify:
            command = WriteNotifyRequest(data, data_type, data_count, self.sid,
                                         ioid, metadata=metadata)
        else:
            command = WriteRequest(data, data_type, data_count, self.sid, ioid,
                                   metadata=metadata)
        return command

    def subscribe(self, data_type=None, data_count=None,
                  subscriptionid=None,
                  low=0.0, high=0.0, to=0.0, mask=None):
        """
        Generate a valid :class:`EventAddRequest`.

        Parameters
        ----------
        data_type : a ChannelType or corresponding integer ID, optional
            Requested Channel Access data type. Default is the channel's
            native data type, which can be checked in the Channel's attribute
            :attr:`native_data_type`.
        data_count : integer, optional
            Requested number of values. Default is the channel's native data
            count, which can be checked in the Channel's attribute
            :attr:`native_data_count`.
        subscriptionid : integer, optional
        low : number
            Default is 0.
        high : number
            Default is 0.
        to : number
            Default is 0.
        mask :
            Default is None, which resolves to:
            ``(SubscriptionType.DBE_VALUE | ``
            `` SubscriptionType.DBE_ALARM | ``
            `` SubscriptionType.DBE_PROPERTY)``

        Returns
        -------
        EventAddRequest
        """
        data_type, data_count = self._fill_defaults(data_type, data_count)
        if mask is None:
            mask = (SubscriptionType.DBE_VALUE |
                    SubscriptionType.DBE_ALARM |
                    SubscriptionType.DBE_PROPERTY)
        if subscriptionid is None:
            subscriptionid = self.circuit.new_subscriptionid()
        command = EventAddRequest(data_type, data_count, self.sid,
                                  subscriptionid, low, high, to, mask)
        return command

    def unsubscribe(self, subscriptionid):
        """
        Generate a valid :class:`EventAddRequest`.

        Parameters
        ----------
        subscriptionid : integer
            The ``subscriptionid`` that was originally sent in the
            corresponding :class:`EventAddRequest`.

        Returns
        -------
        EventAddRequest
        """
        try:
            event_add = self.circuit.event_add_commands[subscriptionid]
        except KeyError:
            raise CaprotoKeyError("No current subscription has id {!r}"
                                  "".format(subscriptionid))
        if event_add.sid != self.sid:
            raise CaprotoValueError("This subscription is for a different "
                                    "Channel.")
        command = EventCancelRequest(event_add.data_type, self.sid,
                                     subscriptionid)
        return command


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
    def version(self):
        """
        Generate a valid :class:`VersionResponse`.

        Returns
        -------
        VersionResponse
        """
        command = VersionResponse(self.protocol_version)
        return command

    def create(self, native_data_type, native_data_count, sid):
        """
        Generate a valid :class:`CreateChanResponse`.

        Parameters
        ----------
        native_data_type : a ChannelType or corresponding integer ID, optional
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
        data_type : a ChannelType or corresponding integer ID, optional
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
        data_type : a ChannelType or corresponding integer ID, optional
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
        data_type : a ChannelType or corresponding integer ID, optional
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
        data_type : a ChannelType or corresponding integer ID, optional
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


def extract_address(search_response):
    """
    Extract the (host, port) from a SearchResponse.
    """
    if type(search_response) is not SearchResponse:
        raise TypeError("expected SearchResponse, not {!r}"
                        "".format(type(search_response).__name__))
    if search_response.header.parameter1 == 0xffffffff:
        # The CA spec tells us that this sentinel value means we
        # should fall back to using the address of the sender of
        # the UDP datagram.
        address = search_response.sender_address[0]
    else:
        address = search_response.ip
    return (address, search_response.port)
