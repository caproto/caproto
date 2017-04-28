# This module defines classes that encapsulate key abstractions in
# Channel Access: Channels and VirtualCircuits. Each VirtualCircuit is a
# companion to a (user-managed) TCP socket, updating its state in response to
# incoming and outgoing TCP bytestreams. Each Channel belongs to a circuit, and
# tracks state particular to that Channel.
import itertools
from collections import deque
import logging
import getpass
import socket
# N.B. We do no networking whatsoever in caproto. We only use socket for
# socket.gethostname() to give a nice default for a HostNameRequest command.
from ._commands import (AccessRightsResponse, CreateChFailResponse,
                        ClearChannelRequest, ClearChannelResponse,
                        ClientNameRequest, CreateChanRequest,
                        CreateChanResponse, ErrorResponse,
                        EventAddRequest, EventAddResponse,
                        EventCancelRequest, EventCancelResponse,
                        HostNameRequest, ReadNotifyRequest, ReadNotifyResponse,
                        RepeaterConfirmResponse, RepeaterRegisterRequest,
                        SearchRequest, SearchResponse, ServerDisconnResponse,
                        VersionRequest, VersionResponse, WriteNotifyRequest,
                        WriteNotifyResponse,

                        read_datagram, read_from_bytestream,
                        )
from ._state import (ChannelState, CircuitState, get_exception)
from ._utils import (CLIENT, SERVER, NEED_DATA, CaprotoKeyError,
                     CaprotoValueError, LocalProtocolError,
                     CaprotoRuntimeError,
                     )
from ._dbr import (SubscriptionType, )


DEFAULT_PROTOCOL_VERSION = 13
MAX_ID = 2**16 # max value of various integer IDs

# official IANA ports
EPICS_CA1_PORT, EPICS_CA2_PORT = 5064, 5065


class VirtualCircuit:
    """
    An object encapulating the state of one CA client--server connection.

    It is a companion to a TCP socket managed by the user. All data
    received over the socket should be passed to :meth:`recv`. Any data sent
    over the socket should first be passed through :meth:`send`.

    Parameters
    ----------
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
        else:
            self.their_role = CLIENT
        self.address = address
        self.priority = priority
        self.channels = {}  # map cid to Channel
        self.log = logging.getLogger("caproto.VC")
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

    @property
    def key(self):
        if self.priority is None:
            raise CaprotoRuntimeError("This VirtualCircuit has not received a "
                                      "VersionRequest and does not know its "
                                      "priority. Therefore, it does not yet "
                                      "have a key.")
        return self.address, self.priority  # a unique identifier

    def send(self, *commands):
        """
        Convert one or more high-level Commands into buffers of bytes that may
        be broadcast together in one TCP packet while updating our internal
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
            buffers_to_send.append(bytes(command.header))
            buffers_to_send.extend(command.buffers)
        return buffers_to_send

    def recv(self, *buffers):
        """
        Add data received over TCP to our internal recieve buffer.

        This does not actually do any processing on the data, just stores
        it. To trigger processing, you have to call :meth:`next_command`.

        Parameters
        ----------
        *buffers :
            any number of bytes-like buffers
        """
        for byteslike in buffers:
            self.log.debug("Received %d bytes.", len(byteslike))
            self._data += byteslike

    def next_command(self):
        """
        Parse the next Command out of our internal receive buffer, update our
        internal state machine, and return it.

        Returns a :class:`Command` object or a special constant,
        :data:`NEED_DATA`.
        """
        len_data = len(self._data)
        self._data, command = read_from_bytestream(self._data, self.their_role)
        if type(command) is not NEED_DATA:
            self._process_command(self.our_role, command)
            self.log.debug("Parsed %d/%d cached bytes into %r.",
                           len(command), len_data, command)
        else:
            self.log.debug("%d bytes are cached. Need more bytes to parse "
                           "next command.", len(self._data))
        return command

    def _process_command(self, role, command):
        """
        All comands go through here.

        Parameters
        ----------
        role : ``CLIENT`` or ``SERVER``
        command : Message
        """
        # Filter for Commands that are pertinent to a specific Channel, as
        # opposed to the Circuit as a whole:
        if isinstance(command, (ClearChannelRequest, ClearChannelResponse,
                                CreateChanRequest, CreateChanResponse,
                                CreateChFailResponse, AccessRightsResponse,
                                ReadNotifyRequest, ReadNotifyResponse,
                                WriteNotifyRequest, WriteNotifyResponse,
                                EventAddRequest, EventAddResponse,
                                EventCancelRequest, EventCancelResponse,
                                ServerDisconnResponse,)):
            # Identify which Channel this Command is referring to. We have to
            # do this in one of a couple different ways depenending on the
            # Command.
            if isinstance(command, (ReadNotifyRequest, WriteNotifyRequest,
                                    EventAddRequest)):
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
            transitions = chan._process_command(command)

            # If we got this far, the state machine has validated this Command.
            # Update other Channel and Circuit state.
            if isinstance(command, AccessRightsResponse):
                chan.access_rights = command.access_rights
            if isinstance(command, CreateChanResponse):
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
        self.states.disconnect()

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


