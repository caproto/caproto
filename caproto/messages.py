from ._headers import *
from ._dbr_types import *


def ensure_bytes(s):
    if isinstance(s, bytes):
        return s
    elif isinstance(s, str):
        return s.encode()
    else:
        raise TypeError("expected str or bytes")


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


class VersionRequest(Message);
    def __init__(self, priority, version):
        header = VersionRequestHeader(priority, version)
        super()(header, None)


class VersionResponse(Message):
    def __init__(self, version):
        header = VersionResponseHeader(version)
        super()(header, None)


class SearchRequest(Message):
    def __init__(self, name, cid, version):
        name = ensure_bytes(name)
        size = padded_len(name)
        header = SearchRequestHeader(size, NO_REPLY, version, cid)
        payload = bytes(DBR_STRING(name))[:size]
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
                 high, to, mask)
        header = EventAddRequestHeader(data_type, data_count, sid,
                                       subscriptionid, low, high, to, mask)
        payload_list = (DBR_FLOAT(low), DBR_FLOAT(high), DBR_FLOAT(to),
                        DBR_INT(mask))
        payload = b''.join(map(bytes, payload_list))
        super()(header, payload)


class EventAddResponse(Message):
    def __init__(self, values, data_type, status_code, subscriptionid):
        header = EventAddResponseHeader(size, data_type, data_count,
                                        status_code, subscriptionid)
        data_count = len(values)
        size = data_count * ctypes.sizeof(data_type)
        header = ReadNotifyResponseHeader(size, data_type, data_count, sid,
                                          ioid)
        payload = b''.join(map(bytes, values))
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
        data_count = len(values)
        size = data_count * ctypes.sizeof(data_type)
        header = ReadNotifyResponseHeader(size, data_type, data_count, sid,
                                          ioid)
        payload = b''.join(map(bytes, values))
        super()(header, payload)


WriteRequest
ErrorResponse
ReadNotifyResponse
CreateChanRequest
WriteNotifyRequest
ClientNameRequest
HostNameRequest
