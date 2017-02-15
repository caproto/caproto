# This module defines two classes that encapsulate key abstractions in
# Channel Access: Channels and VirtualCircuits. Each VirtualCircuit is a
# companion to a (user-managed) TCP socket, updating its state in response to
# incoming and outgoing TCP bytestreams. A third class, the Hub, owns these
# VirtualCircuits and spawns new ones as needed. The Hub updates its state in
# response to incoming and outgoing UDP datagrams.
import ctypes
import itertools
from io import BytesIO
from collections import defaultdict, deque, namedtuple
import logging
import getpass
import socket
# N.B. We do no networking whatsoever in caproto. We only use socket for
# socket.gethostname() to give a nice default for a HostNameRequest command.
from ._commands import *
from ._dbr_types import *
from ._state import *
from ._utils import *


DEFAULT_PROTOCOL_VERSION = 13
OUR_HOSTNAME = socket.gethostname()
OUR_USERNAME = getpass.getuser()


class VirtualCircuit:
    """
    An object encapulating the state of one CA client--server connection.

    This object can be created as soon as we know the address ``(host, port))``
    of our peer (client/server depending on our role).

    It is a companion to a TCP socket managed by the user. All data
    received over the socket should be passed to :meth:`recv`. Any data sent
    over the socket should first be passed through :meth:`send`.

    Parameters
    ----------
    hub : Hub
    address : tuple
        ``(host, port)`` as a string and an integer respectively
    priority : integer or None
        May be used by the server to prioritize requests when under high
        load. Lowest priority is 0; highest is 99.
    data : bytearray
        data received but not yet processed by the VirtualCircuitProxy before
        it bound to this Virtual Circuit
    state : CircuitState
        passed in by VirtualCircuitProxy
    """
    def __init__(self, hub, address, priority, data, state):
        self._hub = hub
        self.address = address
        self.priority = priority
        # (host, prority) uniquely identifies this circuit
        self.key = (address[0], priority)
        self._state = state
        self._data = data
        self.channels = {}  # map cid to Channel
        self._state.channels = self.channels
        self._channels_sid = {}  # map sid to Channel
        self._ioids = {}  # map ioid to Channel
        self.sub_commands = {}  # map subscriptionid to EventAdd command
        # There are only used by the convenience methods, to auto-generate ids.
        self._ioid_counter = itertools.count(0)
        self._sub_counter = itertools.count(0)
        # Copy these (immutable) hub attributes for convenience.
        self.our_role = hub.our_role
        self.their_role = hub.their_role
        self.log = self._hub.log

    def add_channel(self, channel):
        """
        Assign a Channel to this Virtual Circuit.

        Parameters
        ----------
        channel : :class:`ServerChannel` or :class:`ClientChannel`
        """
        self.channels[channel.cid] = channel

    def send(self, *commands):
        """
        Convert one or more high-level Commands into bytes that may be
        broadcast together in one TCP packet while updating our internal
        state machine.

        Parameters
        ----------
        *commands :
            any number of :class:`Message` objects
        """
        bytes_to_send = b''
        for command in commands:
            self._process_command(self.our_role, command)
            self.log.debug("Serializing %r", command)
            bytes_to_send += bytes(command)
        return bytes_to_send

    def recv(self, byteslike):
        """
        Add data received over TCP to our internal recieve buffer.

        This does not actually do any processing on the data, just stores
        it. To trigger processing, you have to call :meth:`next_command`.

        Parameters
        ----------
        byteslike : bytes-like
        """
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
                    chan = self._channels_sid[sid]
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
            elif isinstance(command, (EventAddResponse,
                                      EventCancelRequest, EventCancelResponse)):
                # Identify the Channel based on its subscriptionid
                try:
                    event_add = self.sub_commands[command.subscriptionid]
                except KeyError:
                    err = get_exception(self.our_role, command)
                    raise err("Unrecognized subscriptionid {!r}"
                              "".format(subscriptionid))
                chan = self._channels_sid[event_add.sid]
            elif isinstance(command, CreateChanRequest):
                # A Channel instance for this cid may already exist.
                try:
                    chan = self._hub.channels[command.cid]
                except KeyError:
                    chan = self._hub.new_channel(name=command.name,
                                                 cid=command.cid)
                    chan.circuit = self
            else:
                # In all other cases, the Command gives us a cid.
                cid = command.cid
                chan = self.channels[cid]

            # Do some additional validation on commands related to an existing
            # subscription.
            if isinstance(command, (EventAddResponse, EventCancelRequest,
                                    EventCancelResponse)):
                # Verify data_type matches the one in the original request.
                event_add = self.sub_commands[command.subscriptionid]
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
                event_add = self.sub_commands[command.subscriptionid]
                if event_add.data_count != command.data_count:
                    err = get_exception(self.our_role, command)
                    raise err("The data_count in {!r} does not match the "
                                "data_count in the original EventAddRequest "
                                "for this subscriptionid, {!r}."
                                "".format(command, event_add.data_count))
            if isinstance(command, (EventCancelRequest, EventCancelResponse)):
                # Verify sid matches the one in the original request.
                event_add = self.sub_commands[command.subscriptionid]
                if event_add.sid != command.sid:
                    err = get_exception(self.our_role, command)
                    raise err("The sid in {!r} does not match the sid in "
                                "in the original EventAddRequest for this "
                                "subscriptionid, {!r}."
                                "".format(command, event_add.sid))

            # Update the state machine of the pertinent Channel.
            # If this is not a valid command, the state machine will raise
            # here.
            chan._state.process_command(self.our_role, type(command))
            chan._state.process_command(self.their_role, type(command))

            # If we got this far, the state machine has validated this Command.
            # Update other Channel and Circuit state.
            if isinstance(command, CreateChanRequest):
                self.add_channel(chan)
            elif isinstance(command, CreateChanResponse):
                chan.native_data_type = command.data_type
                chan.native_data_count = command.data_count
                chan.sid = command.sid
                self._channels_sid[chan.sid] = chan
            elif isinstance(command, ClearChannelResponse):
                self._channels_sid.pop(chan.sid)
                self.channels.pop(chan.cid)
            elif isinstance(command, (ReadNotifyRequest, WriteNotifyRequest)):
                # Stash the ioid for later reference.
                self._ioids[command.ioid] = chan
            elif isinstance(command, EventAddRequest):
                # We will use the info in this command later to validate that
                # {EventAddResponse, EventCancelRequest, EventCancelResponse}
                # send or received in the future are valid.
                self.sub_commands[command.subscriptionid] = command
            elif isinstance(command, EventCancelResponse):
                self.sub_commands.pop(subscriptionid)

        # Otherwise, this Command affects the state of this circuit, not a
        # specific Channel. Run the circuit's state machine.
        else:
            self._state.process_command(self.our_role, type(command))
            self._state.process_command(self.their_role, type(command))

        # The VersionRequest is handled by VirtualCircuitProxy. Here, simply
        # ensure that we are not getting contradictory information.
        if isinstance(command, VersionRequest):
            if self.priority != command.priority:
                err = get_exception(self.our_role, command)
                raise("priority {} does not match previously set priority "
                      "of {} for this circuit".format(command.priority,
                                                      priority))

    def new_subscriptionid(self):
        # This is used by the convenience methods. It does not update any
        # important state.
        # TODO Be more clever and reuse abandoned ids; avoid overrunning.
        return next(self._sub_counter)

    def new_ioid(self):
        # This is used by the convenience methods. It does not update any
        # important state.
        # TODO Be more clever and reuse abandoned ioids; avoid overrunning.
        return next(self._ioid_counter)


