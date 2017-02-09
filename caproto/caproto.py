# A bring-your-own-I/O implementation of Channel Access
# in the spirit of http://sans-io.readthedocs.io/
import ctypes
import itertools
from io import BytesIO
from collections import defaultdict, deque
from ._messages import *
from ._dbr_types import *
from ._state import *


CLIENT_VERSION = 13
_MessageHeaderSize = ctypes.sizeof(MessageHeader)
_ExtendedMessageHeaderSize = ctypes.sizeof(ExtendedMessageHeader)

def parse_command_response(header):
    ...    


def extend_header(header):
    "Return True if header should be extended."
    return header.payload_size == 0xFFFF and header.data_count == 0


class Server:
    "An object encapsulating the state of an EPICS Server."
    def __init__(self):
        self._sid_counter = itertools.count(0)

    def new_sid(self):
        return next(self._sid_counter)

    def version(self):
        return VersionResponse(...)

    def create_channel(self, name, cid):
        return CreateResponse(..., sid)

    def search(self, name):
        return SearchResponse(...)


class VirtualCircuit:
    def __init__(self, host, priority):
        self.host = host
        self.priority = host
        self._state = UNINITIALIZED
        self._data = bytearray()

    def send(self, command):
        ...

    def recv(self, bytes_like):
        self._data += byteslike

    def process_next_response(self):
        header_size = _MessageHeaderSize
        if len(self._data) >= header_size:
            header = MessageHeader.from_buffer(self._data)
        else:
            return NEEDS_DATA
        if extend_header(header):
            header_size = _ExtendedMessageHeaderSize
            if len(self._data) >= header_size:
                header = ExtendedMessageHeader.from_buffer(self._data)
            else:
                return NEEDS_DATA
        payload = None
        if header.payload_size > 0:
            payload = []
            total_size = header_size + header.payload_size
            if len(self._data) >= total_size:
                dbr_struct = DBR_TYPES[header.data_type]
                dbr_size = ctypes.sizeof(dbr_struct)
                start = header_size
                stop = header_size + dbr_size
                for i in enumerate(header.data_count):
                    chunk = self._data[start:stop]
                    payload.append(dbr_struct.from_buffer(chunk))
                    start += dbr_size
                    stop += dbr_size
            else:
                return NEEDS_DATA
            self._data = self._data[total_size:]
        else:
            self._data = self._data[header_size:]
        command = parse_command(header, payload)
        self._update_states(self, command)
        return command

    def _update_states(self, command):
        if type(command) is NEEDS_DATA:
            return
        elif type(command) is SearchResponse:
            chan = self._channels[command.cid]
            cli._names[chan.name] = command.host
            circuit = (command.host, chan.priority)
            chan.connect(circuit)
        elif type(command) is VersionResponse:
            # self._circuits[(host, ????)] = CONNECTED
            pass
        elif type(command) is CreateResponse:
            chan = self._channels[command.cid]
            chan.create(command.data_type, command.data_count, sid)


class Client:
    PROTOCOL_VERSION = 13
    "An object encapsulating the state of an EPICS Client."
    def __init__(self):
        self._names = {}  # map known names to known hosts
        self._circuits = {}  # map (host, priority) to VirtualCircuit
        self._channels = {}  # map cid to Channel
        self._cid_counter = itertools.count(0)
        self._datagram_inbox = deque()
        self._datagram_outbox = deque()
        self._awaiting_response = set()

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
        self._datagram_outbox.append(msg)
        return channel

    def send_datagram(self):
        "Return bytes to broadcast over UDP socket."
        # TODO What to raise or return when outbox is empty?
        msg = self._datagram_outbox.popleft() 
        self._cstate.process_command(msg)
        return msg

    def recv_datagram(self, byteslike, address):
        "Cache but do not process bytes that were received via UDP broadcast."
        self._datagram_inbox.append((byteslike, (host, port)))

    def next_command(self):
        "Process cached received bytes."
        address, msg = self._datagram_index.popleft()


class Channel:
    "An object encapsulating the state of the EPICS Channel on a Client."
    def __init__(self, client, circuit, cid, name, priority=0):
        self._cli = client
        self._circuit = circuit
        self.cid = cid
        self.name = name
        self.priority = priority
        self.native_data_type = None
        self.native_data_count = None
        self.sid = None
        self._requests = deque()

    def connect(self, circuit):
        "Called by the Client when we have a VirtualCircuit for this Channel."
        self._circuit = circuit

    def create(self, native_data_type, native_data_count, sid):
        "Called by the Client when the Server gives this Channel an ID."
        self.native_data_type = native_data_type
        self.native_data_count = native_data_count
        self.sid = sid

    def next_request(self):
        # Do this logic based on a `state` explicit advanced by the Client.
        if self._cli[circuit] != CONNECTED:
            return self.circuit, VersionRequest(self.priority, CLIENT_VERSION)
        elif self.sid is None:
            return self.circuit, CreateRequest(cid, CLIENT_VERSION, self.name)
        return None
     
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
