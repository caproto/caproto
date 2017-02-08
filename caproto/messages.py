from ._headers import *
from ._dbr_types import *


def ensure_bytes(s):
    if isinstance(s, bytes):
        return s
    elif isinstance(s, str):
        return s.encode()
    else:
        raise TypeError("expected str or bytes")


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
        super()(header, None)


class VersionResponse(Message):
    def __init__(self, version):
        header = VersionResponseHeader(version)
        super()(header, None)


class SearchRequest(Message):
    def __init__(self, name, cid, version):
        size, payload = padded_string_payload(name)
        header = SearchRequestHeader(size, NO_REPLY, version, cid)
        super()(header, payload)


class SearchResponse(Message):
    def __init__(self, port, sid, cid, version):
        header = SearchResponseHeader(port, sid, cid)
        payload = bytes(DBR_INT(version))
        super()(header, payload)


class NotFoundResponse(Message):
    def __init__(self, version, cid):
        header = NotFoundResponseHeader(DO_REPLY, version, cid)
        super()(header, None)


class EchoRequest(Messsage):
    def __init__(self):
        super()(EchoRequestHeader(), None)


class EchoResponse(Message):
    def __init__(self):
        super()(EchoResponseHeader(), None)


class RsrvIsUpResponse(Message):
    def __init__(self, server_port, beacon_id, address):
        super()(RsrvIsUpResponseHeader(server_port, beacon_id, address), None)


class CaRepeaterConfirmResponseHeader(Message):
    def __init__(self, repeater_address):
        super()(CaRepeaterConfirmResponseHeader(repeater_address), None)


class CaRepeaterRegisterRequestHeader(Message):
    def __init__(self, client_ip_address):
        super()(CaRepeaterRegisterRequestHeader(client_ip_address), None)

class EventAddRequest(Messsage):
    def __init__(self, data_type, data_count, sid, subscriptionid, low,
                 high, to, mask):
        header = EventAddRequestHeader(data_type, data_count, sid,
                                       subscriptionid, low, high, to, mask)
        payload_list = (DBR_FLOAT(low), DBR_FLOAT(high), DBR_FLOAT(to),
                        DBR_INT(mask))
        payload = b''.join(map(bytes, payload_list))
        super()(header, payload)


class EventAddResponse(Message):
    def __init__(self, values, data_type, data_count,
                 status_code, subscriptionid):
        size, payload = data_payload(values)
        header = EventAddResponseHeader(size, data_type, data_count,
                                        status_code, subscriptionid)
        super()(header, payload)


class EventCancelRequest(Message):
    def __init__(self, data_type, data_count, sid, subscriptionid):
        header = EventCancelRequestHeader(data_type, data_count, sid,
                                          subscriptionid)
        super()(header, None)


class EventCancelResponse(Message):
    def __init__(self, data_type, sid, subscriptionid):
        header = EventCancelResponseHeader(data_type, sid, subscriptionid)
        super()(header, None)


class ReadNotifyRequest(Message):
    def __init__(self, data_type, data_count, sid, ioid):
        header = ReadNotifyRequestHeader(data_type, data_count, sid, ioid)
        super()(header, None)


class ReadNotifyResponse(Message):
    def __init__(self, values, data_type, sid, ioid):
        size, payload = data_payload(values)
        header = ReadNotifyResponseHeader(size, data_type, data_count, sid,
                                          ioid)
        super()(header, payload)


class WriteRequest(Message):
    def __init__(self, values, data_type, sid, ioid):
        size, payload = data_payload(values)
        header = WriteRequestHeader(size, data_type, data_count, sid, ioid)
        super()(header, payload)


class EventsOffRequest(Message):
    def __init__(self):
        super()(EventsOffRequestHeader(), None)


class EventsOnRequest(Message):
    def __init__(self):
        super()(EventsOnRequestHeader(), None)


class ReadSyncRequestRequest(Message):
    def __init__(self):
        super()(ReadSyncRequestRequestHeader(), None)


class ErrorResponse(Message):
    def __init__(self, original_request, cid, status_code, error_message):
        _error_message = DBR_STRING(ensure_bytes(error_message))
        payload = bytes(original_request) + _error_message
        size = len(payload)
        header = ErrorResponseHeader(size, cid, status_code)
        super()(header, payload)


class ClearChannelRequest(Message):
    def __init__(self, sid, cid):
        super()(ClearChannelRequestHeader(sid, cid), None)


class ClearChannelResponse(Message):
    def __init__(self, sid, cid):
        super()(ClearChannelResponseHeader(sid, cid), None)


class ReadNotifyRequest(Message):
    def __init__(self, data_type, data_count, sid, ioid):
        header = ReadNotifyRequestHeader(data_type, data_count, sid, ioid)
        super()(header, None)

    
class ReadNotifyResponse(Message):
    def __init__(self, values, data_type, data_count, sid, ioid):
        size, payload = data_payload(values)
        header = ReadNotifyRequest(size, data_type, data_count, sid, ioid)
        super()(header, payload)


class CreateChanRequest(Message):
    def __init__(self, name, cid, version):
        size, payload = padded_string_payload(name)
        header = CreateChanRequestHeader(size, cid, version)
        super()(header, payload)

class CreateChanResponse(Message):
    def __init__(self, data_type, data_count, cid, sid):
        header = CreateChanResponseHeader(data_type, data_count, cid, sid)
        super()(header, None)


class WriteNotifyRequest(Message):
    def __init__(self, values, data_type, data_count, status, ioid):
        size, payload = data_payload(values)
        header = WriteNotifyRequest(size, data_type, data_count, status, ioid)
        super()(header, payload)


class WriteNotifyResponse(Message):
    def __init__(self, data_type, data_count, status, ioid):
        header = WriteNotifyResponse(data_type, data_count, status, ioid)
        super()(header, None)


class ClientNameRequest(Message):
    def __init__(self, name):
        size, payload = padded_string_payload(name)
        header = ClientNameRequestHeader(size)
        super()(header, payload)


class HostNameRequest(Message):
    def __init__(self, name):
        size, payload = padded_string_payload(name)
        header = HostNameRequestHeader(size)
        super()(header, payload)


class AccessRightsResponse(Message):
    def __init__(self, cid, access_rights):
        header = AccessRightsResponseHeader(cid, access_rights)
        super()(header, None)


class CreateChFailResponse(Message):
    def __init__(self, cid):
        super()(CreateChFailResponseHeader(cid), None)


class ServerDisconnResponse(Message):
    def __init__(self, cid):
        super()(ServerDisconnResponseHeader(cid), None)
