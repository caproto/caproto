import enum
import ctypes
import logging

from collections import namedtuple

from .const import (LITTLE_ENDIAN, BIG_ENDIAN)
from .types import (TypeCode, Decoded)
from .serialization import (serialize_message_field, deserialize_message_field,
                            SerializeCache, NullCache)
from .types import (c_byte, c_ubyte, c_short, c_ushort, c_int, c_uint)
from .pvrequest import pvrequest_string_to_structure
from . import introspection as intro
from .utils import (ip_to_ubyte_array, ubyte_array_to_ip, CLIENT, SERVER,
                    NEED_DATA)


logger = logging.getLogger(__name__)


basic_type_definitions = (
    '''
    struct channel_with_id
        int id
        string channel_name
    ''',
)

basic_types = {}
intro.update_namespace_with_definitions(basic_types, basic_type_definitions,
                                        logger=logger)


class QOS(enum.IntEnum):
    # Default behavior.
    QOS_DEFAULT = 0x00
    # Require reply (acknowledgment for reliable operation).
    QOS_REPLY_REQUIRED = 0x01
    # Best-effort option (no reply).
    QOS_BESY_EFFORT = 0x02
    # Process option.
    QOS_PROCESS = 0x04
    # Initialize option.
    QOS_INIT = 0x08
    # Destroy option.
    QOS_DESTROY = 0x10
    # Share data option.
    QOS_SHARE = 0x20
    # Get.
    QOS_GET = 0x40
    # Get-put.
    QOS_GET_PUT = 0x80


class ApplicationCommands(enum.IntEnum):
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
    MULTIPLE_DATA = 19
    RPC = 20
    CANCEL_REQUEST = 21
    ORIGIN_TAG = 22


class ControlCommands(enum.Enum):
    SET_MARKER = 0
    ACK_MARKER = 1
    SET_ENDIANESS = 2


class GetSubcommands(enum.IntEnum):
    INIT = 0x08
    GET = 0x40
    DESTROY = 0x50


class SearchFlags(enum.IntFlag):
    # 0-bit for replyRequired, 7-th bit for "sent as unicast" (1)/"sent as
    # broadcast/multicast" (0)
    reply_required = 0b00000001
    unicast = 0b10000000
    broadcast = 0b00000000


class EndianSetting(enum.IntEnum):
    use_server_byte_order = 0x00000000
    use_message_byte_order = 0xffffffff


class MessageTypeFlag(enum.IntFlag):
    APP_MESSAGE = 0
    CONTROL_MESSAGE = 1


class SegmentFlag(enum.IntFlag):
    UNSEGMENTED = 0b00
    FIRST = 0b01
    LAST = 0b10
    MIDDLE = 0b11


class DirectionFlag(enum.IntEnum):
    FROM_CLIENT = 0
    FROM_SERVER = 1


class EndianFlag(enum.IntFlag):
    LITTLE_ENDIAN = 0
    BIG_ENDIAN = 1


_flag_masks = {
    # flag: (rshift, mask)
    MessageTypeFlag: (0, 1),
    SegmentFlag: (4, 3),
    DirectionFlag: (6, 1),
    EndianFlag: (7, 1),
}


class StatusType(enum.IntEnum):
    OK = -1
    OK_VERBOSE = 0
    WARNING = 1
    ERROR = 2
    FATAL = 3


class OptionalStopMarker(enum.IntEnum):
    stop = True
    continue_ = False


success_status_types = {StatusType.OK,
                        StatusType.OK_VERBOSE,
                        StatusType.WARNING
                        }

default_pvrequest = 'record[]field()'


def _success_condition(msg, buf):
    return (msg.status_type in success_status_types)


