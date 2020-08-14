import ctypes
import dataclasses
import enum
import functools
import logging
import typing
from typing import Optional, Tuple, Union

from . import _core as core
from ._core import (BIG_ENDIAN, LITTLE_ENDIAN, Deserialized, FieldArrayType,
                    FieldType, SegmentDeserialized, UserFacingEndian)
from ._data import Data, DataWithBitSet, FieldDescAndData, PVRequest
from ._dataclass import array_of, pva_dataclass
from ._fields import BitSet, CacheContext, FieldDesc, SimpleField
from ._utils import (SERVER, ChannelLifeCycle, Role, ip_to_ubyte_array,
                     ubyte_array_to_ip)

NullCache = CacheContext()


@pva_dataclass
class ChannelWithID:
    """
    A channel and ID pair, used for searching and channel creation.
    """
    id: FieldType.int32
    channel_name: FieldType.string


serialization_logger = logging.getLogger('caproto.pva.serialization')


class _MessageField:
    def __post_init__(self):
        if isinstance(self.type, FieldType):
            # Can use a basic FieldType such as FieldType.string
            self.type = SimpleField(name=self.name,
                                    field_type=self.type,
                                    array_type=FieldArrayType.scalar,
                                    size=1,
                                    )
        elif hasattr(self.type, '_pva_struct_'):
            # Can use a pva_struct-wrapped dataclass
            self.type = self.type._pva_struct_

        # With the end result of `type` being a SimpleField or StructuredField


@dataclasses.dataclass
class RequiredField(_MessageField):
    name: str
    type: ...


@dataclasses.dataclass
class NonstandardArrayField(RequiredField):
    count_attr: str = None


@dataclasses.dataclass
class OptionalField(_MessageField):
    name: str
    type: ...
    stop: ...
    condition: typing.Optional[callable]


class QOSFlags(enum.IntFlag):
    'First 7 bits of QOS settings are the priority (see QOS_PRIORITY_MASK)'
    unused_7 = 1 << 7
    low_latency = 1 << 8
    throughput_priority = 1 << 9
    enable_compression = 1 << 10
    unused_11 = 1 << 11
    unused_12 = 1 << 12
    unused_13 = 1 << 13
    unused_14 = 1 << 14
    unused_15 = 1 << 15

    @classmethod
    def encode(cls, priority, flags):
        return (core.QOS_PRIORITY_MASK & priority) | flags

    @classmethod
    def decode(cls, priority_word):
        priority = (priority_word & core.QOS_PRIORITY_MASK)
        flags = QOSFlags(priority_word & ~core.QOS_PRIORITY_MASK)
        return (priority, flags)


class ApplicationCommands(enum.IntEnum):
    """
    Application messages. These are the requests and their responses.
    """
    BEACON = 0
    CONNECTION_VALIDATION = 1
    ECHO = 2
    SEARCH_REQUEST = 3
    SEARCH_RESPONSE = 4
    AUTHNZ = 5
    ACL_CHANGE = 6
    CREATE_CHANNEL = 7
    DESTROY_CHANNEL = 8
    CONNECTION_VALIDATED = 9
    GET = 10
    PUT = 11
    PUT_GET = 12
    MONITOR = 13
    ARRAY = 14
    DESTROY_REQUEST = 15
    PROCESS = 16
    GET_FIELD = 17
    MESSAGE = 18
    RPC = 20
    CANCEL_REQUEST = 21
    ORIGIN_TAG = 22

    # These message codes are never used, and considered deprecated.
    MULTIPLE_DATA = 19


class ControlCommands(enum.Enum):
    """
    Control messages. These include flow control and have no payload.
    """
    # NOTE: this is not set as an IntEnum to avoid clashing with
    # ApplicationCommands in dictionaries.
    SET_MARKER = 0
    ACK_MARKER = 1
    SET_ENDIANESS = 2
    ECHO_REQUEST = 3
    ECHO_RESPONSE = 4


class SearchFlags(enum.IntFlag):
    # 0-bit for replyRequired, 7-th bit for "sent as unicast" (1)/"sent as
    # broadcast/multicast" (0)
    reply_required = 0b00000001
    unicast = 0b10000000
    broadcast = 0b00000000


class EndianSetting(enum.IntEnum):
    use_server_byte_order = 0x00000000
    use_message_byte_order = 0xffffffff


class MessageFlags(enum.IntFlag):
    APP_MESSAGE = 0b0000_0000_0000
    CONTROL_MESSAGE = 0b0000_0000_0001

    UNSEGMENTED = 0b0000_0000_0000
    FIRST = 0b0000_0001_0000
    LAST = 0b0000_0010_0000
    MIDDLE = 0b0000_0011_0000

    FROM_CLIENT = 0b0000_0000_0000
    FROM_SERVER = 0b0000_0100_0000

    LITTLE_ENDIAN = 0b0000_0000_0000
    BIG_ENDIAN = 0b0000_1000_0000

    @property
    def is_segmented(self):
        return any(item in self
                   for item in (self.FIRST, self.LAST, self.MIDDLE)
                   )


class Subcommands(enum.IntEnum):
    # Default behavior
    DEFAULT = 0x00
    # Require reply (acknowledgment for reliable operation)
    REPLY_REQUIRED = 0x01
    # Best-effort option (no reply)
    BEST_EFFORT = 0x02
    PROCESS = 0x04
    INIT = 0x08
    DESTROY = 0x10
    # Share data option
    SHARE = 0x20
    GET = 0x40
    GET_PUT = 0x80


class MonitorSubcommands(enum.IntFlag):
    INIT = 0x08
    DEFAULT = 0x00
    PIPELINE = 0x80
    START = 0x44
    STOP = 0x04
    DESTROY = 0x10


class StatusType(enum.IntEnum):
    OK = -1
    OK_VERBOSE = 0
    WARNING = 1
    ERROR = 2
    FATAL = 3


class OptionalStopMarker(enum.IntEnum):
    stop = True
    continue_ = False


success_status_types = {
    StatusType.OK,
    StatusType.OK_VERBOSE,
    StatusType.WARNING,
}

default_pvrequest = 'record[]field()'


