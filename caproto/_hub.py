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
    """
    def __init__(self, hub, address, priority, data):
        self._hub = hub
        self.address = address
        self.priority = priority
        self._state = CircuitState()
        self._data = data
        self.channels = {}  # map cid to Channel
        self._channels_sid = {}  # map sid to Channel
        self._ioids = {}  # map ioid to Channel
        self._subinfo = {}  # map subscriptionid to stashed EventAdd command
        # There are only used by the convenience methods, to auto-generate ids.
        self._ioid_counter = itertools.count(0)
        self._sub_counter = itertools.count(0)
        # Copy these (immutable) hub attributes for convenience.
        self.our_role = hub.our_role
        self.their_role = hub.their_role

    def add_channel(self, channel):
        self.channels[channel.cid] = channel

    def send(self, command):
        """
        Convert a high-level Command into bytes that can be sent to the peer,
        while updating our internal state machine.
        """
        self._process_command(self.our_role, command)
        return bytes(command)

    def recv(self, byteslike):
        """
        Add data received over TCP to our internal recieve buffer.

        This does not actually do any processing on the data, just stores
        it. To trigger processing, you have to call :meth:`next_command`.
        """
        self._data += byteslike

    def next_command(self):
        """
        Parse the next Command out of our internal receive buffer, update our
        internal state machine, and return it.

        Returns a :class:`Command` object or a special constant,
        :data:`NEED_DATA`.
        """
        self._data, command = read_from_bytestream(self._data, self.their_role)
        if type(command) is not NEED_DATA:
            self._process_command(self.our_role, command)
        return command

    def _process_command(self, role, command):
        # All commands go through here.

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
                    subinfo = self._subinfo[command.subscriptionid]
                except KeyError:
                    err = get_exception(self.our_role, command)
                    raise err("Unrecognized subscriptionid {!r}"
                              "".format(subscriptionid))
                chan = self._channels_sid[subinfo.sid]
            elif isinstance(command, CreateChanRequest):
                # A (Server|Client)Channel will have been craeted for this cid
                # when the SearchRequest was processed by the Hub, but the
                # Channel has not yet been claimed by a VirtualCircuit.
                try:
                    chan = self._hub.channels[command.cid]
                except KeyError:
                    err = _get_exception(self.our_role, command)
                    raise err("Cannot process CreateChanRequest for cid={!r} "
                              "until a SearchRequest for that cid is "
                              "broadcast.")
                # TODO Validate that this channel has not already been Created
            else:
                # In all other cases, the Command gives us a cid.
                cid = command.cid
                chan = self.channels[cid]

            # Do some additional validation on commands related to an existing
            # subscription.
            if isinstance(command, (EventAddResponse, EventCancelRequest,
                                    EventCancelResponse)):
                # Verify data_type matches the one in the original request.
                subinfo = self._subinfo[command.subscriptionid]
                if subinfo.data_type != command.data_type:
                    err = get_exception(self.our_role, command)
                    raise err("The data_type in {!r} does not match the "
                                "data_type in the original EventAddRequest "
                                "for this subscriptionid, {!r}."
                                "".format(command, subinfo.data_type))
            if isinstance(command, (EventAddResponse,)):
                # Verify data_count matches the one in the original request.
                # NOTE The docs say that EventCancelRequest should echo the
                # original data_count too, but in fact it seems to be 0.
                subinfo = self._subinfo[command.subscriptionid]
                if subinfo.data_count != command.data_count:
                    err = get_exception(self.our_role, command)
                    raise err("The data_count in {!r} does not match the "
                                "data_count in the original EventAddRequest "
                                "for this subscriptionid, {!r}."
                                "".format(command, subinfo.data_count))
            if isinstance(command, (EventCancelRequest, EventCancelResponse)):
                # Verify sid matches the one in the original request.
                subinfo = self._subinfo[command.subscriptionid]
                if subinfo.sid != command.sid:
                    err = get_exception(self.our_role, command)
                    raise err("The sid in {!r} does not match the sid in "
                                "in the original EventAddRequest for this "
                                "subscriptionid, {!r}."
                                "".format(command, subinfo.sid))
            if isinstance(command, CreateChanRequest):
                self.add_channel(chan)

            # Update the state machine of the pertinent Channel.
            # If this is not a valid command, the state machine will raise
            # here.
            chan._state.process_command(self.our_role, type(command))
            chan._state.process_command(self.their_role, type(command))

            # If we got this far, the state machine has validated this Command.
            # Update other Channel and Circuit state.
            if isinstance(command, (ReadNotifyRequest, WriteNotifyRequest)):
                # Stash the ioid for later reference.
                self._ioids[command.ioid] = chan
            elif isinstance(command, CreateChanResponse):
                chan.native_data_type = command.data_type
                chan.native_data_count = command.data_count
                chan.sid = command.sid
                self._channels_sid[chan.sid] = chan
            elif isinstance(command, EventAddRequest):
                # We will use the info in this command later to validate that
                # {EventAddResponse, EventCancelRequest, EventCancelResponse}
                # send or received in the future are valid.
                self._subinfo[command.subscriptionid] = command
            elif isinstance(command, EventCancelResponse):
                self._subinfo.pop(subscriptionid)

        # Otherwise, this Command affects the state of this circuit, not a
        # specific Channel. Run the circuit's state machine.
        else:
            self._state.process_command(self.our_role, type(command))
            self._state.process_command(self.their_role, type(command))

        # The VersionRequest is handled by VirtualCircuitProxy. Here, simply
        # ensure that we are not getting contradictory information.
        if isinstance(command, VersionRequest):
            if self.priority != command.priority:
                err = _get_exception(self.our_role, command)
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

    @property
    def address(self):
        if self.our_role is CLIENT:
            return self.host, self.port
        else:
            raise TypeError("Only a CLIENT-side VirtualCircuit has a complete "
                            "address. A SERVER-side only has a port.")


class VirtualCircuitProxy:
    """
    For that awkward moment when you know the address of a circuit but you
    don't yet know the prioirty, so you can't know whether this can use an
    existing TCP connection or needs a new one.
    """
    def __init__(self, hub, address):
        self._hub = hub
        self.address = address
        self.our_role = self._hub.our_role
        self.their_role = self._hub.their_role
        self.__circuit = None
        self._data = bytearray()  # will get handed off to VirtualCircuit

    def _bind_circuit(self, priority):
        # Identify an existing VirtcuitCircuit with the right address and
        # priority, or create one.
        key = (self.address, priority)
        try:
            circuit = self._hub.circuits[key]
        except KeyError:
            circuit = VirtualCircuit(hub=self._hub,
                                     address=self.address,
                                     priority=priority, data=self._data)

            self._hub.circuits[key] = circuit
        self.__circuit = circuit

    def send(self, command):
        """
        Convert a high-level Command into bytes that can be sent to the peer,
        while updating our internal state machine.
        """
        if self.__circuit is None:
            if isinstance(command, VersionRequest):
                self._bind_circuit(command.priority)
            else:
                err = _get_exception(command, self.our_role)
                raise err("This circuit must be initialized with a "
                          "VersionRequest.")
        self.__circuit._process_command(self.our_role, command)
        return bytes(command)

    def recv(self, byteslike):
        """
        Add data received over TCP to our internal recieve buffer.

        This does not actually do any processing on the data, just stores
        it. To trigger processing, you have to call :meth:`next_command`.
        """
        if self.__circuit is None:
            self._data += byteslike
        else:
            return self.__circuit.recv(byteslike)

    def next_command(self):
        """
        Parse the next Command out of our internal receive buffer, update our
        internal state machine, and return it.

        Returns a :class:`Command` object or a special constant,
        :data:`NEED_DATA`.
        """
        if self.__circuit is None:
            self._data, command = read_from_bytestream(self._data,
                                                       self.their_role)
            if type(command) is not NEED_DATA:
                if isinstance(command, VersionRequest):
                    self._bind_circuit(command.priority)
                else:
                    err = _get_exception(command, self.our_role)
                    raise err("This circuit must be initialized with a "
                            "VersionRequest.")
                self._circuit._process_command(self.our_role, command)
        else:
            return self._circuit.next_command()

    @property
    def _circuit(self):
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

    @property
    def address(self):
        if self.our_role is CLIENT:
            return self.host, self.port
        else:
            raise TypeError("Only a CLIENT-side VirtualCircuit has a complete "
                            "address. A SERVER-side only has a port.")

    # Define pass-through methods for every public method of VirtualCircuit.
    def new_subscriptionid(self):
        __doc__ = self._circuit.new_subscriptionid.__doc__
        return self._circuit.new_subscriptionid()

    def new_ioid(self):
        __doc__ = self._circuit.new_ioid.__doc__
        return self._circuit.new_ioid()

    @property
    def priority(self):
        return self._circuit.priority

    @property
    def channels(self):
        return self._circuit.channels

    @property
    def _subinfo(self):
        # TODO Provide a public access for this on VirtualCircuit.
        return self._circuit._subinfo

    @property
    def _state(self):
        # TODO Remove this once _state.py is refactored properly.
        return self._circuit._state


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
    """

    def __init__(self, our_role):
        if our_role not in (SERVER, CLIENT):
            raise CaprotoValueError("role must be caproto.SERVER or "
                                    "caproto.CLIENT")
        self.our_role = our_role
        if our_role is CLIENT:
            self.their_role = SERVER
        else:
            self.their_role = CLIENT
        self._names = {}  # map known Channel names to (host, port)
        self.circuits = {}  # keyed by ((host, port), priority)
        self.channels = {}  # map cid to Channel
        self._datagram_inbox = deque()  # datagrams to be parsed into Commands
        self._history = []  # commands parsed so far from current datagram
        self._parsed_commands = deque()  # parsed Commands to be processed
        # This is only used by the convenience methods, to auto-generate a cid.
        self._cid_counter = itertools.count(0)

    def send_broadcast(self, *commands):
        """
        Convert one or more high-level Commands into bytes that may be
        broadcast together in one UDP datagram while updating our internal
        state machine.
        """
        bytes_to_send = b''
        history = []
        for command in commands:
            history = self._process_command(self.our_role, command, history)
            bytes_to_send += bytes(command)
        return bytes_to_send

    def recv_broadcast(self, byteslike, address):
        """
        Add data from a UDP broadcast to our internal recieve buffer.

        This does not actually do any processing on the data, just stores
        it. To trigger processing, you have to call :meth:`next_command`.
        """
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
            self._parsed_commands.extend(commands)
        command = self._parsed_commands.popleft()
        self._process_command(self.their_role, command, self._history)
        return command

    def _process_command(self, role, command, history):
        # All commands go through here.
        if isinstance(command, SearchRequest):
            if VersionRequest not in map(type, history):
                err = _get_exception(self, command)
                raise err("A broadcasted SearchRequest must be preceded by a "
                          "VersionRequest in the same datagram.")
            cid = command.cid
            try:
                # Maybe the user has manually instantiated a Channel instance
                # with this cid. This is typically (but not necessarily) the
                # case if we are a CLIENT. It is never the case if we are a
                # SERVER.
                chan = self.channels[cid]
            except KeyError:
                # If here, we don't yet have a Channel for this cid. Make one.
                # It will be accessible via self.channels.
                chan = self.new_channel(name=command.name, cid=cid)
            chan._state.process_command(self.our_role, type(command))
            chan._state.process_command(self.their_role, type(command))
        elif isinstance(command, SearchResponse):
            if VersionResponse not in map(type, history):
                err = _get_exception(self, command)
                raise err("A broadcasted SearchResponse must be preceded by a "
                          "VersionResponse in the same datagram.")
            # Update the state machine of the pertinent Channel.
            chan = self.channels[command.cid]
            chan._state.process_command(self.our_role, type(command))
            chan._state.process_command(self.their_role, type(command))
            # Get the address for the VirtualCircuit that TCP
            # communication about this Channel should take place on.
            if self.our_role is CLIENT:
                # Our end of the circuit should hold the address of the server.
                if command.header.parameter1 == 0xffffffff:
                    adddress = command.sender_address
                else:
                    address = command.sid, command.port
            else:
                # Our end of the circuit should hold the address of the client.
                address = command.sender_address
            # We now know the Channel's address so we can assign it to a
            # VirtualCircuitProxy. We will not know the Channel's priority
            # until we see a VersionRequest, hence the *Proxy* in
            # VirtualCircuitProxy.
            circuit = VirtualCircuitProxy(self, address)
            self.circuits[address] = circuit
            chan.circuit = circuit
            # Separately, stash the address where we found this name. This
            # information might remain useful beyond the lifecycle of the
            # circuit.
            self._names[chan.name] = address
        history.append(command)
        return history

    def new_cid(self):
        # This is used by the convenience methods. It does not update any
        # important state.
        # TODO Be more clever and reuse abandoned cids; avoid overrunning.
        return next(self._cid_counter)

    def new_channel(self, name, cid=None):
        """
        A convenience method: instantiate a new :class:`ClientChannel` or
        :class:`ServerChannel`, corresponding to :attr:`our_role`.

        This method does not update any important state. It is equivalent to:
        ``<ChannelClass>(<Hub>, None, <UNIQUE_INT>, name)``
        """
        # This method does not change any state other than the cid counter,
        # which is neither important nor coupled to anything else.
        if cid is None:
            cid = self.new_cid()
        circuit = None
        _class = {CLIENT: ClientChannel, SERVER: ServerChannel}[self.our_role]
        channel = _class(self, circuit, cid, name)
        # If this Client has searched for this name and already knows its
        # host, skip the Search step and create a circuit.
        # if name in self._names:
        #     circuit = self.circuits[(self._names[name], priority)]
        return channel