class MessageBase:
    _pack_ = 1

    def __repr__(self):
        info = ', '.join('{}={!r}'.format(field, getattr(self, field))
                         for field, type_ in self._fields_)
        return '{}({})'.format(type(self).__name__, info)

    def serialize(self, *, default_pvrequest=default_pvrequest,
                  our_cache=None, their_cache=None, user_types=None):
        if not hasattr(self, '_additional_fields_'):
            return bytes(self)
        if user_types is None:
            user_types = basic_types

        buf = [bytes(self)]

        interfaces = {}
        endian = self._ENDIAN
        cache = SerializeCache(ours=our_cache, theirs=their_cache,
                               user_types=basic_types, ioid_interfaces={})

        for field_info in self._additional_fields_:
            if isinstance(field_info, (OptionalField, OptionalInterfaceField)):
                if field_info.condition is not None:
                    if not field_info.condition(self, buf):
                        break

            value = getattr(self, field_info.name)
            interface = None
            if field_info.type == 'PVRequest':
                if not value:
                    value = default_pvrequest
                struct = pvrequest_string_to_structure(value)
                interfaces[field_info.data_field] = struct
            elif field_info.type == 'PVField':
                interface = interfaces[field_info.name]

            def _serialize(v):
                serialized = serialize_message_field(
                    field_info.type, field_info.name, v, nested_types={},
                    interface=interface, endian=endian, cache=cache)
                return serialized

            if not isinstance(field_info, NonstandardArrayField):
                buf.extend(_serialize(value))
            else:
                count = getattr(self, field_info.count_name)
                assert len(value) == count
                for v in value:
                    buf.extend(_serialize(v))

        return b''.join(buf)

    @classmethod
    def deserialize(cls, buf, *, cache=NullCache):
        base_size = ctypes.sizeof(cls)
        buflen = len(buf) - base_size
        buf = memoryview(buf)
        msg = cls.from_buffer(buf[:base_size])

        offset = base_size
        buf = buf[offset:]

        if not hasattr(cls, '_additional_fields_'):
            return Decoded(data=msg, buffer=buf, offset=offset)

        for field_info in cls._additional_fields_:
            if isinstance(field_info, (OptionalField, OptionalInterfaceField)):
                if not buflen:
                    break
                if field_info.condition is not None:
                    if not field_info.condition(msg, buf):
                        if field_info.stop == OptionalStopMarker.stop:
                            break
                        else:
                            continue

            interface = None

            if field_info.type == 'PVField':
                try:
                    interface = cache.ioid_interfaces[msg.ioid]
                except AttributeError:
                    raise RuntimeError(
                        f'Think through the caching more, @klauer '
                        f'{field_info.name!r}') from None
                except KeyError:
                    raise ValueError(
                        f'Interface unspecified for PVField key '
                        f'{field_info.name!r}') from None

            is_nonstandard_array = isinstance(field_info,
                                              NonstandardArrayField)
            count = (1 if not is_nonstandard_array
                     else getattr(msg, field_info.count_name))
            values = []

            for i in range(count):
                value, buf, off = deserialize_message_field(
                    buf=buf, type_name=field_info.type,
                    field_name=field_info.name, nested_types={},
                    interface=interface, endian=cls._ENDIAN, cache=cache,
                )

                offset += off
                buflen -= off
                if is_nonstandard_array:
                    values.append(value)
                else:
                    setattr(msg, field_info.name, value)

            if is_nonstandard_array:
                setattr(msg, field_info.name, values)

        return Decoded(data=msg, buffer=buf, offset=offset)


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


RequiredField = namedtuple('RequiredField', 'name type')
OptionalField = namedtuple('OptionalField', 'name type stop condition')
NonstandardArrayField = namedtuple('OptionalField', 'name type count_name')
RequiredInterfaceField = namedtuple('RequiredField', 'name type data_field')
OptionalInterfaceField = namedtuple('OptionalInterfaceField',
                                    'name type stop condition data_field')