class MessageBase:
    """
    Base class for all Messages.
    """
    _pack_ = 1
    _additional_fields_ = None
    _subcommand_fields_ = None

    def __repr__(self):
        info = ', '.join('{}={!r}'.format(field, getattr(self, field))
                         for field, type_ in self._fields_)
        return '{}({})'.format(type(self).__name__, info)

    @classmethod
    def _get_additional_fields(cls, subcommand=None):
        if (cls._additional_fields_ is None and
                cls._subcommand_fields_ is None):
            return []

        fields = cls._additional_fields_
        if cls._subcommand_fields_ and subcommand is not None:
            try:
                return fields + cls._subcommand_fields_[subcommand]
            except KeyError:
                raise ValueError(f'Invalid (or currently unhandled) subcommand'
                                 f' for class {cls}: {subcommand}') from None
        return fields

    @property
    def has_subcommand(self):
        return ('subcommand', ctypes.c_byte) in self._fields_

    def serialize(self, *, default_pvrequest=default_pvrequest,
                  cache=NullCache):
        additional_fields = self._get_additional_fields(
            subcommand=self.subcommand if self.has_subcommand else None
        )
        if not additional_fields:
            # Without additional fields, this is just a ctypes.Structure
            return bytes(self)

        endian = self._ENDIAN

        # (1) serialize the ctypes.Structure _fields_ first
        buf = [bytes(self)]

        # (2) move onto the "additional fields" which are not as easily
        # serializable:
        for field_info in additional_fields:
            if isinstance(field_info, OptionalField):
                if field_info.condition is not None:
                    if not field_info.condition(self, buf):
                        break

            value = getattr(self, field_info.name)
            if isinstance(field_info, NonstandardArrayField):
                count = getattr(self, field_info.count_attr)
            else:
                value = [value]
                count = 1

            assert len(value) == count

            serialize = functools.partial(
                Data.serialize, field=field_info.type, endian=endian, cache=cache,
                bitset=None
            )

            for v in value:
                buf.extend(serialize(value=v))

        # (3) end result is the sum of all buffers
        return b''.join(buf)

    @classmethod
    def deserialize(cls, buf, *, cache=NullCache, header=None):
        base_size = ctypes.sizeof(cls)
        buflen = len(buf) - base_size
        buf = memoryview(buf)
        msg = cls.from_buffer(buf[:base_size])

        offset = base_size
        buf = buf[offset:]

        additional_fields = cls._get_additional_fields(
            subcommand=msg.subcommand if msg.has_subcommand else None
        )

        if not additional_fields:
            # Without additional fields, this is just a ctypes.Structure
            return Deserialized(data=msg, buffer=buf, offset=offset)

        serialization_logger.debug(
            'deserializing %s base_size=%s subcommand=%s payload=%s', cls,
            base_size, getattr(msg, 'subcommand', None), bytes(buf))

        for field_info in additional_fields:
            if isinstance(field_info, OptionalField):
                if not buflen:
                    # No bytes remaining, and any additional fields are
                    # optional.
                    break
                if field_info.condition is not None:
                    if not field_info.condition(msg, buf):
                        if field_info.stop == OptionalStopMarker.stop:
                            break
                        else:
                            continue

            field_interface = field_info.type

            if field_interface in (Data, DataWithBitSet):
                try:
                    field_interface = cache.ioid_interfaces[msg.ioid]
                except KeyError:
                    raise RuntimeError(
                        f'Field description unavailable for Data in '
                        f'{field_info.name!r} (ioid={msg.ioid})'
                    ) from None
                data_cls = field_info.type
            else:
                data_cls = Data

            is_nonstandard_array = isinstance(field_info,
                                              NonstandardArrayField)

            deserialize = functools.partial(
                data_cls.deserialize, field=field_interface,
                endian=cls._ENDIAN, cache=cache, bitset=None,
            )

            if is_nonstandard_array:
                count = getattr(msg, field_info.count_attr)
                values = []
                for i in range(count):
                    value, buf, off = deserialize(data=buf)
                    offset += off
                    buflen -= off
                    values.append(value)

                setattr(msg, field_info.name, values)
                serialization_logger.debug('%s (%s) = %s', field_info.name,
                                           field_info.type, values)
            else:
                value, buf, off = deserialize(data=buf)
                offset += off
                buflen -= off
                setattr(msg, field_info.name, value)
                serialization_logger.debug('%s (%s) = %s', field_info.name,
                                           field_info.type, value)

        # Attach the header for future reference
        msg.header = header
        return Deserialized(data=msg, buffer=buf, offset=offset)


class ExtendedMessageBase(MessageBase):
    '''
    Additional fields in _additional_fields_ with pva-specific types, and
    optional entries based on certain conditions
    '''
    _fields_ = []

    def __repr__(self):
        def name_and_value(name):
            if name.startswith('_'):
                prop_name = name.lstrip('_')
                if hasattr(type(self), prop_name):
                    return (prop_name, getattr(self, prop_name))
            return name, getattr(self, name)

        info = ', '.join('{}={!r}'.format(*name_and_value(field))
                         for field, type_ in self._fields_)
        if not self._additional_fields_:
            return '{}({})'.format(type(self).__name__, info)

        if info:
            info += ', '

        info += ', '.join('{}={!r}'.format(*name_and_value(fi.name))
                          for fi in self._additional_fields_)
        return '{}({})'.format(type(self).__name__, info)


def _success_condition(msg, buf):
    """
    Continue if-and-only-if the status message indicates success.
    """
    return (msg.status_type in success_status_types)


def SuccessField(name: str,
                 type,
                 stop=OptionalStopMarker.stop) -> OptionalField:
    'Return an OptionalField which requires the message status be successful'
    return OptionalField(name, type, stop, _success_condition)


def _make_endian(cls: type, endian: core.UserFacingEndian) -> type:
    '''Creates big- or little-endian versions of a Structure

    Checks for _additional_fields from ExtendedMessageBase
    Adds _ENDIAN attr for easy struct.unpacking = big (>) or little (<)
    '''

    if endian == LITTLE_ENDIAN:
        endian_base = ctypes.LittleEndianStructure
        suffix = 'LE'
    else:
        endian_base = ctypes.BigEndianStructure
        suffix = 'BE'

    name = cls.__name__.lstrip('_') + suffix
    endian_cls = type(name, (cls, endian_base),
                      {'_fields_': cls._fields_})

    if endian_cls._additional_fields_:
        for field_info in endian_cls._additional_fields_:
            setattr(endian_cls, field_info.name, None)

    cls._ENDIAN = None
    endian_cls._ENDIAN = (LITTLE_ENDIAN
                          if endian_base is ctypes.LittleEndianStructure
                          else BIG_ENDIAN)
    return endian_cls


class MessageHeader(MessageBase):
    _fields_ = [
        ('magic', ctypes.c_ubyte),
        ('version', ctypes.c_ubyte),
        ('_flags', ctypes.c_ubyte),
        ('message_command', ctypes.c_ubyte),
        ('payload_size', ctypes.c_uint),
    ]

    def __init__(self, *, flags: MessageFlags,
                 command: typing.Union[ApplicationCommands, ControlCommands],
                 payload_size: int):
        self.magic = 0xca
        self.version = 1
        self._flags = flags
        self.message_command = command
        self.payload_size = payload_size

    @property
    def flags(self):
        return MessageFlags(self._flags)

    @property
    def valid(self):
        return self.magic == 0xca

    @property
    def byte_order(self):
        'Byte order/endianness of message'
        return (BIG_ENDIAN
                if bool(self._flags & MessageFlags.BIG_ENDIAN)
                else LITTLE_ENDIAN)

    def get_message(self, direction: MessageFlags, *,
                    use_fixed_byte_order=None):
        byte_order = (use_fixed_byte_order
                      if use_fixed_byte_order is not None
                      else self.byte_order)
        flags = self.flags

        if MessageFlags.CONTROL_MESSAGE in flags:
            command = ControlCommands(self.message_command)
        else:
            command = ApplicationCommands(self.message_command)

        try:
            message_group = messages[(byte_order, direction)]
            return message_group[command]
        except KeyError as ex:
            raise KeyError(
                f'{ex} where flags={flags} and command={command!r}'
            )


MessageHeaderLE = _make_endian(MessageHeader, LITTLE_ENDIAN)
MessageHeaderBE = _make_endian(MessageHeader, BIG_ENDIAN)
_MessageHeaderSize = ctypes.sizeof(MessageHeaderLE)