class _BaseChannel:
    # This is subclassed by ClientChannel and ServerChannel, which merely add
    # convenience methods that compose valid commands. They do not mutate any
    # _BaseChannel state. All the critical code is here in the base class.
    def __init__(self, hub, circuit, cid, name):
        self._hub = hub
        self._circuit = circuit  # may be None at __init__ time
        self.cid = cid
        self.name = name
        self._state = ChannelState()
        # The Channel maybe not have a circuit yet, but it always needs to be
        # registered by a Hub. When the Hub processes a SearchRequest Command
        # regarding this Channel, that Command includes this Channel's cid,
        # which the Hub can use to identify this Channel instance.
        hub.channels[cid] = self
        # These are updated when the circuit processes CreateChanResponse.
        self.native_data_type = None
        self.native_data_count = None
        self.sid = None

    def _fill_defaults(self, data_type, data_count):
        # Boilerplate used in many convenience methods:
        # Replace `None` default arg with actual default value.
        if data_type is None:
            data_type = self.native_data_type
        if data_count is None:
            data_count = self.native_data_count
        return data_type, data_count

    @property
    def circuit(self):
        return self._circuit

    @circuit.setter
    def circuit(self, circuit):
        # The hub assigns a VirtualCircuit to this Channel.
        # This occurs when a :class:`SearchResponse` locating the Channel's
        # name is processed.
        if self._circuit is None:
            self._circuit = circuit
            self._state.couple_circuit(circuit)
        else:
            raise RuntimeError("circuit may only be set once")


