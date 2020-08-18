import ctypes
import dataclasses
import enum
import functools
import logging
import typing
from typing import Dict, List, Optional, Tuple, Type, Union

from . import _annotations as annotations
from . import _core as core
from ._core import (BIG_ENDIAN, LITTLE_ENDIAN, Deserialized, FieldArrayType,
                    FieldType, SegmentDeserialized, Serializable,
                    StatelessSerializable, UserFacingEndian)
from ._data import (Data, DataSerializer, DataWithBitSet, FieldDescAndData,
                    PVRequest)
from ._dataclass import array_of, pva_dataclass
from ._fields import BitSet, CacheContext, FieldDesc, SimpleField
from ._utils import (SERVER, ChannelLifeCycle, Role, ip_to_ubyte_array,
                     ubyte_array_to_ip)

NullCache = CacheContext()
CommandType = typing.Union['ControlCommand', 'ApplicationCommand']
SubcommandType = typing.Union['Subcommand', 'MonitorSubcommand']


@pva_dataclass
class ChannelWithID:
    """
    A channel and ID pair, used for searching and channel creation.
    """
    id: annotations.Int32
    channel_name: annotations.String


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


class OptionalStopMarker(enum.IntEnum):
    """
    Marker for message fields.

    Indicates whether to stop or continue processing messages when the
    condition is not met.
    """
    stop = True
    continue_ = False


MessageFieldType = Union[FieldType, FieldDesc, type, Type[DataSerializer],
                         Type[Serializable], Type[StatelessSerializable]]


@dataclasses.dataclass
class RequiredField(_MessageField):
    name: str
    type: MessageFieldType


@dataclasses.dataclass
class NonstandardArrayField(RequiredField):
    count_attr: str = None


@dataclasses.dataclass
class OptionalField(_MessageField):
    name: str
    type: MessageFieldType
    stop: OptionalStopMarker = OptionalStopMarker.stop
    condition: Optional[typing.Callable] = None


def _not_ok_condition(msg, buf):
    return msg.status_type != StatusType.OK


def _success_condition(msg, buf):
    """Continuation condition: only if the status reported success."""
    return msg.status_type in success_status_types


@dataclasses.dataclass
class SuccessField(OptionalField):
    condition: Optional[typing.Callable] = _success_condition


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


class ApplicationCommand(enum.IntEnum):
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


class ControlCommand(enum.Enum):
    """
    Control messages. These include flow control and have no payload.
    """
    # NOTE: this is not set as an IntEnum to avoid clashing with
    # ApplicationCommand in dictionaries.
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


class Subcommand(enum.IntEnum):
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


class MonitorSubcommand(enum.IntFlag):
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


success_status_types = {
    StatusType.OK,
    StatusType.OK_VERBOSE,
    StatusType.WARNING,
}

default_pvrequest = 'record[]field()'


