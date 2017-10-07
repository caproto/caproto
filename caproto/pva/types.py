import ctypes
import enum

from array import array
from collections import namedtuple

Decoded = namedtuple('Decoded', 'data buffer offset')


c_bool = ctypes.c_ubyte
c_byte = ctypes.c_byte
c_ubyte = ctypes.c_ubyte
c_short = ctypes.c_int16
c_ushort = ctypes.c_uint16
c_int = ctypes.c_int32
c_uint = ctypes.c_uint32
c_long = ctypes.c_int64
c_ulong = ctypes.c_uint16
c_float = ctypes.c_float
c_double = ctypes.c_double


class TypeCode(enum.IntFlag):
    NULL_TYPE_CODE = 0xFF
    ONLY_ID_TYPE_CODE = 0xFE  # + ID
    FULL_WITH_ID_TYPE_CODE = 0xFD  # + ID + FieldDesc
    FULL_TAGGED_ID_TYPE_CODE = 0xFC  # + ID + tag + FieldDesc
    # RESERVED = 0xFB to 0xE0
    # FieldDesc FULL_TYPE_CODE = (0xDF - 0x00)


class FieldType(enum.IntEnum):
    # reserved_unused3 = 0b111
    # reserved_unused2 = 0b110
    # reserved_unused1 = 0b101
    complex = 0b100
    string = 0b011
    float = 0b010
    integer = 0b001
    boolean = 0b000


class FieldArrayType(enum.IntEnum):
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


class FieldIntegerSize(enum.IntEnum):
    ulong = 0b111
    long = 0b011
    uint = 0b110
    int = 0b010
    ushort = 0b101
    short = 0b001
    ubyte = 0b100
    byte = 0b000


class FloatSize(enum.IntEnum):
    # reserved1 = 0b111
    # reserved2 = 0b110
    # reserved3 = 0b101
    float128 = 0b100
    float64 = 0b011
    float32 = 0b010
    float16 = 0b001
    # reserved4 = 0b000


class ComplexType(enum.IntEnum):
    reserved1 = 0b111
    reserved2 = 0b110
    reserved3 = 0b101
    reserved4 = 0b100
    bounded_string = 0b011
    variant_union = 0b010
    union = 0b001
    structure = 0b000


_type_specific_map = {
    FieldType.integer: FieldIntegerSize,
    FieldType.float: FloatSize,
    FieldType.complex: ComplexType,
}


class FieldDesc(ctypes.Structure):
    _fields_ = [('_type_specific', ctypes.c_ubyte, 3),
                ('_array_type', ctypes.c_ubyte, 2),
                ('_type', ctypes.c_ubyte, 3),
                ]

    @property
    def type_specific(self):
        'Additional information depending on FieldType'
        enum = _type_specific_map.get(self._type)
        if enum is not None:
            return enum(self._type_specific)
        else:
            return self._type_specific

    @property
    def array_type(self):
        'FieldArrayType'
        return FieldArrayType(self._array_type)

    @property
    def type(self):
        'FieldType'
        return FieldType(self._type)

    def __repr__(self):
        return ('{}(type={!r}, array_type={!r}, type_specific={})'
                ''.format(type(self).__name__, self.type, self.array_type,
                          self.type_specific))

    @property
    def type_name(self):
        return type_names[(self.type, self.type_specific)]


type_names = {
    (FieldType.string, 0): 'string',
    (FieldType.boolean, 0): 'bool',

    (FieldType.float, FloatSize.float16): 'float16',
    (FieldType.float, FloatSize.float32): 'float',
    (FieldType.float, FloatSize.float64): 'double',
    (FieldType.float, FloatSize.float128): 'float128',

    (FieldType.integer, FieldIntegerSize.ulong): 'ulong',
    (FieldType.integer, FieldIntegerSize.long): 'long',
    (FieldType.integer, FieldIntegerSize.uint): 'uint',
    (FieldType.integer, FieldIntegerSize.int): 'int',
    (FieldType.integer, FieldIntegerSize.ushort): 'ushort',
    (FieldType.integer, FieldIntegerSize.short): 'short',
    (FieldType.integer, FieldIntegerSize.ubyte): 'ubyte',
    (FieldType.integer, FieldIntegerSize.byte): 'byte',

    (FieldType.complex, ComplexType.bounded_string): 'bounded_string',
    (FieldType.complex, ComplexType.variant_union): 'any',
    (FieldType.complex, ComplexType.union): 'union',
    (FieldType.complex, ComplexType.structure): 'struct',
}

type_to_array_code = {
    'bool': 'B',
    'float': 'f',
    'double': 'd',
    'ulong': 'L',
    'long': 'l',
    'uint': 'I',
    'int': 'i',
    'ushort': 'H',
    'short': 'h',
    'ubyte': 'B',
    'byte': 'b',
}

scalar_type_names = set(tuple(type_to_array_code.keys()))

# TODO may have to tweak above to support other architectures

_type_code_byte_size = {
    'bool': 1,
    'float': 4,
    'double': 8,
    'ulong': 8,
    'long': 8,
    'uint': 4,
    'int': 4,
    'ushort': 2,
    'short': 2,
    'ubyte': 1,
    'byte': 1,
}


variant_type_map = {
    str: 'string',
    bytes: 'string',
    int: 'long',
    bool: 'bool',
    float: 'double',
}


def _check_type_code_sizes():
    "Architecture size type check: fail if types don't match expectations"
    for type_code, size in _type_code_byte_size.items():
        assert array(type_to_array_code[type_code]).itemsize == size


_check_type_code_sizes()

type_name_to_type = dict((v, k) for k, v in type_names.items())
