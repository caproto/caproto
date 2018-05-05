import enum
import ctypes
import logging
import inspect
import ipaddress

from collections import namedtuple

from .const import (LITTLE_ENDIAN, BIG_ENDIAN)
from .types import (TypeCode, Decoded)
from .serialization import (serialize_message_field, deserialize_message_field,
                            SerializeCache)
from . import (introspection as intro)
from .types import (c_byte, c_ubyte, c_short, c_ushort, c_int, c_uint)
from .pvrequest import pvrequest_string_to_structure


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


class ControlCommands(enum.IntEnum):
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


class DirectionFlag(enum.IntFlag):
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


success_status_types = (StatusType.OK, StatusType.OK_VERBOSE,
                        StatusType.WARNING)

default_pvrequest = 'record[]field()'


def _success_condition(msg, buf):
    return (msg.status_type in success_status_types)


def _ip_to_ubyte_array(ip):
    'Convert an IPv4 or IPv6 to a c_ubyte*16 array'
    addr = ipaddress.ip_address(ip)
    packed = addr.packed
    if len(packed) == 4:
        # case of IPv4
        packed = [0] * 10 + [0xff, 0xff] + list(packed)

    return (ctypes.c_ubyte * 16)(*packed)


def _ubyte_array_to_ip(arr):
    'Convert an address encoded as a c_ubyte array to a string'
    addr = ipaddress.ip_address(bytes(arr))
    ipv4 = addr.ipv4_mapped
    if ipv4:
        return str(ipv4)
    else:
        return str(addr)


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
                               user_types=basic_types)

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
    def deserialize(cls, buf, *, our_cache, user_types=None, interfaces=None):
        if user_types is None:
            user_types = basic_types
        base_size = ctypes.sizeof(cls)
        buflen = len(buf) - base_size
        buf = memoryview(buf)
        msg = cls.from_buffer(buf[:base_size])

        offset = base_size
        buf = buf[offset:]

        if not hasattr(cls, '_additional_fields_'):
            return Decoded(data=msg, buffer=buf, offset=offset)

        cache = SerializeCache(ours=our_cache, theirs=None,
                               user_types=user_types)
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
                    interface = interfaces[field_info.name]
                except (TypeError, KeyError):
                    raise ValueError('Interface unspecified for PVField key {}'
                                     ''.format(field_info.name))

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

        info += ', ' + ', '.join('{}={!r}'.format(*name_and_value(fi.name))
                                 for fi in self._additional_fields_)
        return '{}({})'.format(type(self).__name__, info)


RequiredField = namedtuple('RequiredField', 'name type')
OptionalField = namedtuple('OptionalField', 'name type stop condition')
NonstandardArrayField = namedtuple('OptionalField', 'name type count_name')
RequiredInterfaceField = namedtuple('RequiredField', 'name type data_field')
OptionalInterfaceField = namedtuple('OptionalInterfaceField',
                                    'name type stop condition data_field')


def _dual_endian_decorator(cls):
    '''Creates both big- and little-endian versions of a Structure

    Checks for _additional_fields from ExtendedMessageBase
    Adds _ENDIAN attr for easy struct.unpacking = big (>) or little (<)
    '''
    for endian_base, suffix in ((ctypes.BigEndianStructure, 'BE'),
                                (ctypes.LittleEndianStructure, 'LE')):
        name = cls.__name__.lstrip('_') + suffix
        endian_cls = type(name, (cls, endian_base),
                          {'_fields_': cls._fields_})

        if hasattr(endian_cls, '_additional_fields_'):
            for field_info in endian_cls._additional_fields_:
                setattr(endian_cls, field_info.name, None)
        endian_cls._ENDIAN = (LITTLE_ENDIAN
                              if endian_base is ctypes.LittleEndianStructure
                              else BIG_ENDIAN)
        globals()[name] = endian_cls

    return cls


MessageHeaderLE = None  # linter hint
MessageHeaderBE = None  # linter hint


