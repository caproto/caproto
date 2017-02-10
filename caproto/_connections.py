# A bring-your-own-I/O implementation of Channel Access
# in the spirit of http://sans-io.readthedocs.io/
import ctypes
import itertools
from io import BytesIO
from collections import defaultdict, deque
from ._commands import *
from ._dbr_types import *
from ._state import *
from ._utils import *


__all__ = ['VirtualCircuit', 'Connections', 'Channel']


class VirtualCircuit:
    def __init__(self, address, priority):
        self.our_role = CLIENT
        self.their_role = SERVER
        self.address = address
        self.priority = priority
        self._state = CircuitState()
        self._data = bytearray()
        self._channels_cid = {}
        self._channels_sid = {}

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
        elif isinstance(command, (ReadNotifyRequest, ReadNotifyResponse)):
            print('>>>', command)
            chan = self._channels_sid[command.sid]
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


class Connections:
    """An object encapsulating the state of Channel Access connections.

    This tracks the state of:
    - one Client and all its connected Servers,
    - or one Server and all its connected Clients

    It sees all outgoing bytes before they are sent over a socket and receives
    all incoming bytes after they are received from a socket. it verifies that
    all incoming and outgoing commands abide by the Channel Access protocol,
    and it updates an internal state machine representing the state of all
    CA channels and CA virtual circuits.

    It may also be used to compose valid commands using a pleasant Python API
    and to decode incomming bytestreams into these same kinds of objects.
    """
    PROTOCOL_VERSION = 13

    def __init__(self, our_role):
        if our_role not in (SERVER, CLIENT):
            raise ValueError('role must be caproto.SERVER or caproto.CLIENT')
        self.our_role = our_role
        if our_role is CLIENT:
            self.their_role = SERVER
        else:
            self.their_role = CLIENT
        self._names = {}  # map known names to (host, port)
        self._circuits = {}  # keyed by (address, priority)
        self._channels = {}  # map cid to Channel
        self._cid_counter = itertools.count(0)
        self._datagram_inbox = deque()
        self._parsed_commands = deque()

    def new_channel(self, name, priority=0):
        cid = next(self._cid_counter)
        circuit = None
        channel = Channel(name, circuit, cid, name, priority)
        self._channels[cid] = channel
        # If this Client has searched for this name and already knows its
        # host, skip the Search step and create a circuit.
        # if name in self._names:
        #     circuit = self._circuits[(self._names[name], priority)]
        msg = SearchRequest(name, cid, self.PROTOCOL_VERSION)
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
    "An object encapsulating the state of the EPICS Channel on a Client."
    def __init__(self, client, circuit, cid, name, priority=0):
        self._cli = client
        self._circuit = circuit
        self.cid = cid
        self.name = name
        self.priority = priority
        self._state = ChannelState()
        self.native_data_type = None
        self.native_data_count = None
        self.sid = None
        self._requests = deque()

    @property
    def circuit(self):
        return self._circuit

    @circuit.setter
    def circuit(self, circuit):
        if self._circuit is None:
            self._circuit = circuit
            circuit.add_channel(self)
            self._state.couple_circuit(circuit)
        else:
            raise RuntimeError("circuit may only be set once")

    def read(self, data_type=None, data_count=None):
        if data_type is None:
            data_type = self.native_data_type
        if data_count is None:
            data_count = self.native_data_count
        return self.circuit, ReadRequest(...)

    def write(self, data):
        return self.circuit, WriteRequest(...)

    def subscribe(self, data_type=None, data_count=None):
        if data_type is None:
            data_type = self.native_data_type
        if data_count is None:
            data_count = self.native_data_count
        return self.circuit, SubscribeRequest(...)