class _StatusBase:
    """
    Mixin class that can be used to provide a common interface for messages
    with status responses.

    NOTE
    ----
    It's up to the struct to place '_status_type' in its _fields_, as its exact
    location may change based on the message.
    """
    _status_type: ctypes.c_byte

    _additional_fields_ = [
        OptionalField('message', FieldType.string, OptionalStopMarker.continue_,
                      lambda msg, buf: msg.status_type != StatusType.OK),
        OptionalField('call_tree', FieldType.string, OptionalStopMarker.continue_,
                      lambda msg, buf: msg.status_type != StatusType.OK),
    ]

    @property
    def is_successful(self) -> bool:
        return self.status_type in success_status_types

    @property
    def has_message(self) -> bool:
        return self.status_type != StatusType.OK

    @property
    def status_type(self):
        return StatusType(self._status_type)


class Status(_StatusBase, ExtendedMessageBase):
    _fields_ = [('_status_type', ctypes.c_byte)]


class BeaconMessage(ExtendedMessageBase):
    """
    A beacon message.

    Notes
    -----
    Servers MUST broadcast or multicast beacons over UDP. Beacons are be used
    to announce the appearance and continued presense of servers. Clients may
    use Beacons to detect when new servers appear, and may use this information
    to more quickly retry unanswered CMD_SEARCH messages.
    """
    ID = ApplicationCommands.BEACON
    # FieldDesc serverStatusIF;
    # [if serverStatusIF != NULL_TYPE_CODE] PVField serverStatus;
    _fields_ = [
        ('guid', ctypes.c_ubyte * 12),
        ('flags', ctypes.c_ubyte),
        ('beacon_sequence_id', ctypes.c_ubyte),
        ('change_count', ctypes.c_uint16),  # TODO_DOCS
        ('server_address', ctypes.c_ubyte * 16),
        ('server_port', ctypes.c_uint16),
    ]

    _additional_fields_ = [
        RequiredField('protocol', FieldType.string),
        RequiredField('server_status', FieldDescAndData),
    ]


# NOTE: the following control messages do not have any elements which require
# an endian setting. They are arbitrarily set to little-endian here for all
# platforms.
class SetMarker(MessageHeaderLE):
    """
    A control command which sets a marker for total bytes sent.

    Notes
    -----
    (from pva documentation)
    Note that this message type has so far not been used.

    The payload size field holds the value of the total bytes sent. The client
    SHOULD respond with an acknowledgment control message (0x01) as soon as
    possible.
    """
    ID = ControlCommands.SET_MARKER


class AcknowledgeMarker(MessageHeaderLE):
    """
    A control command to acknowledge the total bytes received.

    Notes
    -----
    (from pva documentation)
    Note that this message type has so far not been used.

    The payload size field holds the acknowledge value of total bytes received.
    This must match the previously received marked value as described above.
    """
    ID = ControlCommands.ACK_MARKER


class SetByteOrder(MessageHeaderLE):
    """
    An indicator to set the byte order of future messages.

    Notes
    -----
    The 7-th bit of a header flags field indicates the server's selected byte
    order for the connection on which this message was received. Client MUST
    encode all the messages sent via this connection using this byte order.
    """
    ID = ControlCommands.SET_ENDIANESS
    # uses EndianSetting in header payload size

    def __init__(self, endian_setting):
        assert endian_setting in (EndianSetting.use_message_byte_order,
                                  EndianSetting.use_server_byte_order)
        self.message_type = 0
        self.payload_size = endian_setting

    @property
    def byte_order_setting(self):
        return EndianSetting(self.payload_size)


class EchoRequest(MessageHeaderLE):
    """
    A request to echo the payload.

    Notes
    -----
    Diagnostic/test echo message. The receiver should respond with an Echo
    response (0x04) message with the same payload size field value.

    In protocol version v1:
    * v1 servers reply to 'Echo' with empty payload.
    * v1 clients never send 'Echo'.
    * v1 peers never timeout inactive TCP connections.

    In protocol version v2:
    * v2 clients must send 'Echo' more often than $EPICS_PVA_CONN_TMO seconds.
    The recommended interval is half of $EPICS_PVA_CONN_TMO (default 15 sec.).
    """
    ID = ControlCommands.ECHO_REQUEST


class EchoResponse(MessageHeaderLE):
    """
    A response to an echo request.

    Notes
    -----
    The payload size field contains the same value as in the request message.

    In protocol version v2:
    * v2 server's 'Echo' reply must include the request payload.
    * v2 peers must close TCP connections when no data has been received in
    $EPICS_PVA_CONN_TMO seconds (default 30 sec.).
    """
    ID = ControlCommands.ECHO_REQUEST


class ConnectionValidationRequest(ExtendedMessageBase):
    """
    A validation request from the server.

    Notes
    -----
    A ConnectionValidationRequest message MUST be the first application message
    sent from the server to a client when a TCP/IP connection is established
    (after a Set byte order Control message). The client MUST NOT send any
    messages on the connection until it has received a connection validation
    message from the server.

    The server lists the support authentication methods. Currently supported
    are "anonymous" and "ca". In the ConnectionValidationResponse, the client
    selects one of these. For "anonymous", no further detail is required. For
    "ca", a structure with string elements "user" and "host" needs to follow.
    """
    ID = ApplicationCommands.CONNECTION_VALIDATION

    _fields_ = [
        ('server_buffer_size', ctypes.c_int32),
        ('server_registry_size', ctypes.c_int16),
    ]

    _additional_fields_ = [
        RequiredField('auth_nz', array_of(FieldType.string)),
    ]


class ConnectionValidationResponse(ExtendedMessageBase):
    """
    A client's connection validation response message.

    Notes
    -----
    Each Quality of Service (QoS) parameter value REQUIRES a separate TCP/IP
    connection. If the Low-latency priority bit is set, this indicates clients
    should attempt to minimize latency if they have the capacity to do so. If
    the Throughput priority bit is set, this indicates a client similarly
    should attempt to maximize throughput. How this is achieved is
    implementation defined. The Compression bit enables compression for the
    connection (Which compression? From which support layer?). A matter for a
    future version of the specification should be whether a streaming mode
    algorithm should be specified.
    """
    ID = ApplicationCommands.CONNECTION_VALIDATION

    _fields_ = [
        ('client_buffer_size', ctypes.c_int32),
        ('client_registry_size', ctypes.c_int16),
        ('connection_qos', ctypes.c_int16),
    ]

    _additional_fields_ = [
        RequiredField('auth_nz', FieldType.string),
        OptionalField('user', FieldType.string,
                      condition=lambda msg, buf: msg.auth_nz == 'ca',
                      stop=OptionalStopMarker.stop),
        OptionalField('host', FieldType.string,
                      condition=lambda msg, buf: msg.auth_nz == 'ca',
                      stop=OptionalStopMarker.stop),
    ]


class Echo(ExtendedMessageBase):
    """
    A TCP Echo request/response.

    Notes
    -----
    An Echo diagnostic message is usually sent to check if TCP/IP connection is
    still valid.
    """
    ID = ApplicationCommands.ECHO
    _additional_fields_ = [
        RequiredField('payload', array_of(FieldType.byte)),
    ]


class ConnectionValidatedResponse(Status):
    """Validation results - success depends on the status."""
    ID = ApplicationCommands.CONNECTION_VALIDATED


