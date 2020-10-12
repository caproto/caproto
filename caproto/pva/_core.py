import abc
import array
import ctypes
import dataclasses
import enum
import sys
import typing
from dataclasses import field
from typing import Dict, List, Optional, Tuple, Union

from ._utils import ChannelLifeCycle, _SimpleReprEnum

if typing.TYPE_CHECKING:
    from ._fields import BitSet, FieldDesc

AddressTuple = Tuple[str, int]


class UserFacingEndian(str, _SimpleReprEnum):
    LITTLE_ENDIAN = '<'
    BIG_ENDIAN = '>'


class StatusType(enum.IntEnum):
    OK = -1
    OK_VERBOSE = 0
    WARNING = 1
    ERROR = 2
    FATAL = 3


MAX_INT32 = 2 ** 31 - 1
PVA_SERVER_PORT, PVA_BROADCAST_PORT = 5075, 5076
LITTLE_ENDIAN = UserFacingEndian.LITTLE_ENDIAN
BIG_ENDIAN = UserFacingEndian.BIG_ENDIAN
SYS_ENDIAN = (LITTLE_ENDIAN if sys.byteorder == 'little' else BIG_ENDIAN)
QOS_PRIORITY_MASK = 0x7f


if sys.version_info >= (3, 8):
    Endian = typing.Literal['<', '>']
else:
    Endian = typing.NewType('Endian', str)


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

    uint64 = 0b11100001
    int64 = 0b01100001

    uint32 = 0b11000001
    int32 = 0b01000001

    uint16 = 0b10100001
    int16 = 0b00100001

    uint8 = 0b10000001
    int8 = 0b00000001

    boolean = 0b00000000

    @property
    def _type_specific(self) -> int:
        return (0b11100000 & self.value) >> 5

    @property
    def _type(self) -> int:
        return 0b111 & self.value

    @property
    def is_complex(self) -> bool:
        """Is the FieldType a union, struct, or any field?"""
        return self in {FieldType.union, FieldType.struct, FieldType.any}

    @property
    def is_numeric(self) -> bool:
        """Is the FieldType integer or floating point?"""
        return self.is_integral or self.is_floating

    @property
    def is_integral(self) -> bool:
        """Is the FieldType integer-based?"""
        return self in {
            FieldType.uint64, FieldType.int64, FieldType.uint32,
            FieldType.int32, FieldType.uint16, FieldType.int16,
            FieldType.uint8, FieldType.int8,
        }

    @property
    def is_floating(self) -> bool:
        """Is the FieldType floating point?"""
        return self in {
            FieldType.float16, FieldType.float32, FieldType.float64,
            FieldType.float128,
        }

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

    Notes
    -----
    ``ours[fd_hash] = FieldDesc(..)``
    ``theirs[identifier] = fd_hash``
    ``ioid_interfaces[ioid] = FieldDesc(...)``
    """
    ours: Dict[int, 'FieldDesc'] = field(default_factory=dict)
    theirs: Dict[int, int] = field(default_factory=dict)

    # TODO: it may be possible to factor this out (I hope...)
    ioid_interfaces: Dict[int, 'FieldDesc'] = field(default_factory=dict)

    def clear(self):
        for dct in (self.ours, self.theirs, self.ioid_interfaces):
            dct.clear()


class Deserialized(typing.Iterable):
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
    data: typing.Any
    buffer: Union[bytes, memoryview]
    offset: int

    SUPER_DEBUG = False

    if not SUPER_DEBUG:
        def __init__(self,
                     data: typing.Any,
                     buffer: bytes,
                     offset: int):
            self.data = data
            self.buffer = buffer
            self.offset = offset

    else:
        def __init__(self,
                     data: typing.Any,
                     buffer: bytes,
                     offset: int):
            self.data = data
            self.buffer = buffer
            self.offset = offset

            import inspect
            import textwrap
            for idx in (3, 4):
                caller = inspect.stack()[idx]
                print(caller.filename, caller.lineno)
                print(textwrap.dedent('\n'.join(caller.code_context or [])).rstrip())
            print('------> deserialized', repr(self.data), 'next is',
                  bytes(self.buffer)[:10], self.offset)

    def __repr__(self):
        return (
            f"{self.__class__.__name__}(data={self.data!r}, "
            f"buffer={self.buffer!r}, "
            f"offset={self.offset})"
        )

    def __iter__(self):
        return iter((self.data, self.buffer, self.offset))


class SegmentDeserialized(typing.Iterable):
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

    def __init__(self,
                 data: Deserialized,
                 bytes_needed: int,
                 segment_state: Optional[Union[ChannelLifeCycle, bytes]]):
        self.data = data
        self.bytes_needed = bytes_needed
        self.segment_state = segment_state

    def __iter__(self):
        return iter((self.data, self.bytes_needed, self.segment_state))

    def __repr__(self):
        return (
            f"{self.__class__.__name__}(data={self.data!r}, "
            f"bytes_needed={self.bytes_needed!r}, "
            f"segment_state={self.segment_state})"
        )


class CoreSerializable(abc.ABC):
    """
    A serializable item. May be instantiated (and hold state).
    """

    @abc.abstractmethod
    def serialize(self, endian: Endian) -> List[bytes]:
        ...

    @abc.abstractmethod
    def deserialize(cls, data: bytes, *, endian: Endian) -> Deserialized:
        ...


class CoreStatelessSerializable(abc.ABC):
    """
    A stateless, serializable item. Instance-level data may not be used as
    serialize and deserialize are class methods.
    """

    @abc.abstractmethod
    def serialize(self, value, endian: Endian) -> List[bytes]:
        ...

    @abc.abstractmethod
    def deserialize(cls, data: bytes, *, endian: Endian) -> Deserialized:
        ...


class CoreSerializableWithCache(abc.ABC):
    """
    A serializable item which uses the serialization cache context. May be
    instantiated (and hold state).

    If additional state is necessary for deserialization, ``deserialize`` may
    be an instance method.
    """

    @abc.abstractmethod
    def serialize(self, endian: Endian, cache: CacheContext) -> List[bytes]:
        ...

    @abc.abstractmethod
    def deserialize(cls, data: bytes, *, endian: Endian,
                    cache: CacheContext) -> Deserialized:
        ...


class _DataSerializer(abc.ABC):
    """ABC for DataSerializer in caproto.pva._data."""
    @abc.abstractmethod
    def serialize(cls,
                  field: 'FieldDesc',
                  value: typing.Any,
                  endian: Endian,
                  bitset: 'BitSet' = None,
                  cache: CacheContext = None,
                  ) -> List[bytes]:
        ...

    @abc.abstractmethod
    def deserialize(cls,
                    field: 'FieldDesc',
                    data: bytes, *,
                    endian: Endian,
                    bitset: 'BitSet' = None,
                    cache: CacheContext = None,
                    ) -> Deserialized:
        ...


class _ArrayBasedDataSerializer:
    """
    A data serializer which works not on an element-by-element basis, but
    rather with an array of elements.  Used for arrays of basic data types.
    """

    @abc.abstractmethod
    def serialize(cls,
                  field: 'FieldDesc',
                  value: typing.Any,
                  endian: Endian,
                  bitset: 'BitSet' = None,
                  cache: CacheContext = None,
                  ) -> List[Union[bytes, array.array]]:
        ...

    @abc.abstractmethod
    def deserialize(cls,
                    field: 'FieldDesc',
                    data: bytes,
                    count: int,  # <-- note the count here
                    *,
                    endian: Endian,
                    bitset: Optional['BitSet'] = None,
                    cache: Optional[CacheContext] = None,
                    ) -> Deserialized:
        ...
