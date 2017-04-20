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
# ``next_command`` method of a :class:`Broadcaster` or a
# :class:`VirtualCircuit`.
import ctypes
import inspect
import struct
import socket
from ._headers import (MessageHeader, ExtendedMessageHeader,
                       AccessRightsResponseHeader, ClearChannelRequestHeader,
                       ClearChannelResponseHeader, ClientNameRequestHeader,
                       CreateChFailResponseHeader, CreateChanRequestHeader,
                       CreateChanResponseHeader, EchoRequestHeader,
                       EchoResponseHeader, ErrorResponseHeader,
                       EventAddRequestHeader, EventAddResponseHeader,
                       EventCancelRequestHeader, EventCancelResponseHeader,
                       EventsOffRequestHeader, EventsOnRequestHeader,
                       HostNameRequestHeader, NotFoundResponseHeader,
                       ReadNotifyRequestHeader, ReadNotifyResponseHeader,
                       ReadResponseHeader, ReadSyncRequestHeader,
                       RepeaterConfirmResponseHeader,
                       RepeaterRegisterRequestHeader, RsrvIsUpResponseHeader,
                       SearchRequestHeader, SearchResponseHeader,
                       ServerDisconnResponseHeader, VersionRequestHeader,
                       VersionResponseHeader, WriteNotifyRequestHeader,
                       WriteNotifyResponseHeader, WriteRequestHeader,

                       )

from ._dbr import (DBR_INT, DBR_STRING, DBR_TYPES, DO_REPLY, NO_REPLY,
                   ChannelType, float_t, short_t, to_builtin, ushort_t,
                   native_type, timestamp_to_epics, MAX_ENUM_STRING_SIZE)

from ._utils import (CLIENT, NEED_DATA, REQUEST, RESPONSE,
                     SERVER, CaprotoTypeError, CaprotoValueError)


_MessageHeaderSize = ctypes.sizeof(MessageHeader)
_ExtendedMessageHeaderSize = ctypes.sizeof(ExtendedMessageHeader)


def ensure_bytes(s):
    if isinstance(s, bytes):
        return s
    elif isinstance(s, str):
        # be sure to include a null terminator
        return s.encode() + b'\0'
    else:
        raise CaprotoTypeError("expected str or bytes")


def from_buffer(data_type, buffer):
    "Wraps dbr_type.from_buffer and special-case strings."
    if data_type == ChannelType.STRING:
        _len = len(buffer)
        if _len > 40:
            raise CaprotoValueError("EPICS imposes a 40-character limit on "
                                    "strings. The " "string {!r} is {} "
                                    "characters.".format(buffer, _len))
        if _len < 40:
            buffer = buffer.ljust(40, b'\x00')
    return DBR_TYPES[data_type].from_buffer(buffer)


