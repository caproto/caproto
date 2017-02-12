# This module contains high-level "command" objects, one for each CA command.
# A command wraps together a ``MessageHeader`` from _headers.py with a payload
# of raw bytes (if applicable). It provides a more user-friendly __init__ that
# accepts standard Python types and handles details like type conversation and
# bit-padding. For every argument to the __init__ there is a corresponding
# property to allow high-level introspection of a command. There are also
# ``header`` and ``payload`` attributes for lower-level introspection. Finally,
# the command objects support ``__bytes__``, encoding them for sending over the
# wire.

# A command class may be instantiated in one of two ways:
# 1. For sending: by passing user-friendly inputs to ``__init__``.
# 2. For receiving: by passing a datagram or bytestream to the functions
#    ``read_datagram`` and `read_bytestream`` respectively. These identify the
#    command type and instiate the appropriate class from bytes using
#    ``__new__``.
#
# (1) is typically done by the user. (2) is typically done by calling the
# ``next_command`` method of a :class:`Hub` or a :class:`VirtualCircuit`.
import inspect
import struct
import socket
import math
from ._headers import *
from ._dbr_types import *
from ._utils import *


_MessageHeaderSize = ctypes.sizeof(MessageHeader)
_ExtendedMessageHeaderSize = ctypes.sizeof(ExtendedMessageHeader)


def ensure_bytes(s):
    if isinstance(s, bytes):
        return s
    elif isinstance(s, str):
        return s.encode()
    else:
        raise CaprotoTypeError("expected str or bytes")


def from_buffer(dbr_type, buffer):
    "Wraps dbr_type.from_buffer and special-case strings."
    if dbr_type is DBR_STRING:
        _len = len(buffer)
        if _len > 40:
            raise CaprotoValueError("EPICS imposes a 40-character limit on "
                                    "strings. The " "string {!r} is {} "
                                    "characters.".format(buffer, _len))
        if _len < 40:
            buffer = buffer.ljust(40, b'\x00')
    return dbr_type.from_buffer(buffer)


def padded_len(s):
    "Length of a (byte)string rounded up to the nearest multiple of 8."
    if len(s) > 40:
        raise CaprotoValueError("EPICS imposes a 40-character limit on "
                                "strings. The " "string {!r} is {} "
                                "characters.".format(s, len(s)))
    return 8 * math.ceil(len(s) / 8)


def padded_string_payload(name):
    name = ensure_bytes(name)
    size = padded_len(name)
    payload = bytes(DBR_STRING(name))[:size]
    return size, payload


def data_payload(values, data_count, data_type):
    size = data_count * ctypes.sizeof(DBR_TYPES[data_type])
    if data_count != 1:
        assert data_count == len(values)
        payload = b''.join(map(bytes, values))
    else:
        payload = bytes(DBR_TYPES[data_type](values))
    # Payloads must be zeropadded to have a size that is a multiple of 8.
    if size % 8 != 0:
        size = 8 * math.ceil(size/8)
        payload = payload.ljust(size, b'\x00')
    return size, payload


def read_datagram(data, address, role):
    "Parse bytes from one datagram into one or more commands."
    barray = bytearray(data)
    commands = []
    while barray:
        header = MessageHeader.from_buffer(barray)
        barray = barray[_MessageHeaderSize:]
        _class = Commands[role][header.command]
        payload_size = header.payload_size
        if _class.HAS_PAYLOAD:
            payload_bytes = barray[:header.payload_size]
            barray = barray[payload_size:]
        else:
            payload_bytes = None
        command = _class.from_wire(header, payload_bytes)
        command.sender_address = address  # (host, port)
        commands.append(command)
    return commands


def read_from_bytestream(data, role):
    header_size = _MessageHeaderSize
    # We need at least one header's worth of bytes to interpret anything.
    if len(data) < header_size:
        return data, NEED_DATA
    header = MessageHeader.from_buffer(data)
    # Looks for sentinels that mark this as an "extended header".
    if header.payload_size == 0xFFFF and header.data_count == 0:
        header_size = _ExtendedMessageHeaderSize
        # Do we have enough bytes to interpret the extended header?
        if len(data) < header_size:
            return data, NEED_DATA
        header = ExtendedMessageHeader.from_buffer(data)
    _class = Commands[role][header.command]
    payload_size = header.payload_size

    # SPECIAL CASE TO WORK AROUND libca bug
    if _class is CreateChanRequest:
        if header.payload_size == 0:
            payload_size = 16 
    # END SPECIAL CASE

    total_size = header_size + payload_size
    # Do we have all the bytes in the payload?
    if len(data) < total_size:
        return data, NEED_DATA
    # Receive the buffer (zero-copy).
    payload_bytes = data[header_size:total_size]
    command = _class.from_wire(header, payload_bytes)
    # Advance the buffer.
    return data[total_size:], command


