# A bring-your-own-I/O implementation of Channel Access
# in the spirit of http://sans-io.readthedocs.io/
import cyptes
from io import BytesIO
from collections import defaultdict
from .commands import *


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

sentinels = ("CHANNEL VIRTUAL_CIRCUIT"
             # states
             "BROADCAST_SEARCH NEEDS_BROADCAST_SEARCH_RESPONSE "
             "CONNECT_CIRCUIT NEEDS_CONNECT_CIRCUIT_RESPONSE "
             "CREATE_CHANNEL NEEDS_CREATE_CHANNEL_RESPONSE "
             "READY SUBSCRIBED CONNECTED UNINITIALIZED DISCONNECTED "
             # responses
             "NEEDS_DATA SearchResponse VersionResponse "
             "CreateChannelResponse".split())
for token in sentinels:
    globals()[token] = make_sentinel(token)


class MessageHeader(ctypes.BigEndianStructure):
    _fields_ = [("command", ctypes.c_uint16),
                ("payload_size", ctypes.c_uint16),
                ("data_type", ctypes.c_uint16),
                ("data_count", ctypes.c_uint16),
                ("parameter1", ctypes.c_uint32),
                ("parameter2", ctypes.c_uint32),
               ]


class ExtendedMessageHeader(BigEndianStructure):
    _fields_ = [("command", ctypes.c_uint16),
                ("marker1", ctypes.c_uint16),
                ("data_type", ctypes.c_uint16),
                ("marker2", ctypes.c_uint16),
                ("parameter1", ctypes.c_uint32),
                ("parameter2", ctypes.c_uint32),
                ("payload_size", ctypes.c_uint32),
                ("data_count", ctypes.c_uint32),
               ]


_MessageHeaderSize = ctypes.sizeof(MessageHeader)
_ExtendedMessageHeaderSize = ctypes.sizeof(ExtendedMessageHeader)

def parse_command_response(header):
    ...    


def extend_header(header):
    "Return True if header should be extended."
    return header.payload_size == 0xFFFF and header.data_count == 0


class Context:
    def __init__(self):
        self._names = {}  # map known names to known hosts
        # map (host, priority) to circuit state
        self._circuits = defaultdict(lambda: UNINITIALIZED)
        self._channels = {}  # map cid to Channel
        self._data = bytearray()
        self._cid_counter = itertools.count(0)

    def new_channel(self, name, priority=0):
        cid = next(self._cid_counter)
        if name in self._names:
            circuit = self._circuits[(self._names[name], priority)]
        else:
            circuit = None
        channel = Channel(name, circuit, cid, name, priority)
        self._channels[cid] = channel

    def send(self, command):
        if type(command) is 

    def recv(self, byteslike):
        self._data += byteslike

    def next_command(self):
        header_size = _MessageHeaderSize
        if len(self._data) >= header_size:
            header = MessageHeader.from_buffer(self._data)
        else:
            return NEEDS_DATA
        if extend_header(header):
            header_size = _ExtendedMessageHeaderSize
            if len(self._data) >= header_size
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
            ctx._names[chan.name] = command.host
            circuit = (command.host, chan.priority)
            chan.connect(circuit)
        elif type(command) is ConnectResponse:
            self._circuits[(host, ????)] = CONNECTED
        elif type(command) is CreateResponse:
            chan = self._channels[command.cid]
            chan.complete(command.data_type, command.data_count, sid)


class Channel:
    def __init__(self, context, circuit, cid, name, priority=0):
        self._ctx = context
        self._circuit = circuit
        self._cid = cid
        self.name = name
        self.priority = priority

    def complete(self, native_data_type, native_data_count, sid):
        self._native_data_type = native_data_type
        self._native_data_count = native_data_count
        self._sid = sid

    @property
    def state(self):
        if self._circuit is None:
            ...???

    def next_request(self):
        # put all the SearchRequest, ConnectRequest stuff in here instead of
        # giving them separate names?
        # or go read h11 again until this makes sense.
     
    def SearchRequest(self):
        return Search(self.name)

    def ConnectRequest(self):
        return ConnectRequest(*self._circuit)

    def connect(self, circuit):
        self._circuit = circuit

    def CreateRequest(self):
        return CreateRequest(*

    def create(self):
        return Create(...)

    def read(self, data_type=None, data_count=None):
        if data_type is None:
            data_type = self._native_data_type
        if data_count is None:
            data_count = self._native_data_count
        return Read(...)

    def write(self, data):
        return Write(...)

    def subscribe(self, data_type=None, data_count=None):
        if data_type is None:
            data_type = self._native_data_type
        if data_count is None:
            data_count = self._native_data_count
        return Subscribe(...)



EVENT_TRIGGERED_TRANSITIONS = {
    CHANNEL: {
        BROADCAST_SERACH: {
            Search: NEEDS_BROADCAST_SEARCH_REPLY
        }
        NEEDS_BROADCAST_SEARCH_RESPOSE: {
            SearchResponse: CONNECT_CIRCUIT
        }
        CONNECT_CIRCUIT: {
            Version: NEEDS_CONNECT_CIRCUIT_RESPONSE
        }
        NEEDS_CONNECT_CIRCUIT_RESPONSE: {
            VersionResponse: CREATE_CHANNEL
        }
        CREATE_CHANNEL: {
            CreateChannel: NEEDS_CREATE_CHANNEL_RESPONSE
        }
        NEEDS_CREATE_CHANNEL_RESPONSE: {
            CreateChannelResponse: READY
        }
        READY: {
            Subscribe: SUBSCRIBED
        }
        SUBSCRIBED: {
            Unsubscribe: READY
        }
    }
}
