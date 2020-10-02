# This module contains high-level "command" objects, one for each CA command.
# A command wraps together a ``MessageHeader`` from _headers.py with a payload
# of raw bytes (if applicable). It provides a more user-friendly __init__ that
# accepts standard Python types and handles details like type conversion and
# bit-padding. For every argument to the __init__ there is a corresponding
# property to allow high-level introspection of a command. There are also
# ``header`` and ``payload`` attributes for lower-level introspection. Finally,
# the command objects support ``__bytes__``, encoding them for sending over the
# wire.

# A command class may be instantiated in one of two ways:
# 1. For sending: by passing user-friendly inputs to ``__init__``.
# 2. For receiving: by passing a datagram or bytestream to the functions
#    ``read_datagram`` and `read_from _bytestream`` respectively. These
#    identify the command type and instantiate the appropriate class from bytes
#    using ``__new__``.
#
# (1) is typically done by the user. (2) is typically done by calling the
# ``next_command`` method of a :class:`Broadcaster` or a
# :class:`VirtualCircuit`.
import array
from collections.abc import Iterable
import ctypes
import _ctypes
import inspect
import os
import struct
import socket
import warnings
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
                       ReadRequestHeader, ReadResponseHeader,
                       ReadSyncRequestHeader,
                       RepeaterConfirmResponseHeader,
                       RepeaterRegisterRequestHeader, BeaconHeader,
                       SearchRequestHeader, SearchResponseHeader,
                       ServerDisconnResponseHeader, VersionRequestHeader,
                       VersionResponseHeader, WriteNotifyRequestHeader,
                       WriteNotifyResponseHeader, WriteRequestHeader,
                       )

from ._constants import (DO_REPLY, NO_REPLY, MAX_RECORD_LENGTH)
from ._dbr import (DBR_INT, DBR_TYPES, ChannelType, float_t, short_t, ushort_t,
                   native_type, special_types, MAX_STRING_SIZE, AccessRights)

from . import _dbr as dbr
from ._backend import backend
from ._status import eca_value_to_status, ensure_eca_value
from ._utils import (CLIENT, NEED_DATA, REQUEST, RESPONSE, SERVER,
                     CaprotoTypeError, CaprotoValueError,
                     CaprotoNotImplementedError, ValidationError,
                     ensure_bytes)


__all__ = ('AccessRightsResponse', 'ClearChannelRequest',
           'ClearChannelResponse', 'ClientNameRequest',
           'CreateChFailResponse', 'CreateChanRequest',
           'CreateChanResponse', 'EchoRequest',
           'EchoResponse', 'ErrorResponse',
           'EventAddRequest', 'EventAddRequestPayload', 'EventAddResponse',
           'EventCancelRequest', 'EventCancelResponse',
           'EventsOffRequest', 'EventsOnRequest',
           'get_command_class', 'HostNameRequest',
           'ipv4_from_int32', 'ipv4_to_int32',
           'NotFoundResponse',
           'ReadNotifyRequest', 'ReadNotifyResponse',
           'ReadRequest', 'ReadResponse',
           'ReadSyncRequest',
           'RepeaterConfirmResponse',
           'RepeaterRegisterRequest', 'Beacon',
           'SearchRequest', 'SearchResponse',
           'ServerDisconnResponse', 'VersionRequest',
           'VersionResponse', 'WriteNotifyRequest',
           'WriteNotifyResponse', 'WriteRequest',
           'Message')


_MessageHeaderSize = ctypes.sizeof(MessageHeader)
_ExtendedMessageHeaderSize = ctypes.sizeof(ExtendedMessageHeader)

_pad_buffer = {mod_sz: b'\0' * (8 - mod_sz)
               for mod_sz in range(1, 8)}
_pad_buffer[0] = b''

STR_ENC = os.environ.get('CAPROTO_STRING_ENCODING', 'latin-1')


def ipv4_to_int32(ip: str) -> int:
    '''Pack an IPv4 into a 32-bit integer (in network byte order)'''
    encoded_ip = socket.inet_pton(socket.AF_INET, ip)
    return struct.unpack('!I', encoded_ip)[0]


def ipv4_from_int32(int_packed_ip: int) -> str:
    '''Unpack an IPv4 from a 32-bit integer (in network byte order)'''
    encoded_ip = struct.pack('!I', int_packed_ip)
    return socket.inet_ntop(socket.AF_INET, encoded_ip)


def has_metadata(data_type):
    'Does data_type have associated metadata?'
    return (data_type in special_types or
            data_type != native_type(data_type))


def from_buffer(data_type, data_count, buffer):
    "Wraps dbr_type.from_buffer and special-case strings."
    payload_size = data_count * ctypes.sizeof(
        DBR_TYPES[native_type(data_type)])
    if has_metadata(data_type):
        md_payload = DBR_TYPES[data_type].from_buffer(buffer)
        md_size = ctypes.sizeof(DBR_TYPES[data_type])
    else:
        md_payload = b''
        md_size = 0
    # Use payload_size to strip off any right-padding that may have been added
    # to make the byte-size of the payload a multiple of 8.
    data_payload = memoryview(buffer)[md_size:md_size + payload_size]
    return md_payload, data_payload