class SearchRequest(ExtendedMessageBase):
    """
    A search request for PVs by name.

    Notes
    -----
    A channel "search request" message SHOULD be sent over UDP/IP, however UDP
    congestion control SHOULD be implemented in this case. A server MUST accept
    this message also over TCP/IP.

    Note that the element count for protocol uses the normal size encoding,
    i.e. unsigned 8-bit integer 1 for one supported protocol. The element count
    for the channels array, however, always uses an unsigned 16 bit integer.
    This choice is based on the reference implementations which append channel
    names to the network buffer and update the count. With normal size
    encoding, an increment to 254 would change the count from requiring 1 byte
    to 3 bytes, shifting already added channel names.

    In caproto-pva, this becomes the :class:`NonstandardArrayField`.
    """
    ID = ApplicationCommands.SEARCH_REQUEST

    _fields_ = [
        ('sequence_id', ctypes.c_int32),
        ('flags', ctypes.c_ubyte),
        ('reserved', ctypes.c_ubyte * 3),
        ('_response_address', ctypes.c_ubyte * 16),
        ('response_port', ctypes.c_uint16),
    ]

    _additional_fields_ = [
        RequiredField('protocols', array_of(FieldType.string)),
        # TODO custom handling as this expects a SHORT count before the number
        # of arrays.
        # if it were implemented as expected, this would be all that's
        # necessary:
        # RequiredField('channels', 'channel_with_id[]'),
        RequiredField('channel_count', FieldType.uint16),
        NonstandardArrayField('channels', ChannelWithID,
                              count_attr='channel_count'),
    ]

    @property
    def response_address(self):
        return ubyte_array_to_ip(self._response_address)

    @response_address.setter
    def response_address(self, value):
        self._response_address = ip_to_ubyte_array(value)

    def serialize(self, *args, **kwargs):
        self.channel_count = len(self.channels)
        return super().serialize(*args, **kwargs)


def _array_property(name, doc):
    'Array property to make handling ctypes arrays a bit easier'
    def fget(self):
        return bytes(getattr(self, name))

    def fset(self, value):
        item = getattr(self, name)
        item[:] = value

    return property(fget, fset, doc=doc)


class SearchResponse(ExtendedMessageBase):
    """
    A response to a SearchRequest.

    Notes
    -----
    A client MUST examine the protocol member field to verify it supports the
    given exchange protocol; if not, the search response is ignored.

    The count for the number of searchInstanceIDs elements is always sent as an
    unsigned 16 bit integer, not using the default size encoding.
    """
    ID = ApplicationCommands.SEARCH_RESPONSE

    _fields_ = [
        ('_guid', ctypes.c_ubyte * 12),
        ('sequence_id', ctypes.c_int32),
        ('_server_address', ctypes.c_ubyte * 16),
        ('server_port', ctypes.c_uint16),
    ]

    _additional_fields_ = [
        RequiredField('protocol', FieldType.string),
        # TODO_DOCS found is not 'int' but 'byte' (uint8 or int8?)
        RequiredField('found', FieldType.uint8),
        # TODO_DOCS search_instance_ids array is prefixed by a short length
        #  i.e., a nonstandard array serialization format
        # RequiredField('search_instance_ids', array_of(FieldType.int32)),
        RequiredField('search_count', FieldType.int16),
        NonstandardArrayField('search_instance_ids', FieldType.int32,
                              count_attr='search_count'),
    ]

    guid = _array_property('_guid', 'GUID for server')

    @property
    def server_address(self):
        return ubyte_array_to_ip(self._server_address)

    @server_address.setter
    def server_address(self, value):
        self._server_address = ip_to_ubyte_array(value)


class CreateChannelRequest(ExtendedMessageBase):
    """
    A client's request to create a channel.

    Notes
    -----
    A channel provides a communication path between a client and a server
    hosted "process variable."  Each channel instance MUST be bound only to one
    connection.

    The CreateChannelRequest.channels array starts with a short count, not
    using the normal size encoding. Current PVA server implementations only
    support requests for creating a single channel, i.e. the count must be 1.

    """
    ID = ApplicationCommands.CREATE_CHANNEL

    _additional_fields_ = [
        RequiredField('count', FieldType.uint16),
        NonstandardArrayField('channels', ChannelWithID, count_attr='count'),
    ]


class CreateChannelResponse(_StatusBase, ExtendedMessageBase):
    """
    A server's response to a CreateChannelRequest.

    Notes
    -----
    A server MUST store the client ChannelID and respond with its value in a
    destroyChannelMessage when a channel destroy request is requested, see
    below. A client uses the serverChannelID value for all subsequent requests
    on the channel. Agents SHOULD NOT make any assumptions about how given IDs
    are generated. IDs MUST be unique within a connection and MAY be recycled
    after a channel is disconnected.
    """
    ID = ApplicationCommands.CREATE_CHANNEL

    _fields_ = [('client_chid', ctypes.c_int32),
                ('server_chid', ctypes.c_int32),
                ('_status_type', ctypes.c_byte),
                ]
    _additional_fields_ = Status._additional_fields_ + [
        # TODO access rights aren't sent, even if status_type is OK
        SuccessField('access_rights', FieldType.int16),
    ]


class ChannelDestroyRequest(MessageBase):
    """
    Request to destroy a previously-created channel.

    Notes
    -----
    A "destroy channel" message is sent by a client to a server to destroy a
    channel that was previously created (with a create channel message).

    A server may also send this message to the client when the channel is no
    longer available. Examples include a PVA gateway that sends this message
    from its server side when it lost a channel on its client side.
    """
    # TODO: caproto-pva does not allow for a server to send this at the moment
    ID = ApplicationCommands.DESTROY_CHANNEL
    _fields_ = [('client_chid', ctypes.c_int32),
                ('server_chid', ctypes.c_int32),
                ]


class ChannelDestroyResponse(_StatusBase, ExtendedMessageBase):
    """
    A response to a destroy request.

    Notes
    -----
    If the request (clientChannelID, serverChannelID) pair does not match, the
    server MUST respond with an error status. The server MAY break its response
    into several messages.

    A server MUST send this message to a client to notify the client about
    server-side initiated channel destruction. Subsequently, a client MUST mark
    such channels as disconnected. If the client's interest in the process
    variable continues, it MUST start sending search request messages for the
    channel.
    """
    ID = ApplicationCommands.DESTROY_CHANNEL

    _fields_ = [('client_chid', ctypes.c_int32),
                ('server_chid', ctypes.c_int32),
                ('_status_type', ctypes.c_byte),
                ]


class ChannelGetRequest(ExtendedMessageBase):
    """
    A "channel get" set of messages are used to retrieve (get) data from the channel.
    """
    ID = ApplicationCommands.GET

    _fields_ = [
        ('server_chid', ctypes.c_int32),
        ('ioid', ctypes.c_int32),
        ('subcommand', ctypes.c_byte),
    ]

    _additional_fields_ = []
    _subcommand_fields_ = {
        Subcommands.INIT: [
            RequiredField('pv_request', PVRequest),
        ],
        Subcommands.GET: [],
        Subcommands.DESTROY: [],
    }


class ChannelGetResponse(_StatusBase, ExtendedMessageBase):
    """
    A response to a ChannelGetRequest.
    """
    ID = ApplicationCommands.GET

    _fields_ = [
        ('ioid', ctypes.c_int32),
        ('subcommand', ctypes.c_byte),
        ('_status_type', ctypes.c_byte),
    ]
    _subcommand_fields_ = {
        Subcommands.INIT: [
            SuccessField('pv_structure_if', FieldDesc),
        ],
        Subcommands.GET: [
            SuccessField('pv_data', DataWithBitSet,
                         # `pv_structure_if` is tracked by ioid
                         ),
        ],
        Subcommands.DESTROY: [],
    }


class ChannelFieldInfoRequest(ExtendedMessageBase):
    """
    Used to retrieve a channel's type introspection data, i.e., a :class:`FieldDesc`.
    """
    ID = ApplicationCommands.GET_FIELD

    _fields_ = [('server_chid', ctypes.c_int32),
                ('ioid', ctypes.c_int32),
                ]
    _additional_fields_ = [
        RequiredField('sub_field_name', FieldType.string),
    ]