def _make_endian(cls, endian):
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

    if hasattr(endian_cls, '_additional_fields_'):
        for field_info in endian_cls._additional_fields_:
            setattr(endian_cls, field_info.name, None)

    cls._ENDIAN = None
    endian_cls._ENDIAN = (LITTLE_ENDIAN
                          if endian_base is ctypes.LittleEndianStructure
                          else BIG_ENDIAN)
    return endian_cls


class MessageHeader(MessageBase):
    _fields_ = [
        ('magic', c_ubyte),
        ('version', c_ubyte),
        ('flags', c_ubyte),
        ('message_command', c_ubyte),
        ('payload_size', c_uint),
    ]

    def __init__(self, *, message_type, direction, endian, command,
                 payload_size, segment=SegmentFlag.UNSEGMENTED):
        self.magic = 0xca
        self.version = 1

        self.flags = MessageHeader.flag_from_enums(message_type, direction,
                                                   endian, segment)
        self.message_command = command
        self.payload_size = payload_size

    @staticmethod
    def flag_from_enums(message_type, direction, endian, segment):
        # be a bit lax on these for now...
        if endian == LITTLE_ENDIAN:
            endian = EndianFlag.LITTLE_ENDIAN
        elif endian == BIG_ENDIAN:
            endian = EndianFlag.BIG_ENDIAN

        values = [(MessageTypeFlag, message_type),
                  (DirectionFlag, direction),
                  (EndianFlag, endian),
                  (SegmentFlag, segment),
                  ]
        masks = [_flag_masks[cls] for cls, value in values]
        return sum(((value & mask) << shift)
                   for (cls, value), (shift, mask) in zip(values, masks))

    @property
    def message_type(self):
        'Message type flag'
        rshift, mask = _flag_masks[MessageTypeFlag]
        return MessageTypeFlag((self.flags >> rshift) & mask)

    @property
    def segment(self):
        'Message segment flag'
        rshift, mask = _flag_masks[SegmentFlag]
        return SegmentFlag((self.flags >> rshift) & mask)

    @property
    def flags_as_enums(self):
        flags = self.flags
        return tuple(cls((flags >> rshift) & mask)
                     for cls, (rshift, mask)
                     in _flag_masks.items())

    @property
    def direction(self):
        'Direction of message'
        rshift, mask = _flag_masks[DirectionFlag]
        return DirectionFlag((self.flags >> rshift) & mask)

    @property
    def valid(self):
        return self.magic == 0xca

    @property
    def byte_order(self):
        'Byte order/endianness of message'
        rshift, mask = _flag_masks[EndianFlag]
        flag = EndianFlag((self.flags >> rshift) & mask)
        return (LITTLE_ENDIAN if flag == EndianFlag.LITTLE_ENDIAN
                else BIG_ENDIAN)

    def get_message(self, direction, *, use_fixed_byte_order=None):
        byte_order = (use_fixed_byte_order
                      if use_fixed_byte_order is not None
                      else self.byte_order)
        message_type = self.message_type

        if message_type == MessageTypeFlag.APP_MESSAGE:
            command = ApplicationCommands(self.message_command)
        else:
            command = ControlCommands(self.message_command)

        key = (byte_order, direction, command)

        try:
            return messages[key]
        except KeyError as ex:
            direction = DirectionFlag(direction).name
            raise KeyError(
                f'{ex} where message_type={message_type} '
                f'byte order={byte_order} direction={direction} '
                f'command={command!r}'
            ) from None


MessageHeaderLE = _make_endian(MessageHeader, LITTLE_ENDIAN)
MessageHeaderBE = _make_endian(MessageHeader, BIG_ENDIAN)
_MessageHeaderSize = ctypes.sizeof(MessageHeaderLE)


class Status(ExtendedMessageBase):
    _fields_ = [('status_type', c_byte)]
    _additional_fields_ = [
        OptionalField('message', 'string', OptionalStopMarker.continue_,
                      lambda msg, buf: msg.status_type != StatusType.OK),
        OptionalField('call_tree', 'string', OptionalStopMarker.continue_,
                      lambda msg, buf: msg.status_type != StatusType.OK),
    ]


