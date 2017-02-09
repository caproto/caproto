import math
from ._headers import *
from ._dbr_types import *


_MessageHeaderSize = ctypes.sizeof(MessageHeader)
_ExtendedMessageHeaderSize = ctypes.sizeof(ExtendedMessageHeader)


def ensure_bytes(s):
    if isinstance(s, bytes):
        return s
    elif isinstance(s, str):
        return s.encode()
    else:
        raise TypeError("expected str or bytes")


def padded_len(s):
    "Length of a (byte)string rounded up to the nearest multiple of 8."
    return 8 * math.ceil(len(s) / 8)


def padded_string_payload(name):
    name = ensure_bytes(name)
    size = padded_len(name)
    payload = bytes(DBR_STRING(name))[:size]
    return size, payload


def data_payload(values, data_count, data_type):
    size = data_count * ctypes.sizeof(data_type)
    if data_count != 1:
        assert data_count == len(values)
        payload = b''.join(map(bytes, values))
    else:
        payload = bytes(values)
    return size, payload


def read_datagram(data, role):
    "Parse bytes from one datagram into an instance of the pertinent Command."
    barray = bytearray(data)
    header = MessageHeader.from_buffer(barray)
    payload_bytes = barray[_MessageHeaderSize:]
    _class = Commands[str(role)][header.command]
    return _class.from_wire(header, payload_bytes)


def read_from_bytestream(data, role):
    header_size = _MessageHeaderSize
    # We need at least one header's worth of bytes to interpret anything.
    if len(data) < header_size:
        return NEEDS_DATA
    header = MessageHeader.from_buffer(data)
    # Looks for sentinels that mark this as an "extended header".
    if header.payload_size == 0xFFFF and header.data_count == 0:
        header_size = _ExtendedMessageHeaderSize
        # Do we have enough bytes to interpret the extended header?
        if len(data) < header_size:
            return NEEDS_DATA
        header = ExtendedMessageHeader.from_buffer(data)
    total_size = header_size + header.payload_size
    # Do we have all the bytes in the payload?
    if len(data) < total_size:
        return NEEDS_DATA
    # Receive the buffer (zero-copy).
    _class = Commands[str(role)][header.command]
    payload_bytes = data[header_size:total_size]
    command = _class.from_wire(header, payload_bytes)
    # Advance the buffer.
    return data[total_size:], command