class ChannelFieldInfoResponse(_StatusBase, ExtendedMessageBase):
    """
    A response to a :class:`ChannelFieldInfoRequest`.
    """
    ID = ApplicationCommands.GET_FIELD

    _fields_ = [('ioid', ctypes.c_int32),
                ('_status_type', ctypes.c_byte),
                ]
    _additional_fields_ = Status._additional_fields_ + [
        SuccessField('field_if', FieldDesc),
    ]


class ChannelPutRequest(ExtendedMessageBase):
    """
    A "channel put" message is used to set (put) data to the channel.

    After a put request is successfully initialized, the client can issue
    actual put request(s) on the channel.

    Notes
    -----
    A "GET_PUT" subcommand here retrieves the remote put structure. This MAY be
    used by user applications to show data that was set the last time by the
    application.
    """
    ID = ApplicationCommands.PUT

    _fields_ = [('server_chid', ctypes.c_int32),
                ('ioid', ctypes.c_int32),
                ('subcommand', ctypes.c_byte),
                ]
    _additional_fields_ = []
    _subcommand_fields_ = {
        Subcommands.INIT: [
            RequiredField('pv_request', PVRequest),
        ],
        Subcommands.GET: [
            # Query what the last put request was
            RequiredField('pv_put_data', Data),
        ],
        Subcommands.DEFAULT: [
            # Perform the put
            RequiredField('put_data', DataWithBitSet),
        ],
        # TODO mask DESTROY | DEFAULT
        Subcommands.DESTROY: [],
    }


class ChannelPutResponse(_StatusBase, ExtendedMessageBase):
    """
    A response to a :class:`ChannelPutRequest`.
    """
    ID = ApplicationCommands.PUT

    _fields_ = [('ioid', ctypes.c_int32),
                ('subcommand', ctypes.c_byte),
                ('_status_type', ctypes.c_byte),
                ]

    _subcommand_fields_ = {
        Subcommands.INIT: [
            SuccessField('put_structure_if', FieldDesc),
        ],
        Subcommands.DEFAULT: [
            # The actual put
        ],
        Subcommands.DESTROY: [
        ],
    }


class ChannelPutGetRequest(ExtendedMessageBase):
    """
    A "channel put-get" set of messages are used to set (put) data to the
    channel and then immediately retrieve data from the channel. Channels are
    usually "processed" or "updated" by their host between put and get, so that
    the get reflects changes in the process variable's state.

    After a put-get request is successfully initialized, the client can issue
    actual put-get request(s) on the channel.

    Notes
    -----
    A "GET_PUT" request retrieves the remote put structure. This MAY be used by
    user applications to show data that was set the last time by the application.
    """
    ID = ApplicationCommands.PUT_GET

    _fields_ = [('server_chid', ctypes.c_int32),
                ('ioid', ctypes.c_int32),
                ('subcommand', ctypes.c_byte),
                ]
    _additional_fields_ = []
    _subcommand_fields_ = {
        Subcommands.INIT: [
            RequiredField('pv_request', PVRequest),
        ],
        Subcommands.DEFAULT: [
            RequiredField('put_data', DataWithBitSet)
        ],
        Subcommands.GET: [
            # Get the remote "put request"
        ],
        Subcommands.GET_PUT: [
            # Get the remote "get request"
        ],
        Subcommands.DESTROY: [],
    }


class ChannelPutGetResponse(_StatusBase, ExtendedMessageBase):
    """
    A response to a :class:`ChannelPutGetRequest`.
    """
    ID = ApplicationCommands.PUT_GET

    _fields_ = [('ioid', ctypes.c_int32),
                ('subcommand', ctypes.c_byte),
                ('_status_type', ctypes.c_byte),
                ]

    _subcommand_fields_ = {
        Subcommands.INIT: [
            SuccessField('put_structure_if', FieldDesc),
            SuccessField('get_structure_if', FieldDesc),
        ],
        Subcommands.DEFAULT: [
            SuccessField('pv_data', Data),
        ],
        Subcommands.GET: [
            SuccessField('get_data', Data),
        ],
        Subcommands.GET_PUT: [
            SuccessField('put_data', Data),
        ],
        Subcommands.DESTROY: [],
    }


class ChannelArrayRequest(ExtendedMessageBase):
    """
    A "channel array" set of messages are used to handle remote array values.
    Requests allow a client agent to: retrieve (get) and set (put) data from/to
    the array, and to change the array's length (number of valid elements in
    the array).

    Notes
    -----
    This is not yet implemented in caproto-pva.
    """
    ID = ApplicationCommands.ARRAY
    # TODO


class ChannelArrayResponse(ExtendedMessageBase):
    """
    A response to a :class:`ChannelArrayRequest`.

    Notes
    -----
    This is not yet implemented in caproto-pva.
    """
    ID = ApplicationCommands.ARRAY
    # TODO


class ChannelRequestDestroyRequest(ExtendedMessageBase):
    """
    A "destroy request" messages is used destroy any request instance, i.e. an
    instance with requestID.

    Notes
    -----
    This is not yet implemented in caproto-pva.
    """
    ID = ApplicationCommands.DESTROY_REQUEST
    # TODO


class ChannelRequestDestroyResponse(ExtendedMessageBase):
    """
    A response to a :class:`ChannelRequestDestroyRequest`.

    Notes
    -----
    This is not yet implemented in caproto-pva.
    """
    ID = ApplicationCommands.DESTROY_REQUEST
    # TODO


class ChannelRequestCancelRequest(ExtendedMessageBase):
    """
    A "cancel request" messages is used cancel any pending request, i.e. an
    instance with a requestID.

    Notes
    -----
    This is not yet implemented in caproto-pva.
    """
    ID = ApplicationCommands.CANCEL_REQUEST
    # TODO


class ChannelRequestCancelResponse(ExtendedMessageBase):
    """
    A response to a :class:`ChannelRequestCancelRequest`.

    Notes
    -----
    This is not yet implemented in caproto-pva.
    """
    ID = ApplicationCommands.CANCEL_REQUEST
    # TODO


class ChannelMonitorRequest(ExtendedMessageBase):
    """
    The "channel monitor" set of messages are used by client agents to indicate
    that they wish to be asynchronously informed of changes in the state or
    values of the process variable of a channel.

    Notes
    -----
    This is currently partially supported by caproto-pva.

    More details on the `wiki <https://github.com/epics-base/pvAccessCPP/wiki/Protocol-Operation-Monitor>`_.
    """
    ID = ApplicationCommands.MONITOR

    _fields_ = [('server_chid', ctypes.c_int32),
                ('ioid', ctypes.c_int32),
                ('subcommand', ctypes.c_byte),
                ]
    _additional_fields_ = []
    _subcommand_fields_ = {
        Subcommands.INIT: [
            RequiredField('pv_request', PVRequest),
            OptionalField('queue_size', 'int',
                          OptionalStopMarker.stop,
                          lambda msg, buf: bool(msg.subcommand &
                                                MonitorSubcommands.PIPELINE)),
        ],
        Subcommands.DEFAULT: [],
        MonitorSubcommands.START: [],
        MonitorSubcommands.STOP: [],
        # Subcommands.PIPELINE: [],
        Subcommands.DESTROY: [],
    }