class ClientChannel(_BaseChannel):
    """An object encapsulating the state of the EPICS Channel on a Client.

    A Channel may be created as soon as the desired ``name`` is known, maybe
    before the server providing that name is located.

    A Channel will be assigned to a VirtualCircuit (corresponding to one
    client--server TCP connection), which is may share with other Channels.

    Parameters
    ----------
    hub : :class:`Hub`
    circuit : None or :class:VirtualCircuit`
    cid : integer
        unique Channel ID
    name : string
        Channnel name (PV)
    """

    def version_broadcast(self, priority):
        """
        A convenience method: generate a valid :class:`VersionRequest`.

        This method does not update any important state. The command only has
        an effect if it is passed to the :meth:`send` method of the Hub.

        Note that, unlike most the other :class:`ClientChannel` convenience
        mehtods, this does not return a VirtualCircuit. It should be passed to
        ``Hub.send_broadcast`` and broadcast over UDP.


        Parameters
        ----------
        priority : integer or None
            May be used by the server to prioritize requests when under high
            load. Lowest priority is 0; highest is 99.

        Returns
        -------
        VersionRequest

        See Also
        --------
        :meth:`version_broadcast`
        """
        command = VersionRequest(DEFAULT_PROTOCOL_VERSION, priority)
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
        command = SearchRequest(self.name, self.cid, DEFAULT_PROTOCOL_VERSION)
        return command

    def version(self, priority):
        """
        A convenience method: generate a valid :class:`VersionRequest`.

        This method does not update any important state. The command only has
        an effect if it is passed to the :meth:`send` method of the
        corresponding :class:`VirtualCircuit`.

        Parameters
        ----------
        priority : integer or None
            May be used by the server to prioritize requests when under high
            load. Lowest priority is 0; highest is 99.

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
                                    DEFAULT_PROTOCOL_VERSION)
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
        data : object

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
        data : object

        Returns
        -------
        VirtualCircuit, EventAddRequest
        """
        try:
            sub_info = self.circuit._subinfo[subscriptionid]
        except KeyError:
            raise CaprotoKeyError("No current subscription has id {!r}"
                                  "".format(subscriptionid))
        if sub_info.sid != self.sid:
            raise CaprotoValueError("This subscription is for a different "
                                    "Channel.")
        command = EventCancelRequest(sub_info.data_type, self.sid,
                                     subscriptionid)
        return self.circuit, command