def padded_len(s):
    "Length of a (byte)string rounded up to the nearest multiple of 8."
    return 8 * ((len(s) + 7) // 8)


def pad_buffers(*buffers):
    '''Get a bytestring for padding a concatenated set of buffers

    Parameters
    ----------
    *buffers : supported buffer type

    Returns
    -------
    full_padded_length, pad_buffer
    '''
    unpadded_size = sum(bytelen(buf) for buf in buffers)
    pad_buffer = _pad_buffer[unpadded_size % 8]
    return unpadded_size + len(pad_buffer), pad_buffer


def padded_string_payload(payload):
    byte_payload = ensure_bytes(payload)
    padded_size = padded_len(byte_payload)
    return padded_size, byte_payload.ljust(padded_size, b'\x00')


def bytelen(item):
    """
    Meaasure the byte length of an item.

    Supports:
    - ``array.array`` (from the builtin Python lib)
    - ``ctypes`` objects
    - an object that has an ``nbytes`` attribute (notably, numpy arrays and
    ``memoryview``)
    - ``bytes``
    - ``bytearray``
    """
    if isinstance(item, array.array):
        return item.itemsize * len(item)
    elif isinstance(item, (ctypes.Structure, _ctypes._SimpleCData)):
        return ctypes.sizeof(item)
    elif hasattr(item, 'nbytes'):
        # Duck-type as numpy array / memoryview.
        return item.nbytes
    elif isinstance(item, (bytes, bytearray)):
        return len(item)
    else:
        # We could just fall back on len() but I worry that someone will
        # unwittingly use this on a type that has a __len__ that is not its
        # bytelength and is not already caught above. Better to fail like this.
        raise CaprotoNotImplementedError("Not sure how to measure byte length "
                                         "of object of type {}"
                                         "".format(type(item)))


def parse_metadata(metadata, data_type):
    """
    Parse metadata tuple into bytes or DBR.

    If input is:

    * tuple -> DBR struct
    * DBR struct or bytes -> no-op
    * None -> empty bytes object

    Parameters
    ----------
    metadata : a DBR struct, any iterable, or bytes
    data_type : integer

    Returns
    -------
    md_payload : a DBR struct or bytes
    """
    if hasattr(metadata, 'DBR_ID'):
        # This is already a DBR.
        md_payload = metadata
    elif isinstance(metadata, bytes):
        md_payload = metadata
    elif metadata is None:
        md_payload = b''
    elif isinstance(metadata, Iterable):
        # This is a tuple of values to be encoded into a DBR.
        justified_md = []
        for val in metadata:
            if isinstance(val, str):
                if len(val) > MAX_STRING_SIZE:  # 39?
                    raise CaprotoValueError("The protocol limits strings to "
                                            "40 characters.")
                val = val.ljust(MAX_STRING_SIZE, b'\x00')
            justified_md.append(val)
        md_payload = DBR_TYPES[data_type](*justified_md)
    else:
        raise CaprotoTypeError("metadata given as type we cannot handle - {}"
                               "".format(type(metadata)))
    return md_payload


def data_payload(data, metadata, data_type, data_count):
    """
    Pack bytes into a set of buffers for usage as a single payload

    Parameters
    ----------
    data : ``array.array``, ``numpy.ndarray``, any iterable, or bytes
        If input is bytes or ``array.array``, we assume that the byte order of
        the input is big-endian. (We have no means of checking.) If the input
        is ``numpy.ndarray`` or any other iterable, we ensure big-endianness.
    metadata : a DBR struct, any iterable, or bytes
    data_type : integer
    data_count : integer

    Returns
    -------
    size, md_payload, data_payload[, pad_payload]
        pad_payload will only be returned if needed
    """

    # Make the data payload.
    if isinstance(data, bytes):
        # Assume bytes are big-endian; we have no way of checking.
        data_payload = data
    elif (isinstance(data, backend.array_types) or
          isinstance(data, Iterable)):
        data_payload = backend.python_to_epics(
            native_type(data_type), data, byteswap=True)
    elif data is None:
        data_payload = b''
    else:
        raise CaprotoTypeError("data given as type we cannot handle - {}"
                               "".format(type(data)))

    md_payload = parse_metadata(metadata, data_type)
    size, pad_payload = pad_buffers(md_payload, data_payload)
    if pad_payload:
        return size, md_payload, data_payload, pad_payload
    else:
        return size, md_payload, data_payload


def extract_data(buffer, data_type, data_count):
    "Return a scalar or big-endian array (numpy.ndarray or array.array)."
    data = backend.epics_to_python(buffer, native_type(data_type), data_count,
                                   auto_byteswap=True)
    if data_count < len(data):
        return data[:data_count]  # (no copy)
    return data


def extract_metadata(payload, data_type):
    "Return one of the classes in _data.py."
    if data_type < 7:
        return None
    payload = bytearray(payload)  # Makes a copy -- maybe not necessary?
    return dbr.DBR_TYPES[data_type].from_buffer(payload)


def get_command_class(role, header):
    return Commands[role][header.command]


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
        command = _class.from_wire(header, payload_bytes,
                                   sender_address=address)
        commands.append(command)
    return commands


def bytes_needed_for_command(data, role):
    '''
    Parameters
    ----------
    data
    role

    Returns
    -------
    (header, num_bytes_needed)
    '''

    header_size = _MessageHeaderSize
    data_len = len(data)

    # We need at least one header's worth of bytes to interpret anything.
    if data_len < header_size:
        return None, header_size - data_len

    header = MessageHeader.from_buffer(data)
    # Looks for sentinels that mark this as an "extended header".
    if header.payload_size == 0xFFFF and header.data_count == 0:
        header_size = _ExtendedMessageHeaderSize
        # Do we have enough bytes to interpret the extended header?
        if data_len < header_size:
            return None, header_size - data_len
        header = ExtendedMessageHeader.from_buffer(data)

    total_size = header_size + header.payload_size
    # Do we have all the bytes in the payload?
    if data_len < total_size:
        return header, total_size - data_len
    return header, 0


def read_from_bytestream(data, role):
    '''
    Parameters
    ----------
    data
    role

    Returns
    -------
    (remaining_data, command, num_bytes_needed)
        if more data is required, NEED_DATA will be returned in place of
        `command`
    '''

    header, num_bytes_needed = bytes_needed_for_command(data, role)

    if num_bytes_needed > 0:
        return data, NEED_DATA, num_bytes_needed

    _class = Commands[role][header.command]

    header_size = ctypes.sizeof(header)
    total_size = header_size + header.payload_size

    # Receive the buffer (zero-copy).
    payload_bytes = memoryview(data)[header_size:total_size]
    command = _class.from_wire(header, payload_bytes)
    # Advance the buffer.
    return data[total_size:], command, 0


Commands = {}
Commands[CLIENT] = {}
Commands[SERVER] = {}
_commands = set()


class Message:
    __slots__ = ('header', 'buffers', 'sender_address')
    ID = None  # integer, to be overriden by subclass

    def __init_subclass__(cls, register=True):
        if register:
            # Add this class to the global registries of commands.
            name = cls.__name__
            if name.endswith('Request'):
                direction = REQUEST
                command_dict = Commands[CLIENT]
            else:
                direction = RESPONSE
                command_dict = Commands[SERVER]

            cls.DIRECTION = direction

            if cls.ID is not None:
                command_dict[cls.ID] = cls

            if name in ('Beacon, '):
                Commands[CLIENT][cls.ID] = cls
                Commands[SERVER][cls.ID] = cls

            _commands.add(cls)

    def __init__(self, header, *buffers, validate=True, sender_address=None):
        self.header = header
        self.buffers = buffers
        self.sender_address = sender_address

        if validate:
            self.validate()

    def validate(self):
        size = sum(bytelen(buf) for buf in self.buffers)
        if self.buffers == () and self.header.payload_size != 0:
            raise ValidationError(
                "{}.header.payload_size {} > 0 but payload is None."
                "".format(type(self).__name__, self.header.payload_size))
        elif self.header.payload_size != size:
            raise ValidationError(
                "{}.header.payload_size {} != payload size of {}"
                "".format(type(self).__name__, self.header.payload_size, size))
        if self.header.command != self.ID:
            raise ValidationError(
                "A {} must have a header with header.command == {}, not {}."
                "".format(type(self).__name__, self.ID, self.header.command))

    @classmethod
    def from_wire(cls, header, payload_bytes, *, sender_address=None,
                  validate=False):
        """
        Use header.dbr_type to pack payload bytes into the right structure.

        Some Command types allocate a different meaning to the header.dbr_type
        field, and these override this method in their subclass.

        We do *not* validate by default, both for performance and for
        forward-compability. But validation may be useful to turn on in the
        context of consuming network traffic and trying to identify CA packets
        (e.g. caproto.sync.shark).
        """
        if not cls.HAS_PAYLOAD:
            return cls.from_components(header)
        payload = from_buffer(header.data_type, header.data_count,
                              payload_bytes)
        return cls.from_components(header, *payload,
                                   sender_address=sender_address,
                                   validate=validate)

    @classmethod
    def from_components(cls, header, *buffers, sender_address=None,
                        validate=False):
        # Bwahahahaha
        instance = cls.__new__(cls)
        instance.header = header
        instance.buffers = buffers
        instance.sender_address = sender_address
        if validate:
            instance.validate()
        return instance

    def __eq__(self, other):
        return bytes(self) == bytes(other)

    def __hash__(self):
        return hash(bytes(self))

    def __ne__(self, other):
        return bytes(self) != bytes(other)

    def __bytes__(self):
        # In general it's better to use self.buffers over bytes(self) because
        # The former does not copy large continuous memory arrays.
        raw_bytes = bytearray()
        # Concatenate buffers -- this copies data!
        for buf in self.buffers:
            raw_bytes += bytes(buf)
        # Trim 40-char string struct to payload_size.
        trimmed_bytes = raw_bytes[:self.header.payload_size]
        # Pad to multiple of 8.
        payload_bytes = trimmed_bytes.ljust(padded_len(trimmed_bytes), b'\x00')
        return bytes(self.header) + bytes(payload_bytes)

    def __repr__(self):
        signature = inspect.signature(type(self))
        parameters = (signature.parameters if type(self) is not Message
                      else ['header'])

        def safe_repr(arg):
            try:
                return repr(getattr(self, arg))
            except Exception as ex:
                return f'(repr: {ex})'

        d = [(arg, safe_repr(arg)) for arg in parameters]
        formatted_args = ", ".join(["{!s}={}".format(k, v)
                                    for k, v in d])
        return "{}({})".format(type(self).__name__, formatted_args)

    def __len__(self):
        return (ctypes.sizeof(self.header) +
                sum(bytelen(buf) for buf in self.buffers))

    @property
    def nbytes(self):
        return len(self)


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
    __slots__ = ()
    ID = 0
    HAS_PAYLOAD = False

    def __init__(self, priority, version):
        header = VersionRequestHeader(priority, version)
        super().__init__(header)

    priority = property(lambda self: self.header.data_type)
    version = property(lambda self: self.header.data_count)

    def validate(self):
        if not (0 <= self.priority < 100):
            raise ValidationError("Expecting 0 < priority < 100")


class VersionResponse(Message):
    """
    Respond to a client's initiation of a new connection or broadcast.

    Fields:

    .. attribute:: version

        The version of the Channel Access protocol.
    """
    __slots__ = ()
    ID = 0
    HAS_PAYLOAD = False

    def __init__(self, version):
        header = VersionResponseHeader(version)
        super().__init__(header)

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
    __slots__ = ()
    ID = 6
    HAS_PAYLOAD = True

    def __init__(self, name, cid, version, reply=NO_REPLY):
        size, payload = padded_string_payload(name)
        rec, _, field = name.partition('.')
        _len = len(rec)
        if _len > MAX_RECORD_LENGTH:
            raise CaprotoValueError('EPICS 3.14 imposes a {}-character limit '
                                    'on record names. The record {!r} is {} '
                                    'characters.'
                                    ''.format(MAX_RECORD_LENGTH, name, _len))
        header = SearchRequestHeader(size, reply, version, cid)
        super().__init__(header, b'', payload)

    @classmethod
    def from_wire(cls, header, *buffers, sender_address=None, validate=False):
        # Special-case to handle the fact that data_type holds whether or not
        # to reply to the request upon failure - this can cause part of the
        # payload to be interpreted as metadata in from_buffer (TODO: is there
        # a better place to special-case/fix this?)
        payload_buffer = b''.join(buffers)
        return cls.from_components(header, b'', payload_buffer,
                                   sender_address=sender_address,
                                   validate=validate)

    payload_size = property(lambda self: self.header.payload_size)
    reply = property(lambda self: self.header.data_type)
    version = property(lambda self: self.header.data_count)
    cid = property(lambda self: self.header.parameter1)
    name = property(lambda self: bytes(self.buffers[1]).rstrip(b'\x00').decode(STR_ENC))


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
    __slots__ = ()
    ID = 6
    HAS_PAYLOAD = True

    def __init__(self, port, ip, cid, version):
        if ip is None:
            ip = '255.255.255.255'

        header = SearchResponseHeader(data_type=port,
                                      sid=ipv4_to_int32(ip),
                                      cid=cid)
        # Pad a uint16 to fill 8 bytes.
        payload = bytes(DBR_INT(version)).ljust(8, b'\x00')
        super().__init__(header, payload)

    @classmethod
    def from_wire(cls, header, *buffers, sender_address=None, validate=False):
        # Special-case to handle the fact that data_type field is not the data
        # type. (It's used to hold the server port, unrelated to the payload.)
        return cls.from_components(header, *buffers,
                                   sender_address=sender_address,
                                   validate=validate)

    @property
    def ip(self):
        # for CA version >= 4.11
        return ipv4_from_int32(self.header.parameter1)

    @property
    def version(self):
        return DBR_INT.from_buffer(bytearray(self.buffers[0])[:2]).value

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
    __slots__ = ()
    ID = 14
    HAS_PAYLOAD = False

    def __init__(self, version, cid):
        header = NotFoundResponseHeader(DO_REPLY, version, cid)
        super().__init__(header)

    reply_flag = property(lambda self: self.header.data_type)
    version = property(lambda self: self.header.data_count)
    cid = property(lambda self: self.header.parameter1)


class EchoRequest(Message):
    """
    Request an :class:`EchoResponse`.

    This command has no fields.
    """
    __slots__ = ()
    ID = 23
    HAS_PAYLOAD = False

    def __init__(self):
        super().__init__(EchoRequestHeader())


class EchoResponse(Message):
    """
    Respond to an :class:`EchoRequest`.

    This command has no fields.
    """
    __slots__ = ()
    ID = 23
    HAS_PAYLOAD = False

    def __init__(self):
        super().__init__(EchoResponseHeader())


class Beacon(Message):
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
    __slots__ = ()
    ID = 13
    HAS_PAYLOAD = False

    def __init__(self, version, server_port, beacon_id, address):
        # TODO if address is 0, it should be replaced with the remote ip from
        # the udp packet
        header = BeaconHeader(version, server_port, beacon_id,
                              ipv4_to_int32(str(address)))
        super().__init__(header)

    version = property(lambda self: self.header.data_type)
    server_port = property(lambda self: self.header.data_count)
    beacon_id = property(lambda self: self.header.parameter1)
    address = property(lambda self: ipv4_from_int32(self.header.parameter2))


class RepeaterConfirmResponse(Message):
    """
    Confirm successful client registration with the Repeater.

    Fields:

    .. attribute:: repeater_address

        IP address of repeater (as a string).
    """
    __slots__ = ()
    ID = 17
    HAS_PAYLOAD = False

    def __init__(self, repeater_address):
        header = RepeaterConfirmResponseHeader(
            ipv4_to_int32(str(repeater_address)))
        super().__init__(header)

    @property
    def repeater_address(self):
        return ipv4_from_int32(self.header.parameter2)


class RepeaterRegisterRequest(Message):
    """
    Register a client with the Repeater.

    Fields:

    .. attribute:: client_address

        IP address of the client (as a string).
    """
    __slots__ = ()
    ID = 24
    HAS_PAYLOAD = False

    def __init__(self, client_address='0.0.0.0'):
        header = RepeaterRegisterRequestHeader(
            ipv4_to_int32(str(client_address)))
        super().__init__(header)

    @property
    def client_address(self):
        return ipv4_from_int32(self.header.parameter2)


class EventAddRequestPayload(ctypes.BigEndianStructure):
    '''
    Attributes
    ----------
    low : float
        Low delta value (deprecated)
    high : float
        High delta value (deprecated)
    to : float
        Period between samples (deprecated)
    mask : int
        Event selection mask


    '''
    _fields_ = [('low', float_t),
                ('high', float_t),
                ('to', float_t),
                ('mask', ushort_t),
                ('__padding', short_t),
                ]

    def __init__(self, low=0.0, high=0.0, to=0.0, mask=0):
        self.low = low
        self.high = high
        self.to = to
        self.mask = mask
        self.__padding = 0

    def __len__(self):
        return ctypes.sizeof(self)

    @property
    def nbytes(self):
        return len(self)


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
    __slots__ = ()
    ID = 1
    HAS_PAYLOAD = True

    def __init__(self, data_type, data_count, sid, subscriptionid, low,
                 high, to, mask):
        header = EventAddRequestHeader(data_type, data_count, sid,
                                       subscriptionid)
        payload = EventAddRequestPayload(low=low, high=high, to=to, mask=mask)
        super().__init__(header, payload)

    @classmethod
    def from_wire(cls, header, *buffers, sender_address=None,
                  validate=False):
        payload_struct = EventAddRequestPayload.from_buffer(buffers[0])
        return cls.from_components(header, payload_struct,
                                   sender_address=sender_address,
                                   validate=validate)

    @property
    def payload_struct(self):
        return EventAddRequestPayload.from_buffer(self.buffers[0])

    data_type = property(lambda self: ChannelType(self.header.data_type))
    data_count = property(lambda self: self.header.data_count)
    sid = property(lambda self: self.header.parameter1)
    subscriptionid = property(lambda self: self.header.parameter2)
    low = property(lambda self: self.payload_struct.low)
    high = property(lambda self: self.payload_struct.high)
    to = property(lambda self: self.payload_struct.to)
    mask = property(lambda self: self.payload_struct.mask)
    __padding = property(lambda self: self.payload_struct.__padding)


class EventAddResponse(Message):
    """
    Notify the client of a change in a Channel's value.

    Fields:

    .. attribute:: data

        data as built-in Python or numpy types

    .. attribute:: data_type

        Integer code of DBR type of reading.

    .. attribute:: data_count

        Number of elements in this reading.

    .. attribute:: sid

        Integer ID of this Channel designated by the server.

    .. attribute:: status

        As per Channel Access spec, 1 is success; 0 or >1 are various failures.

    .. attribute:: subscriptionid

        Echoing the :data:`subscriptionid` in the :class:`EventAddRequest`
    """
    __slots__ = ('__weakref__',)
    ID = 1
    HAS_PAYLOAD = True

    def __init__(self, data, data_type, data_count,
                 status, subscriptionid, *, metadata=None):
        size, *buffers = data_payload(data, metadata, data_type, data_count)
        status = ensure_eca_value(status)
        header = EventAddResponseHeader(size, data_type, data_count,
                                        status, subscriptionid)
        super().__init__(header, *buffers)

    payload_size = property(lambda self: self.header.payload_size)
    data_type = property(lambda self: ChannelType(self.header.data_type))
    data_count = property(lambda self: self.header.data_count)
    subscriptionid = property(lambda self: self.header.parameter2)

    @property
    def data(self):
        return extract_data(self.buffers[1], self.data_type, self.data_count)

    @property
    def metadata(self):
        return extract_metadata(self.buffers[0], self.data_type)

    @property
    def status(self):
        return eca_value_to_status[self.header.parameter1]

    @classmethod
    def from_wire(cls, header, payload_bytes, *, sender_address=None,
                  validate=False):
        # libca responds to EventCancelRequest with an
        # EventAddResponse with an empty payload.
        if not payload_bytes:
            return cls.from_components(header,
                                       sender_address=sender_address,
                                       validate=validate)
        payload = from_buffer(header.data_type, header.data_count,
                              payload_bytes)
        return cls.from_components(header, *payload,
                                   sender_address=sender_address,
                                   validate=validate)


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
    __slots__ = ()
    ID = 2
    HAS_PAYLOAD = False

    def __init__(self, data_type, sid, subscriptionid):
        header = EventCancelRequestHeader(data_type, 0, sid, subscriptionid)
        super().__init__(header)

    data_type = property(lambda self: ChannelType(self.header.data_type))
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
    __slots__ = ()
    ID = 2
    HAS_PAYLOAD = False

    def __init__(self, data_type, sid, subscriptionid, data_count):
        header = EventCancelResponseHeader(data_type, data_count, sid,
                                           subscriptionid)
        super().__init__(header)

    data_type = property(lambda self: ChannelType(self.header.data_type))
    data_count = property(lambda self: self.header.data_count)
    sid = property(lambda self: self.header.parameter1)
    subscriptionid = property(lambda self: self.header.parameter2)

    def validate(self):
        # special case because of weird ID
        if self.header.command != 1:
            raise ValidationError("A {} must have a header with "
                                  "header.command == 1, not {}."
                                  "".format(type(self), self.header.command))

        if any(len(buf) for buf in self.buffers):
            raise ValidationError("A {} must have no payload."
                                  "".format(type(self)))
        # do not call super()


class ReadRequest(Message):
    "Deprecated by Channel Access since 3.13. See :class:`ReadNotifyRequest`."
    __slots__ = ()
    ID = 3
    HAS_PAYLOAD = False

    def __init__(self, data_type, data_count, sid, ioid):
        header = ReadRequestHeader(data_type, data_count, sid, ioid)
        super().__init__(header, validate=False)

    data_type = property(lambda self: ChannelType(self.header.data_type))
    data_count = property(lambda self: self.header.data_count)
    sid = property(lambda self: self.header.parameter1)
    ioid = property(lambda self: self.header.parameter2)


class ReadResponse(Message):
    "Deprecated by Channel Access since 3.13. See :class:`ReadNotifyResponse`."
    __slots__ = ()
    ID = 3
    HAS_PAYLOAD = True

    @classmethod
    def from_wire(cls, header, payload_bytes, *, sender_address=None,
                  validate=False):
        warnings.warn("ReadResponse was deprecated by ChannelAccess in 3.13, "
                      "and is not well-supported by caproto. De-serialization "
                      "may not be correct.")
        return super().from_wire(header, payload_bytes,
                                 sender_address=sender_address,
                                 validate=validate)

    def __init__(self, data, data_type, data_count, sid, ioid, *,
                 metadata=None):
        warnings.warn("ReadResponse was deprecated by ChannelAccess in 3.13, "
                      "and is not well-supported by caproto. Serialization "
                      "may not be correct.")
        size, *buffers = data_payload(data, metadata, data_type, data_count)
        header = ReadResponseHeader(size, data_type, data_count, sid, ioid)
        super().__init__(header, *buffers)

    payload_size = property(lambda self: self.header.payload_size)
    data_type = property(lambda self: self.header.data_type)
    data_count = property(lambda self: self.header.data_count)
    sid = property(lambda self: self.header.parameter1)
    ioid = property(lambda self: self.header.parameter2)

    @property
    def data(self):
        return extract_data(self.buffers[1], self.data_type, self.data_count)

    @property
    def metadata(self):
        return extract_metadata(self.buffers[0], self.data_type)


class WriteRequest(Message):
    "Deprecated: See :class:`WriteNotifyRequest`."
    __slots__ = ()
    ID = 4
    HAS_PAYLOAD = True

    def __init__(self, data, data_type, data_count, sid, ioid, *,
                 metadata=None):
        size, *buffers = data_payload(data, metadata, data_type, data_count)
        header = WriteRequestHeader(size, data_type, data_count, sid, ioid)
        super().__init__(header, *buffers)

    payload_size = property(lambda self: self.header.payload_size)
    data_type = property(lambda self: ChannelType(self.header.data_type))
    data_count = property(lambda self: self.header.data_count)
    sid = property(lambda self: self.header.parameter1)
    ioid = property(lambda self: self.header.parameter2)

    @property
    def data(self):
        return extract_data(self.buffers[1], self.data_type, self.data_count)

    @property
    def metadata(self):
        return extract_metadata(self.buffers[0], self.data_type)

# There is no 'WriteResponse'. See WriteNotifyRequest/WriteNotifyResponse.


class EventsOffRequest(Message):
    """
    Temporarily turn off :class:`EventAddResponse` notifications.

    This command has no fields.
    """
    __slots__ = ()
    ID = 8
    HAS_PAYLOAD = False

    def __init__(self):
        super().__init__(EventsOffRequestHeader())


class EventsOnRequest(Message):
    """
    Restore :class:`EventAddResponse` notifications.

    This command has no fields.
    """
    __slots__ = ()
    ID = 9
    HAS_PAYLOAD = False

    def __init__(self):
        super().__init__(EventsOnRequestHeader())


class ReadSyncRequest(Message):
    "Deprecated by Channel Access: See :class:`ReadNotifyRequest`"
    __slots__ = ()
    ID = 10
    HAS_PAYLOAD = False

    def __init__(self):
        super().__init__(ReadSyncRequestHeader())


class ErrorResponse(Message):
    """
    Notify client of a server-side error, including some details about error.

    Fields:

    .. attribute:: cid

        Integer ID for this Channel designated by the client.

    .. attribute:: status

        As per Channel Access spec, 1 is success; 0 or >1 are various failures.

    """
    __slots__ = ()
    ID = 11
    HAS_PAYLOAD = True

    def __init__(self, original_request, cid, status, error_message):
        msg_size, msg_payload = padded_string_payload(error_message)
        req_bytes = bytes(original_request.header)

        size = len(req_bytes) + msg_size
        payload = req_bytes + msg_payload

        status = ensure_eca_value(status)
        header = ErrorResponseHeader(size, cid, status)
        super().__init__(header, b'', payload)

    payload_size = property(lambda self: self.header.payload_size)
    cid = property(lambda self: self.header.parameter1)

    @property
    def error_message(self):
        err_msg_bytes = bytearray(self.buffers[1][_MessageHeaderSize:])
        return err_msg_bytes

    @property
    def original_request(self):
        req_bytes = bytearray(self.buffers[1][:_MessageHeaderSize])
        return MessageHeader.from_buffer(req_bytes)

    @property
    def status(self):
        return eca_value_to_status[self.header.parameter2]

    @classmethod
    def from_wire(cls, header, payload_bytes, *, sender_address=None,
                  validate=False):
        return cls.from_components(header, b'', payload_bytes,
                                   sender_address=sender_address,
                                   validate=validate)


class ClearChannelRequest(Message):
    """
    Close a Channel.

    Fields:

    .. attribute:: cid

        Integer ID for this Channel designated by the client.

    .. attribute:: sid

        Integer ID for this Channel designated by the server.
    """
    __slots__ = ()
    ID = 12
    HAS_PAYLOAD = False

    def __init__(self, sid, cid):
        super().__init__(ClearChannelRequestHeader(sid, cid))

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
    __slots__ = ()
    ID = 12
    HAS_PAYLOAD = False

    def __init__(self, sid, cid):
        super().__init__(ClearChannelResponseHeader(sid, cid))

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
    __slots__ = ()
    ID = 15
    HAS_PAYLOAD = False

    def __init__(self, data_type, data_count, sid, ioid):
        header = ReadNotifyRequestHeader(data_type, data_count, sid, ioid)
        super().__init__(header)

    data_type = property(lambda self: ChannelType(self.header.data_type))
    data_count = property(lambda self: self.header.data_count)
    sid = property(lambda self: self.header.parameter1)
    ioid = property(lambda self: self.header.parameter2)


class ReadNotifyResponse(Message):
    """
    Request a fresh reading of a Channel.

    Fields:

    .. attribute:: data

        data as built-in Python or numpy types

    .. attribute:: metadata

        metadata in a ctypes.Structure

    .. attribute:: data_type

        Integer code of desired DBR type of readings.

    .. attribute:: data_count

        Desired number of elements per reading.

    .. attribute:: status

        As per Channel Access spec, 1 is success; 0 or >1 are various failures.

    .. attribute:: ioid

        Integer ID for I/O transaction, echoing :class:`ReadNotifyRequest`.

    """
    __slots__ = ()
    ID = 15
    HAS_PAYLOAD = True

    def __init__(self, data, data_type, data_count, status, ioid, *,
                 metadata=None):
        size, *buffers = data_payload(data, metadata, data_type, data_count)
        status = ensure_eca_value(status)
        header = ReadNotifyResponseHeader(size, data_type, data_count, status,
                                          ioid)
        super().__init__(header, *buffers)

    payload_size = property(lambda self: self.header.payload_size)

    @property
    def data(self):
        return extract_data(self.buffers[1], self.data_type, self.data_count)

    @property
    def metadata(self):
        return extract_metadata(self.buffers[0], self.data_type)

    @property
    def status(self):
        return eca_value_to_status[self.header.parameter1]

    data_type = property(lambda self: ChannelType(self.header.data_type))
    data_count = property(lambda self: self.header.data_count)
    ioid = property(lambda self: self.header.parameter2)


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
    __slots__ = ()
    ID = 18
    HAS_PAYLOAD = True

    def __init__(self, name, cid, version):
        size, payload = padded_string_payload(name)
        header = CreateChanRequestHeader(size, cid, version)
        super().__init__(header, b'', payload)

    @classmethod
    def from_wire(cls, header, payload_bytes, *, sender_address=None,
                  validate=False):
        """
        Use header.dbr_type to pack payload bytes into the right strucutre.

        Some Command types allocate a different meaning to the header.dbr_type
        field, and these override this method in their subclass.
        """

        return cls.from_components(header, b'', payload_bytes,
                                   sender_address=sender_address,
                                   validate=validate)

    payload_size = property(lambda self: self.header.payload_size)
    cid = property(lambda self: self.header.parameter1)
    version = property(lambda self: self.header.parameter2)
    name = property(lambda self: bytes(self.buffers[1]).rstrip(b'\x00').decode(STR_ENC))


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
    __slots__ = ()
    ID = 18
    HAS_PAYLOAD = False

    def __init__(self, data_type, data_count, cid, sid):
        header = CreateChanResponseHeader(data_type, data_count, cid, sid)
        super().__init__(header)

    data_type = property(lambda self: ChannelType(self.header.data_type))
    data_count = property(lambda self: self.header.data_count)
    cid = property(lambda self: self.header.parameter1)
    sid = property(lambda self: self.header.parameter2)


class WriteNotifyRequest(Message):
    """
    Write a value to a Channel.

    Fields:

    .. attribute:: data

        data as built-in Python or numpy types

    .. attribute:: metadata

        metadata in a ctypes.Structure

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
    __slots__ = ()
    ID = 19
    HAS_PAYLOAD = True

    def __init__(self, data, data_type, data_count, sid, ioid, *,
                 metadata=None):
        size, *buffers = data_payload(data, metadata, data_type, data_count)
        header = WriteNotifyRequestHeader(size, data_type, data_count, sid,
                                          ioid)
        super().__init__(header, *buffers)

    payload_size = property(lambda self: self.header.payload_size)
    data_type = property(lambda self: ChannelType(self.header.data_type))
    data_count = property(lambda self: self.header.data_count)
    sid = property(lambda self: self.header.parameter1)
    ioid = property(lambda self: self.header.parameter2)

    @property
    def data(self):
        return extract_data(self.buffers[1], self.data_type, self.data_count)

    @property
    def metadata(self):
        return extract_metadata(self.buffers[0], self.data_type)


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
    __slots__ = ()
    ID = 19
    HAS_PAYLOAD = False

    def __init__(self, data_type, data_count, status, ioid):
        status = ensure_eca_value(status)
        header = WriteNotifyResponseHeader(data_type, data_count, status, ioid)
        super().__init__(header)

    data_type = property(lambda self: ChannelType(self.header.data_type))
    data_count = property(lambda self: self.header.data_count)
    ioid = property(lambda self: self.header.parameter2)

    @property
    def status(self):
        return eca_value_to_status[self.header.parameter1]


class ClientNameRequest(Message):
    """
    Tell the server the client name (i.e., user name) of the client.

    Fields:

    .. attribute:: name

        Client name.
    """
    __slots__ = ()
    ID = 20
    HAS_PAYLOAD = True

    def __init__(self, name):
        size, payload = padded_string_payload(name)
        header = ClientNameRequestHeader(size)
        super().__init__(header, b'', payload)

    @classmethod
    def from_wire(cls, header, payload_bytes, *, sender_address=None,
                  validate=False):
        """
        Use header.dbr_type to pack payload bytes into the right strucutre.

        Some Command types allocate a different meaning to the header.dbr_type
        field, and these override this method in their subclass.
        """
        return cls.from_components(header, b'', payload_bytes,
                                   sender_address=sender_address,
                                   validate=validate)

    payload_size = property(lambda self: self.header.payload_size)
    name = property(lambda self: bytes(self.buffers[1]).rstrip(b'\x00').decode(STR_ENC))


class HostNameRequest(Message):
    """
    Tell the server the host name of the client.

    Fields:

    .. attribute:: name

        Host name.
    """
    __slots__ = ()
    ID = 21
    HAS_PAYLOAD = True

    def __init__(self, name):
        size, payload = padded_string_payload(name)
        header = HostNameRequestHeader(size)
        super().__init__(header, b'', payload)

    payload_size = property(lambda self: self.header.payload_size)
    name = property(lambda self: bytes(self.buffers[1]).rstrip(b'\x00').decode(STR_ENC))

    @classmethod
    def from_wire(cls, header, payload_bytes, *, sender_address=None,
                  validate=False):
        return cls.from_components(header, b'', payload_bytes,
                                   sender_address=sender_address,
                                   validate=validate)


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
    __slots__ = ()
    ID = 22
    HAS_PAYLOAD = False

    def __init__(self, cid, access_rights):
        header = AccessRightsResponseHeader(cid, access_rights)
        super().__init__(header)

    cid = property(lambda self: self.header.parameter1)
    access_rights = property(lambda self: AccessRights(self.header.parameter2))


class CreateChFailResponse(Message):
    """
    Notify the client that channel creation failed.

    Fields:

    .. attribute:: cid

        Integer ID for this Channel designated by the client.
    """
    __slots__ = ()
    ID = 26
    HAS_PAYLOAD = False

    def __init__(self, cid):
        super().__init__(CreateChFailResponseHeader(cid))

    cid = property(lambda self: self.header.parameter1)


class ServerDisconnResponse(Message):
    """
    Notify the client that server will disconnect from this Channel.

    Fields:

    .. attribute:: cid

        Integer ID for this Channel designated by the client.
    """
    __slots__ = ()
    ID = 27
    HAS_PAYLOAD = False

    def __init__(self, cid):
        super().__init__(ServerDisconnResponseHeader(cid))

    cid = property(lambda self: self.header.parameter1)