class Message:
    ID = None  # integer, to be overriden by subclass
    DIRECTION = None  # REQUEST or RESPONSE; set at the end of this module
    sender_address = None  # set for the read_datagram function

    def __init__(self, header, payload=None):
        if payload is None:
            if header.payload_size != 0:
                raise CaprotoValueError("header.payload_size {} > 0 but "
                                        "payload is None."
                                        "".format(header.payload_size))
        elif header.payload_size != len(payload):
            raise CaprotoValueError("header.payload_size {} != len(payload) {}"
                                    "".format(header.payload_size, payload))
        if header.command != self.ID:
            raise CaprotoTypeError("A {} must have a header with "
                                   "header.command = {}, not {}."
                                   "".format(type(self), self.ID,
                                             header.commmand))
        self.header = header
        self.payload = payload

    def __setstate__(self, val):
        header, payload = val
        self.__dict__ = {'header': header, 'payload': payload}

    @classmethod
    def from_wire(cls, header, payload_bytes):
        """
        Use header.dbr_type to pack payload bytes into the right strucutre.

        Some Command types allocate a different meaning to the header.dbr_type
        field, and these override this method in their subclass.
        """
        if not cls.HAS_PAYLOAD:
            return cls.from_components(header, None)
        dbr_type = DBR_TYPES[header.data_type]
        payload_struct = from_buffer(dbr_type, payload_bytes)
        return cls.from_components(header, payload_struct)

    @classmethod
    def from_components(cls, header, payload):
        # Bwahahahaha
        instance = cls.__new__(cls)
        instance.__dict__.update({'header': header, 'payload': payload})
        return instance

    def __bytes__(self):
        return bytes(self.header) + bytes(self.payload or b'')

    def __repr__(self):
        signature = inspect.signature(type(self))
        d = [(arg, getattr(self, arg)) for arg in signature.parameters]
        formatted_args = ", ".join(["{}={}".format(k, v)
                                    for k, v in d])
        return "{}({})".format(type(self).__name__, formatted_args)


class VersionRequest(Message):
    ID = 0
    HAS_PAYLOAD = False
    def __init__(self, priority, version):
        if not (0 <= priority < 100):
            raise CaprotoValueError("Expecting 0 < priority < 100")
        header = VersionRequestHeader(priority, version)
        super().__init__(header, None)

    priority = property(lambda self: self.header.data_type)
    version = property(lambda self: self.header.data_count)


class VersionResponse(Message):
    ID = 0
    HAS_PAYLOAD = False
    def __init__(self, version):
        header = VersionResponseHeader(version)
        super().__init__(header, None)

    version = property(lambda self: self.header.data_count)


class SearchRequest(Message):
    ID = 6
    HAS_PAYLOAD = True
    def __init__(self, name, cid, version):
        size, payload = padded_string_payload(name)
        header = SearchRequestHeader(size, NO_REPLY, version, cid)
        super().__init__(header, payload)

    payload_size = property(lambda self: self.header.payload_size)
    reply = property(lambda self: self.header.data_type)
    version = property(lambda self: self.header.data_count)
    cid = property(lambda self: self.header.parameter1)
    name = property(lambda self: bytes(self.payload).rstrip(b'\x00'))


class SearchResponse(Message):
    ID = 6
    HAS_PAYLOAD = True
    def __init__(self, port, sid, cid, version):
        header = SearchResponseHeader(port, sid, cid)
        payload = bytes(DBR_INT(version))
        super().__init__(header, payload)

    @classmethod
    def from_wire(cls, header, payload_bytes):
        # For SearchResponse, the header.data_type is use for something other
        # than data type, so the base payload parser will fail and we need this
        # custom one.
        payload = DBR_INT.from_buffer(payload_bytes)
        return cls.from_components(header, payload)

    port = property(lambda self: self.header.data_type)
    sid = property(lambda self: self.header.parameter1)
    cid = property(lambda self: self.header.parameter2)
    version = property(lambda self: int(self.payload.value))


class NotFoundResponse(Message):
    ID = 14
    HAS_PAYLOAD = False
    def __init__(self, version, cid):
        header = NotFoundResponseHeader(DO_REPLY, version, cid)
        super().__init__(header, None)

    reply_flag = property(lambda self: self.header.data_type)
    version = property(lambda self: self.header.data_count)
    cid = property(lambda self: self.header.parameter1)