class ChannelMonitorResponse(ExtendedMessageBase):
    """
    A response to a :class:`ChannelMonitorRequest`.
    """
    ID = ApplicationCommands.MONITOR

    _fields_ = [('ioid', ctypes.c_int32),
                ('subcommand', ctypes.c_byte),
                ]

    @property
    def is_successful(self) -> bool:
        # status_type only on INIT!  Do not mix in _StatusBase.
        status_type = getattr(self, '_status_type', StatusType.OK)
        return status_type in success_status_types

    _additional_fields_ = []
    _subcommand_fields_ = {
        MonitorSubcommands.INIT: [
            RequiredField('status_type', FieldType.byte),
        ] + Status._additional_fields_ + [
            SuccessField('pv_structure_if', FieldDesc),
        ],
        MonitorSubcommands.DEFAULT: [
            # `pv_structure_if` is tracked by ioid
            RequiredField('pv_data', DataWithBitSet),
            RequiredField('overrun_bitset', BitSet),
        ],
        # MonitorSubcommands.START: [],
        # MonitorSubcommands.STOP: [],
        MonitorSubcommands.PIPELINE: [
            RequiredField('nfree', FieldType.int32),
        ],
        Subcommands.DESTROY: [],
    }


class ChannelProcessRequest(ExtendedMessageBase):
    """
    A "channel process" set of messages are used to indicate to the server that
    the computation actions associated with a channel should be executed.

    In EPICS terminology, this means that the channel should be "processed".

    Notes
    -----
    After a process request is successfully initialized, the client can issue
    the actual process request(s).
    """
    ID = ApplicationCommands.PROCESS

    _fields_ = [('server_chid', ctypes.c_int32),
                ('ioid', ctypes.c_int32),
                ('subcommand', ctypes.c_byte),
                ]
    _additional_fields_ = []
    _subcommand_fields_ = {
        Subcommands.INIT: [
            RequiredField('pv_request', PVRequest),
            # TODO_DOCS typo serverStatusIF -> PVRequestIF
        ],
        Subcommands.DEFAULT: [],  # TODO: not PROCESS?
        Subcommands.DESTROY: [],
    }


class ChannelProcessResponse(_StatusBase, ExtendedMessageBase):
    """
    A response to a :class:`ChannelProcessRequest`.
    """
    ID = ApplicationCommands.PROCESS

    _fields_ = [('ioid', ctypes.c_int32),
                ('subcommand', ctypes.c_byte),
                ('_status_type', ctypes.c_byte),
                ]

    _subcommand_fields_ = {
        Subcommands.INIT: [],
        Subcommands.DEFAULT: [],  # TODO: not PROCESS?
        Subcommands.DESTROY: [],
    }


class ChannelRpcRequest(ExtendedMessageBase):
    """
    A remote procedure call request.

    Notes
    -----
    The "channel RPC" set of messages are used to provide remote procedure call
    (RPC) support over pvAccess. After a RPC request is successfully
    initialized, the client can issue actual RPC request(s).

    """
    ID = ApplicationCommands.RPC

    _fields_ = [('server_chid', ctypes.c_int32),
                ('ioid', ctypes.c_int32),
                ('subcommand', ctypes.c_byte),
                ]
    _additional_fields_ = []
    _subcommand_fields_ = {
        Subcommands.INIT: [
            RequiredField('pv_request', PVRequest),
        ],
        Subcommands.DEFAULT: [
            RequiredField('pv_data', FieldDescAndData),
        ],
        Subcommands.DESTROY: [],
    }


class ChannelRpcResponse(_StatusBase, ExtendedMessageBase):
    ID = ApplicationCommands.PROCESS

    _fields_ = [('ioid', ctypes.c_int32),
                ('subcommand', ctypes.c_byte),
                ('_status_type', ctypes.c_byte),
                ]

    _subcommand_fields_ = {
        Subcommands.INIT: [],
        Subcommands.DEFAULT: [
            SuccessField('pv_response', FieldDescAndData),
        ],
        Subcommands.DESTROY: [],
    }


class OriginTagRequest(_StatusBase, ExtendedMessageBase):
    """
    When a client or server receives a packet containing a Search message with
    flagged "sent as unicast" it may resend this as a multicast to
    "224.0.0.128" through the loopback interface ("127.0.0.1").

    Notes
    -----
    This is not yet implemented in caproto-pva.

    More details on the `wiki
    <https://github.com/epics-base/pvAccessCPP/wiki/Protocol-Messages#cmd_origin_tag-0x16>`_.
    """
    ID = ApplicationCommands.ORIGIN_TAG


BIG_ENDIAN, LITTLE_ENDIAN = BIG_ENDIAN, LITTLE_ENDIAN  # removed below
BeaconMessageBE = _make_endian(BeaconMessage, BIG_ENDIAN)
BeaconMessageLE = _make_endian(BeaconMessage, LITTLE_ENDIAN)
EchoBE = _make_endian(Echo, BIG_ENDIAN)
EchoLE = _make_endian(Echo, LITTLE_ENDIAN)
StatusBE = _make_endian(Status, BIG_ENDIAN)
StatusLE = _make_endian(Status, LITTLE_ENDIAN)

ChannelDestroyRequestBE = _make_endian(ChannelDestroyRequest, BIG_ENDIAN)
ChannelDestroyRequestLE = _make_endian(ChannelDestroyRequest, LITTLE_ENDIAN)
ChannelDestroyResponseBE = _make_endian(ChannelDestroyResponse, BIG_ENDIAN)
ChannelDestroyResponseLE = _make_endian(ChannelDestroyResponse, LITTLE_ENDIAN)
ChannelFieldInfoRequestBE = _make_endian(ChannelFieldInfoRequest, BIG_ENDIAN)
ChannelFieldInfoRequestLE = _make_endian(ChannelFieldInfoRequest, LITTLE_ENDIAN)
ChannelFieldInfoResponseBE = _make_endian(ChannelFieldInfoResponse, BIG_ENDIAN)
ChannelFieldInfoResponseLE = _make_endian(ChannelFieldInfoResponse, LITTLE_ENDIAN)
ChannelGetRequestBE = _make_endian(ChannelGetRequest, BIG_ENDIAN)
ChannelGetRequestLE = _make_endian(ChannelGetRequest, LITTLE_ENDIAN)
ChannelGetResponseBE = _make_endian(ChannelGetResponse, BIG_ENDIAN)
ChannelGetResponseLE = _make_endian(ChannelGetResponse, LITTLE_ENDIAN)
ChannelMonitorRequestBE = _make_endian(ChannelMonitorRequest, BIG_ENDIAN)
ChannelMonitorRequestLE = _make_endian(ChannelMonitorRequest, LITTLE_ENDIAN)
ChannelMonitorResponseBE = _make_endian(ChannelMonitorResponse, BIG_ENDIAN)
ChannelMonitorResponseLE = _make_endian(ChannelMonitorResponse, LITTLE_ENDIAN)
ChannelProcessRequestBE = _make_endian(ChannelProcessRequest, BIG_ENDIAN)
ChannelProcessRequestLE = _make_endian(ChannelProcessRequest, LITTLE_ENDIAN)
ChannelProcessResponseBE = _make_endian(ChannelProcessResponse, BIG_ENDIAN)
ChannelProcessResponseLE = _make_endian(ChannelProcessResponse, LITTLE_ENDIAN)
ChannelPutGetRequestBE = _make_endian(ChannelPutGetRequest, BIG_ENDIAN)
ChannelPutGetRequestLE = _make_endian(ChannelPutGetRequest, LITTLE_ENDIAN)
ChannelPutGetResponseBE = _make_endian(ChannelPutGetResponse, BIG_ENDIAN)
ChannelPutGetResponseLE = _make_endian(ChannelPutGetResponse, LITTLE_ENDIAN)
ChannelPutRequestBE = _make_endian(ChannelPutRequest, BIG_ENDIAN)
ChannelPutRequestLE = _make_endian(ChannelPutRequest, LITTLE_ENDIAN)
ChannelPutResponseBE = _make_endian(ChannelPutResponse, BIG_ENDIAN)
ChannelPutResponseLE = _make_endian(ChannelPutResponse, LITTLE_ENDIAN)
ChannelRpcRequestBE = _make_endian(ChannelRpcRequest, BIG_ENDIAN)
ChannelRpcRequestLE = _make_endian(ChannelRpcRequest, LITTLE_ENDIAN)
ChannelRpcResponseBE = _make_endian(ChannelRpcResponse, BIG_ENDIAN)
ChannelRpcResponseLE = _make_endian(ChannelRpcResponse, LITTLE_ENDIAN)
ConnectionValidatedResponseBE = _make_endian(ConnectionValidatedResponse, BIG_ENDIAN)
ConnectionValidatedResponseLE = _make_endian(ConnectionValidatedResponse, LITTLE_ENDIAN)
ConnectionValidationRequestBE = _make_endian(ConnectionValidationRequest, BIG_ENDIAN)
ConnectionValidationRequestLE = _make_endian(ConnectionValidationRequest, LITTLE_ENDIAN)
ConnectionValidationResponseBE = _make_endian(ConnectionValidationResponse, BIG_ENDIAN)
ConnectionValidationResponseLE = _make_endian(ConnectionValidationResponse, LITTLE_ENDIAN)
CreateChannelRequestBE = _make_endian(CreateChannelRequest, BIG_ENDIAN)
CreateChannelRequestLE = _make_endian(CreateChannelRequest, LITTLE_ENDIAN)
CreateChannelResponseBE = _make_endian(CreateChannelResponse, BIG_ENDIAN)
CreateChannelResponseLE = _make_endian(CreateChannelResponse, LITTLE_ENDIAN)
SearchRequestBE = _make_endian(SearchRequest, BIG_ENDIAN)
SearchRequestLE = _make_endian(SearchRequest, LITTLE_ENDIAN)
SearchResponseBE = _make_endian(SearchResponse, BIG_ENDIAN)
SearchResponseLE = _make_endian(SearchResponse, LITTLE_ENDIAN)

