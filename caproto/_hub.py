# This module defines two classes that encapsulate key abstractions in # Channel Access: Channels and VirtualCircuits. Each VirtualCircuit is a
# companion to a (user-managed) TCP socket, updating its state in response to
# incoming and outgoing TCP bytestreams. A third class, the Hub, owns these
# VirtualCircuits and spawns new ones as needed. The Hub updates its state in
# response to incoming and outgoing UDP datagrams.
import ctypes
import itertools
from io import BytesIO
from collections import defaultdict, deque
from ._commands import *
from ._dbr_types import *
from ._state import *
from ._utils import *


DEFAULT_PROTOCOL_VERSION = 13


class VirtualCircuit:
    """
    An object encapulating the state of one CA client--server connection.

    This object can be created as soon as we know the address ``(host, port))``
    of our peer (client/server depending on our role).

    It is a companion to a TCP socket managed by the user. All data
    received over the socket should be passed to :meth:`recv`. Any data sent
    over the socket should first be passed through :meth:`send`.
    """
    def __init__(self, address, priority):
        self.our_role = CLIENT
        self.their_role = SERVER
        self.address = address
        self.priority = priority
        self._state = CircuitState()
        self._data = bytearray()
        self.channels = {}
        self._channels_sid = {}
        self._ioids = {}
        # This is only used by the convenience methods, to auto-generate ioid.
        self._ioid_counter = itertools.count(0)

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
            if isinstance(command, (ReadNotifyRequest, WriteNotifyRequest)):
                # Identify the Channel based on its sid.
                ioid, sid = command.ioid, command.sid
                chan = self._channels_sid[sid]
            elif isinstance(command, (ReadNotifyResponse,
                                      WriteNotifyResponse)):
                # Identify the Channel based on its ioid.
                chan = self._ioids[command.ioid]
            else:
                # In all other cases, the Command gives us a cid.
                cid = command.cid
                chan = self.channels[cid]

            # Update the state machine of the pertinent Channel.
            # If this is not a valid command, the state machine will raise
            # here.
            chan._state.process_command(self.our_role, type(command))
            chan._state.process_command(self.their_role, type(command))

            # If we got this far, the state machine has validated this Command.
            # Update other Channel and Circuit state..
            if isinstance(command, (ReadNotifyRequest, WriteNotifyRequest)):
                # Stash the ioid for later reference.
                self._ioids[ioid] = chan
            elif isinstance(command, CreateChanResponse):
                chan.native_data_type = command.data_type 
                chan.native_data_count = command.data_count
                chan.sid = command.sid
                self._channels_sid[chan.sid] = chan

        # Otherwise, this Command affects the state of this circuit, not a
        # specific Channel. Run the circuit's state machine.
        else:
            self._state.process_command(self.our_role, type(command))
            self._state.process_command(self.their_role, type(command))

    def new_ioid(self):
        # This is used by the convenience methods. It does not update any
        # important state.
        # TODO Be more clever and reuse abandoned ioids; avoid overrunning.
        return next(self._ioid_counter)

    def add_channel(self, channel):
        # This is called by the Hub when a SearchRequest is processed that
        # associates some Channel with this circuit.
        self.channels[channel.cid] = channel


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
    and to decode incomming bytestreams into these same kinds of objects.
    """

    def __init__(self, our_role):
        if our_role not in (SERVER, CLIENT):
            raise ValueError('role must be caproto.SERVER or caproto.CLIENT')
        self.our_role = our_role
        if our_role is CLIENT:
            self.their_role = SERVER
        else:
            self.their_role = CLIENT
        self._names = {}  # map known Channel names to (host, port)
        self.circuits = {}  # keyed by ((host, port), priority)
        self.channels = {}  # map cid to Channel
        self._datagram_inbox = deque()  # datagrams to be parsed into Commands
        self._parsed_commands = deque()  # parsed Commands to be processed
        # This is only used by the convenience methods, to auto-generate a cid.
        self._cid_counter = itertools.count(0)

    def send_broadcast(self, command):
        """
        Convert a high-level Command into bytes that can be broadcast over UDP,
        while updating our internal state machine.
        """
        self._process_command(self.our_role, command)
        return bytes(command)

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
            byteslike, address = self._datagram_inbox.popleft()
            commands = read_datagram(byteslike, address, self.their_role)
            self._parsed_commands.extend(commands)
        command = self._parsed_commands.popleft()
        self._process_command(self.their_role, command)
        return command

    def _process_command(self, role, command):
        # All commands go through here.
        if isinstance(command, SearchRequest):
            cid = command.cid
            try:
                # If the user instantiated a Channel for this cid, then it is
                # already registered with the Hub.
                chan = self.channels[cid]
            except KeyError:
                # The user has not instantiated a Channel for this cid.
                # Create one.
                chan = Channel(self, None, cid, command.name, command.priority)
            chan._state.process_command(self.our_role, type(command))
            chan._state.process_command(self.their_role, type(command))
        elif isinstance(command, SearchResponse):
            # Update the state machine of the pertinent Channel.
            chan = self.channels[command.cid]
            chan._state.process_command(self.our_role, type(command))
            chan._state.process_command(self.their_role, type(command))
            # Identify an existing VirtcuitCircuit with the right address and
            # priority, or create one.
            key = (command.address, chan.priority)
            try:
                circuit = self.circuits[key]
            except KeyError:
                circuit = VirtualCircuit(*key)
                self.circuits[key] = circuit
            chan.circuit = circuit
            circuit.add_channel(chan)
            # Separately, stash the address where we found this name. This
            # information might remain useful beyond the lifecycle of the
            # circuit.
            self._names[chan.name] = command.address

    def new_cid(self):
        # This is used by the convenience methods. It does not update any
        # important state.
        # TODO Be more clever and reuse abandoned cids; avoid overrunning.
        return next(self._cid_counter)

    def new_channel(self, name, priority=0):
        """
        A convenience method: instantiate a new :class:`Channel`.

        This method does not update any important state. It is equivalent to:
        ``Channel(<Hub>, None, <UNIQUE_INT>, name, priority)``
        """
        # This method does not change any state other than the cid counter,
        # which is neither important nor coupled to anything else.
        cid = self.new_cid()
        circuit = None
        channel = Channel(self, circuit, cid, name, priority)
        # If this Client has searched for this name and already knows its
        # host, skip the Search step and create a circuit.
        # if name in self._names:
        #     circuit = self.circuits[(self._names[name], priority)]
        return channel

    def add_channel(self, channel):
        # called by Channel.__init__ to register Channel with Hub
        self.channels[channel.cid] = channel


class Channel:
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
    priority : integer
        Controls priority given to this channel by the server. Must be between
        0 (lowest priority) and 99 (highest), inclusive.
    """
    def __init__(self, hub, circuit, cid, name, priority=0):
        self._hub = hub
        self._circuit = circuit  # may be None at __init__ time
        self.cid = cid
        self.name = name
        self.priority = priority  # on [0, 99]
        self._state = ChannelState()
        # The Channel maybe not have a circuit yet, but it always needs to be
        # registered by a Hub. When the Hub processes a SearchRequest Command
        # regarding this Channel, that Command includes this Channel's cid,
        # which the Hub can use to identify this Channel instance.
        self._hub.add_channel(self)
        # These are updated when the circuit processes CreateChanResponse.
        self.native_data_type = None
        self.native_data_count = None
        self.sid = None

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

    def search(self):
        """
        A convenience method: generate a valid :class:`SearchRequest`.

        Returns
        -------
        circuit, SearchRequest
        """
        return SearchRequest(self.name, self.cid, DEFAULT_PROTOCOL_VERSION)

    def read(self, data_type=None, data_count=None):
        """
        A convenience method: generate a valid :class:`ReadNotifyRequest`.

        This method does not update any important state. It is equivalent to:
        ``ReadNotifyRequest(data_type, data_count, <self.sid>, <UNIQUE_INT>)``

        Returns
        -------
        circuit, ReadNotifyRequest
        """
        if data_type is None:
            data_type = self.native_data_type
        if data_count is None:
            data_count = self.native_data_count
        ioid = self.circuit.new_ioid()
        return self.circuit, ReadNotifyRequest(data_type, data_count,
                                               self.sid, ioid)

    def write(self, data):
        """
        A convenience method: generate a valid :class:`WriteNotifyRequest`.

        This method does not update any important state. It is equivalent to:
        ``WriteNotifyRequest(data, data_type, data_count, <self.sid>, <UNIQUE_INT>)``

        Parameters
        ----------
        data : object

        Returns
        -------
        circuit, ReadNotifyRequest
        """
        ioid = self.circuit.new_ioid()
        return self.circuit, ReadNotifyRequest(data, data_type, data_count,
                                               self.sid, ioid)

    def subscribe(self, data_type=None, data_count=None):
        # TO DO
        if data_type is None:
            data_type = self.native_data_type
        if data_count is None:
            data_count = self.native_data_count
        return self.circuit, SubscribeRequest(...)