class EchoRequest(Message):
    ID = 23
    HAS_PAYLOAD = False
    def __init__(self):
        super().__init__(EchoRequestHeader(), None)


class EchoResponse(Message):
    ID = 23
    HAS_PAYLOAD = False
    def __init__(self):
        super().__init__(EchoResponseHeader(), None)


class RsrvIsUpResponse(Message):
    ID = 13
    HAS_PAYLOAD = False
    def __init__(self, server_port, beacon_id, address):
        header = RsrvIsUpResponseHeader(server_port, beacon_id, address)
        super().__init__(header, None)

    server_port = property(lambda self: self.header.data_type)
    beaconid = property(lambda self: self.header.parameter1)
    address = property(lambda self: self.header.parameter2)


class RepeaterConfirmResponse(Message):
    ID = 17
    HAS_PAYLOAD = False
    def __init__(self, repeater_address):
        header = RepeaterConfirmResponseHeader(repeater_address)
        super().__init__(header, None)

    repeater_address = property(lambda self: self.header.parameter2)


class RepeaterRegisterRequest(Message):
    ID = 24
    HAS_PAYLOAD = False
    def __init__(self, client_ip_address):
        encoded_ip = socket.inet_pton(socket.AF_INET, client_ip_address)
        int_encoded_ip, = struct.unpack('i', encoded_ip)  # bytes -> int
        header = RepeaterRegisterRequestHeader(int_encoded_ip)
        super().__init__(header, None)

    client_ip_address = property(lambda self: self.header.parameter2)


class EventAddRequest(Message):
    ID = 1
    HAS_PAYLOAD = True
    def __init__(self, data_type, data_count, sid, subscriptionid, low,
                 high, to, mask):
        header = EventAddRequestHeader(data_type, data_count, sid,
                                       subscriptionid)
        padding = b'\0\0'
        payload_list = (DBR_FLOAT(low), DBR_FLOAT(high), DBR_FLOAT(to),
                        DBR_INT(mask), padding)

        payload = b''.join(map(bytes, payload_list))
        super().__init__(header, payload)

        # TODO: this is strictly for debug output
        self.low = low
        self.high = high
        self.to = to
        self.mask = mask

    data_type = property(lambda self: self.header.data_type)
    data_count = property(lambda self: self.header.data_count)
    sid = property(lambda self: self.header.parameter1)
    subscriptionid = property(lambda self: self.header.parameter2)


class EventAddResponse(Message):
    ID = 1
    HAS_PAYLOAD = True
    def __init__(self, values, data_type, data_count,
                 status_code, subscriptionid):
        size, payload = data_payload(values, data_count, data_type)
        header = EventAddResponseHeader(size, data_type, data_count,
                                        status_code, subscriptionid)
        super().__init__(header, payload)

    payload_size = property(lambda self: self.header.payload_size)
    data_type = property(lambda self: self.header.data_type)
    data_count = property(lambda self: self.header.data_count)
    status_code = property(lambda self: self.header.parameter1)
    subscriptionid = property(lambda self: self.header.parameter2)
    values = property(lambda self: self.payload)

    @classmethod
    def from_wire(cls, header, payload_bytes):
        # SPECIAL CASE TO WORK AROUND libca BUG
        # libca seems to response to EventCancelRequest with an
        # EventAddResponse with an empty payload.
        # END SPECIAL CASE
        if not payload_bytes:
            print('EventAdd with an empty payload!')
            return cls.from_components(header, None)
        payload_struct = from_buffer(dbr_type, payload_bytes)
        return cls.from_components(header, payload_struct)


class EventCancelRequest(Message):
    ID = 2
    HAS_PAYLOAD = False
    def __init__(self, data_type, sid, subscriptionid):
        header = EventCancelRequestHeader(data_type, 0, sid, subscriptionid)
        super().__init__(header, None)

    data_type = property(lambda self: self.header.data_type)
    data_count = property(lambda self: self.header.data_count)
    sid = property(lambda self: self.header.parameter1)
    subscriptionid = property(lambda self: self.header.parameter2)


class EventCancelResponse(Message):
    ID = 2
    HAS_PAYLOAD = False
    def __init__(self, data_type, sid, subscriptionid):
        header = EventCancelResponseHeader(data_type, sid, subscriptionid)
        super().__init__(header, None)

    data_type = property(lambda self: self.header.data_type)
    sid = property(lambda self: self.header.parameter1)
    subscriptionid = property(lambda self: self.header.parameter2)


