import abc
import ctypes
import dataclasses
import enum
import sys
import typing
from dataclasses import field
from typing import Dict, List, Optional, Union

from ._utils import ChannelLifeCycle, _SimpleReprEnum

if typing.TYPE_CHECKING:
    from ._fields import BitSet, FieldDesc


class UserFacingEndian(str, _SimpleReprEnum):
    LITTLE_ENDIAN = '<'
    BIG_ENDIAN = '>'


MAX_INT32 = 2 ** 31 - 1
PVA_SERVER_PORT, PVA_BROADCAST_PORT = 5075, 5076
LITTLE_ENDIAN = UserFacingEndian.LITTLE_ENDIAN
BIG_ENDIAN = UserFacingEndian.BIG_ENDIAN
SYS_ENDIAN = (LITTLE_ENDIAN if sys.byteorder == 'little' else BIG_ENDIAN)
QOS_PRIORITY_MASK = 0x7f


if hasattr(typing, 'Literal'):  # 3.8
    Endian = typing.Literal['<', '>']
else:
    Endian = str


class TypeCode(enum.IntEnum):
    """
    Type code information for structures.

    Optionally used in FieldDesc descriptions, it allows for the
    synchronization of FieldDesc caches between client and server.
    """
    # No introspection data (also implies no data).
    NULL_TYPE_CODE = 0xFF

    # Serialization contains only an ID that was assigned by one of the
    # previous FULL_WITH_ID_TYPE_CODE or FULL_TAGGED_ID_TYPE_CODE descriptions.
    ONLY_ID_TYPE_CODE = 0xFE  # + ID

    # Serialization contains an ID (that can be used later, if cached) and full
    # interface description. Any existing definition with the same ID is
    # overriden.
    FULL_WITH_ID_TYPE_CODE = 0xFD  # + ID + FieldDesc

    # Not implemented:
    FULL_TAGGED_ID_TYPE_CODE = 0xFC  # + ID + tag + FieldDesc
    # RESERVED = 0xFB to 0xE0
    # FieldDesc FULL_TYPE_CODE = (0xDF - 0x00)


class FieldArrayType(enum.IntEnum):
    """
    The field array type information, indicating whether the associated field
    (of type :class:`FieldType`) is a scalar or array.
    """
    scalar = 0b00
    fixed_array = 0b11
    bounded_array = 0b10
    variable_array = 0b01

    @property
    def has_field_desc_size(self):
        'Fixed and bounded arrays have size information in FieldDesc'
        return self.value in (FieldArrayType.fixed_array,
                              FieldArrayType.bounded_array)

    @property
    def has_serialization_size(self):
        'Bounded and variable arrays serialize size information'
        return self.value in (FieldArrayType.bounded_array,
                              FieldArrayType.variable_array)

    def summary_with_size(self, size=None):
        if size is None:
            size = ''

        if self == FieldArrayType.fixed_array:
            return f'[{size}]'
        if self == FieldArrayType.bounded_array:
            return f'<{size}>'
        if self == FieldArrayType.variable_array:
            return f'[{size}]'
        return ''


class FieldDescByte(ctypes.Structure):
    """
    Field description first byte.

    Attributes
    ----------
    field_type : FieldType
        The field type information, indicating whether it's a structure,
        string, int, union, etc.

    array_type : FieldArrayType
        The array type - scalar, variable_array, etc.
    """

    _fields_ = [
        ('_type_specific', ctypes.c_ubyte, 3),
        ('_array_type', ctypes.c_ubyte, 2),
        ('_type', ctypes.c_ubyte, 3),
    ]

    def serialize(self, endian: Endian = None) -> typing.List[bytes]:
        return [bytes(self)]

    @classmethod
    def deserialize(cls, data, endian: Endian = None) -> 'Deserialized':
        fd = cls.from_buffer(bytearray([data[0]]))
        return Deserialized(data=fd, buffer=data[1:], offset=1)

    @property
    def field_type(self) -> 'FieldType':
        return FieldType((self._type_specific << 5) | self._type)

    @property
    def array_type(self) -> FieldArrayType:
        return FieldArrayType(self._array_type)

    def __repr__(self):
        return (
            f'{self.__class__.__name__}(field_type={self.field_type!r}, '
            f'array_type={self.array_type!r})'
        )

    @classmethod
    def from_field(cls, field: 'FieldDesc') -> 'FieldDescByte':
        """Create a FieldDescByte from the given FieldDesc."""
        return cls(field.field_type._type_specific, field.array_type,
                   field.field_type._type)


