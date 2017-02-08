# A bring-your-own-I/O implementation of Channel Access
# in the spirit of http://sans-io.readthedocs.io/
import math
import ctypes
import itertools
from io import BytesIO
from collections import defaultdict, deque
from .commands import *
from .dbr_types import *


CLIENT_VERSION = 13
# This sentinel code is copied, with thanks and admiration, from h11,
# which is released under an MIT license.
#
# Sentinel values
#
# - Inherit identity-based comparison and hashing from object
# - Have a nice repr
# - Have a *bonus property*: type(sentinel) is sentinel
#
# The bonus property is useful if you want to take the return value from
# next_event() and do some sort of dispatch based on type(event).
class _SentinelBase(type):
    def __repr__(self):
        return self.__name__

def make_sentinel(name):
    cls = _SentinelBase(name, (_SentinelBase,), {})
    cls.__class__ = cls
    return cls

sentinels = ("CHANNEL VIRTUAL_CIRCUIT "
             # states
             "BROADCAST_SEARCH NEEDS_BROADCAST_SEARCH_RESPONSE "
             "CONNECT_CIRCUIT NEEDS_CONNECT_CIRCUIT_RESPONSE "
             "CREATE_CHANNEL NEEDS_CREATE_CHANNEL_RESPONSE "
             "READY SUBSCRIBED CONNECTED UNINITIALIZED DISCONNECTED "
             # responses
             "NEEDS_DATA SearchResponse VersionResponse "
             "CreateChanResponse".split())
for token in sentinels:
    globals()[token] = make_sentinel(token)


def padded_len(s):
    "Length of a (byte)string rounded up to the nearest multiple of 8."
    return 8 * math.ceil(len(s) / 8)


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
    "An object encapsulating the state of an EPICS Client."
    def __init__(self):
        self._names = {}  # map known names to known hosts
        self._circuits = {}  # map (host, priority) to VirtualCircuit
        self._channels = {}  # map cid to Channel
        self._cid_counter = itertools.count(0)
        self._datagram_inbox = deque()
        self._datagram_outbox = deque()

    def new_channel(self, name, priority=0):
        cid = next(self._cid_counter)
        circuit = None
        channel = Channel(name, circuit, cid, name, priority)
        self._channels[cid] = channel
        # If this Client has searched for this name and already knows its
        # host, skip the Search step and create a circuit.
        # if name in self._names:
        #     circuit = self._circuits[(self._names[name], priority)]
        size = padded_len(name)
        header = SearchRequest(size, NO_REPLY, CLIENT_VERSION, cid)
        payload = bytes(DBR_STRING(name.encode()))[:size]
        msg = Message(header, payload)
        self._datagram_outbox.append(msg)
        return channel

    def send_datagram(self):
        "Return bytes to broadcast over UDP socket."
        return self._datagram_outbox.popleft() 

    def recv_datagram(self, byteslike):
        "Inject bytes that were received via UDP broadcast."
        self._datagram_inbox.append(byteslike)

    def next_event(self):
        "Process injected bytes."
        command 


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


EVENT_TRIGGERED_TRANSITIONS = {
    CHANNEL: {
        BROADCAST_SEARCH: {
            SearchRequest: NEEDS_BROADCAST_SEARCH_RESPONSE
        },
        NEEDS_BROADCAST_SEARCH_RESPONSE: {
            SearchResponse: CONNECT_CIRCUIT
        },
        CONNECT_CIRCUIT: {
            VersionRequest: NEEDS_CONNECT_CIRCUIT_RESPONSE
        },
        NEEDS_CONNECT_CIRCUIT_RESPONSE: {
            VersionResponse: CREATE_CHANNEL
        },
        CREATE_CHANNEL: {
            CreateChanRequest: NEEDS_CREATE_CHANNEL_RESPONSE
        },
        NEEDS_CREATE_CHANNEL_RESPONSE: {
            CreateChanResponse: READY
        },
        READY: {
            EventAddRequest: SUBSCRIBED
        },
        SUBSCRIBED: {
            EventCancelRequest: READY
        },
    },
    VIRTUAL_CIRCUIT: {
        UNINITIALIZED: {
            VersionRequest: NEEDS_CONNECT_CIRCUIT_RESPONSE
        },
        NEEDS_CONNECT_CIRCUIT_RESPONSE: {
            VersionResponse: CONNECTED
        },
        CONNECTED: {
            ClearChannelRequest: DISCONNECTED
        },
        DISCONNECTED: {
            VersionResponse: CONNECTED
        },
    }
}