class VirtualCircuitProxy:
    """
    For that awkward moment when you know the address of a circuit but you
    don't yet know the prioirty

    As a CLIENT, until you know the 'priority', you can't know whether this can
    use an existing circuit or will need a new one (and a new corresponding TCP
    connection, managed by the user.

    As a SERVER, you create one of these directly, in reponse to an incoming
    request to accept a TCP connection. But you still don't bind the proxy to a
    VirtualCircuit until you know the 'priority'.

    Parameters
    ----------
    hub : Hub
    address : tuple
        ``(host, port)`` as a string and an integer respectively
    """
    def __init__(self, hub, address):
        self._hub = hub
        self.address = address
        self.our_role = self._hub.our_role
        self._state = CircuitState()
        self.their_role = self._hub.their_role
        self.__circuit = None
        self._data = bytearray()  # will get handed off to VirtualCircuit
        self.log = self._hub.log

    def _bind_circuit(self, priority):
        # Identify an existing VirtcuitCircuit with the right host and
        # priority, or create one.
        key = (self.address[0], priority)
        try:
            circuit = self._hub.circuits[key]
        except KeyError:
            circuit = VirtualCircuit(hub=self._hub,
                                     address=self.address,
                                     priority=priority,
                                     data=self._data,
                                     state=self._state)

            self._hub.circuits[key] = circuit
        self.__circuit = circuit

    def send(self, *commands):
        """
        Convert one or more high-level Commands into bytes that may be
        broadcast together in one TCP packet while updating our internal
        state machine.

        Parameters
        ----------
        *commands :
            any number of :class:`Message` objects
        """
        if commands and not self.bound:
            first_command, *_= commands
            if isinstance(first_command, VersionRequest):
                self._bind_circuit(first_command.priority)
            else:
                err = get_exception(first_command, self.our_role)
                raise err("This circuit must be initialized with a "
                          "VersionRequest.")
        bytes_to_send = b''
        for command in commands:
            self.circuit._process_command(self.our_role, command)
            self.log.debug("Serializing %r", command)
            bytes_to_send += bytes(command)
        return bytes_to_send

    def recv(self, byteslike):
        """
        Add data received over TCP to our internal recieve buffer.

        This does not actually do any processing on the data, just stores
        it. To trigger processing, you have to call :meth:`next_command`.

        Parameters
        ----------
        byteslike : bytes-like
        """
        self.log.debug("Received %d bytes into cache.", len(byteslike))
        if not self.bound:
            self._data += byteslike
        else:
            return self.circuit.recv(byteslike)

    def next_command(self):
        """
        Parse the next Command out of our internal receive buffer, update our
        internal state machine, and return it.

        Returns a :class:`Command` object or a special constant,
        :data:`NEED_DATA`.
        """
        if not self.bound:
            self._data, command = read_from_bytestream(self._data,
                                                       self.their_role)
            if type(command) is not NEED_DATA:
                if isinstance(command, VersionRequest):
                    self._bind_circuit(command.priority)
                else:
                    err = get_exception(command, self.our_role)
                    raise err("This circuit must be initialized with a "
                              "VersionRequest.")
                self.circuit._process_command(self.our_role, command)
            return command
        else:
            return self.circuit.next_command()

    @property
    def circuit(self):
        if self.__circuit is None:
            text = ("A VersionRequest command must be sent through this "
                    "VirtualCircuitProxy to bind it to a VirtualCircuit "
                    "before any other of its methods may be used.")
            raise UninitializedVirtualCircuit(text)
        else:
            return self.__circuit

    @property
    def bound(self):
        return self.__circuit is not None

    # Define pass-through methods for every public method of VirtualCircuit.
    def new_subscriptionid(self):
        __doc__ = self.circuit.new_subscriptionid.__doc__
        return self.circuit.new_subscriptionid()

    def new_ioid(self):
        __doc__ = self.circuit.new_ioid.__doc__
        return self.circuit.new_ioid()

    @property
    def priority(self):
        return self.circuit.priority

    @property
    def channels(self):
        return self.circuit.channels

    @property
    def key(self):
        return self.circuit.key

    @property
    def sub_commands(self):
        return self.circuit.sub_commands