class FieldType(enum.IntEnum):
    """
    The field type information, indicating whether it's a structure, string,
    int, union, etc.  Used in conjunction with FieldArrayType.
    """
    # complex_reserved1 = 11100100
    # complex_reserved2 = 11000100
    # complex_reserved3 = 10100100
    # complex_reserved4 = 10000100
    bounded_string = 0b01100100
    string = 0b00000011

    any = 0b01000100

    union = 0b00100100
    struct = 0b00000100

    float16 = 0b00100010
    float32 = 0b01000010
    float64 = 0b01100010
    float128 = 0b10000010

    float = float32
    double = float64

    uint64 = 0b11100001
    int64 = 0b01100001
    ulong = uint64
    long = int64

    uint32 = 0b11000001
    int32 = 0b01000001

    uint = uint32
    int = int32

    uint16 = 0b10100001
    int16 = 0b00100001

    ushort = uint16
    short = int16

    uint8 = 0b10000001
    int8 = 0b00000001

    ubyte = uint8
    byte = int8

    boolean = 0b00000000

    @property
    def _type_specific(self) -> int:
        return (0b11100000 & self.value) >> 5

    @property
    def _type(self) -> int:
        return (0b111 & self.value)

    @property
    def is_complex(self) -> bool:
        return self in {FieldType.union, FieldType.struct, FieldType.any}

    @property
    def has_value(self) -> bool:
        'Can this field contain data directly?'
        return self not in {FieldType.union, FieldType.struct}


@dataclasses.dataclass
class CacheContext:
    """
    Per-VirtualCircuit cache context.

    Tracks Field Description information between clients and servers, and also
    those associated with specific I/O identifiers (ioids)
    """
    ours: Dict[int, 'FieldDesc'] = field(default_factory=dict)
    theirs: Dict[int, 'FieldDesc'] = field(default_factory=dict)
    ioid_interfaces: Dict[int, 'FieldDesc'] = field(default_factory=dict)

    def clear(self):
        for dct in (self.ours, self.theirs, self.ioid_interfaces):
            dct.clear()


@dataclasses.dataclass
class Deserialized:
    """
    Deserialization result container.

    Attributes
    ----------
    data : object
        The deserialized object.

    buffer : bytearray
        The remaining buffer contents, after consuming `data`.

    offset : int
        The number of bytes consumed in deserializing `data`, i.e., the offset
        to the buffer passed in to ``deserialize()``.
    """
    data: object
    buffer: bytearray
    offset: int

    SUPER_DEBUG = False
    if SUPER_DEBUG:
        def __post_init__(self):
            import inspect
            import textwrap
            for idx in (3, 4):
                caller = inspect.stack()[idx]
                print(caller.filename, caller.lineno)
                print(textwrap.dedent('\n'.join(caller.code_context)).rstrip())
            print('------> deserialized', repr(self.data), 'next is', bytes(self.buffer)[:10], self.offset)

    def __iter__(self):
        return iter((self.data, self.buffer, self.offset))


@dataclasses.dataclass
class SegmentDeserialized:
    """
    Serialized messages may be segmented when sent over TCP with pvAccess.
    This class contains additional deserialization information necessary to
    track it, along with the usual :class:`Deserialized` information.

    Between segments, control messages can be interspersed according to the
    pvAccess specification.

    Attributes
    ----------
    deserialized : Deserialized
        Contains the deserialized message, remaining data, bytes consumed.

    bytes_needed : int
        The number of bytes needed to finish the segment.

    segment_state : ChannelLifeCycle, bytes, or None
        Segmentation control information.
    """
    data: Deserialized
    bytes_needed: int
    segment_state: Optional[Union[ChannelLifeCycle, bytes]]

    def __iter__(self):
        return iter((self.data, self.bytes_needed, self.segment_state))


class Serializable(abc.ABC):
    """
    A serializable item. May be instantiated (and hold state).
    """

    @abc.abstractmethod
    def serialize(self, endian: Endian) -> List[bytes]:
        ...

    @abc.abstractclassmethod
    def deserialize(cls, data: bytes, *, endian: Endian) -> Deserialized:  # noqa
        ...


class StatelessSerializable(abc.ABC):
    """
    A stateless, serializable item. Instance-level data may not be used as
    serialize and deserialize are class methods.
    """

    @abc.abstractclassmethod
    def serialize(self, value, endian: Endian) -> List[bytes]:
        ...

    @abc.abstractclassmethod
    def deserialize(cls, data: bytes, *, endian: Endian) -> Deserialized:  # noqa
        ...


class _DataSerializer(abc.ABC):
    """ABC for DataSerializer below."""
    @abc.abstractclassmethod
    def serialize(cls,
                  field: 'FieldDesc',
                  value: typing.Any,
                  endian: Endian,
                  bitset: 'BitSet' = None,
                  cache: CacheContext = None,
                  ) -> List[bytes]:
        ...

    @abc.abstractclassmethod
    def deserialize(cls,
                    field: 'FieldDesc',
                    data: bytes, *,
                    endian: Endian,
                    bitset: 'BitSet' = None,
                    cache: CacheContext = None,
                    ) -> Deserialized:
        ...