class Broadcaster:
    """
    An object encapulating the state of one CA UDP connection.

    It is a companion to a UDP socket managed by the user. All data
    received over the socket should be passed to :meth:`recv`. Any data sent
    over the socket should first be passed through :meth:`send`.

    Parameters
    ----------
    our_role : CLIENT or SERVER
    protocol_version : integer
        Default is ``DEFAULT_PROTOCOL_VERSION``.
    """
    def __init__(self, our_role, protocol_version=DEFAULT_PROTOCOL_VERSION):
        if our_role not in (SERVER, CLIENT):
            raise CaprotoValueError("role must be caproto.SERVER or "
                                    "caproto.CLIENT")
        self.our_role = our_role
        if our_role is CLIENT:
            self.their_role = SERVER
        else:
            self.their_role = CLIENT
        self.protocol_version = protocol_version
        self.unanswered_searches = {}  # map search id (cid) to name
        self._datagram_inbox = deque()  # datagrams to be parsed into Commands
        self._history = []  # commands parsed so far from current datagram
        self._parsed_commands = deque()  # parsed Commands to be processed
        # Unlike VirtualCircuit and Channel, there is very little state to
        # track for the Broadcaster. We don't need a full state machine, just
        # one flag to check whether we have yet registered with a repeater.
        self._registered = False
        self._search_id_counter = itertools.count(0)
        logger_name = "caproto.Broadcaster"
        self.log = logging.getLogger(logger_name)

    def send(self, *commands):
        """
        Convert one or more high-level Commands into bytes that may be
        broadcast together in one UDP datagram while updating our internal
        state machine.

        Parameters
        ----------
        *commands :
            any number of :class:`Message` objects

        Returns
        -------
        bytes_to_send : bytes
            bytes to send over a socket
        """
        bytes_to_send = b''
        history = []  # commands sent as part of this datagram
        self.log.debug("Serializing %d commands into one datagram",
                       len(commands))
        for i, command in enumerate(commands):
            self.log.debug("%d of %d %r", 1 + i, len(commands), command)
            self._process_command(self.our_role, command, history)
            bytes_to_send += bytes(command)
        return bytes_to_send

    def recv(self, byteslike, address):
        """
        Add data from a UDP broadcast to our internal recieve buffer.

        This does not actually do any processing on the data, just stores
        it. To trigger processing, you have to call :meth:`next_command`.

        Parameters
        ----------
        byteslike : bytes-like
        address : tuple
            ``(host, port)`` as a string and an integer respectively
        """
        logging.debug("Received datagram from %r with %d bytes.",
                      address, len(byteslike))
        self._datagram_inbox.append((byteslike, address))

    def next_command(self):
        """
        Parse the next Command out of our internal receive buffer, update our
        internal state machine, and return it.

        Returns a :class:`Command` object or a special constant,
        :data:`NEED_DATA`.
        """
        if not self._parsed_commands:
            if not self._datagram_inbox:
                return NEED_DATA
            self._history.clear()
            byteslike, address = self._datagram_inbox.popleft()
            commands = read_datagram(byteslike, address, self.their_role)
            self.log.debug("Parsed %d commands from first datagram in queue.",
                           len(commands))
            for i, command in enumerate(commands):
                self.log.debug("%d of %d: %r", i, len(commands), command)
            self._parsed_commands.extend(commands)
            if not commands:
                # Handle rare edge case: empty datagram.
                return self.next_command()
        self.log.debug(("Processing 1/%d commands left in datagram. "
                        "%d more datagrams are cached."),
                       len(self._parsed_commands), len(self._datagram_inbox))
        command = self._parsed_commands.popleft()
        self._process_command(self.their_role, command, self._history)
        return command

    def _process_command(self, role, command, history):
        """
        All comands go through here.

        Parameters
        ----------
        role : ``CLIENT`` or ``SERVER``
        command : Message
        history : list
            This input will be mutated: command will be appended at the end.
        """
        # All commands go through here.
        if isinstance(command, RepeaterRegisterRequest):
            pass
        elif isinstance(command, RepeaterConfirmResponse):
            self._registered = True
        elif (role is CLIENT and
              self.our_role is CLIENT and
              not self._registered):
            raise LocalProtocolError("Client must send a "
                                     "RegisterRepeaterRequest before any "
                                     "other commands")
        elif isinstance(command, SearchRequest):
            if VersionRequest not in map(type, history):
                err = get_exception(self.our_role, command)
                raise err("A broadcasted SearchResponse must be preceded by a "
                          "VersionResponse in the same datagram.")
            self.unanswered_searches[command.cid] = command.name
        elif isinstance(command, SearchResponse):
            if VersionResponse not in map(type, history):
                err = get_exception(self.our_role, command)
                raise err("A broadcasted SearchResponse must be preceded by a "
                          "VersionResponse in the same datagram.")
            try:
                search_request = self.unanswered_searches.pop(command.cid)
            except KeyError:
                err = get_exception(self.our_role, command)
                raise err("No SearchRequest we have seen has a cid matching "
                          "this response: {!r}".format(command))
        history.append(command)

    ### CONVENIENCE METHODS ###

    def new_search_id(self):
        # Return the next sequential unused id. Wrap back to 0 on overflow.
        while True:
            i = next(self._search_id_counter)
            if i in self.unanswered_searches:
                continue
            if i == MAX_ID:
                self._search_id_counter = itertools.count(0)
                continue
            return i

    def search(self, name):
        """
        Generate a valid :class:`VersionRequest` and :class:`SearchRequest`.

        The protocol requires that these be transmitted together as part of one
        datagram.

        Parameters
        ----------
        name : string
            Channnel name (PV)

        Returns
        -------
        (VersionRequest, SearchRequest)
        """
        cid = self.new_search_id()
        commands = (VersionRequest(0, self.protocol_version),
                    SearchRequest(name, cid, self.protocol_version))
        return commands

    def register(self, ip=None):
        """
        Generate a valid :class:`RepeaterRegisterRequest`.

        Parameters
        ----------
        ip : string, optional
            Our IP address. Defaults is output of ``socket.gethostbyname``.

        Returns
        -------
        RepeaterRegisterRequest
        """
        if ip is None:
            hostname = socket.gethostname()
            ip = socket.gethostbyname(hostname)
        command = RepeaterRegisterRequest(ip)
        return command


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

    def _process_command(self, command):
        if isinstance(command, CreateChanResponse):
            self.native_data_type = command.data_type
            self.native_data_count = command.data_count

        transitions = []
        for role in (self.circuit.our_role, self.circuit.their_role):
            initial_state = self.states[role]
            self.states.process_command_type(role, type(command))
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

    def host_name(self, host_name=None):
        """
        Generate a valid :class:`HostNameRequest`.

        Parameters
        ----------
        host_name : string, optional
            defaults to output of ``socket.gethostname()``

        Returns
        -------
        HostNameRequest
        """
        if host_name is None:
            host_name = socket.gethostname()[:39]  # Truncate for EPICS.
        command = HostNameRequest(host_name)
        return command

    def client_name(self, client_name=None):
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
        if client_name is None:
            client_name = getpass.getuser()
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

    def clear(self):
        """
        Generate a valid :class:`ClearChannelRequest`.

        Returns
        -------
        ClearChannelRequest
        """
        command = ClearChannelRequest(self.sid, self.cid)
        return command

    def read(self, data_type=None, data_count=None):
        """
        Generate a valid :class:`ReadNotifyRequest`.

        Parameters
        ----------
        data_type : a :class:`DBR_TYPE` or its designation integer ID, optional
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
        ioid = self.circuit.new_ioid()
        command = ReadNotifyRequest(data_type, data_count, self.sid, ioid)
        return command

    def write(self, data, data_type=None, data_count=None, metadata=None):
        """
        Generate a valid :class:`WriteNotifyRequest`.

        Parameters
        ----------
        data : tuple, ``numpy.ndarray``, ``array.array``, or bytes
        data_type : a :class:`DBR_TYPE` or its designation integer ID, optional
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
        ioid = self.circuit.new_ioid()
        command = WriteNotifyRequest(data, data_type, data_count, self.sid,
                                     ioid, metadata=metadata)
        return command

    def subscribe(self, data_type=None, data_count=None, low=0.0, high=0.0,
                  to=0.0, mask=None):
        """
        Generate a valid :class:`EventAddRequest`.

        Parameters
        ----------
        data_type : a :class:`DBR_TYPE` or its designation integer ID, optional
            Requested Channel Access data type. Default is the channel's
            native data type, which can be checked in the Channel's attribute
            :attr:`native_data_type`.
        data_count : integer, optional
            Requested number of values. Default is the channel's native data
            count, which can be checked in the Channel's attribute
            :attr:`native_data_count`.
        low : number
            Default is 0.
        high : number
            Default is 0.
        to : number
            Default is 0.
        mask :
            Default is None.

        Returns
        -------
        EventAddRequest
        """
        data_type, data_count = self._fill_defaults(data_type, data_count)
        if mask is None:
            mask = (SubscriptionType.DBE_VALUE |
                    SubscriptionType.DBE_ALARM |
                    SubscriptionType.DBE_PROPERTY)
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

    def clear(self):
        """
        Generate a valid :class:`ClearChannelResponse`.

        Returns
        -------
        ClearChannelResponse
        """
        command = ClearChannelResponse(self.sid, self.cid)
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