@_dual_endian_decorator
class _MessageHeader(MessageBase):
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

        self.flags = _MessageHeader.flag_from_enums(message_type, direction,
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

    def get_message(self, direction, use_fixed_byte_order=None):
        byte_order = (use_fixed_byte_order
                      if use_fixed_byte_order is not None
                      else self.byte_order)
        command = ApplicationCommands(self.message_command)
        try:
            return messages[byte_order][direction][command]
        except KeyError as ex:
            raise KeyError('{} where byte order={} direction={!r} command={!r}'
                           ''.format(ex, byte_order,
                                     DirectionFlag(direction), command))


@_dual_endian_decorator
class _Status(ExtendedMessageBase):
    _fields_ = [('status_type', c_byte)]
    _additional_fields_ = [
        OptionalField('message', 'string', OptionalStopMarker.continue_,
                      lambda msg, buf: msg.status_type != StatusType.OK),
        OptionalField('call_tree', 'string', OptionalStopMarker.continue_,
                      lambda msg, buf: msg.status_type != StatusType.OK),
    ]


@_dual_endian_decorator
class _BeaconMessage(ExtendedMessageBase):
    ID = ApplicationCommands.BEACON
    # FieldDesc serverStatusIF;
    # [if serverStatusIF != NULL_TYPE_CODE] PVField serverStatus;
    _fields_ = [
        ('guid', c_ubyte * 12),
        ('flags', c_ubyte),
        ('beacon_sequence_id', c_ubyte),
        ('change_count', c_ushort),  # TODO: docs
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


class SetMarker(MessageHeaderLE):
    ID = ControlCommands.SET_MARKER


class AcknowledgeMarker(MessageHeaderLE):
    ID = ControlCommands.ACK_MARKER


class SetByteOrder(MessageHeaderLE):
    ID = ControlCommands.SET_ENDIANESS
    # uses EndianSetting in header payload size

    @property
    def byte_order_setting(self):
        return EndianSetting(self.payload_size)


@_dual_endian_decorator
class _ConnectionValidationRequest(ExtendedMessageBase):
    ID = ApplicationCommands.CONNECTION_VALIDATION

    _fields_ = [
        ('server_buffer_size', c_int),
        ('server_registry_size', c_short),
    ]

    _additional_fields_ = [
        RequiredField('auth_nz', 'string[]'),
    ]


@_dual_endian_decorator
class _ConnectionValidationResponse(ExtendedMessageBase):
    ID = ApplicationCommands.CONNECTION_VALIDATION

    _fields_ = [
        ('client_buffer_size', c_int),
        ('client_registry_size', c_short),
        ('connection_qos', c_short),
    ]

    _additional_fields_ = [
        RequiredField('auth_nz', 'string'),
    ]


@_dual_endian_decorator
class _Echo(ExtendedMessageBase):
    ID = ApplicationCommands.ECHO
    _additional_fields_ = [
        RequiredField('payload', 'byte[]'),
    ]


@_dual_endian_decorator
class _ConnectionValidatedResponse(_Status):
    ID = ApplicationCommands.CONNECTION_VALIDATED


@_dual_endian_decorator
class _SearchRequest(ExtendedMessageBase):
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
        return _ubyte_array_to_ip(self._response_address)

    @response_address.setter
    def response_address(self, value):
        self._response_address = _ip_to_ubyte_array(value)

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


@_dual_endian_decorator
class _SearchResponse(ExtendedMessageBase):
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
        return _ubyte_array_to_ip(self._server_address)

    @server_address.setter
    def server_address(self, value):
        self._server_address = _ip_to_ubyte_array(value)


@_dual_endian_decorator
class _CreateChannelRequest(ExtendedMessageBase):
    ID = ApplicationCommands.CREATE_CHANNEL

    _additional_fields_ = [
        # RequiredField('channels', 'channel_with_id[]'),
        # ^-- DOCS_TODO indicate this as accurate, but it is not.
        RequiredField('count', 'ushort'),
        # ^-- DOCS_TODO is not documented as such, and must be 1
        RequiredField('channels', 'channel_with_id'),
    ]


@_dual_endian_decorator
class _CreateChannelResponse(ExtendedMessageBase):
    ID = ApplicationCommands.CREATE_CHANNEL

    _fields_ = [('client_chid', c_int),
                ('server_chid', c_int),
                ('status_type', c_byte),
                ]
    _additional_fields_ = _Status._additional_fields_ + [
        # TODO access rights aren't sent, even if status_type is OK
        OptionalField('access_rights', 'short', OptionalStopMarker.stop,
                      _success_condition
                      ),
    ]


def _is_get_init_condition(msg, buf):
    return msg.subcommand == GetSubcommands.INIT


@_dual_endian_decorator
class _ChannelGetRequest(ExtendedMessageBase):
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


@_dual_endian_decorator
class _ChannelGetResponse(ExtendedMessageBase):
    ID = ApplicationCommands.GET

    _fields_ = [('request_id', c_int),
                ('subcommand', c_byte),
                ('status_type', c_byte),
                ]

    _additional_fields_ = _Status._additional_fields_ + [
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


@_dual_endian_decorator
class _ChannelFieldInfoRequest(ExtendedMessageBase):
    ID = ApplicationCommands.GET_FIELD

    _fields_ = [('server_chid', c_int),
                ('ioid', c_int),
                ]
    _additional_fields_ = [
        RequiredField('sub_field_name', 'string'),
    ]


@_dual_endian_decorator
class _ChannelFieldInfoResponse(ExtendedMessageBase):
    ID = ApplicationCommands.GET_FIELD

    _fields_ = [('ioid', c_int),
                ('status_type', c_byte),
                ]
    _additional_fields_ = _Status._additional_fields_ + [
        OptionalField('field_if', 'FieldDesc', OptionalStopMarker.stop,
                      _success_condition
                      ),
    ]


# List of entries where the server is requesting information and the client is
# replying:
_server_requests = (ApplicationCommands.CONNECTION_VALIDATION, )


def _build_message_dict():
    d = {LITTLE_ENDIAN: {DirectionFlag.FROM_SERVER: {},
                         DirectionFlag.FROM_CLIENT: {}},
         BIG_ENDIAN: {DirectionFlag.FROM_SERVER: {},
                      DirectionFlag.FROM_CLIENT: {}},
         }

    skip_classes = ['MessageBase',
                    'ExtendedMessageBase',
                    'MessageHeaderBE',
                    'MessageHeaderLE',
                    'StatusBE',
                    'StatusLE',
                    ]

    for name, cls in globals().items():
        if name.startswith('_'):
            continue

        if inspect.isclass(cls) and issubclass(cls, MessageBase):
            if any(cls.__name__ == clsname for clsname in skip_classes):
                continue
            elif isinstance(cls.ID, ControlCommands):
                # Control commands have overlapping IDs
                continue

            if hasattr(cls, '_ENDIAN'):
                endian = [cls._ENDIAN]
            else:
                endian = [LITTLE_ENDIAN, BIG_ENDIAN]

            is_request = (name.endswith('RequestBE') or
                          name.endswith('RequestLE'))
            is_response = (name.endswith('ResponseBE') or
                           name.endswith('ResponseLE'))
            if not (is_request or is_response):
                # No indication of Request/Response means it's bidirectional
                is_request = is_response = True
            elif cls.ID in _server_requests:
                is_request, is_response = is_response, is_request

            direction_keys = []
            if is_request:
                direction_keys.append(DirectionFlag.FROM_CLIENT)
            if is_response:
                direction_keys.append(DirectionFlag.FROM_SERVER)

            for end in endian:
                for direct in direction_keys:
                    d[end][direct][cls.ID] = cls

    return d


messages = _build_message_dict()