class Message:
    ID = None  # to be overriden by subclass

    def __init__(self, header, payload=None):
        if payload is None:
            if header.payload_size != 0:
                raise ValueError("header.payload_size {} > 0 but payload is "
                                 "is None.".format(header.payload_size))
        elif header.payload_size != len(payload):
            raise ValueError("header.payload_size {} != len(payload) {}"
                             "".format(header.payload_size, payload))
        if header.command != self.ID:
            raise TypeError("A {} must have a header with header.command == "
                            "{}, not {}.".format(type(self), self.ID,
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
        if not payload_bytes:
            return cls.from_components(header, None)
        dbr_type = DBR_TYPES[header.data_type]
        return cls.from_components(header, dbr_type.from_buffer(payload_bytes))

    @classmethod
    def from_components(cls, header, payload):
        # Bwahahahaha
        instance = cls.__new__(cls)
        instance.__dict__.update({'header': header, 'payload': payload})
        return instance

    def __bytes__(self):
        return bytes(self.header) + bytes(self.payload or b'')


class VersionRequest(Message):
    ID = 0
    def __init__(self, priority, version):
        header = VersionRequestHeader(priority, version)
        super().__init__(header, None)


class VersionResponse(Message):
    ID = 0
    def __init__(self, version):
        header = VersionResponseHeader(version)
        super().__init__(header, None)


class SearchRequest(Message):
    ID = 6
    def __init__(self, name, cid, version):
        size, payload = padded_string_payload(name)
        header = SearchRequestHeader(size, NO_REPLY, version, cid)
        super().__init__(header, payload)


class SearchResponse(Message):
    ID = 6
    def __init__(self, port, sid, cid, version):
        header = SearchResponseHeader(port, sid, cid)
        payload = bytes(DBR_INT(version))
        super().__init__(header, payload)

    @classmethod
    def from_wire(cls, header, payload_bytes):
        # For SearchResponse, the header.data_type is use for something other
        # than data type, so the base payload parser will fail.
        payload = DBR_INT.from_buffer(payload_bytes)
        return cls.from_components(header, payload)


class NotFoundResponse(Message):
    ID = 14
    def __init__(self, version, cid):
        header = NotFoundResponseHeader(DO_REPLY, version, cid)
        super().__init__(header, None)


class EchoRequest(Message):
    ID = 23
    def __init__(self):
        super().__init__(EchoRequestHeader(), None)


class EchoResponse(Message):
    ID = 23
    def __init__(self):
        super().__init__(EchoResponseHeader(), None)


class RsrvIsUpResponse(Message):
    ID = 13
    def __init__(self, server_port, beacon_id, address):
        header = RsrvIsUpResponseHeader(server_port, beacon_id, address)
        super().__init__(header, None)


class CaRepeaterConfirmResponseHeader(Message):
    ID = 17
    def __init__(self, repeater_address):
        header = CaRepeaterConfirmResponseHeader(repeater_address)
        super().__init__(header, None)


class CaRepeaterRegisterRequestHeader(Message):
    ID = 24
    def __init__(self, client_ip_address):
        header = CaRepeaterRegisterRequestHeader(client_ip_address)
        super().__init__(header, None)


class EventAddRequest(Message):
    ID = 1
    def __init__(self, data_type, data_count, sid, subscriptionid, low,
                 high, to, mask):
        header = EventAddRequestHeader(data_type, data_count, sid,
                                       subscriptionid, low, high, to, mask)
        payload_list = (DBR_FLOAT(low), DBR_FLOAT(high), DBR_FLOAT(to),
                        DBR_INT(mask))
        payload = b''.join(map(bytes, payload_list))
        super().__init__(header, payload)


class EventAddResponse(Message):
    ID = 1
    def __init__(self, values, data_type, data_count,
                 status_code, subscriptionid):
        size, payload = data_payload(values)
        header = EventAddResponseHeader(size, data_type, data_count,
                                        status_code, subscriptionid)
        super().__init__(header, payload)


class EventCancelRequest(Message):
    ID = 2
    def __init__(self, data_type, data_count, sid, subscriptionid):
        header = EventCancelRequestHeader(data_type, data_count, sid,
                                          subscriptionid)
        super().__init__(header, None)


class EventCancelResponse(Message):
    ID = 2
    def __init__(self, data_type, sid, subscriptionid):
        header = EventCancelResponseHeader(data_type, sid, subscriptionid)
        super().__init__(header, None)



class ReadRequest(Message):
    "Deprecated: See also ReadNotifyRequest"
    ID = 3
    def __init__(self, data_type, data_count, sid, ioid):
        header = ReadNotifyRequestHeader(data_type, data_count, sid, ioid)
        super().__init__(header, None)


class WriteRequest(Message):
    "Deprecated: See also WriteNotifyRequest"
    ID = 4
    def __init__(self, values, data_type, sid, ioid):
        size, payload = data_payload(values)
        header = WriteRequestHeader(size, data_type, data_count, sid, ioid)
        super().__init__(header, payload)


class EventsOffRequest(Message):
    ID = 8
    def __init__(self):
        super().__init__(EventsOffRequestHeader(), None)


class EventsOnRequest(Message):
    ID = 9
    def __init__(self):
        super().__init__(EventsOnRequestHeader(), None)


class ReadSyncRequestRequest(Message):
    "Deprecated: See also ReadNotifyRequest"
    ID = 10
    def __init__(self):
        super().__init__(ReadSyncRequestRequestHeader(), None)


class ErrorResponse(Message):
    ID = 11
    def __init__(self, original_request, cid, status_code, error_message):
        _error_message = DBR_STRING(ensure_bytes(error_message))
        payload = bytes(original_request) + _error_message
        size = len(payload)
        header = ErrorResponseHeader(size, cid, status_code)
        super().__init__(header, payload)


class ClearChannelRequest(Message):
    ID = 12
    def __init__(self, sid, cid):
        super().__init__(ClearChannelRequestHeader(sid, cid), None)


class ClearChannelResponse(Message):
    ID = 12
    def __init__(self, sid, cid):
        super().__init__(ClearChannelResponseHeader(sid, cid), None)


class ReadNotifyRequest(Message):
    ID = 15
    def __init__(self, data_type, data_count, sid, ioid):
        header = ReadNotifyRequestHeader(data_type, data_count, sid, ioid)
        super().__init__(header, None)

    
class ReadNotifyResponse(Message):
    ID = 15
    def __init__(self, values, data_type, data_count, sid, ioid):
        size, payload = data_payload(values)
        header = ReadNotifyRequest(size, data_type, data_count, sid, ioid)
        super().__init__(header, payload)


class CreateChanRequest(Message):
    ID = 18
    def __init__(self, name, cid, version):
        size, payload = padded_string_payload(name)
        header = CreateChanRequestHeader(size, cid, version)
        super().__init__(header, payload)

class CreateChanResponse(Message):
    ID = 18
    def __init__(self, data_type, data_count, cid, sid):
        header = CreateChanResponseHeader(data_type, data_count, cid, sid)
        super().__init__(header, None)


class WriteNotifyRequest(Message):
    ID = 19
    def __init__(self, values, data_type, data_count, status, ioid):
        size, payload = data_payload(values)
        header = WriteNotifyRequest(size, data_type, data_count, status, ioid)
        super().__init__(header, payload)


class WriteNotifyResponse(Message):
    ID = 19
    def __init__(self, data_type, data_count, status, ioid):
        header = WriteNotifyResponse(data_type, data_count, status, ioid)
        super().__init__(header, None)


class ClientNameRequest(Message):
    ID = 20
    def __init__(self, name):
        size, payload = padded_string_payload(name)
        header = ClientNameRequestHeader(size)
        super().__init__(header, payload)


class HostNameRequest(Message):
    ID = 21
    def __init__(self, name):
        size, payload = padded_string_payload(name)
        header = HostNameRequestHeader(size)
        super().__init__(header, payload)


class AccessRightsResponse(Message):
    ID = 22
    def __init__(self, cid, access_rights):
        header = AccessRightsResponseHeader(cid, access_rights)
        super().__init__(header, None)


class CreateChFailResponse(Message):
    ID = 26
    def __init__(self, cid):
        super().__init__(CreateChFailResponseHeader(cid), None)


class ServerDisconnResponse(Message):
    ID = 27
    def __init__(self, cid):
        super().__init__(ServerDisconnResponseHeader(cid), None)


_classes = [obj for obj in globals().values() if isinstance(obj, type)]
_commands = [_class for _class in _classes if issubclass(_class, Message)]
Commands = {}
Commands['CLIENT'] = {_class.ID: _class for _class in _commands
                      if _class.__name__.endswith('Request')}
Commands['SERVER'] = {_class.ID: _class for _class in _commands
                      if _class.__name__.endswith('Response')}