def padded_len(s):
    "Length of a (byte)string rounded up to the nearest multiple of 8."
    return 8 * ((len(s) + 7) // 8)


def padded_string_payload(payload):
    byte_payload = ensure_bytes(payload)
    padded_size = padded_len(byte_payload)
    return padded_size, byte_payload.ljust(padded_size, b'\x00')


# TODO re-arrange and tweak as desired
metadata_keywords = ('timestamp', 'status', 'severity', 'strs',
                     'units', 'lower_disp_limit', 'upper_disp_limit',
                     'upper_alarm_limit', 'upper_warning_limit',
                     'lower_warning_limit', 'lower_alarm_limit',
                     'upper_ctrl_limit', 'lower_ctrl_limit',
                     'precision', 'timestamp',
                     )


def data_payload(values, data_type, data_count, *, metadata=None):
    ntype = native_type(data_type)
    size = ctypes.sizeof(DBR_TYPES[data_type])

    if ntype != data_type:
        size += (data_count - 1) * ctypes.sizeof(DBR_TYPES[ntype])

    if data_count != 1:
        # TODO this needs some work
        assert data_count == len(values)
        value_payload = b''.join(map(bytes, values))
    else:
        value_payload = DBR_TYPES[ntype](*values)

    payload = DBR_TYPES[data_type]()

    if metadata:
        for attr in metadata_keywords:
            # TODO note that some facilities use the nanosecond integer as
            # a lossless event id and conversion to float is not a good thing
            # ... should incorporate that into the logic here
            if attr == 'timestamp':
                if (hasattr(metadata, 'timestamp') and
                        hasattr(payload, 'secondsSinceEpoch') and
                        hasattr(payload, 'nanoSeconds')):
                    sec, ns = timestamp_to_epics(metadata.timestamp)
                    payload.secondsSinceEpoch = sec
                    payload.nanoSeconds = ns
                    continue

            elif (attr == 'strs' and hasattr(metadata, attr) and
                    hasattr(payload, attr)):
                for i, string in enumerate(metadata.strs):
                    bytes_ = string.encode('latin-1')
                    justified = bytes_.ljust(MAX_ENUM_STRING_SIZE, b'\x00')
                    payload.strs[i][:] = justified
                payload.no_str = len(metadata.strs)
                continue

            if hasattr(metadata, attr) and hasattr(payload, attr):
                value = getattr(metadata, attr)
                if isinstance(value, str):
                    value = value.encode('latin-1')

                try:
                    setattr(payload, attr, value)
                except Exception as ex:
                    # TODO server probably should not fail here
                    # raise ValueError('Invalid metadata for {}={} ({})'
                    #                  ''.format(attr, value, ex))
                    print('set metadata fail', attr, value)
    payload.value = value_payload.value

    payload = bytes(payload)

    # Payloads must be zeropadded to have a size that is a multiple of 8.
    if size % 8 != 0:
        size = 8 * ((size + 7) // 8)
        payload = payload.ljust(size, b'\x00')
    return size, payload


def get_command_class(role, header):
    _class = Commands[role][header.command]
    # Special case for EventCancelResponse which is coded inconsistently.
    if role is SERVER and header.command == 1 and header.payload_size == 0:
        _class = Commands[role][2]
    return _class


def read_datagram(data, address, role):
    "Parse bytes from one datagram into one or more commands."
    barray = bytearray(data)
    commands = []
    while barray:
        header = MessageHeader.from_buffer(barray)
        barray = barray[_MessageHeaderSize:]
        _class = get_command_class(role, header)
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
    _class = get_command_class(role, header)
    payload_size = header.payload_size
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

    def __init__(self, header, payload=None, validate=True):
        self.header = header
        self.payload = payload
        if validate:
            self.validate()

    def validate(self):
        if self.payload is None:
            if self.header.payload_size != 0:
                raise CaprotoValueError("header.payload_size {} > 0 but "
                                        "payload is None."
                                        "".format(self.header.payload_size))
        elif self.header.payload_size != len(self.payload):
            raise CaprotoValueError("header.payload_size {} != len(payload) {}"
                                    "".format(self.header.payload_size,
                                              len(self.payload)))
        if self.header.command != self.ID:
            raise CaprotoTypeError("A {} must have a header with "
                                   "header.command == {}, not {}."
                                   "".format(type(self), self.ID,
                                             self.header.command))

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
        payload_struct = from_buffer(header.data_type, payload_bytes)
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
        parameters = (signature.parameters if type(self) is not Message
                      else ['header'])

        d = []
        for arg in parameters:
            try:
                d.append((arg, repr(getattr(self, arg))))
            except Exception as ex:
                d.append((arg, '(repr failure {})'.format(ex)))

        formatted_args = ", ".join(["{!s}={}".format(k, v)
                                    for k, v in d])
        return "{}({})".format(type(self).__name__, formatted_args)

    def __len__(self):
        return len(bytes(self))


class VersionRequest(Message):
    """
    Initiate a new connection or broadcast between the client and the server.

    Fields:

    .. attribute:: priority

        Between 0 (low) and 99 (high) designating this connection's priority
        in the event of congestion.

    .. attribute:: version

        The version of the Channel Access protocol.
    """
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
    """
    Respond to a client's initiation of a new connection or broadcast.

    Fields:

    .. attribute:: version

        The version of the Channel Access protocol.
    """
    ID = 0
    HAS_PAYLOAD = False

    def __init__(self, version):
        header = VersionResponseHeader(version)
        super().__init__(header, None)

    version = property(lambda self: self.header.data_count)


class SearchRequest(Message):
    """
    Query for the address of the server that provides a given Channel.

    Fields:

    .. attribute:: name

        String name of the channel (i.e. 'PV')

    .. attribute:: cid

        Integer that uniquely identifies this search query on the client side.

    .. attribute:: version

        The version of the Channel Access protocol.

    .. attribute:: payload_size

        Padded length of name string

    .. attribute:: reply

        Hard-coded to :data:`NO_REPLY` (:data:`5`) meaning that only the
        server(s) with an affirmative response should reply.
    """
    ID = 6
    HAS_PAYLOAD = True

    def __init__(self, name, cid, version):
        size, payload = padded_string_payload(name)
        _len = len(name)
        if _len > 40:
            raise CaprotoValueError("EPICS imposes a 40-character limit on "
                                    "strings. The " "string {!r} is {} "
                                    "characters.".format(name, _len))
        header = SearchRequestHeader(size, NO_REPLY, version, cid)
        super().__init__(header, payload)

    payload_size = property(lambda self: self.header.payload_size)
    reply = property(lambda self: self.header.data_type)
    version = property(lambda self: self.header.data_count)
    cid = property(lambda self: self.header.parameter1)
    name = property(lambda self: bytes(self.payload).rstrip(b'\x00'))


class SearchResponse(Message):
    """
    Answer a :class:`SearchRequest` giving the address of a Channel.

    Fields:

    .. attribute:: port

        Port number that will accept TCP connections with clients.

    .. attribute:: ip

        IP address (as a string) that will accept TCP connections with clients.

    .. attribute:: cid

        Echoing :data:`cid` of :class:`SearchRequest` to let the client match
        this response with the original request.

    .. attribute:: version

        The version of the Channel Access protocol.
    """
    ID = 6
    HAS_PAYLOAD = True

    def __init__(self, port, ip, cid, version):
        if ip is None:
            ip = '255.255.255.255'

        encoded_ip = socket.inet_pton(socket.AF_INET, ip)
        int_encoded_ip, = struct.unpack('!I', encoded_ip)  # bytes -> int
        header = SearchResponseHeader(data_type=port,
                                      sid=int_encoded_ip,
                                      cid=cid)
        # Pad a uint16 to fill 8 bytes.
        payload = bytes(DBR_INT(version)).ljust(8, b'\x00')
        super().__init__(header, payload)

    @classmethod
    def from_wire(cls, header, payload_bytes):
        # Special-case to handle the fact that data_type field is not the data
        # type. (It's used to hold the server port, unrelated to the payload.)
        if not payload_bytes:
            return cls.from_components(header, None)
        return cls.from_components(header, payload_bytes)

    @property
    def ip(self):
        # for CA version >= 4.11
        int_encoded_ip = self.header.parameter1
        encoded_ip = struct.pack('!I', int_encoded_ip)  # int -> bytes
        return socket.inet_ntop(socket.AF_INET, encoded_ip)

    @property
    def version(self):
        return DBR_INT.from_buffer(bytearray(self.payload)[:2]).value

    port = property(lambda self: self.header.data_type)
    cid = property(lambda self: self.header.parameter2)


class NotFoundResponse(Message):
    """
    Answer a :class:`SearchResponse` in the negative.

    Fields:

    .. attribute:: cid

        Echoing :data:`cid` of :class:`SearchRequest` to let the client match
        this response with the original request.

    .. attribute:: version

        The version of the Channel Access protocol.
    """
    ID = 14
    HAS_PAYLOAD = False

    def __init__(self, version, cid):
        header = NotFoundResponseHeader(DO_REPLY, version, cid)
        super().__init__(header, None)

    reply_flag = property(lambda self: self.header.data_type)
    version = property(lambda self: self.header.data_count)
    cid = property(lambda self: self.header.parameter1)


class EchoRequest(Message):
    """
    Request an :class:`EchoResponse`.

    This command has no fields.
    """
    ID = 23
    HAS_PAYLOAD = False

    def __init__(self):
        super().__init__(EchoRequestHeader(), None)


class EchoResponse(Message):
    """
    Respond to an :class:`EchoRequest`.

    This command has no fields.
    """
    ID = 23
    HAS_PAYLOAD = False

    def __init__(self):
        super().__init__(EchoResponseHeader(), None)


class RsrvIsUpResponse(Message):
    """
    Heartbeat beacon sent by the server.

    Fields:

    .. attribute:: version

        The version of the Channel Access protocol.

    .. attribute:: server_port

        Port number.

    .. attribute:: beacon_id

        Sequentially incremented integer.

    .. attribute:: address

        IP address encoded as integer.

    .. attribute:: address_string

        IP address as string.
    """
    ID = 13
    HAS_PAYLOAD = False

    def __init__(self, version, server_port, beacon_id, address):
        # TODO if address is 0, it should be replaced with the remote ip from
        # the udp packet
        header = RsrvIsUpResponseHeader(version, server_port, beacon_id,
                                        address)
        super().__init__(header, None)

    version = property(lambda self: self.header.data_type)
    server_port = property(lambda self: self.header.data_count)
    beacon_id = property(lambda self: self.header.parameter1)
    address = property(lambda self: self.header.parameter2)

    @property
    def address_string(self):
        addr_bytes = struct.pack('!I', self.address)
        return socket.inet_ntop(socket.AF_INET, addr_bytes)


class RepeaterConfirmResponse(Message):
    """
    Confirm successful client registration with the Repeater.

    Fields:

    .. attribute:: repeater_address

        IP address of repeater (as a string).
    """
    ID = 17
    HAS_PAYLOAD = False

    def __init__(self, repeater_address):
        encoded_ip = socket.inet_pton(socket.AF_INET, str(repeater_address))
        int_encoded_ip, = struct.unpack('!I', encoded_ip)  # bytes -> int
        header = RepeaterConfirmResponseHeader(int_encoded_ip)
        super().__init__(header, None)

    @property
    def repeater_address(self):
        int_encoded_ip = self.header.parameter2
        encoded_ip = struct.pack('!I', int_encoded_ip)  # int -> bytes
        return socket.inet_ntop(socket.AF_INET, encoded_ip)


class RepeaterRegisterRequest(Message):
    """
    Register a client with the Repeater.

    Fields:

    .. attribute:: client_address

        IP address of the client (as a string).
    """
    ID = 24
    HAS_PAYLOAD = False

    def __init__(self, client_address):
        encoded_ip = socket.inet_pton(socket.AF_INET, str(client_address))
        int_encoded_ip, = struct.unpack('!I', encoded_ip)  # bytes -> int
        header = RepeaterRegisterRequestHeader(int_encoded_ip)
        super().__init__(header, None)

    @property
    def client_address(self):
        int_encoded_ip = self.header.parameter2
        encoded_ip = struct.pack('!I', int_encoded_ip)  # int -> bytes
        return socket.inet_ntop(socket.AF_INET, encoded_ip)


class EventAddRequestPayload(ctypes.BigEndianStructure):
    _fields_ = [('low', float_t),
                ('high', float_t),
                ('to', float_t),
                ('mask', ushort_t),
                ('__padding__', short_t),
                ]

    def __init__(self, low=0.0, high=0.0, to=0.0, mask=0):
        self.low = low
        self.high = high
        self.to = to
        self.mask = mask
        self.__padding__ = 0

    def __len__(self):
        return len(bytes(self))


class EventAddRequest(Message):
    """
    Subscribe; i.e. request to notified of changes in a Channel's value.

    Fields:

    .. attribute:: data_type

        Integer code of desired DBR type of readings.

    .. attribute:: data_count

        Desired number of elements per reading.

    .. attribute:: sid

        Integer ID of this Channel designated by the server.

    .. attribute:: subscriptionid

        New integer ID designated by the client uniquely identifying this
        subscription on this Virtual Circuit.

    .. attribute:: low

        Deprecated. (Use :data:`mask`.)

    .. attribute:: high

        Deprecated. (Use :data:`mask`.)

    .. attribute:: to

        Deprecated. (Use :data:`mask`.)

    .. attribute:: mask

        Mask indicating which changes to report.
    """
    ID = 1
    HAS_PAYLOAD = True

    def __init__(self, data_type, data_count, sid, subscriptionid, low,
                 high, to, mask):
        header = EventAddRequestHeader(data_type, data_count, sid,
                                       subscriptionid)
        payload = EventAddRequestPayload(low=low, high=high, to=to, mask=mask)
        super().__init__(header, payload)

    @classmethod
    def from_wire(cls, header, payload_bytes):
        payload_struct = EventAddRequestPayload.from_buffer(payload_bytes)
        return cls.from_components(header, payload_struct)

    data_type = property(lambda self: self.header.data_type)
    data_count = property(lambda self: self.header.data_count)
    sid = property(lambda self: self.header.parameter1)
    subscriptionid = property(lambda self: self.header.parameter2)
    low = property(lambda self: self.payload.low)
    high = property(lambda self: self.payload.high)
    to = property(lambda self: self.payload.to)
    mask = property(lambda self: self.payload.mask)
    __padding__ = property(lambda self: self.payload.__padding__)


class EventAddResponse(Message):
    """
    Notify the client of a change in a Channel's value.

    Fields:

    .. attribute:: values

        data in a tuple of built-in Python or numpy types

    .. attribute:: data_type

        Integer code of DBR type of reading.

    .. attribute:: data_count

        Number of elements in this reading.

    .. attribute:: sid

        Integer ID of this Channel designated by the server.

    .. attribute:: status_code

        As per Channel Access spec, 1 is success; 0 or >1 are various failures.

    .. attribute:: subscriptionid

        Echoing the :data:`subscriptionid` in the :class:`EventAddRequest`
    """
    ID = 1
    HAS_PAYLOAD = True

    def __init__(self, values, data_type, data_count,
                 status_code, subscriptionid, *, metadata=None):
        size, payload = data_payload(values, data_type, data_count,
                                     metadata=metadata)
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
        # libca responds to EventCancelRequest with an
        # EventAddResponse with an empty payload.
        if not payload_bytes:
            return cls.from_components(header, None)
        payload_struct = from_buffer(header.data_type, payload_bytes)
        return cls.from_components(header, payload_struct)


class EventCancelRequest(Message):
    """
    End notifcations about chnages in a Channel's value.

    Fields:

    .. attribute:: data_type

        Integer code of DBR type of reading.

    .. attribute:: sid

        Integer ID of this Channel designated by the server.

    .. attribute:: subscriptionid

        Integer ID for this subscription.
    """
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
    """
    Confirm receipt of :class:`EventCancelRequest`.

    Fields:

    .. attribute:: data_type

        Integer code of DBR type of reading.

    .. attribute:: sid

        Integer ID of this Channel designated by the server.

    .. attribute:: subscriptionid

        Integer ID for this subscription.
    """
    # Actually this is coded with the ID = 1 like EventAdd*.
    # This is the only weird exception so we special-case it in the function
    # get_command_class.
    ID = 2
    HAS_PAYLOAD = False

    def __init__(self, data_type, sid, subscriptionid):
        # TODO: refactor, this does not exist
        header = EventCancelResponseHeader(data_type, sid, subscriptionid)
        super().__init__(header, None)

    data_type = property(lambda self: self.header.data_type)
    sid = property(lambda self: self.header.parameter1)
    subscriptionid = property(lambda self: self.header.parameter2)

    def validate(self):
        # special case because of weird ID
        if self.header.command != 1:
            raise CaprotoTypeError("A {} must have a header with "
                                   "header.command == 1, not {}."
                                   "".format(type(self), self.header.command))
        if self.payload is not None:
            raise CaprotoTypeError("A {} must have no payload."
                                   "".format(type(self)))
        # do not call super()


class ReadRequest(Message):
    "Deprecated by Channel Access: See :class:`ReadNotifyRequest`."
    ID = 3
    HAS_PAYLOAD = False

    def __init__(self, data_type, data_count, sid, ioid):
        header = ReadNotifyRequestHeader(data_type, data_count, sid, ioid)
        super().__init__(header, None, validate=False)

    data_type = property(lambda self: self.header.data_type)
    data_count = property(lambda self: self.header.data_count)
    sid = property(lambda self: self.header.parameter1)
    ioid = property(lambda self: self.header.parameter2)


class ReadResponse(Message):
    "Deprecated by Channel Access: See :class:`ReadNotifyResponse`."
    ID = 3
    HAS_PAYLOAD = True

    def __init__(self, data, data_type, data_count, sid, ioid, *,
                 metadata=None):
        size, payload = data_payload(data, data_type, data_count,
                                     metadata=metadata)
        header = ReadResponseHeader(size, data_type, data_count, sid, ioid)
        super().__init__(header, payload)

    payload_size = property(lambda self: self.header.payload_size)
    data_type = property(lambda self: self.header.data_type)
    data_count = property(lambda self: self.header.data_count)
    sid = property(lambda self: self.header.parameter1)
    ioid = property(lambda self: self.header.parameter2)
    values = property(lambda self: to_builtin(self.payload, self.data_type,
                                              self.data_count))


class WriteRequest(Message):
    "Deprecated: See :class:`WriteNotifyRequest`."
    ID = 4
    HAS_PAYLOAD = True

    def __init__(self, values, data_type, data_count, sid, ioid, *,
                 metadata=None):
        size, payload = data_payload(values, data_type, data_count,
                                     metadata=metadata)
        header = WriteRequestHeader(size, data_type, data_count, sid, ioid)
        super().__init__(header, payload)

    payload_size = property(lambda self: self.header.payload_size)
    data_type = property(lambda self: self.header.data_type)
    data_count = property(lambda self: self.header.data_count)
    sid = property(lambda self: self.header.parameter1)
    ioid = property(lambda self: self.header.parameter2)
    values = property(lambda self: to_builtin(self.payload, self.data_type,
                                              self.data_count))

# There is no 'WriteResponse'. See WriteNotifyRequest/WriteNotifyResponse.


class EventsOffRequest(Message):
    """
    Temporarily turn off :class:`EventAddResponse` notifications.

    This command has no fields.
    """
    ID = 8
    HAS_PAYLOAD = False

    def __init__(self):
        super().__init__(EventsOffRequestHeader(), None)


class EventsOnRequest(Message):
    """
    Restore :class:`EventAddResponse` notifications.

    This command has no fields.
    """
    ID = 9
    HAS_PAYLOAD = False

    def __init__(self):
        super().__init__(EventsOnRequestHeader(), None)


class ReadSyncRequest(Message):
    "Deprecated by Channel Access: See :class:`ReadNotifyRequest`"
    ID = 10
    HAS_PAYLOAD = False

    def __init__(self):
        super().__init__(ReadSyncRequestHeader(), None)


class _ErrorResponsePayload(ctypes.BigEndianStructure):
    _fields_ = [
        ('value', ctypes.c_char * 100),
    ]


class ErrorResponse(Message):
    """
    Notify client of a server-side error, including some details about error.

    Fields:

    .. attribute:: cid

        Integer ID for this Channel designated by the client.

    .. attribute:: status_code

        As per Channel Access spec, 1 is success; 0 or >1 are various failures.

    """
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

    @classmethod
    def from_wire(cls, header, payload_bytes):
        """
        Override base because payload contains a string >40 characers.
        """
        payload_struct = _ErrorResponsePayload.from_buffer(payload_bytes)
        return cls.from_components(header, payload_struct)


class ClearChannelRequest(Message):
    """
    Close a Channel.

    Fields:

    .. attribute:: cid

        Integer ID for this Channel designated by the client.

    .. attribute:: sid

        Integer ID for this Channel designated by the server.
    """
    ID = 12
    HAS_PAYLOAD = False

    def __init__(self, sid, cid):
        super().__init__(ClearChannelRequestHeader(sid, cid), None)

    sid = property(lambda self: self.header.parameter1)
    cid = property(lambda self: self.header.parameter2)


class ClearChannelResponse(Message):
    """
    Confirm that a Channel has been closed.

    Fields:

    .. attribute:: cid

        Integer ID for this Channel designated by the client.

    .. attribute:: sid

        Integer ID for this Channel designated by the server.
    """
    ID = 12
    HAS_PAYLOAD = False

    def __init__(self, sid, cid):
        super().__init__(ClearChannelResponseHeader(sid, cid), None)

    sid = property(lambda self: self.header.parameter1)
    cid = property(lambda self: self.header.parameter2)


class ReadNotifyRequest(Message):
    """
    Request a fresh reading of a Channel.

    Fields:

    .. attribute:: data_type

        Integer code of desired DBR type of readings.

    .. attribute:: data_count

        Desired number of elements per reading.

    .. attribute:: sid

        Integer ID for this Channel designated by the server.

    .. attribute:: ioid

        New integer ID uniquely identifying this I/O transaction on this
        Virtual Circuit.
    """
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
    """
    Request a fresh reading of a Channel.

    Fields:

    .. attribute:: data_type

        Integer code of desired DBR type of readings.

    .. attribute:: data_count

        Desired number of elements per reading.

    .. attribute:: sid

        Integer ID for this Channel designated by the server.

    .. attribute:: ioid

        Integer ID for I/O transaction, echoing :class:`ReadNotifyRequest`.

    .. attribute:: status

        As per Channel Access spec, 1 is success; 0 or >1 are various failures.

    """
    ID = 15
    HAS_PAYLOAD = True

    def __init__(self, values, data_type, data_count, status, ioid, *,
                 metadata=None):
        size, payload = data_payload(values, data_type, data_count,
                                     metadata=metadata)
        header = ReadNotifyResponseHeader(size, data_type, data_count, status,
                                          ioid)
        super().__init__(header, payload)

    payload_size = property(lambda self: self.header.payload_size)
    data_type = property(lambda self: self.header.data_type)
    data_count = property(lambda self: self.header.data_count)
    status = property(lambda self: self.header.parameter1)
    ioid = property(lambda self: self.header.parameter2)
    values = property(lambda self: to_builtin(self.payload, self.data_type,
                                              self.data_count))


class CreateChanRequest(Message):
    """
    Request a new Channel.

    Fields:

    .. attribute:: name

        String name of the channel (i.e. 'PV')

    .. attribute:: cid

        New integer ID designated by the client, uniquely identifying this
        Channel on its VirtualCircuit.

    .. attribute:: version

        The version of the Channel Access protocol.

    """
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
    """
    Confirm the intialization of a new Channel

    Fields:

    .. attribute:: data_type

        Integer code of native DBR type of readings.

    .. attribute:: data_count

        Native number of elements per reading.

    .. attribute:: cid

        Integer ID for this Channel designated by the client, echoing the value
        in :class:`CreateChanRequest`.

    .. attribute:: sid

        New integer ID for this Channel designated by the server uniquely
        identifying this Channel on its VirtualCircuit.

    """
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
    """
    Write a value to a Channel.

    Fields:

    .. attribute:: values

        data in a tuple of built-in Python or numpy types

    .. attribute:: data_type

        Integer code of DBR type.

    .. attribute:: data_count

        Number of elements.

    .. attribute:: sid

        Integer ID for this Channel designated by the server.

    .. attribute:: ioid

        New integer ID uniquely identifying this I/O transaction on this
        Virtual Circuit.
    """
    ID = 19
    HAS_PAYLOAD = True

    def __init__(self, values, data_type, data_count, sid, ioid, *,
                 metadata=None):
        size, payload = data_payload(values, data_type, data_count,
                                     metadata=metadata)
        header = WriteNotifyRequestHeader(size, data_type, data_count, sid,
                                          ioid)
        super().__init__(header, payload)

    payload_size = property(lambda self: self.header.payload_size)
    data_type = property(lambda self: self.header.data_type)
    data_count = property(lambda self: self.header.data_count)
    sid = property(lambda self: self.header.parameter1)
    ioid = property(lambda self: self.header.parameter2)
    values = property(lambda self: to_builtin(self.payload, self.data_type,
                                              self.data_count))


class WriteNotifyResponse(Message):
    """
    Confirm the receipt of a :class:`WriteNotifyRequest`.

    Fields:

    .. attribute:: data_type

        Integer code of DBR type.

    .. attribute:: data_count

        Number of elements.

    .. attribute:: sid

        Integer ID for this Channel designated by the server.

    .. attribute:: ioid

        Integer ID for this I/O transaction, echoing
        :class:`WriteNotifyRequest`.

    .. attribute:: status

        As per Channel Access spec, 1 is success; 0 or >1 are various failures.
    """
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
    """
    Tell the server the client name (i.e., user name) of the client.

    Fields:

    .. attribute:: name

        Client name.
    """
    ID = 20
    HAS_PAYLOAD = True

    def __init__(self, name):
        size, payload = padded_string_payload(name)
        header = ClientNameRequestHeader(size)
        super().__init__(header, payload)

    payload_size = property(lambda self: self.header.payload_size)
    name = property(lambda self: bytes(self.payload).rstrip(b'\x00'))


class HostNameRequest(Message):
    """
    Tell the server the host name of the client.

    Fields:

    .. attribute:: name

        Host name.
    """
    ID = 21
    HAS_PAYLOAD = True

    def __init__(self, name):
        size, payload = padded_string_payload(name)
        header = HostNameRequestHeader(size)
        super().__init__(header, payload)

    payload_size = property(lambda self: self.header.payload_size)
    name = property(lambda self: bytes(self.payload).rstrip(b'\x00'))

    @classmethod
    def from_wire(cls, header, payload_bytes):
        ''' '''
        return cls.from_components(header, payload_bytes)


class AccessRightsResponse(Message):
    """
    Notify the client that channel creation failed.

    Fields:

    .. attribute:: cid

        Integer ID for this Channel designated by the client.

    .. attribute:: access_rights

        Integer designated level of read or write access. (See Channel Access
        spec for details about meanings.)
    """
    ID = 22
    HAS_PAYLOAD = False

    def __init__(self, cid, access_rights):
        header = AccessRightsResponseHeader(cid, access_rights)
        super().__init__(header, None)

    cid = property(lambda self: self.header.parameter1)
    access_rights = property(lambda self: self.header.parameter2)


class CreateChFailResponse(Message):
    """
    Notify the client that channel creation failed.

    Fields:

    .. attribute:: cid

        Integer ID for this Channel designated by the client.
    """
    ID = 26
    HAS_PAYLOAD = False

    def __init__(self, cid):
        super().__init__(CreateChFailResponseHeader(cid), None)

    cid = property(lambda self: self.header.parameter1)


class ServerDisconnResponse(Message):
    """
    Notify the client that server will disconnect from this Channel.

    Fields:

    .. attribute:: cid

        Integer ID for this Channel designated by the client.
    """
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

# TODO special-case, RsrvIsUp is sent from CA Server to Broadcaster server
Commands[CLIENT][RsrvIsUpResponse.ID] = RsrvIsUpResponse
Commands[SERVER][RsrvIsUpResponse.ID] = RsrvIsUpResponse
RsrvIsUpResponse.DIRECTION = REQUEST