FROM_CLIENT, FROM_SERVER = MessageFlags.FROM_CLIENT, MessageFlags.FROM_SERVER

messages = {
    # LITTLE ENDIAN, CLIENT -> SERVER
    (LITTLE_ENDIAN, FROM_CLIENT): {
        ApplicationCommands.BEACON: BeaconMessageLE,
        ApplicationCommands.CONNECTION_VALIDATION: ConnectionValidationResponseLE,
        ApplicationCommands.ECHO: EchoLE,
        ApplicationCommands.SEARCH_REQUEST: SearchRequestLE,
        ApplicationCommands.CREATE_CHANNEL: CreateChannelRequestLE,
        ApplicationCommands.GET: ChannelGetRequestLE,
        ApplicationCommands.GET_FIELD: ChannelFieldInfoRequestLE,
        ApplicationCommands.DESTROY_CHANNEL: ChannelDestroyRequestLE,
        ApplicationCommands.PUT: ChannelPutRequestLE,
        ApplicationCommands.PUT_GET: ChannelPutGetRequestLE,
        ApplicationCommands.MONITOR: ChannelMonitorRequestLE,
        ApplicationCommands.PROCESS: ChannelProcessRequestLE,
        ApplicationCommands.RPC: ChannelRpcRequestLE,
    },

    # BIG ENDIAN, CLIENT -> SERVER
    (BIG_ENDIAN, FROM_CLIENT): {
        ApplicationCommands.BEACON: BeaconMessageBE,
        ApplicationCommands.CONNECTION_VALIDATION: ConnectionValidationResponseBE,
        ApplicationCommands.ECHO: EchoBE,
        ApplicationCommands.SEARCH_REQUEST: SearchRequestBE,
        ApplicationCommands.CREATE_CHANNEL: CreateChannelRequestBE,
        ApplicationCommands.GET: ChannelGetRequestBE,
        ApplicationCommands.GET_FIELD: ChannelFieldInfoRequestBE,
        ApplicationCommands.DESTROY_CHANNEL: ChannelDestroyRequestBE,
        ApplicationCommands.PUT: ChannelPutRequestBE,
        ApplicationCommands.PUT_GET: ChannelPutGetRequestBE,
        ApplicationCommands.MONITOR: ChannelMonitorRequestBE,
        ApplicationCommands.PROCESS: ChannelProcessRequestBE,
        ApplicationCommands.RPC: ChannelRpcRequestBE,
    },

    # LITTLE ENDIAN, SERVER -> CLIENT
    (LITTLE_ENDIAN, FROM_SERVER): {
        ControlCommands.SET_ENDIANESS: SetByteOrder,
        ApplicationCommands.BEACON: BeaconMessageLE,
        ApplicationCommands.CONNECTION_VALIDATION: ConnectionValidationRequestLE,
        ApplicationCommands.ECHO: EchoLE,
        ApplicationCommands.CONNECTION_VALIDATED: ConnectionValidatedResponseLE,
        ApplicationCommands.SEARCH_RESPONSE: SearchResponseLE,
        ApplicationCommands.CREATE_CHANNEL: CreateChannelResponseLE,
        ApplicationCommands.GET: ChannelGetResponseLE,
        ApplicationCommands.GET_FIELD: ChannelFieldInfoResponseLE,
        ApplicationCommands.DESTROY_CHANNEL: ChannelDestroyResponseLE,
        ApplicationCommands.PUT: ChannelPutResponseLE,
        ApplicationCommands.PUT_GET: ChannelPutGetResponseLE,
        ApplicationCommands.MONITOR: ChannelMonitorResponseLE,
        ApplicationCommands.PROCESS: ChannelProcessResponseLE,
        ApplicationCommands.RPC: ChannelRpcResponseLE,
    },

    # BIG ENDIAN, SERVER -> CLIENT
    (BIG_ENDIAN, FROM_SERVER): {
        ControlCommands.SET_ENDIANESS: SetByteOrder,
        ApplicationCommands.BEACON: BeaconMessageBE,
        ApplicationCommands.CONNECTION_VALIDATION: ConnectionValidationRequestBE,
        ApplicationCommands.ECHO: EchoBE,
        ApplicationCommands.CONNECTION_VALIDATED: ConnectionValidatedResponseBE,
        ApplicationCommands.SEARCH_RESPONSE: SearchResponseBE,
        ApplicationCommands.CREATE_CHANNEL: CreateChannelResponseBE,
        ApplicationCommands.GET: ChannelGetResponseBE,
        ApplicationCommands.GET_FIELD: ChannelFieldInfoResponseBE,
        ApplicationCommands.DESTROY_CHANNEL: ChannelDestroyResponseBE,
        ApplicationCommands.PUT: ChannelPutResponseBE,
        ApplicationCommands.PUT_GET: ChannelPutGetResponseBE,
        ApplicationCommands.MONITOR: ChannelMonitorResponseBE,
        ApplicationCommands.PROCESS: ChannelProcessResponseBE,
        ApplicationCommands.RPC: ChannelRpcResponseBE,
    },
}