class ServerChannel(_BaseChannel):
    """An object encapsulating the state of the EPICS Channel on a Server.

    A Channel will be assigned to a VirtualCircuit (corresponding to one
    client--server TCP connection), which is may share with other Channels
    to that same Client.

    Parameters
    ----------
    hub : :class:`Hub`
    circuit : None or :class:VirtualCircuit`
    cid : integer
        unique Channel ID
    name : string
        Channnel name (PV)
    """
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
        comamnd = VersionResponse(DEFAULT_PROTOCOL_VERSION)
        return command

    def search_broadcast_response(self, sid=None):
        """
        A convenience method: generate a valid :class:`SearchRespone`.

        This method does not update any important state. The command only has
        an effect if it is passed to the :meth:`send_broadcast` method of the
        Hub.

        Note that, unlike all the other :class:`ServerChannel` convenience
        mehtods, this does not return a VirtualCircuit. It should be passed to
        ``Hub.send_broadcast`` and broadcast over UDP.

        Returns
        -------
        SearchResponse
        """
        if sid is None:
            sid = host
        host, port = self.circuit.address
        print(host, port)
        # The sid part of the SearchResponse spec is deprecated.
        command = SearchResponse(port=port, sid=host, cid=self.cid,
                                 version=DEFAULT_PROTOCOL_VERSION)
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

    def create_response(self, data_type, data_count, sid):
        """
        A convenience method: generate a valid :class:`CreateChanResponse`.

        This method does not update any important state. The command only has
        an effect if it is passed to the :meth:`send` method of the
        corresponding :class:`VirtualCircuit`.

        Returns
        -------
        VirtualCircuit, CreateChanResponse
        """
        command = CreateChanResponse(data_type, data_count, self.cid, sid)
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

        Returns
        -------
        VirtualCircuit, EventCancelResponse
        """
        # TODO How does CA actually work? It seems to break its spec.
        ...

def _get_exception(our_role, command):
    """
    Return a (Local|Remote)ProtocolError depending on which command this is and
    which role we are playing.

    Note that this method does not raise; it is up to the caller to raise.

    Parameters
    ----------
    our_role: CLIENT or SERVER
    command : Message
        We will test whether it is a REQUEST or RESPONSE.
    """
    # TO DO Give commands an attribute so we can easily check whether one
    # is a Request or a Response
    if command.DIRECTION is REQUEST:
        party_at_fault = CLIENT
    elif command.DIRECTION is RESPONSE:
        party_at_fault = SERVER
    if our_role is party_at_fault:
        _class = LocalProtocolError
    else:
        _class =  RemoteProtocolError
    return _class