class ReadRequest(Message):
    "Deprecated: See also ReadNotifyRequest"
    ID = 3
    HAS_PAYLOAD = False
    def __init__(self, data_type, data_count, sid, ioid):
        header = ReadNotifyRequestHeader(data_type, data_count, sid, ioid)
        super().__init__(header, None)

    data_type = property(lambda self: self.header.data_type)
    data_count = property(lambda self: self.header.data_count)
    sid = property(lambda self: self.header.parameter1)
    ioid = property(lambda self: self.header.parameter2)


class ReadResponse(Message):
    "Deprecated: See also ReadNotifyResponse"
    ID = 3
    HAS_PAYLOAD = True
    def __init__(self, data_type, data_count, sid, ioid):
        header = ReadRequestHeader(data_type, data_count, sid, ioid)
        super().__init__(header, None)

    payload_size = property(lambda self: self.header.payload_size)
    data_type = property(lambda self: self.header.data_type)
    data_count = property(lambda self: self.header.data_count)
    sid = property(lambda self: self.header.parameter1)
    ioid = property(lambda self: self.header.parameter2)
    

class WriteRequest(Message):
    "Deprecated: See also WriteNotifyRequest"
    ID = 4
    HAS_PAYLOAD = True
    def __init__(self, values, data_type, sid, ioid):
        size, payload = data_payload(values, data_count, data_type)
        header = WriteRequestHeader(size, data_type, data_count, sid, ioid)
        super().__init__(header, payload)

    payload_size = property(lambda self: self.header.payload_size)
    data_type = property(lambda self: self.header.data_type)
    data_count = property(lambda self: self.header.data_count)
    sid = property(lambda self: self.header.parameter1)
    ioid = property(lambda self: self.header.parameter2)
    values = property(lambda self: self.payload)


class EventsOffRequest(Message):
    ID = 8
    HAS_PAYLOAD = False
    def __init__(self):
        super().__init__(EventsOffRequestHeader(), None)


class EventsOnRequest(Message):
    ID = 9
    HAS_PAYLOAD = False
    def __init__(self):
        super().__init__(EventsOnRequestHeader(), None)


class ReadSyncRequestRequest(Message):
    "Deprecated: See also ReadNotifyRequest"
    ID = 10
    HAS_PAYLOAD = False
    def __init__(self):
        super().__init__(ReadSyncRequestRequestHeader(), None)


class ErrorResponse(Message):
    ID = 11
    HAS_PAYLOAD = True
    def __init__(self, original_request, cid, status_code, error_message):
        _error_message = DBR_STRING(ensure_bytes(error_message))
        payload = bytes(original_request) + _error_message
        size = len(payload)
        header = ErrorResponseHeader(size, cid, status_code)
        super().__init__(header, payload)

    payload_size = property(lambda self: self.header.payload_size)
    cid = property(lambda self: self.header.parameter1)
    status_code = property(lambda self: self.header.parameter2)


class ClearChannelRequest(Message):
    ID = 12
    HAS_PAYLOAD = False
    def __init__(self, sid, cid):
        super().__init__(ClearChannelRequestHeader(sid, cid), None)

    sid = property(lambda self: self.header.parameter1)
    cid = property(lambda self: self.header.parameter2)


class ClearChannelResponse(Message):
    ID = 12
    HAS_PAYLOAD = False
    def __init__(self, sid, cid):
        super().__init__(ClearChannelResponseHeader(sid, cid), None)

    sid = property(lambda self: self.header.parameter1)
    cid = property(lambda self: self.header.parameter2)


class ReadNotifyRequest(Message):
    ID = 15
    HAS_PAYLOAD = False
    def __init__(self, data_type, data_count, sid, ioid):
        header = ReadNotifyRequestHeader(data_type, data_count, sid, ioid)
        super().__init__(header, None)

    data_type = property(lambda self: self.header.data_type)
    data_count = property(lambda self: self.header.data_count)
    sid = property(lambda self: self.header.parameter1)
    ioid = property(lambda self: self.header.parameter2)

    
class ReadNotifyResponse(Message):
    ID = 15
    HAS_PAYLOAD = True
    def __init__(self, values, data_type, data_count, status, ioid):
        size, payload = data_payload(values, data_count, data_type)
        header = ReadNotifyRequestHeader(size, data_type, data_count, status,
                                         ioid)
        super().__init__(header, payload)

    payload_size = property(lambda self: self.header.payload_size)
    data_type = property(lambda self: self.header.data_type)
    data_count = property(lambda self: self.header.data_count)
    status = property(lambda self: self.header.parameter1)
    ioid = property(lambda self: self.header.parameter2)
    values = property(lambda self: self.payload)


