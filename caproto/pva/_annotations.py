"""
Includes types that can be used for annotations, as-is or in Lists/Unions.

Examples
--------
``double_item: pva.Float64``
``list_of_doubles: typing.List[pva.Float64]``
``int_or_float: typing.Union[pva.Int32, pva.Float32]``
"""
import typing

from ._core import FieldType

BoundedString = typing.NewType('BoundedString', str)
Any = typing.Any
String = typing.NewType('String', str)
# Union = typing.NewType('Union', int)
# Struct = typing.NewType('Struct', int)
Float16 = typing.NewType('Float16', float)
Float32 = typing.NewType('Float32', float)
Float64 = typing.NewType('Float64', float)
Float128 = typing.NewType('Float128', float)
UInt64 = typing.NewType('UInt64', int)
Int64 = typing.NewType('Int64', int)
UInt32 = typing.NewType('UInt32', int)
Int32 = typing.NewType('Int32', int)
UInt16 = typing.NewType('UInt16', int)
Int16 = typing.NewType('Int16', int)
UInt8 = typing.NewType('UInt8', int)
Int8 = typing.NewType('Int8', int)
Boolean = typing.NewType('Boolean', bool)


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

    UInt64: FieldType.uint64,
    Int64: FieldType.int64,
    UInt32: FieldType.uint32,
    Int32: FieldType.int32,
    UInt16: FieldType.uint16,
    Int16: FieldType.int16,
    UInt8: FieldType.uint8,
    Int8: FieldType.int8,

    Boolean: FieldType.boolean,

    int: FieldType.int64,
    float: FieldType.float64,
    str: FieldType.string,
    bytes: FieldType.uint8,
    bool: FieldType.boolean,
}


type_to_annotation = {
    ft: annotation
    for annotation, ft in annotation_type_map.items()
    if annotation not in (int, float, str, bytes, bool)
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
    FieldType.uint64: 0,
    FieldType.int64: 0,
    FieldType.uint32: 0,
    FieldType.int32: 0,
    FieldType.uint16: 0,
    FieldType.int16: 0,
    FieldType.uint8: 0,
    FieldType.int8: 0,
    FieldType.boolean: False,
}