class BeaconMessage(ExtendedMessageBase):
    ID = ApplicationCommands.BEACON
    # FieldDesc serverStatusIF;
    # [if serverStatusIF != NULL_TYPE_CODE] PVField serverStatus;
    _fields_ = [
        ('guid', c_ubyte * 12),
        ('flags', c_ubyte),
        ('beacon_sequence_id', c_ubyte),
        ('change_count', c_ushort),  # TODO_DOCS
        ('server_address', c_ubyte * 16),
        ('server_port', c_ushort),
    ]

    _additional_fields_ = [
        RequiredField('protocol', 'string'),
        OptionalField('server_status_if', 'FieldDesc',
                      OptionalStopMarker.continue_, None),
        OptionalField('server_status', 'PVField', OptionalStopMarker.continue_,
                      lambda s: (s.server_status_if !=
                                 TypeCode.NULL_TYPE_CODE)),
    ]


# NOTE: the following control messages do not have any elements quick require
# an endian setting. They are arbitrarily set to little-endian here for all
# platforms.

class SetMarker(MessageHeaderLE):
    ID = ControlCommands.SET_MARKER


class AcknowledgeMarker(MessageHeaderLE):
    ID = ControlCommands.ACK_MARKER


class SetByteOrder(MessageHeaderLE):
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


class ConnectionValidationRequest(ExtendedMessageBase):
    ID = ApplicationCommands.CONNECTION_VALIDATION

    _fields_ = [
        ('server_buffer_size', c_int),
        ('server_registry_size', c_short),
    ]

    _additional_fields_ = [
        RequiredField('auth_nz', 'string[]'),
    ]


class ConnectionValidationResponse(ExtendedMessageBase):
    ID = ApplicationCommands.CONNECTION_VALIDATION

    _fields_ = [
        ('client_buffer_size', c_int),
        ('client_registry_size', c_short),
        ('connection_qos', c_short),
    ]

    _additional_fields_ = [
        RequiredField('auth_nz', 'string'),
    ]


class Echo(ExtendedMessageBase):
    ID = ApplicationCommands.ECHO
    _additional_fields_ = [
        RequiredField('payload', 'byte[]'),
    ]


class ConnectionValidatedResponse(Status):
    ID = ApplicationCommands.CONNECTION_VALIDATED