class Hub:
    """An object encapsulating the state of CA connections in process.

    This tracks the state of one Client and all its connected Servers or one
    Server and all its connected Clients.

    It sees all outgoing bytes before they are sent over a socket and receives
    all incoming bytes after they are received from a socket. It verifies that
    all incoming and outgoing commands abide by the Channel Access protocol,
    and it updates an internal state machine representing the state of all
    CA channels and CA virtual circuits.

    It may also be used to compose valid commands using a pleasant Python API
    and to decode incoming bytestreams into these same kinds of objects.

    Parameters
    ----------
    our_role : CLIENT or SERVER
    protocol_version : integer
        default is ``DEFAULT_PROTOCOL_VERSION``
    """
    def __init__(self, our_role, protcol_version=DEFAULT_PROTOCOL_VERSION):
        if our_role not in (SERVER, CLIENT):
            raise CaprotoValueError("role must be caproto.SERVER or "
                                    "caproto.CLIENT")
        self.our_role = our_role
        if our_role is CLIENT:
            self.their_role = SERVER
        else:
            self.their_role = CLIENT
        self.protocol_version = protcol_version
        self._addresses = {}  # map known Channel names to (host, port)
        self.circuits = {}  # keyed by ((host, port), priority)
        self.channels = {}  # map cid to Channel
        self._datagram_inbox = deque()  # datagrams to be parsed into Commands
        self._history = []  # commands parsed so far from current datagram
        self._parsed_commands = deque()  # parsed Commands to be processed
        self._unanswered_searches = []  # search ids (cids)
        # This is only used by the convenience methods, to auto-generate a cid.
        self._channel_id_counter = itertools.count(0)
        logger_name = "caproto.Hub"
        self.log = logging.getLogger(logger_name)

    def send_broadcast(self, *commands):
        """
        Convert one or more high-level Commands into bytes that may be
        broadcast together in one UDP datagram while updating our internal
        state machine.

        Parameters
        ----------
        *commands :
            any number of :class:`Message` objects
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

    def recv_broadcast(self, byteslike, address):
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
        self.log.debug(("Returning 1 of %d commands from the datagram most "
                        "recently parsed. %d more datagrams are cached."),
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
        if isinstance(command, SearchRequest):
            if VersionRequest not in map(type, history):
                err = get_exception(self, command)
                raise err("A broadcasted SearchResponse must be preceded by a "
                          "VersionResponse in the same datagram.")
            self._unanswered_searches.append(command.cid)
        elif isinstance(command, SearchResponse):
            if VersionResponse not in map(type, history):
                err = get_exception(self, command)
                raise err("A broadcasted SearchResponse must be preceded by a "
                          "VersionResponse in the same datagram.")
            try:
                self._unanswered_searches.remove(command.cid)
            except ValueError:
                err = get_exception(self.our_role, command)
                raise err("No SearchRequest we have seen matches this "
                          "SearchResponse.")
        history.append(command)

        if isinstance(command, SearchRequest):
            self._unanswered_searches.append(command.cid)
        elif isinstance(command, SearchResponse):
            if self.our_role is CLIENT:
                # Maybe the user has manually instantiated a Channel instance
                # with this cid. If not, make one.
                try:
                    chan = self.channels[command.cid]
                except KeyError:
                    chan = self.new_channel(name=command.name,
                                            cid=command.cid)

                # Get the address that TCP communication about this Channel
                # should take place on.
                if command.header.parameter1 == 0xffffffff:
                    # The CA spec tells us that this sentinel value means we
                    # should fall back to using the address of the sender of
                    # the UDP datagram.
                    address = command.sender_address
                else:
                    address = command.sid, command.port
                # We now know the Channel's address so we can assign it to a
                # VirtualCircuitProxy. We will not know the Channel's priority
                # until we see a VersionRequest, hence the *Proxy* in
                # VirtualCircuitProxy.
                circuit = VirtualCircuitProxy(self, address)
                chan.circuit = circuit

                # Separately, stash the address where we found this name. This
                # information might remain useful beyond the lifecycle of the
                # circuit.
                self._addresses[chan.name] = address

    def new_channel_id(self):
        "Return a valid value for a cid or sid."
        # This is used by the convenience methods. It does not update any
        # important state.
        # TODO Be more clever and reuse abandoned ids; avoid overrunning.
        return next(self._channel_id_counter)

    def new_channel(self, name, cid=None):
        """
        A convenience method: instantiate a new :class:`ClientChannel` or
        :class:`ServerChannel`, corresponding to :attr:`our_role`.

        This method does not update any important state. It is equivalent to:
        ``<ChannelClass>(<Hub>, None, <UNIQUE_INT>, name)``

        Parameters
        ----------
        name : string
            Channnel name (PV)
        cid : int, optional for CLIENT
            On CLIENT, if None, a valid (i.e., unused) integer is allocated.
        """
        _class = {CLIENT: ClientChannel, SERVER: ServerChannel}[self.our_role]
        channel = _class(self, name, cid)
        # If this Client has searched for this name and already knows its
        # host, skip the Search step and create a VirtualCircuitProxy.
        return channel


class _BaseChannel:
    # Base class for ClientChannel and ServerChannel, which add convenience
    # methods for composing requests and repsponses, respectively. All of the
    # important code is here in the base class.
    def __init__(self, hub, name, cid=None):
        self._hub = hub
        self.name = name
        if cid is None:
            cid = hub.new_channel_id()
        self.cid = cid
        self._state = ChannelState()
        # Register the Channel with the Hub so it knows it recognizes the cid
        # on a pertinent SearchResponses.
        hub.channels[cid] = self
        # This will be set when a SearchResponse is processed.
        self._circuit = None
        # These will be set when the circuit processes CreateChanResponse.
        self.native_data_type = None
        self.native_data_count = None
        self.sid = None
        self.cleared = False  # If True, Channel is at end of life.

    @property
    def circuit(self):
        return self._circuit

    @circuit.setter
    def circuit(self, virtual_circuit_proxy):
        if self._circuit is not None:
            raise RuntimeError("circuit can only be assigned once")
        self._circuit = virtual_circuit_proxy
        self._state.circuit_state = virtual_circuit_proxy._state

    @property
    def subscriptions(self):
        """
        Get cached EventAdd commands for this channel's active subscriptions.
        """
        return {k: v for k, v in self._circuit.sub_commands.items()
                if v.cid == self.cid}

    def _fill_defaults(self, data_type, data_count):
        # Boilerplate used in many convenience methods:
        # Replace `None` default arg with actual default value.
        if data_type is None:
            data_type = self.native_data_type
        if data_count is None:
            data_count = self.native_data_count
        return data_type, data_count



class ClientChannel(_BaseChannel):
    """An object encapsulating the state of the EPICS Channel on a Client.

    There are two ways that a ClientChannel may be instantiated:

    (1) The user instantiates a ClientChannel with a name and, optionally, a
    integer identifier, cid. If no cid is given, a valid one is obtained from
    an internal counter maintained by the Hub.
    (2) A SearchResponse is processed by the Hub that refers to a cid not yet
    seen. A ClientChannel will be implicitly instantiated with the
    name and cid indicated that SearchResponse command.

    Life-cycle of a ClientChannel:

    * At instantiation time, a ClientChannel is registered with the Hub.
    * When (if) a SearchResponse with this channel's cid is received and
    processed by the Hub, we then know the address of its peer. It is
    assigned a VirtualCircuitProxy.
    * When (if) a VersionRequest with this channel's cid is received and
    processed by its VirtualCircuitProxy, we then know its priority. Its
    VirtualCircuitProxy is bound to a VirtualCircuit (corresponding to one
    client--server TCP connection) which it may share with other Channels.
    * When a ClearChannelRequest with this channel's cid is received and
    processed by its VirtualCircuit[Proxy], the ClientChannel cannot be used
    again.

    Parameters
    ----------
    hub : :class:`Hub`
    name : string
        Channnel name (PV)
    cid : integer
        Unique Channel ID
    """
    def version_broadcast(self, priority=0):
        """
        A convenience method: generate a valid :class:`VersionRequest`.

        This method does not update any important state. The command only has
        an effect if it is passed to the :meth:`send` method of the Hub.

        Note that, unlike most the other :class:`ClientChannel` convenience
        mehtods, this does not return a VirtualCircuit. It should be passed to
        ``Hub.send_broadcast`` and broadcast over UDP.


        Parameters
        ----------
        priority : integer, optional
            May be used by the server to prioritize requests when under high
            load. Lowest priority is 0; highest is 99. Default is 0.

        Returns
        -------
        VersionRequest

        See Also
        --------
        :meth:`version_broadcast`
        """
        command = VersionRequest(priority, self._hub.protocol_version)
        return command

    def search_broadcast(self):
        """
        A convenience method: generate a valid :class:`SearchRequest`.

        This method does not update any important state. The command only has
        an effect if it is passed to the :meth:`send_broadcast` method of the
        Hub.

        Note that, unlike most the other :class:`ClientChannel` convenience
        mehtods, this does not return a VirtualCircuit. It should be passed to
        ``Hub.send_broadcast`` and broadcast over UDP.

        Returns
        -------
        SearchRequest
        """
        command = SearchRequest(self.name, self.cid,
                                self._hub.protocol_version)
        return command

    def version(self, priority=0):
        """
        A convenience method: generate a valid :class:`VersionRequest`.

        This method does not update any important state. The command only has
        an effect if it is passed to the :meth:`send` method of the
        corresponding :class:`VirtualCircuit`.

        Parameters
        ----------
        priority : integer, optional
            May be used by the server to prioritize requests when under high
            load. Lowest priority is 0; highest is 99. Default is 0.

        Returns
        -------
        VirtualCircuit, VersionRequest

        See Also
        --------
        :meth:`version_broadcast`
        """
        return self.circuit, self.version_broadcast(priority)

    def host_name(self, host_name=OUR_HOSTNAME):
        """
        A convenience method: generate a valid :class:`HostNameRequest`.

        This method does not update any important state. The command only has
        an effect if it is passed to the :meth:`send` method of the
        corresponding :class:`VirtualCircuit`.

        Parameters
        ----------
        host_name : string, optional
            defaults to output of ``socket.gethostname()``

        Returns
        -------
        VirtualCircuit, HostNameRequest
        """
        command = HostNameRequest(host_name)
        return self.circuit, command

    def client_name(self, client_name=OUR_USERNAME):
        """
        A convenience method: generate a valid :class:`ClientNameRequest`.

        This method does not update any important state. The command only has
        an effect if it is passed to the :meth:`send` method of the
        corresponding :class:`VirtualCircuit`.

        Parameters
        ----------
        client_name : string, optional
            defaults to output of ``getuser.getpass()``

        Returns
        -------
        VirtualCircuit, ClientNameRequest
        """
        command = ClientNameRequest(client_name)
        return self.circuit, command

    def create(self):
        """
        A convenience method: generate a valid :class:`CreateChanRequest`.

        This method does not update any important state. The command only has
        an effect if it is passed to the :meth:`send` method of the
        corresponding :class:`VirtualCircuit`.

        Returns
        -------
        VirtualCircuit, CreateChanRequest
        """
        command = CreateChanRequest(self.name, self.cid,
                                    self._hub.protocol_version)
        return self.circuit, command

    def clear(self):
        """
        A convenience method: generate a valid :class:`ClearChannelRequest`.

        This method does not update any important state. The command only has
        an effect if it is passed to the :meth:`send` method of the
        corresponding :class:`VirtualCircuit`.

        Returns
        -------
        VirtualCircuit, ClearChannelRequest
        """
        command = ClearChannelRequest(self.sid, self.cid)
        return self.circuit, command

    def read(self, data_type=None, data_count=None):
        """
        A convenience method: generate a valid :class:`ReadNotifyRequest`.

        This method does not update any important state. The command only has
        an effect if it is passed to the :meth:`send` method of the
        corresponding :class:`VirtualCircuit`.

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
        VirtualCircuit, ReadNotifyRequest
        """
        data_type, data_count = self._fill_defaults(data_type, data_count)
        ioid = self.circuit.new_ioid()
        command = ReadNotifyRequest(data_type, data_count, self.sid, ioid)
        return self.circuit, command

    def write(self, data, data_type=None, data_count=None):
        """
        A convenience method: generate a valid :class:`WriteNotifyRequest`.

        This method does not update any important state. The command only has
        an effect if it is passed to the :meth:`send` method of the
        corresponding :class:`VirtualCircuit`.

        Parameters
        ----------
        data : object
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
        VirtualCircuit, WriteNotifyRequest
        """
        data_type, data_count = self._fill_defaults(data_type, data_count)
        ioid = self.circuit.new_ioid()
        command = ReadNotifyRequest(data_type, data_count, self.sid, ioid)
        return self.circuit, command

    def subscribe(self, data_type=None, data_count=None, low=0.0, high=0.0,
                  to=0.0, mask=None):
        """
        A convenience method: generate a valid :class:`EventAddRequest`.

        This method does not update any important state. The command only has
        an effect if it is passed to the :meth:`send` method of the
        corresponding :class:`VirtualCircuit`.

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
        VirtualCircuit, EventAddRequest
        """
        data_type, data_count = self._fill_defaults(data_type, data_count)
        if mask is None:
            mask = DBE_VALUE | DBE_ALARM | DBE_PROPERTY
        subscriptionid = self.circuit.new_subscriptionid()
        command = EventAddRequest(data_type, data_count, self.sid,
                                  subscriptionid, low, high, to, mask)
        return self.circuit, command

    def unsubscribe(self, subscriptionid):
        """
        A convenience method: generate a valid :class:`EventAddRequest`.

        This method does not update any important state. The command only has
        an effect if it is passed to the :meth:`send` method of the
        corresponding :class:`VirtualCircuit`.

        Parameters
        ----------
        subscriptionid : integer
            The ``subscriptionid`` that was originally sent in the
            corresponding :class:`EventAddRequest`.

        Returns
        -------
        VirtualCircuit, EventAddRequest
        """
        try:
            event_add = self.circuit.sub_commands[subscriptionid]
        except KeyError:
            raise CaprotoKeyError("No current subscription has id {!r}"
                                  "".format(subscriptionid))
        if event_add.sid != self.sid:
            raise CaprotoValueError("This subscription is for a different "
                                    "Channel.")
        command = EventCancelRequest(event_add.data_type, self.sid,
                                     subscriptionid)
        return self.circuit, command


class ServerChannel(_BaseChannel):
    def version_broadcast_response(self):
        """
        A convenience method: generate a valid :class:`VersionRespone`.

        This method does not update any important state. The command only has
        an effect if it is passed to the :meth:`send_broadcast` method of the
        Hub.

        Note that, unlike all the other :class:`ServerChannel` convenience
        mehtods, this does not return a VirtualCircuit. It should be passed to
        ``Hub.send_broadcast`` and broadcast over UDP.

        Returns
        -------
        VersionResponse

        See Also
        --------
        :meth:`version_response`
        """
        comamnd = VersionResponse(self._hub.protocol_version)
        return command

    def search_broadcast_response(self, server_address):
        """
        A convenience method: generate a valid :class:`SearchRespone`.

        This method does not update any important state. The command only has
        an effect if it is passed to the :meth:`send_broadcast` method of the
        Hub.

        Note that, unlike all the other :class:`ServerChannel` convenience
        mehtods, this does not return a VirtualCircuit. It should be passed to
        ``Hub.send_broadcast`` and broadcast over UDP.

        Parameters
        ----------
        server_address : tuple
            ``(host, port)`` where server is accepting TCP connections

        Returns
        -------
        SearchResponse
        """
        command = SearchResponse(port=server_port, sid=server_host,
                                 cid=self.cid, version=version)
        return command

    def version_reponse(self, version):
        """
        A convenience method: generate a valid :class:`VersionResponse`.

        This method does not update any important state. The command only has
        an effect if it is passed to the :meth:`send` method of the
        corresponding :class:`VirtualCircuit`.

        Returns
        -------
        VirtualCircuit, VersionResponse

        See Also
        --------
        :meth:`version_broadcast_response`
        """
        return self.circuit, self.version_broadcast_response(version)

    def create_response(self, native_data_type, native_data_count, sid):
        """
        A convenience method: generate a valid :class:`CreateChanResponse`.

        This method does not update any important state. The command only has
        an effect if it is passed to the :meth:`send` method of the
        corresponding :class:`VirtualCircuit`.

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
        VirtualCircuit, CreateChanResponse
        """
        command = CreateChanResponse(native_data_type, native_data_count,
                                     self.cid, sid)
        return self.circuit, command

    def clear(self):
        """
        A convenience method: generate a valid :class:`ClearChannelResponse`.

        This method does not update any important state. The command only has
        an effect if it is passed to the :meth:`send` method of the
        corresponding :class:`VirtualCircuit`.

        Returns
        -------
        VirtualCircuit, ClearChannelResponse
        """
        command = ClearChannelResponse(self.sid, self.cid)
        return self.circuit, command

    def read_response(self, values, ioid, data_type=None, data_count=None,
                      status=1):
        """
        A convenience method: generate a valid :class:`ReadNotifyResponse`.

        This method does not update any important state. The command only has
        an effect if it is passed to the :meth:`send` method of the
        corresponding :class:`VirtualCircuit`.

        Parameters
        ----------
        values : ???
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
        VirtualCircuit, ReadNotifyResponse
        """
        data_type, data_count = self._fill_defaults(data_type, data_count)
        command = ReadNotifyResponse(values, data_type, data_count, status,
                                     ioid)
        return self.circuit, command

    def write_response(self, ioid, data_type=None, data_count=None, status=1):
        """
        A convenience method: generate a valid :class:`WriteNotifyResponse`.

        This method does not update any important state. The command only has
        an effect if it is passed to the :meth:`send` method of the
        corresponding :class:`VirtualCircuit`.

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
        VirtualCircuit, WriteNotifyResponse
        """
        data_type, data_count = self._fill_defaults(data_type, data_count)
        command = WriteNotifyResponse(data_type, data_count, status, ioid)
        return self.circuit, command

    def subscribe_response(self, values, subscriptionid, data_type=None,
                           data_count=None, status_code=32):
        """
        A convenience method: generate a valid :class:`EventAddResponse`.

        This method does not update any important state. The command only has
        an effect if it is passed to the :meth:`send` method of the
        corresponding :class:`VirtualCircuit`.

        Parameters
        ----------
        values :
        subscriptionid :
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

        Returns
        -------
        VirtualCircuit, EventAddResponse
        """
        # TODO It's unclear what the status_code means here.
        data_type, data_count = self._fill_defaults(data_type, data_count)
        command = EventAddResponse(values, data_type, data_count, status_code,
                                   subscriptionid)
        return self.circuit, command

    def unsubscribe_response(self, subscriptionid, data_type=None,
                             data_count=None):
        """
        A convenience method: generate a valid :class:`EventCancelResponse`.

        This method does not update any important state. The command only has
        an effect if it is passed to the :meth:`send` method of the
        corresponding :class:`VirtualCircuit`.

        Parameters
        ----------
        subscriptionid :
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
        VirtualCircuit, EventCancelResponse
        """
        # TODO How does CA actually work? It seems to break its spec.
        ...
