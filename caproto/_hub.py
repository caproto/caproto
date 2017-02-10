# This module defines two classes that encapsulate key abstractions in
# Channel Access: Channels and VirtualCircuits. Each VirtualCircuit is a
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
        self._channels_cid = {}
        self._channels_sid = {}
        self._ioids = {}
        # This is only used by the convenience methods, to auto-generate ioid.
        self._ioid_counter = itertools.count(0)

    def new_ioid(self):
        # TODO Be more clever and reuse abandoned ioids; avoid overrunning.
        return next(self._ioid_counter)

    def add_channel(self, channel):
        self._channels_cid[channel.cid] = channel

    def send(self, command):
        self._process_command(self.our_role, command)
        return bytes(command)

    def recv(self, byteslike):
        self._data += byteslike

    def _process_command(self, role, command):
        # All commands go through here.
        if isinstance(command, (ClearChannelRequest, ClearChannelResponse,
                                CreateChanRequest)):
            # Update the state machine of the pertinent Channel.
            cid = command.cid
            chan = self._channels_cid[cid]
            chan._state.process_command(self.our_role, type(command))
            chan._state.process_command(self.their_role, type(command))
        elif isinstance(command, CreateChanResponse):
            chan = self._channels_cid[command.cid]
            chan.native_data_type = command.data_type 
            chan.native_data_count = command.data_count
            chan.sid = command.sid
            self._channels_sid[chan.sid] = chan
            chan._state.process_command(self.our_role, type(command))
            chan._state.process_command(self.their_role, type(command))
        elif isinstance(command, (ReadNotifyRequest, WriteNotifyRequest)):
            chan = self._ioids[command.ioid] = self._channels_sid[command.sid]
            chan._state.process_command(self.our_role, type(command))
            chan._state.process_command(self.their_role, type(command))
        elif isinstance(command, (ReadNotifyResponse, WriteNotifyResponse)):
            chan = self._ioids[command.ioid]
            chan._state.process_command(self.our_role, type(command))
            chan._state.process_command(self.their_role, type(command))
        else:
            self._state.process_command(self.our_role, type(command))
            self._state.process_command(self.their_role, type(command))

    def next_command(self):
        self._data, command = read_from_bytestream(self._data, self.their_role)
        if type(command) is not NEED_DATA:
            self._process_command(self.our_role, command)
        return command


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
        self._circuits = {}  # keyed by ((host, port), priority)
        self._channels = {}  # map cid to Channel
        self._datagram_inbox = deque()  # datagrams to be parsed into Commands
        self._parsed_commands = deque()  # parsed Commands to be processed
        # This is only used by the convenience methods, to auto-generate a cid.
        self._cid_counter = itertools.count(0)

    def new_cid(self):
        # TODO Be more clever and reuse abandoned cids; avoid overrunning.
        return next(self._cid_counter)

    def new_channel(self, name, priority=0):
        """
        A convenience method: instantiate a new :class:`Channel`.

        You are not required to use this method; you can also role your own
        :class:`Channel`. The Hub state will not be updated until a
        :class:`SearchResponse` for this :class:`Channel` is processed.

        This is equivalent to:

        ``Channel(<Hub>, None, <UNIQUE_INTEGER>, name, priority)``
        """
        # This method does not change any state other than the cid counter,
        # which is neither important nor coupled to anything else.
        cid = self.new_cid()
        circuit = None
        channel = Channel(name, circuit, cid, name, priority)
        self._channels[cid] = channel
        # If this Client has searched for this name and already knows its
        # host, skip the Search step and create a circuit.
        # if name in self._names:
        #     circuit = self._circuits[(self._names[name], priority)]
        return channel

    def send_broadcast(self, command):
        "Return bytes to broadcast over UDP socket."
        self._process_command(self.our_role, command)
        return bytes(command)

    def recv_broadcast(self, byteslike, address):
        "Cache but do not process bytes that were received via UDP broadcast."
        self._datagram_inbox.append((byteslike, address))

    def next_command(self):
        "Process cached received bytes."
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
            # Update the state machine of the pertinent Channel.
            cid = command.header.parameter2
            chan = self._channels[cid]
            chan._state.process_command(self.our_role, type(command))
            chan._state.process_command(self.their_role, type(command))
        elif isinstance(command, SearchResponse):
            # Update the state machine of the pertinent Channel.
            chan = self._channels[command.header.parameter2]
            chan._state.process_command(self.our_role, type(command))
            chan._state.process_command(self.their_role, type(command))
            # Identify an existing VirtcuitCircuit with the right address and
            # priority, or create one.
            self._names[chan.name] = command.address
            key = (command.address, chan.priority)
            try:
                circuit = self._circuits[key]
            except KeyError:
                circuit = VirtualCircuit(*key)
                self._circuits[key] = circuit
            chan.circuit = circuit


class Channel:
    """An object encapsulating the state of the EPICS Channel on a Client.
    
    A Channel may be created as soon as the desired ``name`` is known, maybe
    before the server providing that name is located.

    A Channel will be assigned to a VirtualCircuit (corresponding to one
    client--server TCP connection), which is may share with other Channels.
    """
    def __init__(self, hub, circuit, cid, name, priority=0):
        self._hub = hub
        self._circuit = circuit  # may be None at __init__ time
        self.cid = cid
        self.name = name
        self.priority = priority  # on [0, 99]
        self._state = ChannelState()
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
            circuit.add_channel(self)
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
        if data_type is None:
            data_type = self.native_data_type
        if data_count is None:
            data_count = self.native_data_count
        return self.circuit, SubscribeRequest(...)