class SearchRequest(ExtendedMessageBase):
    ID = ApplicationCommands.SEARCH_REQUEST

    _fields_ = [
        ('sequence_id', c_int),
        ('flags', c_ubyte),
        ('reserved', c_ubyte * 3),
        ('_response_address', c_ubyte * 16),
        ('response_port', c_ushort),
    ]

    _additional_fields_ = [
        RequiredField('protocols', 'string[]'),
        # TODO custom handling as this expects a SHORT count before the number
        # of arrays.
        RequiredField('channel_count', 'ushort'),
        NonstandardArrayField('channels', 'channel_with_id',
                              count_name='channel_count'),
        # if it were implemented as expected, this would be all that's
        # necessary:
        # RequiredField('channels', 'channel_with_id[]'),
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
        # well, not that much easier for now...
        raise NotImplementedError()

    return property(fget, fset, doc=doc)


class SearchResponse(ExtendedMessageBase):
    ID = ApplicationCommands.SEARCH_RESPONSE

    _fields_ = [
        ('_guid', c_ubyte * 12),
        ('sequence_id', c_int),
        ('_server_address', c_ubyte * 16),
        ('server_port', c_ushort),
    ]

    _additional_fields_ = [
        RequiredField('protocol', 'string'),
        # TODO_DOCS found is not 'int' but 'byte'
        RequiredField('found', 'byte'),
        # TODO_DOCS search_instance_ids array is prefixed by a short length
        #  i.e., a nonstandard array serialization format
        # RequiredField('search_instance_ids', 'int[]'),
        RequiredField('search_count', 'short'),
        NonstandardArrayField('search_instance_ids', 'int',
                              count_name='search_count'),
    ]

    guid = _array_property('_guid', 'GUID for server')

    @property
    def server_address(self):
        return ubyte_array_to_ip(self._server_address)

    @server_address.setter
    def server_address(self, value):
        self._server_address = ip_to_ubyte_array(value)


class CreateChannelRequest(ExtendedMessageBase):
    ID = ApplicationCommands.CREATE_CHANNEL

    _additional_fields_ = [
        # RequiredField('channels', 'channel_with_id[]'),
        # ^-- DOCS_TODO indicate this as accurate, but it is not.
        RequiredField('count', 'ushort'),
        # ^-- DOCS_TODO is not documented as such, and must be 1
        RequiredField('channels', 'channel_with_id'),
    ]


class CreateChannelResponse(ExtendedMessageBase):
    ID = ApplicationCommands.CREATE_CHANNEL

    _fields_ = [('client_chid', c_int),
                ('server_chid', c_int),
                ('status_type', c_byte),
                ]
    _additional_fields_ = Status._additional_fields_ + [
        # TODO access rights aren't sent, even if status_type is OK
        OptionalField('access_rights', 'short', OptionalStopMarker.stop,
                      _success_condition
                      ),
    ]


class ChannelDestroyRequest(MessageBase):
    ID = ApplicationCommands.DESTROY_CHANNEL
    _fields_ = [('client_chid', c_int),
                ('server_chid', c_int),
                ]


class ChannelDestroyResponse(ExtendedMessageBase):
    ID = ApplicationCommands.DESTROY_CHANNEL

    _fields_ = [('client_chid', c_int),
                ('server_chid', c_int),
                ('status_type', c_byte),
                ]

    _additional_fields_ = Status._additional_fields_


def _is_get_init_condition(msg, buf):
    return msg.subcommand == GetSubcommands.INIT


class ChannelGetRequest(ExtendedMessageBase):
    ID = ApplicationCommands.GET

    _fields_ = [('server_chid', c_int),
                ('ioid', c_int),
                ('subcommand', c_byte),
                ]

    _additional_fields_ = [
        OptionalInterfaceField('pv_request_if', 'PVRequest',
                               stop=OptionalStopMarker.stop,
                               condition=_is_get_init_condition,
                               data_field='pv_request'),
        OptionalField('pv_request', 'PVField',
                      stop=OptionalStopMarker.stop,
                      condition=_is_get_init_condition,
                      ),
    ]


def _get_response_init_cond(msg, buf):
    return ((msg.status_type in success_status_types) and
            msg.subcommand == GetSubcommands.INIT)


def _get_response_get_cond(msg, buf):
    return ((msg.status_type in success_status_types) and
            msg.subcommand == GetSubcommands.GET)


class ChannelGetResponse(ExtendedMessageBase):
    ID = ApplicationCommands.GET

    _fields_ = [('ioid', c_int),
                ('subcommand', c_byte),
                ('status_type', c_byte),
                ]

    _additional_fields_ = Status._additional_fields_ + [
        # TODO some structure to break up subcommands into separate responses
        # for now, this is handled by the optional.conditions

        # init:
        OptionalInterfaceField('pv_structure_if', 'FieldDesc',
                               stop=OptionalStopMarker.continue_,
                               condition=_get_response_init_cond,
                               data_field='pv_request'),

        # get:
        OptionalField('changed_bit_set', 'BitSet',
                      stop=OptionalStopMarker.continue_,
                      condition=_get_response_get_cond),
        OptionalField('pv_data', 'PVField',
                      stop=OptionalStopMarker.stop,
                      condition=_get_response_get_cond),
    ]


class ChannelFieldInfoRequest(ExtendedMessageBase):
    ID = ApplicationCommands.GET_FIELD

    _fields_ = [('server_chid', c_int),
                ('ioid', c_int),
                ]
    _additional_fields_ = [
        RequiredField('sub_field_name', 'string'),
    ]


class ChannelFieldInfoResponse(ExtendedMessageBase):
    ID = ApplicationCommands.GET_FIELD

    _fields_ = [('ioid', c_int),
                ('status_type', c_byte),
                ]
    _additional_fields_ = Status._additional_fields_ + [
        OptionalField('field_if', 'FieldDesc', OptionalStopMarker.stop,
                      _success_condition
                      ),
    ]


AppCmd = ApplicationCommands
CtrlCmd = ControlCommands

BE, LE = BIG_ENDIAN, LITTLE_ENDIAN  # removed below
StatusLE = _make_endian(Status, LE)
StatusBE = _make_endian(Status, BE)
BeaconMessageLE = _make_endian(BeaconMessage, LE)
BeaconMessageBE = _make_endian(BeaconMessage, BE)
ConnectionValidationRequestLE = _make_endian(ConnectionValidationRequest, LE)
ConnectionValidationRequestBE = _make_endian(ConnectionValidationRequest, BE)
EchoLE = _make_endian(Echo, LE)
EchoBE = _make_endian(Echo, BE)
ConnectionValidatedResponseLE = _make_endian(ConnectionValidatedResponse, LE)
ConnectionValidatedResponseBE = _make_endian(ConnectionValidatedResponse, BE)
SearchResponseLE = _make_endian(SearchResponse, LE)
SearchResponseBE = _make_endian(SearchResponse, BE)
CreateChannelResponseLE = _make_endian(CreateChannelResponse, LE)
CreateChannelResponseBE = _make_endian(CreateChannelResponse, BE)
ChannelGetResponseLE = _make_endian(ChannelGetResponse, LE)
ChannelGetResponseBE = _make_endian(ChannelGetResponse, BE)
ChannelFieldInfoResponseLE = _make_endian(ChannelFieldInfoResponse, LE)
ChannelFieldInfoResponseBE = _make_endian(ChannelFieldInfoResponse, BE)
BeaconMessageLE = _make_endian(BeaconMessage, LE)
BeaconMessageBE = _make_endian(BeaconMessage, BE)
ConnectionValidationResponseLE = _make_endian(ConnectionValidationResponse, LE)
ConnectionValidationResponseBE = _make_endian(ConnectionValidationResponse, BE)
EchoLE = _make_endian(Echo, LE)
EchoBE = _make_endian(Echo, BE)
SearchRequestLE = _make_endian(SearchRequest, LE)
SearchRequestBE = _make_endian(SearchRequest, BE)
CreateChannelRequestLE = _make_endian(CreateChannelRequest, LE)
CreateChannelRequestBE = _make_endian(CreateChannelRequest, BE)
ChannelGetRequestLE = _make_endian(ChannelGetRequest, LE)
ChannelGetRequestBE = _make_endian(ChannelGetRequest, BE)
ChannelDestroyRequestLE = _make_endian(ChannelDestroyRequest, LE)
ChannelDestroyRequestBE = _make_endian(ChannelDestroyRequest, BE)
ChannelDestroyResponseLE = _make_endian(ChannelDestroyResponse, LE)
ChannelDestroyResponseBE = _make_endian(ChannelDestroyResponse, BE)
ChannelFieldInfoRequestLE = _make_endian(ChannelFieldInfoRequest, LE)
ChannelFieldInfoRequestBE = _make_endian(ChannelFieldInfoRequest, BE)

FROM_CLIENT, FROM_SERVER = DirectionFlag.FROM_CLIENT, DirectionFlag.FROM_SERVER

messages = {
    # LITTLE ENDIAN, SERVER -> CLIENT
    (LE, FROM_SERVER, CtrlCmd.SET_ENDIANESS): SetByteOrder,
    (LE, FROM_SERVER, AppCmd.BEACON): BeaconMessageLE,
    (LE, FROM_SERVER, AppCmd.CONNECTION_VALIDATION): ConnectionValidationRequestLE,
    (LE, FROM_SERVER, AppCmd.ECHO): EchoLE,
    (LE, FROM_SERVER, AppCmd.CONNECTION_VALIDATED): ConnectionValidatedResponseLE,
    (LE, FROM_SERVER, AppCmd.SEARCH_RESPONSE): SearchResponseLE,
    (LE, FROM_SERVER, AppCmd.CREATE_CHANNEL): CreateChannelResponseLE,
    (LE, FROM_SERVER, AppCmd.GET): ChannelGetResponseLE,
    (LE, FROM_SERVER, AppCmd.GET_FIELD): ChannelFieldInfoResponseLE,
    (LE, FROM_SERVER, AppCmd.DESTROY_CHANNEL): ChannelDestroyResponseLE,

    # LITTLE ENDIAN, CLIENT -> SERVER
    (LE, FROM_CLIENT, AppCmd.BEACON): BeaconMessageLE,
    (LE, FROM_CLIENT, AppCmd.CONNECTION_VALIDATION): ConnectionValidationResponseLE,
    (LE, FROM_CLIENT, AppCmd.ECHO): EchoLE,
    (LE, FROM_CLIENT, AppCmd.SEARCH_REQUEST): SearchRequestLE,
    (LE, FROM_CLIENT, AppCmd.CREATE_CHANNEL): CreateChannelRequestLE,
    (LE, FROM_CLIENT, AppCmd.GET): ChannelGetRequestLE,
    (LE, FROM_CLIENT, AppCmd.GET_FIELD): ChannelFieldInfoRequestLE,
    (LE, FROM_CLIENT, AppCmd.DESTROY_CHANNEL): ChannelDestroyRequestLE,

    # BIG ENDIAN, SERVER -> CLIENT
    (BE, FROM_SERVER, CtrlCmd.SET_ENDIANESS): SetByteOrder,
    (BE, FROM_SERVER, AppCmd.BEACON): BeaconMessageBE,
    (BE, FROM_SERVER, AppCmd.CONNECTION_VALIDATION): ConnectionValidationRequestBE,
    (BE, FROM_SERVER, AppCmd.ECHO): EchoBE,
    (BE, FROM_SERVER, AppCmd.CONNECTION_VALIDATED): ConnectionValidatedResponseBE,
    (BE, FROM_SERVER, AppCmd.SEARCH_RESPONSE): SearchResponseBE,
    (BE, FROM_SERVER, AppCmd.CREATE_CHANNEL): CreateChannelResponseBE,
    (BE, FROM_SERVER, AppCmd.GET): ChannelGetResponseBE,
    (BE, FROM_SERVER, AppCmd.GET_FIELD): ChannelFieldInfoResponseBE,
    (BE, FROM_SERVER, AppCmd.DESTROY_CHANNEL): ChannelDestroyResponseBE,

    # BIG ENDIAN, CLIENT -> SERVER
    (BE, FROM_CLIENT, AppCmd.BEACON): BeaconMessageBE,
    (BE, FROM_CLIENT, AppCmd.CONNECTION_VALIDATION): ConnectionValidationResponseBE,
    (BE, FROM_CLIENT, AppCmd.ECHO): EchoBE,
    (BE, FROM_CLIENT, AppCmd.SEARCH_REQUEST): SearchRequestBE,
    (BE, FROM_CLIENT, AppCmd.CREATE_CHANNEL): CreateChannelRequestBE,
    (BE, FROM_CLIENT, AppCmd.GET): ChannelGetRequestBE,
    (BE, FROM_CLIENT, AppCmd.GET_FIELD): ChannelFieldInfoRequestBE,
    (BE, FROM_CLIENT, AppCmd.DESTROY_CHANNEL): ChannelDestroyRequestBE,
}


def _get_grouped(start_key):
    return {key[-1]: cls
            for key, cls in messages.items()
            if key[:len(start_key)] == start_key
            }


messages_grouped = {
    (LE, FROM_CLIENT): _get_grouped((LE, FROM_CLIENT)),
    (BE, FROM_CLIENT): _get_grouped((BE, FROM_CLIENT)),
    (LE, FROM_SERVER): _get_grouped((LE, FROM_SERVER)),
    (BE, FROM_SERVER): _get_grouped((BE, FROM_SERVER)),
}

del AppCmd
del CtrlCmd
del LE
del BE


def read_datagram(data, address, role, *, fixed_byte_order=None,
                  cache=NullCache):
    "Parse bytes from one datagram into one or more commands."
    buf = bytearray(data)
    commands = []
    offset = 0
    direction_flag = (DirectionFlag.FROM_SERVER
                      if role == SERVER
                      else DirectionFlag.FROM_CLIENT)

    while buf:
        header, buf, off = MessageHeaderLE.deserialize(buf, cache=cache)
        offset += off

        msg_class = header.get_message(
            direction_flag, use_fixed_byte_order=fixed_byte_order)
        msg, buf, off = msg_class.deserialize(buf, cache=cache)
        offset += off

        commands.append(msg)

    return commands


def header_from_wire(data, byte_order):
    if byte_order is not None:
        # Use a fixed byte order, ignoring header flags
        header_cls = (MessageHeaderLE
                      if byte_order == LITTLE_ENDIAN
                      else MessageHeaderBE)
        header = header_cls.from_buffer(data)
        assert header.valid
        return header

    # Guess little-endian, but fall back to big-endian if wrong.
    header = MessageHeaderLE.from_buffer(data)
    if header.byte_order != LITTLE_ENDIAN:
        header = MessageHeaderBE.from_buffer(data)

    assert header.valid
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
        return header, 0, SegmentFlag.UNSEGMENTED

    total_size = _MessageHeaderSize + header.payload_size
    if header.segment != SegmentFlag.UNSEGMENTED:
        # At the very least, we need more than one header...
        raise NotImplementedError('TODO')  # see simple_client.py
    else:
        # Do we have all the bytes in the payload?
        if data_len < total_size:
            return header, total_size - data_len, SegmentFlag.UNSEGMENTED
        return header, 0, SegmentFlag.UNSEGMENTED


def read_from_bytestream(data, role, cache, *, byte_order=None):
    '''
    Parameters
    ----------
    data
    role
        Their role
    cache : dict
        Serialization cache
    byte_order : LITTLE_ENDIAN or BIG_ENDIAN, optional
        Fixed byte order if server message endianness is to be interpreted on a
        message-by-message basis.

    Returns
    -------
    (remaining_data, command, consumed, num_bytes_needed)
        if more data is required, NEED_DATA will be returned in place of
        `command`
    '''
    direction = (DirectionFlag.FROM_SERVER
                 if role == SERVER
                 else DirectionFlag.FROM_CLIENT)

    header, num_bytes_needed, segmented = bytes_needed_for_command(
        data, direction, cache=cache, byte_order=byte_order)

    if num_bytes_needed > 0:
        return data, NEED_DATA, 0, num_bytes_needed

    msg_class = header.get_message(direction=direction,
                                   use_fixed_byte_order=byte_order)

    if issubclass(msg_class, (SetByteOrder, )):
        total_size = _MessageHeaderSize
        offset = _MessageHeaderSize
        data = memoryview(data)
        next_data = data[offset:]
        return bytearray(next_data), msg_class.from_buffer(data), offset, 0

    # Receive the buffer (zero-copy).
    data = bytearray(data)
    offset = _MessageHeaderSize

    cmd, data, off = msg_class.deserialize(memoryview(data)[offset:],
                                           cache=cache)

    offset += off

    cmd.header = header
    # Buffer is advanced automatically by deserialize()
    return bytearray(data), cmd, offset, 0