class MessageBase:
    """Base class for all Messages."""
    _pack_ = 1
    _fields_: typing.Sequence[Tuple[str, object]]
    _additional_fields_: Optional[List[_MessageField]] = None
    _subcommand_fields_: Optional[Dict[SubcommandType, List[_MessageField]]] = None
    # The following is set in endian subclasses for the varieties of messages:
    _ENDIAN: UserFacingEndian

    subcommand: Optional[SubcommandType] = None

    def __repr__(self):
        def name_and_value(name):
            prop_name = name.lstrip('_')
            if hasattr(self.__class__, prop_name):
                name = prop_name
            value = getattr(self, name, None)
            return f'{name}={value!r}'

        info = ', '.join(name_and_value(attr) for attr, *_ in self._fields_)
        if self._additional_fields_:
            if info:
                info += ', '
            info += ', '.join(name_and_value(field.name)
                              for field in self._additional_fields_)
        return f'{self.__class__.__name__}({info})'

    @classmethod
    def _get_additional_fields(cls, subcommand=None):
        fields = cls._additional_fields_ or []
        if not cls._subcommand_fields_ or subcommand is None:
            return fields

        try:
            return fields + cls._subcommand_fields_[subcommand]
        except KeyError:
            raise ValueError(f'Invalid (or currently unhandled) subcommand'
                             f' for class {cls}: {subcommand}') from None

    def serialize(self, *, default_pvrequest=default_pvrequest,
                  cache=NullCache):
        additional_fields = self._get_additional_fields(
            subcommand=getattr(self, 'subcommand', None)
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

        subcommand = getattr(msg, 'subcommand', None)
        additional_fields = cls._get_additional_fields(subcommand=subcommand)

        if not additional_fields:
            # Without additional fields, this is just a ctypes.Structure
            return Deserialized(data=msg, buffer=buf, offset=offset)

        serialization_logger.debug(
            'deserializing %s base_size=%s subcommand=%s payload=%s', cls,
            base_size, subcommand, bytes(buf))

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


class _LE(ctypes.LittleEndianStructure):
    _ENDIAN = LITTLE_ENDIAN


class _BE(ctypes.BigEndianStructure):
    _ENDIAN = BIG_ENDIAN


class MessageHeader(MessageBase):
    magic: int
    version: int
    _flags: int
    message_command: int
    payload_size: int

    _fields_ = [
        ('magic', ctypes.c_ubyte),
        ('version', ctypes.c_ubyte),
        ('_flags', ctypes.c_ubyte),
        ('message_command', ctypes.c_ubyte),
        ('payload_size', ctypes.c_uint),
    ]

    def __init__(self, *, flags: MessageFlags,
                 command: CommandType,
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
            command = ControlCommand(self.message_command)
        else:
            command = ApplicationCommand(self.message_command)

        try:
            message_group = messages[(byte_order, direction)]
            return message_group[command]
        except KeyError as ex:
            raise KeyError(
                f'{ex} where flags={flags} and command={command!r}'
            )


class MessageHeaderLE(MessageHeader, _LE): _fields_ = MessageHeader._fields_  # noqa  E305
class MessageHeaderBE(MessageHeader, _BE): _fields_ = MessageHeader._fields_  # noqa  E305


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
    _status_type: int
    message: Optional[str] = None
    call_tree: Optional[str] = None

    _additional_fields_: Optional[List[_MessageField]] = [
        OptionalField(
            name='message',
            type=FieldType.string,
            stop=OptionalStopMarker.continue_,
            condition=_not_ok_condition,
        ),
        OptionalField(
            name='call_tree',
            type=FieldType.string,
            stop=OptionalStopMarker.continue_,
            condition=_not_ok_condition,
        ),
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


class Status(_StatusBase, MessageBase):
    _status_type: int
    _fields_ = [('_status_type', ctypes.c_byte)]


class BeaconMessage(MessageBase):
    """
    A beacon message.

    Notes
    -----
    Servers MUST broadcast or multicast beacons over UDP. Beacons are be used
    to announce the appearance and continued presense of servers. Clients may
    use Beacons to detect when new servers appear, and may use this information
    to more quickly retry unanswered CMD_SEARCH messages.
    """
    ID = ApplicationCommand.BEACON
    # FieldDesc serverStatusIF;
    # [if serverStatusIF != NULL_TYPE_CODE] PVField serverStatus;
    guid: bytes
    flags: int
    beacon_sequence_id: int
    change_count: int
    server_address: bytes
    server_port: int

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
    ID = ControlCommand.SET_MARKER


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
    ID = ControlCommand.ACK_MARKER


class SetByteOrder(MessageHeaderLE):
    """
    An indicator to set the byte order of future messages.

    Notes
    -----
    The 7-th bit of a header flags field indicates the server's selected byte
    order for the connection on which this message was received. Client MUST
    encode all the messages sent via this connection using this byte order.
    """
    ID = ControlCommand.SET_ENDIANESS
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
    ID = ControlCommand.ECHO_REQUEST
    _fields_ = []


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
    ID = ControlCommand.ECHO_REQUEST
    _fields_ = []


class ConnectionValidationRequest(MessageBase):
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
    ID = ApplicationCommand.CONNECTION_VALIDATION

    server_buffer_size: int
    server_registry_size: int
    _fields_ = [
        ('server_buffer_size', ctypes.c_int32),
        ('server_registry_size', ctypes.c_int16),
    ]

    _additional_fields_ = [
        RequiredField('auth_nz', array_of(FieldType.string)),
    ]


class ConnectionValidationResponse(MessageBase):
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
    ID = ApplicationCommand.CONNECTION_VALIDATION

    client_buffer_size: int
    client_registry_size: int
    connection_qos: int

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


class Echo(MessageBase):
    """
    A TCP Echo request/response.

    Notes
    -----
    An Echo diagnostic message is usually sent to check if TCP/IP connection is
    still valid.
    """
    ID = ApplicationCommand.ECHO
    _fields_ = []
    _additional_fields_ = [
        RequiredField('payload', array_of(FieldType.int8)),
    ]


class ConnectionValidatedResponse(Status):
    """Validation results - success depends on the status."""
    ID = ApplicationCommand.CONNECTION_VALIDATED


class SearchRequest(MessageBase):
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
    ID = ApplicationCommand.SEARCH_REQUEST

    sequence_id: int
    flags: int
    reserved: bytes
    _response_address: bytes
    response_port: int

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


class SearchResponse(MessageBase):
    """
    A response to a SearchRequest.

    Notes
    -----
    A client MUST examine the protocol member field to verify it supports the
    given exchange protocol; if not, the search response is ignored.

    The count for the number of searchInstanceIDs elements is always sent as an
    unsigned 16 bit integer, not using the default size encoding.
    """
    ID = ApplicationCommand.SEARCH_RESPONSE

    _guid: bytes
    sequence_id: int
    _server_address: bytes
    server_port: int

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


class CreateChannelRequest(MessageBase):
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
    ID = ApplicationCommand.CREATE_CHANNEL

    count: int
    channels: List[Union[ChannelWithID, Dict]]  # TODO: consistent types

    _fields_ = []
    _additional_fields_ = [
        RequiredField('count', FieldType.uint16),
        NonstandardArrayField('channels', ChannelWithID, count_attr='count'),
    ]


class CreateChannelResponse(_StatusBase, MessageBase):
    """
    A server's response to a CreateChannelRequest.

    Notes
    -----
    A server MUST store the client ChannelID and respond with its value in a
    ChannelDestroyRequest, see below.

    A client uses the serverChannelID value for all subsequent requests on the
    channel. Agents SHOULD NOT make any assumptions about how given IDs are
    generated. IDs MUST be unique within a connection and MAY be recycled after
    a channel is disconnected.
    """
    ID = ApplicationCommand.CREATE_CHANNEL

    client_chid: int
    server_chid: int

    _fields_ = [
        ('client_chid', ctypes.c_int32),
        ('server_chid', ctypes.c_int32),
        ('_status_type', ctypes.c_byte),
    ]
    _additional_fields_ = list(Status._additional_fields_) + [
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
    ID = ApplicationCommand.DESTROY_CHANNEL
    client_chid: int
    server_chid: int
    _fields_ = [
        ('client_chid', ctypes.c_int32),
        ('server_chid', ctypes.c_int32),
    ]


class ChannelDestroyResponse(_StatusBase, MessageBase):
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
    ID = ApplicationCommand.DESTROY_CHANNEL

    client_chid: int
    server_chid: int
    _status_type: int

    _fields_ = [
        ('client_chid', ctypes.c_int32),
        ('server_chid', ctypes.c_int32),
        ('_status_type', ctypes.c_byte),
    ]


class ChannelGetRequest(MessageBase):
    """
    A "channel get" set of messages are used to retrieve (get) data from the channel.
    """
    ID = ApplicationCommand.GET

    server_chid: int
    ioid: int

    _fields_ = [
        ('server_chid', ctypes.c_int32),
        ('ioid', ctypes.c_int32),
        ('subcommand', ctypes.c_byte),
    ]

    _subcommand_fields_ = {
        Subcommand.INIT: [
            RequiredField('pv_request', PVRequest),
        ],
        Subcommand.GET: [],
        Subcommand.DESTROY: [],
    }


class ChannelGetResponse(_StatusBase, MessageBase):
    """
    A response to a ChannelGetRequest.
    """
    ID = ApplicationCommand.GET

    ioid: int
    _status_type: int
    pv_structure_if: FieldDesc
    pv_data: typing.Any

    _fields_ = [
        ('ioid', ctypes.c_int32),
        ('subcommand', ctypes.c_byte),
        ('_status_type', ctypes.c_byte),
    ]
    _subcommand_fields_ = {
        Subcommand.INIT: [
            SuccessField('pv_structure_if', FieldDesc),
        ],
        Subcommand.GET: [
            SuccessField('pv_data', DataWithBitSet,
                         # `pv_structure_if` is tracked by ioid
                         ),
        ],
        Subcommand.DESTROY: [],
    }


class ChannelFieldInfoRequest(MessageBase):
    """
    Used to retrieve a channel's type introspection data, i.e., a :class:`FieldDesc`.
    """
    ID = ApplicationCommand.GET_FIELD

    server_chid: int
    ioid: int

    _fields_ = [
        ('server_chid', ctypes.c_int32),
        ('ioid', ctypes.c_int32),
    ]

    _additional_fields_ = [
        RequiredField('sub_field_name', FieldType.string),
    ]


class ChannelFieldInfoResponse(_StatusBase, MessageBase):
    """
    A response to a :class:`ChannelFieldInfoRequest`.
    """
    ID = ApplicationCommand.GET_FIELD

    ioid: int

    _fields_ = [
        ('ioid', ctypes.c_int32),
        ('_status_type', ctypes.c_byte),
    ]
    _additional_fields_ = list(Status._additional_fields_) + [
        SuccessField('field_if', FieldDesc),
    ]


class ChannelPutRequest(MessageBase):
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
    ID = ApplicationCommand.PUT

    server_chid: int
    ioid: int

    _fields_ = [
        ('server_chid', ctypes.c_int32),
        ('ioid', ctypes.c_int32),
        ('subcommand', ctypes.c_byte),
    ]
    _subcommand_fields_ = {
        Subcommand.INIT: [
            RequiredField('pv_request', PVRequest),
        ],
        Subcommand.GET: [
            # Query what the last put request was
            RequiredField('pv_put_data', Data),
        ],
        Subcommand.DEFAULT: [
            # Perform the put
            RequiredField('put_data', DataWithBitSet),
        ],
        # TODO mask DESTROY | DEFAULT
        Subcommand.DESTROY: [],
    }


class ChannelPutResponse(_StatusBase, MessageBase):
    """
    A response to a :class:`ChannelPutRequest`.
    """
    ID = ApplicationCommand.PUT

    ioid: int
    put_structure_if: Optional[FieldDesc] = None

    _fields_ = [
        ('ioid', ctypes.c_int32),
        ('subcommand', ctypes.c_byte),
        ('_status_type', ctypes.c_byte),
    ]

    _subcommand_fields_ = {
        Subcommand.INIT: [
            SuccessField('put_structure_if', FieldDesc),
        ],
        Subcommand.DEFAULT: [
            # The actual put
        ],
        Subcommand.DESTROY: [
        ],
    }


class ChannelPutGetRequest(MessageBase):
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
    ID = ApplicationCommand.PUT_GET

    server_chid: int
    ioid: int

    _fields_ = [
        ('server_chid', ctypes.c_int32),
        ('ioid', ctypes.c_int32),
        ('subcommand', ctypes.c_byte),
    ]
    _subcommand_fields_ = {
        Subcommand.INIT: [
            RequiredField('pv_request', PVRequest),
        ],
        Subcommand.DEFAULT: [
            RequiredField('put_data', DataWithBitSet)
        ],
        Subcommand.GET: [
            # Get the remote "put request"
        ],
        Subcommand.GET_PUT: [
            # Get the remote "get request"
        ],
        Subcommand.DESTROY: [],
    }


class ChannelPutGetResponse(_StatusBase, MessageBase):
    """
    A response to a :class:`ChannelPutGetRequest`.
    """
    ID = ApplicationCommand.PUT_GET

    ioid: int
    get_structure_if: Optional[FieldDesc]
    put_structure_if: Optional[FieldDesc]
    get_data: Optional[typing.Any]
    put_data: Optional[typing.Any]
    pv_data: Optional[typing.Any]

    _fields_ = [
        ('ioid', ctypes.c_int32),
        ('subcommand', ctypes.c_byte),
        ('_status_type', ctypes.c_byte),
    ]

    _subcommand_fields_ = {
        Subcommand.INIT: [
            SuccessField('put_structure_if', FieldDesc),
            SuccessField('get_structure_if', FieldDesc),
        ],
        Subcommand.DEFAULT: [
            SuccessField('pv_data', Data),
        ],
        Subcommand.GET: [
            SuccessField('get_data', Data),
        ],
        Subcommand.GET_PUT: [
            SuccessField('put_data', Data),
        ],
        Subcommand.DESTROY: [],
    }


class ChannelArrayRequest(MessageBase):
    """
    A "channel array" set of messages are used to handle remote array values.
    Requests allow a client agent to: retrieve (get) and set (put) data from/to
    the array, and to change the array's length (number of valid elements in
    the array).

    Notes
    -----
    This is not yet implemented in caproto-pva.
    """
    ID = ApplicationCommand.ARRAY
    # TODO


class ChannelArrayResponse(MessageBase):
    """
    A response to a :class:`ChannelArrayRequest`.

    Notes
    -----
    This is not yet implemented in caproto-pva.
    """
    ID = ApplicationCommand.ARRAY
    # TODO


class ChannelRequestDestroyRequest(MessageBase):
    """
    A "destroy request" messages is used destroy any request instance, i.e. an
    instance with requestID.

    Notes
    -----
    This is not yet implemented in caproto-pva.
    """
    ID = ApplicationCommand.DESTROY_REQUEST
    # TODO


class ChannelRequestDestroyResponse(MessageBase):
    """
    A response to a :class:`ChannelRequestDestroyRequest`.

    Notes
    -----
    This is not yet implemented in caproto-pva.
    """
    ID = ApplicationCommand.DESTROY_REQUEST
    # TODO


class ChannelRequestCancelRequest(MessageBase):
    """
    A "cancel request" messages is used cancel any pending request, i.e. an
    instance with a requestID.

    Notes
    -----
    This is not yet implemented in caproto-pva.
    """
    ID = ApplicationCommand.CANCEL_REQUEST
    # TODO


class ChannelRequestCancelResponse(MessageBase):
    """
    A response to a :class:`ChannelRequestCancelRequest`.

    Notes
    -----
    This is not yet implemented in caproto-pva.
    """
    ID = ApplicationCommand.CANCEL_REQUEST
    # TODO


class ChannelMonitorRequest(MessageBase):
    """
    The "channel monitor" set of messages are used by client agents to indicate
    that they wish to be asynchronously informed of changes in the state or
    values of the process variable of a channel.

    Notes
    -----
    This is currently partially supported by caproto-pva.

    More details on the `wiki <https://github.com/epics-base/pvAccessCPP/wiki/Protocol-Operation-Monitor>`_.
    """
    ID = ApplicationCommand.MONITOR
    subcommand: Optional[MonitorSubcommand] = None

    server_chid: int
    ioid: int

    _fields_ = [
        ('server_chid', ctypes.c_int32),
        ('ioid', ctypes.c_int32),
        ('subcommand', ctypes.c_byte),
    ]
    _subcommand_fields_ = {
        Subcommand.INIT: [
            RequiredField('pv_request', PVRequest),
            OptionalField('queue_size', 'int',
                          OptionalStopMarker.stop,
                          lambda msg, buf: bool(msg.subcommand &
                                                MonitorSubcommand.PIPELINE)),
        ],
        Subcommand.DEFAULT: [],
        MonitorSubcommand.START: [],
        MonitorSubcommand.STOP: [],
        # Subcommand.PIPELINE: [],
        Subcommand.DESTROY: [],
    }


class ChannelMonitorResponse(MessageBase):
    """
    A response to a :class:`ChannelMonitorRequest`.
    """
    ID = ApplicationCommand.MONITOR

    ioid: int
    subcommand: Optional[MonitorSubcommand] = None
    pv_structure_if: FieldDesc
    pv_data: typing.Any
    overrun_bitset: BitSet

    _fields_ = [
        ('ioid', ctypes.c_int32),
        ('subcommand', ctypes.c_byte),
    ]

    @property
    def is_successful(self) -> bool:
        # status_type only on INIT!  Do not mix in _StatusBase.
        status_type = getattr(self, '_status_type', StatusType.OK)
        return status_type in success_status_types

    _subcommand_fields_ = {
        MonitorSubcommand.INIT: [
            RequiredField('status_type', FieldType.int8),
        ] + list(Status._additional_fields_) + [
            SuccessField('pv_structure_if', FieldDesc),
        ],
        MonitorSubcommand.DEFAULT: [
            # `pv_structure_if` is tracked by ioid
            RequiredField('pv_data', DataWithBitSet),
            RequiredField('overrun_bitset', BitSet),
        ],
        # MonitorSubcommand.START: [],
        # MonitorSubcommand.STOP: [],
        MonitorSubcommand.PIPELINE: [
            RequiredField('nfree', FieldType.int32),
        ],
        Subcommand.DESTROY: [],
    }


class ChannelProcessRequest(MessageBase):
    """
    A "channel process" set of messages are used to indicate to the server that
    the computation actions associated with a channel should be executed.

    In EPICS terminology, this means that the channel should be "processed".

    Notes
    -----
    After a process request is successfully initialized, the client can issue
    the actual process request(s).
    """
    ID = ApplicationCommand.PROCESS

    server_chid: int
    ioid: int

    _fields_ = [
        ('server_chid', ctypes.c_int32),
        ('ioid', ctypes.c_int32),
        ('subcommand', ctypes.c_byte),
    ]
    _subcommand_fields_ = {
        Subcommand.INIT: [
            RequiredField('pv_request', PVRequest),
            # TODO_DOCS typo serverStatusIF -> PVRequestIF
        ],
        Subcommand.DEFAULT: [],  # TODO: not PROCESS?
        Subcommand.DESTROY: [],
    }


class ChannelProcessResponse(_StatusBase, MessageBase):
    """
    A response to a :class:`ChannelProcessRequest`.
    """
    ID = ApplicationCommand.PROCESS

    ioid: int

    _fields_ = [
        ('ioid', ctypes.c_int32),
        ('subcommand', ctypes.c_byte),
        ('_status_type', ctypes.c_byte),
    ]

    _subcommand_fields_ = {
        Subcommand.INIT: [],
        Subcommand.DEFAULT: [],  # TODO: not PROCESS?
        Subcommand.DESTROY: [],
    }


class ChannelRpcRequest(MessageBase):
    """
    A remote procedure call request.

    Notes
    -----
    The "channel RPC" set of messages are used to provide remote procedure call
    (RPC) support over pvAccess. After a RPC request is successfully
    initialized, the client can issue actual RPC request(s).

    """
    ID = ApplicationCommand.RPC

    server_chid: int
    ioid: int

    _fields_ = [
        ('server_chid', ctypes.c_int32),
        ('ioid', ctypes.c_int32),
        ('subcommand', ctypes.c_byte),
    ]
    _subcommand_fields_ = {
        Subcommand.INIT: [
            RequiredField('pv_request', PVRequest),
        ],
        Subcommand.DEFAULT: [
            RequiredField('pv_data', FieldDescAndData),
        ],
        Subcommand.DESTROY: [],
    }


class ChannelRpcResponse(_StatusBase, MessageBase):
    ID = ApplicationCommand.PROCESS

    ioid: int
    _status_type: int

    _fields_ = [
        ('ioid', ctypes.c_int32),
        ('subcommand', ctypes.c_byte),
        ('_status_type', ctypes.c_byte),
    ]

    _subcommand_fields_ = {
        Subcommand.INIT: [],
        Subcommand.DEFAULT: [
            SuccessField('pv_response', FieldDescAndData),
        ],
        Subcommand.DESTROY: [],
    }


class OriginTagRequest(_StatusBase, MessageBase):
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
    ID = ApplicationCommand.ORIGIN_TAG


BIG_ENDIAN, LITTLE_ENDIAN = BIG_ENDIAN, LITTLE_ENDIAN  # removed below

class BeaconMessageBE(BeaconMessage, _BE): _fields_ = BeaconMessage._fields_  # noqa
class BeaconMessageLE(BeaconMessage, _LE): _fields_ = BeaconMessage._fields_  # noqa
class EchoBE(Echo, _BE): _fields_ = Echo._fields_  # noqa
class EchoLE(Echo, _LE): _fields_ = Echo._fields_  # noqa
class StatusBE(Status, _BE): _fields_ = Status._fields_  # noqa
class StatusLE(Status, _LE): _fields_ = Status._fields_  # noqa

class ChannelDestroyRequestBE(ChannelDestroyRequest, _BE): _fields_ = ChannelDestroyRequest._fields_  # noqa
class ChannelDestroyRequestLE(ChannelDestroyRequest, _LE): _fields_ = ChannelDestroyRequest._fields_  # noqa
class ChannelDestroyResponseBE(ChannelDestroyResponse, _BE): _fields_ = ChannelDestroyResponse._fields_  # noqa
class ChannelDestroyResponseLE(ChannelDestroyResponse, _LE): _fields_ = ChannelDestroyResponse._fields_  # noqa
class ChannelFieldInfoRequestBE(ChannelFieldInfoRequest, _BE): _fields_ = ChannelFieldInfoRequest._fields_  # noqa
class ChannelFieldInfoRequestLE(ChannelFieldInfoRequest, _LE): _fields_ = ChannelFieldInfoRequest._fields_  # noqa
class ChannelFieldInfoResponseBE(ChannelFieldInfoResponse, _BE): _fields_ = ChannelFieldInfoResponse._fields_  # noqa
class ChannelFieldInfoResponseLE(ChannelFieldInfoResponse, _LE): _fields_ = ChannelFieldInfoResponse._fields_  # noqa
class ChannelGetRequestBE(ChannelGetRequest, _BE): _fields_ = ChannelGetRequest._fields_  # noqa
class ChannelGetRequestLE(ChannelGetRequest, _LE): _fields_ = ChannelGetRequest._fields_  # noqa
class ChannelGetResponseBE(ChannelGetResponse, _BE): _fields_ = ChannelGetResponse._fields_  # noqa
class ChannelGetResponseLE(ChannelGetResponse, _LE): _fields_ = ChannelGetResponse._fields_  # noqa
class ChannelMonitorRequestBE(ChannelMonitorRequest, _BE): _fields_ = ChannelMonitorRequest._fields_  # noqa
class ChannelMonitorRequestLE(ChannelMonitorRequest, _LE): _fields_ = ChannelMonitorRequest._fields_  # noqa
class ChannelMonitorResponseBE(ChannelMonitorResponse, _BE): _fields_ = ChannelMonitorResponse._fields_  # noqa
class ChannelMonitorResponseLE(ChannelMonitorResponse, _LE): _fields_ = ChannelMonitorResponse._fields_  # noqa
class ChannelProcessRequestBE(ChannelProcessRequest, _BE): _fields_ = ChannelProcessRequest._fields_  # noqa
class ChannelProcessRequestLE(ChannelProcessRequest, _LE): _fields_ = ChannelProcessRequest._fields_  # noqa
class ChannelProcessResponseBE(ChannelProcessResponse, _BE): _fields_ = ChannelProcessResponse._fields_  # noqa
class ChannelProcessResponseLE(ChannelProcessResponse, _LE): _fields_ = ChannelProcessResponse._fields_  # noqa
class ChannelPutGetRequestBE(ChannelPutGetRequest, _BE): _fields_ = ChannelPutGetRequest._fields_  # noqa
class ChannelPutGetRequestLE(ChannelPutGetRequest, _LE): _fields_ = ChannelPutGetRequest._fields_  # noqa
class ChannelPutGetResponseBE(ChannelPutGetResponse, _BE): _fields_ = ChannelPutGetResponse._fields_  # noqa
class ChannelPutGetResponseLE(ChannelPutGetResponse, _LE): _fields_ = ChannelPutGetResponse._fields_  # noqa
class ChannelPutRequestBE(ChannelPutRequest, _BE): _fields_ = ChannelPutRequest._fields_  # noqa
class ChannelPutRequestLE(ChannelPutRequest, _LE): _fields_ = ChannelPutRequest._fields_  # noqa
class ChannelPutResponseBE(ChannelPutResponse, _BE): _fields_ = ChannelPutResponse._fields_  # noqa
class ChannelPutResponseLE(ChannelPutResponse, _LE): _fields_ = ChannelPutResponse._fields_  # noqa
class ChannelRpcRequestBE(ChannelRpcRequest, _BE): _fields_ = ChannelRpcRequest._fields_  # noqa
class ChannelRpcRequestLE(ChannelRpcRequest, _LE): _fields_ = ChannelRpcRequest._fields_  # noqa
class ChannelRpcResponseBE(ChannelRpcResponse, _BE): _fields_ = ChannelRpcResponse._fields_  # noqa
class ChannelRpcResponseLE(ChannelRpcResponse, _LE): _fields_ = ChannelRpcResponse._fields_  # noqa
class ConnectionValidatedResponseBE(ConnectionValidatedResponse, _BE): _fields_ = ConnectionValidatedResponse._fields_  # noqa
class ConnectionValidatedResponseLE(ConnectionValidatedResponse, _LE): _fields_ = ConnectionValidatedResponse._fields_  # noqa
class ConnectionValidationRequestBE(ConnectionValidationRequest, _BE): _fields_ = ConnectionValidationRequest._fields_  # noqa
class ConnectionValidationRequestLE(ConnectionValidationRequest, _LE): _fields_ = ConnectionValidationRequest._fields_  # noqa
class ConnectionValidationResponseBE(ConnectionValidationResponse, _BE): _fields_ = ConnectionValidationResponse._fields_  # noqa
class ConnectionValidationResponseLE(ConnectionValidationResponse, _LE): _fields_ = ConnectionValidationResponse._fields_  # noqa
class CreateChannelRequestBE(CreateChannelRequest, _BE): _fields_ = CreateChannelRequest._fields_  # noqa
class CreateChannelRequestLE(CreateChannelRequest, _LE): _fields_ = CreateChannelRequest._fields_  # noqa
class CreateChannelResponseBE(CreateChannelResponse, _BE): _fields_ = CreateChannelResponse._fields_  # noqa
class CreateChannelResponseLE(CreateChannelResponse, _LE): _fields_ = CreateChannelResponse._fields_  # noqa
class SearchRequestBE(SearchRequest, _BE): _fields_ = SearchRequest._fields_  # noqa
class SearchRequestLE(SearchRequest, _LE): _fields_ = SearchRequest._fields_  # noqa
class SearchResponseBE(SearchResponse, _BE): _fields_ = SearchResponse._fields_  # noqa
class SearchResponseLE(SearchResponse, _LE): _fields_ = SearchResponse._fields_  # noqa


FROM_CLIENT, FROM_SERVER = MessageFlags.FROM_CLIENT, MessageFlags.FROM_SERVER

messages = {
    # LITTLE ENDIAN, CLIENT -> SERVER
    (LITTLE_ENDIAN, FROM_CLIENT): {
        ApplicationCommand.BEACON: BeaconMessageLE,
        ApplicationCommand.CONNECTION_VALIDATION: ConnectionValidationResponseLE,
        ApplicationCommand.ECHO: EchoLE,
        ApplicationCommand.SEARCH_REQUEST: SearchRequestLE,
        ApplicationCommand.CREATE_CHANNEL: CreateChannelRequestLE,
        ApplicationCommand.GET: ChannelGetRequestLE,
        ApplicationCommand.GET_FIELD: ChannelFieldInfoRequestLE,
        ApplicationCommand.DESTROY_CHANNEL: ChannelDestroyRequestLE,
        ApplicationCommand.PUT: ChannelPutRequestLE,
        ApplicationCommand.PUT_GET: ChannelPutGetRequestLE,
        ApplicationCommand.MONITOR: ChannelMonitorRequestLE,
        ApplicationCommand.PROCESS: ChannelProcessRequestLE,
        ApplicationCommand.RPC: ChannelRpcRequestLE,
    },

    # BIG ENDIAN, CLIENT -> SERVER
    (BIG_ENDIAN, FROM_CLIENT): {
        ApplicationCommand.BEACON: BeaconMessageBE,
        ApplicationCommand.CONNECTION_VALIDATION: ConnectionValidationResponseBE,
        ApplicationCommand.ECHO: EchoBE,
        ApplicationCommand.SEARCH_REQUEST: SearchRequestBE,
        ApplicationCommand.CREATE_CHANNEL: CreateChannelRequestBE,
        ApplicationCommand.GET: ChannelGetRequestBE,
        ApplicationCommand.GET_FIELD: ChannelFieldInfoRequestBE,
        ApplicationCommand.DESTROY_CHANNEL: ChannelDestroyRequestBE,
        ApplicationCommand.PUT: ChannelPutRequestBE,
        ApplicationCommand.PUT_GET: ChannelPutGetRequestBE,
        ApplicationCommand.MONITOR: ChannelMonitorRequestBE,
        ApplicationCommand.PROCESS: ChannelProcessRequestBE,
        ApplicationCommand.RPC: ChannelRpcRequestBE,
    },

    # LITTLE ENDIAN, SERVER -> CLIENT
    (LITTLE_ENDIAN, FROM_SERVER): {
        ControlCommand.SET_ENDIANESS: SetByteOrder,
        ApplicationCommand.BEACON: BeaconMessageLE,
        ApplicationCommand.CONNECTION_VALIDATION: ConnectionValidationRequestLE,
        ApplicationCommand.ECHO: EchoLE,
        ApplicationCommand.CONNECTION_VALIDATED: ConnectionValidatedResponseLE,
        ApplicationCommand.SEARCH_RESPONSE: SearchResponseLE,
        ApplicationCommand.CREATE_CHANNEL: CreateChannelResponseLE,
        ApplicationCommand.GET: ChannelGetResponseLE,
        ApplicationCommand.GET_FIELD: ChannelFieldInfoResponseLE,
        ApplicationCommand.DESTROY_CHANNEL: ChannelDestroyResponseLE,
        ApplicationCommand.PUT: ChannelPutResponseLE,
        ApplicationCommand.PUT_GET: ChannelPutGetResponseLE,
        ApplicationCommand.MONITOR: ChannelMonitorResponseLE,
        ApplicationCommand.PROCESS: ChannelProcessResponseLE,
        ApplicationCommand.RPC: ChannelRpcResponseLE,
    },

    # BIG ENDIAN, SERVER -> CLIENT
    (BIG_ENDIAN, FROM_SERVER): {
        ControlCommand.SET_ENDIANESS: SetByteOrder,
        ApplicationCommand.BEACON: BeaconMessageBE,
        ApplicationCommand.CONNECTION_VALIDATION: ConnectionValidationRequestBE,
        ApplicationCommand.ECHO: EchoBE,
        ApplicationCommand.CONNECTION_VALIDATED: ConnectionValidatedResponseBE,
        ApplicationCommand.SEARCH_RESPONSE: SearchResponseBE,
        ApplicationCommand.CREATE_CHANNEL: CreateChannelResponseBE,
        ApplicationCommand.GET: ChannelGetResponseBE,
        ApplicationCommand.GET_FIELD: ChannelFieldInfoResponseBE,
        ApplicationCommand.DESTROY_CHANNEL: ChannelDestroyResponseBE,
        ApplicationCommand.PUT: ChannelPutResponseBE,
        ApplicationCommand.PUT_GET: ChannelPutGetResponseBE,
        ApplicationCommand.MONITOR: ChannelMonitorResponseBE,
        ApplicationCommand.PROCESS: ChannelProcessResponseBE,
        ApplicationCommand.RPC: ChannelRpcResponseBE,
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
        return SegmentDeserialized(
            data=Deserialized(data=ChannelLifeCycle.NEED_DATA, buffer=data,
                              offset=0),
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
