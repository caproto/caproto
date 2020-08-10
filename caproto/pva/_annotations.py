"""
Includes types that can be used for annotations, as-is or in Lists/Unions.

Examples
--------
``double_item: pva.Double``
``list_of_doubles: typing.List[pva.Double]``
``int_or_float: typing.Union[pva.Int32, pva.Float32]``
"""
import typing

from ._core import FieldType

BoundedString = typing.NewType('BoundedString', int)
String = typing.NewType('String', int)
Any = typing.NewType('Any', int)
# Union = typing.NewType('Union', int)
# Struct = typing.NewType('Struct', int)
Float16 = typing.NewType('Float16', int)
Float32 = typing.NewType('Float32', int)
Float64 = typing.NewType('Float64', int)
Float128 = typing.NewType('Float128', int)
Float = typing.NewType('Float', int)
Double = typing.NewType('Double', int)
UInt64 = typing.NewType('UInt64', int)
Int64 = typing.NewType('Int64', int)
ULong = typing.NewType('ULong', int)
Long = typing.NewType('Long', int)
UInt32 = typing.NewType('UInt32', int)
Int32 = typing.NewType('Int32', int)
UInt = typing.NewType('UInt', int)
Int = typing.NewType('Int', int)
UInt16 = typing.NewType('UInt16', int)
Int16 = typing.NewType('Int16', int)
UShort = typing.NewType('UShort', int)
Short = typing.NewType('Short', int)
UInt8 = typing.NewType('UInt8', int)
Int8 = typing.NewType('Int8', int)
UByte = typing.NewType('UByte', int)
Byte = typing.NewType('Byte', int)
Boolean = typing.NewType('Boolean', int)


annotation_type_map = {
    BoundedString: FieldType.bounded_string,
    String: FieldType.string,
    Any: FieldType.any,
    # Union: FieldType.union,
    # Struct: FieldType.struct,
    Float16: FieldType.float16,
    Float32: FieldType.float32,
    Float64: FieldType.float64,
    Float128: FieldType.float128,
    Float: FieldType.float,
    Double: FieldType.double,
    UInt64: FieldType.uint64,
    Int64: FieldType.int64,
    ULong: FieldType.ulong,
    Long: FieldType.long,
    UInt32: FieldType.uint32,
    Int32: FieldType.int32,
    UInt: FieldType.uint,
    Int: FieldType.int,
    UInt16: FieldType.uint16,
    Int16: FieldType.int16,
    UShort: FieldType.ushort,
    Short: FieldType.short,
    UInt8: FieldType.uint8,
    Int8: FieldType.int8,
    UByte: FieldType.ubyte,
    Byte: FieldType.byte,
    Boolean: FieldType.boolean,

    int: FieldType.int64,
    float: FieldType.double,
    str: FieldType.string,
    bytes: FieldType.byte,
}


type_to_annotation = {
    ft: annotation
    for annotation, ft in annotation_type_map.items()
    if annotation not in (int, float, str, bytes)
}


annotation_default_values = {
    FieldType.bounded_string: '',
    FieldType.string: '',
    FieldType.any: None,
    # FieldType.union: 0,
    # FieldType.struct: 0,
    FieldType.float16: 0.0,
    FieldType.float32: 0.0,
    FieldType.float64: 0.0,
    FieldType.float128: 0.0,
    FieldType.float: 0.0,
    FieldType.double: 0.0,

    FieldType.uint64: 0,
    FieldType.int64: 0,
    FieldType.ulong: 0,
    FieldType.long: 0,
    FieldType.uint32: 0,
    FieldType.int32: 0,
    FieldType.uint: 0,
    FieldType.int: 0,
    FieldType.uint16: 0,
    FieldType.int16: 0,
    FieldType.ushort: 0,
    FieldType.short: 0,
    FieldType.uint8: 0,
    FieldType.int8: 0,
    FieldType.ubyte: 0,
    FieldType.byte: 0,
    FieldType.boolean: False,
}
