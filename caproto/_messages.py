import math
from ._headers import *
from ._dbr_types import *


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


class Message:
    def __init__(self, header, payload=None):
        if payload is None:
            if header.payload_size != 0:
                raise ValueError("header.payload_size {} > 0 but payload is "
                                 "is None.".format(header.payload_size))
        elif header.payload_size != len(payload):
            raise ValueError("header.payload_size {} != len(payload) {}"
                             "".format(header.payload_size, payload))
        self.header = header
        self.payload = payload

    def __bytes__(self):
        return bytes(self.header) + bytes(self.payload)


class VersionRequest(Message):
    def __init__(self, priority, version):
        header = VersionRequestHeader(priority, version)
        super().__init__(header, None)


class VersionResponse(Message):
    def __init__(self, version):
        header = VersionResponseHeader(version)
        super().__init__(header, None)


class SearchRequest(Message):
    def __init__(self, name, cid, version):
        size, payload = padded_string_payload(name)
        header = SearchRequestHeader(size, NO_REPLY, version, cid)
        super().__init__(header, payload)


class SearchResponse(Message):
    def __init__(self, port, sid, cid, version):
        header = SearchResponseHeader(port, sid, cid)
        payload = bytes(DBR_INT(version))
        super().__init__(header, payload)


class NotFoundResponse(Message):
    def __init__(self, version, cid):
        header = NotFoundResponseHeader(DO_REPLY, version, cid)
        super().__init__(header, None)


class EchoRequest(Message):
    def __init__(self):
        super().__init__(EchoRequestHeader(), None)


class EchoResponse(Message):
    def __init__(self):
        super().__init__(EchoResponseHeader(), None)


class RsrvIsUpResponse(Message):
    def __init__(self, server_port, beacon_id, address):
        header = RsrvIsUpResponseHeader(server_port, beacon_id, address)
        super().__init__(header, None)


class CaRepeaterConfirmResponseHeader(Message):
    def __init__(self, repeater_address):
        header = CaRepeaterConfirmResponseHeader(repeater_address)
        super().__init__(header, None)


class CaRepeaterRegisterRequestHeader(Message):
    def __init__(self, client_ip_address):
        header = CaRepeaterRegisterRequestHeader(client_ip_address)
        super().__init__(header, None)


class EventAddRequest(Message):
    def __init__(self, data_type, data_count, sid, subscriptionid, low,
                 high, to, mask):
        header = EventAddRequestHeader(data_type, data_count, sid,
                                       subscriptionid, low, high, to, mask)
        payload_list = (DBR_FLOAT(low), DBR_FLOAT(high), DBR_FLOAT(to),
                        DBR_INT(mask))
        payload = b''.join(map(bytes, payload_list))
        super().__init__(header, payload)


class EventAddResponse(Message):
    def __init__(self, values, data_type, data_count,
                 status_code, subscriptionid):
        size, payload = data_payload(values)
        header = EventAddResponseHeader(size, data_type, data_count,
                                        status_code, subscriptionid)
        super().__init__(header, payload)


class EventCancelRequest(Message):
    def __init__(self, data_type, data_count, sid, subscriptionid):
        header = EventCancelRequestHeader(data_type, data_count, sid,
                                          subscriptionid)
        super().__init__(header, None)


class EventCancelResponse(Message):
    def __init__(self, data_type, sid, subscriptionid):
        header = EventCancelResponseHeader(data_type, sid, subscriptionid)
        super().__init__(header, None)


class ReadNotifyRequest(Message):
    def __init__(self, data_type, data_count, sid, ioid):
        header = ReadNotifyRequestHeader(data_type, data_count, sid, ioid)
        super().__init__(header, None)


class ReadNotifyResponse(Message):
    def __init__(self, values, data_type, sid, ioid):
        size, payload = data_payload(values)
        header = ReadNotifyResponseHeader(size, data_type, data_count, sid,
                                          ioid)
        super().__init__(header, payload)


class WriteRequest(Message):
    def __init__(self, values, data_type, sid, ioid):
        size, payload = data_payload(values)
        header = WriteRequestHeader(size, data_type, data_count, sid, ioid)
        super().__init__(header, payload)


class EventsOffRequest(Message):
    def __init__(self):
        super().__init__(EventsOffRequestHeader(), None)


class EventsOnRequest(Message):
    def __init__(self):
        super().__init__(EventsOnRequestHeader(), None)


class ReadSyncRequestRequest(Message):
    def __init__(self):
        super().__init__(ReadSyncRequestRequestHeader(), None)


class ErrorResponse(Message):
    def __init__(self, original_request, cid, status_code, error_message):
        _error_message = DBR_STRING(ensure_bytes(error_message))
        payload = bytes(original_request) + _error_message
        size = len(payload)
        header = ErrorResponseHeader(size, cid, status_code)
        super().__init__(header, payload)


class ClearChannelRequest(Message):
    def __init__(self, sid, cid):
        super().__init__(ClearChannelRequestHeader(sid, cid), None)


class ClearChannelResponse(Message):
    def __init__(self, sid, cid):
        super().__init__(ClearChannelResponseHeader(sid, cid), None)


class ReadNotifyRequest(Message):
    def __init__(self, data_type, data_count, sid, ioid):
        header = ReadNotifyRequestHeader(data_type, data_count, sid, ioid)
        super().__init__(header, None)

    
class ReadNotifyResponse(Message):
    def __init__(self, values, data_type, data_count, sid, ioid):
        size, payload = data_payload(values)
        header = ReadNotifyRequest(size, data_type, data_count, sid, ioid)
        super().__init__(header, payload)


class CreateChanRequest(Message):
    def __init__(self, name, cid, version):
        size, payload = padded_string_payload(name)
        header = CreateChanRequestHeader(size, cid, version)
        super().__init__(header, payload)

class CreateChanResponse(Message):
    def __init__(self, data_type, data_count, cid, sid):
        header = CreateChanResponseHeader(data_type, data_count, cid, sid)
        super().__init__(header, None)


class WriteNotifyRequest(Message):
    def __init__(self, values, data_type, data_count, status, ioid):
        size, payload = data_payload(values)
        header = WriteNotifyRequest(size, data_type, data_count, status, ioid)
        super().__init__(header, payload)


class WriteNotifyResponse(Message):
    def __init__(self, data_type, data_count, status, ioid):
        header = WriteNotifyResponse(data_type, data_count, status, ioid)
        super().__init__(header, None)


class ClientNameRequest(Message):
    def __init__(self, name):
        size, payload = padded_string_payload(name)
        header = ClientNameRequestHeader(size)
        super().__init__(header, payload)


class HostNameRequest(Message):
    def __init__(self, name):
        size, payload = padded_string_payload(name)
        header = HostNameRequestHeader(size)
        super().__init__(header, payload)


class AccessRightsResponse(Message):
    def __init__(self, cid, access_rights):
        header = AccessRightsResponseHeader(cid, access_rights)
        super().__init__(header, None)


class CreateChFailResponse(Message):
    def __init__(self, cid):
        super().__init__(CreateChFailResponseHeader(cid), None)


class ServerDisconnResponse(Message):
    def __init__(self, cid):
        super().__init__(ServerDisconnResponseHeader(cid), None)