def read_datagram(data: bytes,
                  address: Tuple[str, int],
                  role: Role,
                  *,
                  fixed_byte_order: Optional[UserFacingEndian] = None,
                  cache: CacheContext = NullCache
                  ) -> Deserialized:
    """
    Parse bytes from one datagram into one or more commands.

    Parameters
    ----------
    data : bytes
        The data to deserialize.

    address : (addr, port)
        The sender's address.

    role : Role
        The role of the sender.

    fixed_byte_order : UserFacingEndian, optional
        Use this specific byte order for deserialization.

    cache : CacheContext, optional
        The serialization cache.
    """
    buf = bytearray(data)
    commands = []
    offset = 0
    direction_flag = (MessageFlags.FROM_SERVER
                      if role == SERVER
                      else MessageFlags.FROM_CLIENT)

    while buf:
        header, buf, off = MessageHeaderLE.deserialize(buf, cache=cache)
        offset += off

        msg_class = header.get_message(
            direction_flag, use_fixed_byte_order=fixed_byte_order)
        msg, buf, off = msg_class.deserialize(buf, cache=cache)
        offset += off

        commands.append(msg)

    return Deserialized(data=commands, buffer=buf, offset=offset)


def header_from_wire(data: bytes,
                     byte_order: Optional[UserFacingEndian] = None
                     ) -> 'MessageHeader':
    """
    Deserialize a message header from the wire.

    Parameters
    ----------
    data : bytes
        The data to deserialize.

    byte_order : LITTLE_ENDIAN or BIG_ENDIAN, optional
        Defaults to LITTLE_ENDIAN, falling back to BIG_ENDIAN if incorrect.
        If specified, the fallback is not attempted.
    """
    if byte_order is not None:
        # Use a fixed byte order, ignoring header flags
        header_cls = (MessageHeaderLE
                      if byte_order == LITTLE_ENDIAN
                      else MessageHeaderBE)
        header = header_cls.from_buffer(data)
        assert header.valid, 'invalid header'
        return header

    # Guess little-endian, but fall back to big-endian if wrong.
    header = MessageHeaderLE.from_buffer(data)
    if header.byte_order != LITTLE_ENDIAN:
        header = MessageHeaderBE.from_buffer(data)

    assert header.valid, 'invalid header'
    return header


def bytes_needed_for_command(data, direction, cache, *, byte_order=None):
    '''
    Parameters
    ----------
    data
    direction

    Returns
    -------
    (header, num_bytes_needed, segmented)

    If segmented, num_bytes_needed only applies to the current segment.
    '''
    data_len = len(data)

    # We need at least one header's worth of bytes to interpret anything.
    if data_len < _MessageHeaderSize:
        return None, _MessageHeaderSize - data_len, None

    header = header_from_wire(data, byte_order)
    command = header.get_message(direction=direction,
                                 use_fixed_byte_order=byte_order)
    if issubclass(command, (SetByteOrder, )):
        # SetByteOrder uses the payload in a custom way
        return header, 0, False

    total_size = _MessageHeaderSize + header.payload_size

    if data_len < total_size:
        return header, total_size - data_len, header.flags.is_segmented
    return header, 0, header.flags.is_segmented


def _deserialize_unsegmented_message(
        msg_class: MessageBase,
        data: bytes,
        header: MessageHeader,
        cache: CacheContext,
        *,
        payload_size: Optional[int] = None):
    """
    Deserialize a single, unsegmented message.

    Parameters
    ----------
    msg_class : MessageBase
        The message type to deserialize.

    data : bytes
        Sufficient data to deserialize the message.

    header : MessageHeader
        The associated message header.

    cache : CacheContext
        Serialization cache context.

    payload_size : int, optional
        The size of the message payload, if needed.  Generally, this can be
        determined from the header.  However, some messages use the header
        payload size in "special" ways, so allow overriding it as an argument.
    """

    if payload_size is None:
        payload_size = header.payload_size

    cmd, _, off = msg_class.deserialize(data, cache=cache, header=header)

    if off != payload_size:
        raise RuntimeError(
            f'Number of bytes used in deserialization ({off}) did not match '
            f'full payload size: {payload_size}'
        )

    return cmd, off


def read_from_bytestream(
        data: bytes, role: Role,
        segment_state: Optional[Union[bytes, ChannelLifeCycle]],
        cache: CacheContext,
        *,
        byte_order=UserFacingEndian) -> SegmentDeserialized:
    '''
    Handles segmentation but requires the caller to track it for us.

    Parameters
    ----------
    data : bytes
        The new data.

    role : Role
        Their role.

    segment_state : ChannelLifeCycle, byte, or None
        The state of segmentation, if available.

    cache : CacheContext
        Serialization cache context.

    byte_order : LITTLE_ENDIAN or BIG_ENDIAN, optional
        Fixed byte order if server message endianness is to be interpreted on a
        message-by-message basis.

    Returns
    -------
    SegmentDeserialized
    '''
    direction = (MessageFlags.FROM_SERVER
                 if role == SERVER
                 else MessageFlags.FROM_CLIENT)

    header, num_bytes_needed, segmented = bytes_needed_for_command(
        data, direction, cache=cache, byte_order=byte_order)

    if num_bytes_needed > 0:
        data = Deserialized(data=ChannelLifeCycle.NEED_DATA, buffer=data, offset=0)
        return SegmentDeserialized(data,
                                   bytes_needed=num_bytes_needed,
                                   segment_state=None)

    msg_class = header.get_message(direction=direction,
                                   use_fixed_byte_order=byte_order)

    data = memoryview(data)
    payload_start = _MessageHeaderSize
    if issubclass(msg_class, (SetByteOrder, )):
        message_start = 0
        payload_size = _MessageHeaderSize
    else:
        message_start = payload_start
        payload_size = header.payload_size

    message_end = message_start + payload_size
    next_data = data[message_end:]
    payload_data = data[message_start:message_end]

    if not header.flags.is_segmented:
        msg, offset = _deserialize_unsegmented_message(
            msg_class=msg_class,
            data=payload_data,
            header=header,
            cache=cache,
            payload_size=payload_size,
        )
        return SegmentDeserialized(
            Deserialized(data=msg, buffer=next_data, offset=offset),
            bytes_needed=0, segment_state=None,
        )

    # Otherwise, we're dealing with a segmented message - a large message
    # broken up over multiple segments.

    # TODO: docs indicate payloads should be aligned, but i can't confirm this
    # if len(segment_state):
    #     last_segment = segment_state[-1]
    #     start_padding = 8 - (len(last_segment) % 8)
    #     print('alignment padding', start_padding)
    #     message_start += start_padding

    if MessageFlags.LAST not in header.flags:
        # Not the last segment - just return it; need at least another header
        return SegmentDeserialized(
            Deserialized(data=ChannelLifeCycle.NEED_DATA, buffer=next_data,
                         offset=message_end),
            bytes_needed=_MessageHeaderSize,
            segment_state=bytes(payload_data),
        )

    # This is the last segment, combine all and deserialize.
    full_payload = bytearray(b''.join(segment_state))
    full_payload += payload_data

    header.payload_size = len(full_payload)
    msg, _ = _deserialize_unsegmented_message(
        msg_class=msg_class,
        data=memoryview(full_payload),
        header=header,
        cache=cache,
        payload_size=header.payload_size,
    )
    return SegmentDeserialized(
        Deserialized(data=msg, buffer=next_data, offset=message_end),
        bytes_needed=0,
        segment_state=ChannelLifeCycle.CLEAR_SEGMENTS,
    )