class CreateChanRequest(Message):
    ID = 18
    HAS_PAYLOAD = True
    def __init__(self, name, cid, version):
        size, payload = padded_string_payload(name)
        header = CreateChanRequestHeader(size, cid, version)
        super().__init__(header, payload)

    payload_size = property(lambda self: self.header.payload_size)
    cid = property(lambda self: self.header.parameter1)
    version = property(lambda self: self.header.parameter2)
    name = property(lambda self: bytes(self.payload).rstrip(b'\x00'))

class CreateChanResponse(Message):
    ID = 18
    HAS_PAYLOAD = False
    def __init__(self, data_type, data_count, cid, sid):
        header = CreateChanResponseHeader(data_type, data_count, cid, sid)
        super().__init__(header, None)

    data_type = property(lambda self: self.header.data_type)
    data_count = property(lambda self: self.header.data_count)
    cid = property(lambda self: self.header.parameter1)
    sid = property(lambda self: self.header.parameter2)


class WriteNotifyRequest(Message):
    ID = 19
    HAS_PAYLOAD = True
    def __init__(self, values, data_type, data_count, sid, ioid):
        size, payload = data_payload(values, data_count, data_type)
        header = WriteNotifyRequestHeader(size, data_type, data_count, sid,
                                          ioid)
        super().__init__(header, payload)

    payload_size = property(lambda self: self.header.payload_size)
    data_type = property(lambda self: self.header.data_type)
    data_count = property(lambda self: self.header.data_count)
    sid = property(lambda self: self.header.parameter1)
    ioid = property(lambda self: self.header.parameter2)
    values = property(lambda self: self.payload)


class WriteNotifyResponse(Message):
    ID = 19
    HAS_PAYLOAD = False
    def __init__(self, data_type, data_count, status, ioid):
        header = WriteNotifyResponseHeader(data_type, data_count, status, ioid)
        super().__init__(header, None)

    data_type = property(lambda self: self.header.data_type)
    data_count = property(lambda self: self.header.data_count)
    status = property(lambda self: self.header.parameter1)
    ioid = property(lambda self: self.header.parameter2)


class ClientNameRequest(Message):
    ID = 20
    HAS_PAYLOAD = True
    def __init__(self, name):
        size, payload = padded_string_payload(name)
        header = ClientNameRequestHeader(size)
        super().__init__(header, payload)

    payload_size = property(lambda self: self.header.payload_size)
    name = property(lambda self: bytes(self.payload).rstrip(b'\x00'))


class HostNameRequest(Message):
    ID = 21
    HAS_PAYLOAD = True
    def __init__(self, name):
        size, payload = padded_string_payload(name)
        header = HostNameRequestHeader(size)
        super().__init__(header, payload)

    payload_size = property(lambda self: self.header.payload_size)
    name = property(lambda self: bytes(self.payload).rstrip(b'\x00'))


class AccessRightsResponse(Message):
    ID = 22
    HAS_PAYLOAD = False
    def __init__(self, cid, access_rights):
        header = AccessRightsResponseHeader(cid, access_rights)
        super().__init__(header, None)

    cid = property(lambda self: self.header.parameter1)
    access_rights = property(lambda self: self.header.parameter2)


class CreateChFailResponse(Message):
    ID = 26
    HAS_PAYLOAD = False
    def __init__(self, cid):
        super().__init__(CreateChFailResponseHeader(cid), None)

    cid = property(lambda self: self.header.parameter1)


class ServerDisconnResponse(Message):
    ID = 27
    HAS_PAYLOAD = False
    def __init__(self, cid):
        super().__init__(ServerDisconnResponseHeader(cid), None)

    cid = property(lambda self: self.header.parameter1)


_classes = [obj for obj in globals().values() if isinstance(obj, type)]
_commands = [_class for _class in _classes if issubclass(_class, Message)]
Commands = {}
Commands[CLIENT] = {_class.ID: _class for _class in _commands
                    if _class.__name__.endswith('Request')}
Commands[SERVER] = {_class.ID: _class for _class in _commands
                    if _class.__name__.endswith('Response')}
for command in Commands[CLIENT].values():
    command.DIRECTION = REQUEST
for command in Commands[SERVER].values():
    command.DIRECTION = RESPONSE
