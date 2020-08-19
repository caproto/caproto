import array
import ctypes
import functools
import typing
from typing import Dict, List, Optional

from . import _core as core
from ._core import (Deserialized, Endian, FieldArrayType, FieldType, TypeCode,
                    _DataSerializer)
from ._fields import (BitSet, CacheContext, FieldDesc, SimpleField, Size,
                      String, StructuredField)
from ._pvrequest import PVRequestStruct


class SerializationFailure(Exception):
    ...


class DataSerializer(_DataSerializer):
    """
    Tracks subclasses which handle certain data types for serialization.
    """

    handlers: Dict['FieldType', _DataSerializer] = {}

    def __init_subclass__(cls, handles):
        super().__init_subclass__()
        for handle in handles:
            DataSerializer.handlers[handle] = cls


class ArrayBasedDataSerializer(DataSerializer, handles={}):
    """
    A data serializer which works not on an element-by-element basis, but
    rather with an array of elements.  Used for arrays of basic data types.
    """

    @classmethod
    def deserialize(cls,
                    field: 'FieldDesc',
                    data: bytes, *,
                    endian: Endian,
                    bitset: Optional[BitSet] = None,
                    cache: Optional[CacheContext] = None,
                    count: int = 1,
                    ) -> Deserialized:
        ...


class StringFieldData(DataSerializer,
                      handles={FieldType.string, FieldType.bounded_string}):
    """
    Data serializer for run-length encoded strings.

    Wraps :class:`String` to support the :class:`DataSerializer` interface.
    """

    @classmethod
    def serialize(cls,
                  field: FieldDesc,
                  value: typing.Union[str, List[str]],
                  endian: Endian,
                  bitset: Optional[BitSet] = None,
                  cache: Optional[CacheContext] = None,
                  ) -> List[bytes]:
        return String.serialize(value, endian=endian)

    @classmethod
    def deserialize(cls,
                    field: FieldDesc,
                    data: bytes, *,
                    endian: Endian,
                    bitset: Optional[BitSet] = None,
                    cache: Optional[CacheContext] = None,
                    count: int = 1,
                    ) -> Deserialized:
        return String.deserialize(data, endian=endian)


_numeric_types = {
    FieldType.float16, FieldType.float32, FieldType.float64,
    FieldType.float128, FieldType.uint64, FieldType.int64, FieldType.uint32,
    FieldType.int32, FieldType.uint16, FieldType.int16, FieldType.uint8,
    FieldType.int8, FieldType.boolean
}


class NumericFieldData(ArrayBasedDataSerializer, handles=_numeric_types):
    """
    Numeric field data serialization.

    Handles integer and floating point type variations.
    """

    type_to_ctypes: Dict[FieldType, typing.Type[ctypes._SimpleCData]] = {
        # FieldType.float16 ?
        FieldType.float32: ctypes.c_float,
        FieldType.float64: ctypes.c_double,
        FieldType.uint64: ctypes.c_uint64,
        FieldType.int64: ctypes.c_int64,
        FieldType.uint32: ctypes.c_uint32,
        FieldType.int32: ctypes.c_int32,
        FieldType.uint16: ctypes.c_uint16,
        FieldType.int16: ctypes.c_int16,
        FieldType.uint8: ctypes.c_uint8,
        FieldType.int8: ctypes.c_int8,
        FieldType.boolean: ctypes.c_ubyte,
    }

    @classmethod
    def serialize(cls,
                  field: FieldDesc,
                  value: typing.Union[str, List[str]],
                  endian: Endian,
                  bitset: Optional[BitSet] = None,
                  cache: Optional[CacheContext] = None,
                  ) -> List[bytes]:
        try:
            len(value)
        except TypeError:
            value = (value, )

        if field.array_type == FieldArrayType.scalar and len(value) > 1:
            raise ValueError('Too many values for FieldArrayType.scalar')

        type_code = cls.type_to_ctypes[field.field_type]._type_  # type: ignore
        arr = array.array(type_code, value)
        if endian != core.SYS_ENDIAN:
            arr.byteswap()
        return [arr]

    @classmethod
    def deserialize(cls,
                    field: FieldDesc,
                    data: bytes, *,
                    endian: Endian,
                    bitset: Optional[BitSet] = None,
                    cache: Optional[CacheContext] = None,
                    count: int = 1,
                    ) -> Deserialized:
        ctypes_type = cls.type_to_ctypes[field.field_type]
        byte_size = count * ctypes.sizeof(ctypes_type)

        type_code = ctypes_type._type_  # type: ignore
        value = array.array(type_code)

        if len(data) < byte_size:
            raise SerializationFailure(
                f'Deserialization buffer does not hold all values. Expected '
                f'byte length {byte_size}, actual length {len(data)}. '
                f'Value of type {field}[{count}]'
            )

        value.frombytes(data[:byte_size])
        if endian != core.SYS_ENDIAN:
            value.byteswap()

        return Deserialized(data=value,
                            buffer=data[byte_size:],
                            offset=byte_size)


class VariantFieldData(DataSerializer, handles={FieldType.any}):
    """
    Variant (i.e., "any") data type.

    Handles serialization of the FieldDesc of the item and the data contained.
    """

    type_map = {
        str: FieldType.string,
        bytes: FieldType.string,
        int: FieldType.int64,
        bool: FieldType.boolean,
        float: FieldType.float64,
    }

    @classmethod
    def field_from_value(cls, value: typing.Any, *, name: str = '') -> FieldDesc:
        'Name and native Python value -> field description dictionary'
        if isinstance(value, (str, bytes)):
            return SimpleField(
                name=name,
                field_type=FieldType.string,
                size=1,
                array_type=FieldArrayType.scalar,
            )

        if isinstance(value, (tuple, list, array.array)):
            if len(value) > 1:
                return SimpleField(
                    name=name,
                    field_type=cls.type_map[type(value[0])],
                    size=len(value),
                    array_type=FieldArrayType.variable_array,
                )

            value = value[0]

        return SimpleField(
            name=name,
            field_type=cls.type_map[type(value)],
            size=1,
            array_type=FieldArrayType.scalar,
        )

    @classmethod
    def serialize(cls,
                  field: FieldDesc,
                  value: typing.Any,
                  endian: Endian,
                  bitset: Optional[BitSet] = None,
                  cache: Optional[CacheContext] = None,
                  ) -> List[bytes]:
        if value is None:
            return [bytes([TypeCode.NULL_TYPE_CODE])]

        new_field = cls.field_from_value(value)
        serialized = new_field.serialize(endian=endian)
        serialized += Data.serialize(new_field, value=value, endian=endian,
                                     bitset=None, cache=cache)
        return serialized

    @classmethod
    def deserialize(cls,
                    field: FieldDesc,
                    data: bytes, *,
                    endian: Endian,
                    bitset: Optional[BitSet] = None,
                    cache: Optional[CacheContext] = None,
                    count: int = 1,
                    ) -> Deserialized:

        any_field, data, offset = FieldDesc.deserialize(
            data, endian=endian, cache=cache, named=False)
        if any_field is None:
            return Deserialized(data=None, buffer=data, offset=offset)

        value, data, off = Data.deserialize(any_field, data=data,
                                            endian=endian, bitset=None,
                                            cache=cache)
        offset += off
        return Deserialized(data=value, buffer=data, offset=offset)


class UnionFieldData(DataSerializer, handles={FieldType.union}):
    """
    Union field data.

    Handles serialization of the field selector (i.e., which element is
    chosen from the union) and the data contained.
    """

    @classmethod
    def serialize(cls,
                  field: FieldDesc,
                  value: typing.Any,
                  endian: Endian,
                  bitset: Optional[BitSet] = None,
                  cache: Optional[CacheContext] = None,
                  ) -> List[bytes]:
        field = typing.cast(StructuredField, field)
        possible_keys = set(field.children)
        found_keys = set(value).intersection(possible_keys)
        if len(found_keys) == 0:
            return Size.serialize(None, endian=endian)

        if len(found_keys) > 1:
            raise SerializationFailure(
                f'Too many keys specified for union. Options: {possible_keys};'
                f' found: {found_keys}.'
            )

        key, = found_keys
        child = field.children[key]
        index = list(field.children).index(key)
        serialized = Size.serialize(index, endian=endian)
        serialized.extend(
            Data.serialize(field=child, value=value[key], endian=endian,
                           bitset=None, cache=cache)
        )
        return serialized

    @classmethod
    def deserialize(cls,
                    field: FieldDesc,
                    data: bytes, *,
                    endian: Endian,
                    bitset: Optional[BitSet] = None,
                    cache: Optional[CacheContext] = None,
                    count: int = 1,
                    ) -> Deserialized:
        field = typing.cast(StructuredField, field)
        index, data, offset = Size.deserialize(data, endian=endian)
        if index is None:
            return Deserialized(data=None, buffer=data, offset=offset)

        selected_key, selected_field = list(field.children.items())[index]
        value, data, off = Data.deserialize(
            selected_field, data=data, endian=endian, bitset=None, cache=cache)

        offset += off
        return Deserialized(data={selected_key: value}, buffer=data, offset=offset)


class StructFieldData(DataSerializer, handles={FieldType.struct}):
    """
    Struct field data.

    Handles serialization of the children of the struct, respecting the
    provided BitSet.
    """

    @classmethod
    def serialize(cls,
                  field: FieldDesc,
                  value: typing.Any,
                  endian: Endian,
                  bitset: Optional[BitSet] = None,
                  cache: Optional[CacheContext] = None,
                  ) -> List[bytes]:
        field = typing.cast(StructuredField, field)
        if bitset is None:
            bitset = BitSet({0})

        bitset_index_to_child = [
            (field.descendents.index((name, child)) + 1, child)
            for name, child in field.children.items()
        ]

        serialized = []
        child_bitset: Optional[BitSet]

        for index, child in bitset_index_to_child:
            if child.field_type in {FieldType.struct, FieldType.union}:
                # Child may have bits selected
                child_bitset = bitset.offset_by(-index)
            elif index not in bitset and 0 not in bitset:
                continue
            else:
                child_bitset = None

            child_value = value[child.name]
            serialized.extend(
                Data.serialize(field=child, value=child_value, endian=endian,
                               cache=cache, bitset=child_bitset)
            )
        return serialized

    @classmethod
    def deserialize(cls,
                    field: FieldDesc,
                    data: bytes, *,
                    endian: Endian,
                    bitset: Optional[BitSet] = None,
                    cache: Optional[CacheContext] = None,
                    count: int = 1,
                    ) -> Deserialized:
        field = typing.cast(StructuredField, field)
        if bitset is None:
            bitset = BitSet({0})

        offset = 0
        if field.array_type == FieldArrayType.variable_array:
            # TODO: haven't been able to confirm where this comes from
            # always appears to be 1
            count, data, off = Size.deserialize(data, endian=endian)
            offset += off
            assert count == 1

        bitset_index_to_child = [
            (field.descendents.index((name, child)) + 1, child)
            for name, child in field.children.items()
        ]
        value = {}
        for index, child in bitset_index_to_child:
            if child.field_type == FieldType.struct:
                if child.array_type == FieldArrayType.variable_array:
                    if index not in bitset and 0 not in bitset:
                        continue
                    child_bitset = BitSet({0})
                else:
                    # Child may have bits selected
                    child_bitset = bitset.offset_by(-index)
                    if not child_bitset:
                        continue
            elif index not in bitset and 0 not in bitset:
                continue
            else:
                child_bitset = None

            value[child.name], data, off = Data.deserialize(
                field=child, data=data, endian=endian,
                cache=cache, bitset=child_bitset
            )
            offset += off

        return Deserialized(data=value, buffer=data, offset=offset)


class DataWithBitSet(DataSerializer, handles={'bitset_and_data'}):
    """
    Pair of Data, described by ``field`` (FieldDesc), and BitSet.

    Serializes the BitSet first, and then the Data that goes along with it.
    """

    field_type = 'bitset_and_data'  # hack
    array_type = FieldArrayType.scalar  # hack
    size = 1

    @classmethod
    def serialize(cls,
                  field: FieldDesc,
                  value: typing.Any,
                  endian: Endian,
                  bitset: Optional[BitSet] = None,
                  cache: Optional[CacheContext] = None,
                  ) -> List[bytes]:
        serialized = []
        # TODO especially awkward handling
        serialized.extend(value['bitset'].serialize(endian=endian))
        serialized.extend(Data.serialize(value['interface'],
                                         value=value['data'],
                                         endian=endian, bitset=bitset,
                                         cache=cache))
        return serialized

    @classmethod
    def deserialize(cls,
                    field: str,
                    data: bytes, *,
                    endian: Endian,
                    bitset: Optional[BitSet] = None,
                    cache: Optional[CacheContext] = None,
                    count: int = 1,
                    ) -> Deserialized:
        bitset, data, offset = BitSet.deserialize(data, endian=endian)
        value, data, off = Data.deserialize(field, data=data, endian=endian,
                                            bitset=bitset, cache=cache)
        offset += off
        return Deserialized(data=dict(field=field, value=value),
                            buffer=data,
                            offset=offset)


class FieldDescAndData(DataSerializer, handles={'field_and_data'}):
    """
    A field description and associated data.

    Serializes the field description first, and then the associated data.
    """

    field_type = 'field_and_data'  # hack
    array_type = FieldArrayType.scalar  # hack
    field_class = FieldDesc
    size = 1

    @classmethod
    def serialize(cls,
                  field: FieldDesc,
                  value: typing.Any,
                  endian: Endian,
                  bitset: Optional[BitSet] = None,
                  cache: Optional[CacheContext] = None,
                  ) -> List[bytes]:
        if value is None:
            return [bytes([TypeCode.NULL_TYPE_CODE])]

        field = value['field']
        value = value['value']
        serialized = []
        serialized.extend(field.serialize(endian=endian, cache=cache))
        serialized.extend(Data.serialize(field, value=value, endian=endian,
                                         bitset=bitset, cache=cache))
        return serialized

    @classmethod
    def deserialize(cls,
                    field: str,
                    data: bytes, *,
                    endian: Endian,
                    bitset: Optional[BitSet] = None,
                    cache: Optional[CacheContext] = None,
                    count: int = 1,
                    ) -> Deserialized:
        field, data, offset = cls.field_class.deserialize(
            data, endian=endian, cache=cache)
        if field is None:
            value = None
        else:
            value, data, off = Data.deserialize(field, data=data, endian=endian,
                                                bitset=bitset, cache=cache)
            offset += off
        return Deserialized(data=dict(field=field, value=value),
                            buffer=data,
                            offset=offset)


class PVRequest(FieldDescAndData, handles={'PVRequest'}):
    """
    A special form of FieldDescAndData, representing a PVRequest.

    Handles string to PVRequest structure translation, if required.
    """

    field_type = 'PVRequest'  # hack
    array_type = FieldArrayType.scalar  # hack
    field_class = FieldDesc  # PVRequestStruct

    @classmethod
    def serialize(cls,
                  field: FieldDesc,
                  value: typing.Any,
                  endian: Endian,
                  bitset: Optional[BitSet] = None,
                  cache: Optional[CacheContext] = None,
                  ) -> List[bytes]:
        if isinstance(value, str):
            st = PVRequestStruct.from_string(value)
            value = {'field': st, 'value': st.values}
        else:
            assert 'field' in value
            assert 'value' in value

        return super().serialize(field=None, value=value, endian=endian,
                                 bitset=bitset, cache=cache)


class Data(DataSerializer, handles={}):
    """
    Top-level data serializer.  Dispatches serialization to the handlers.
    """

    @classmethod
    def serialize(cls,
                  field: FieldDesc,
                  value: typing.Any,
                  endian: Endian,
                  bitset: Optional[BitSet] = None,
                  cache: Optional[CacheContext] = None,
                  ) -> List[bytes]:

        if field is FieldDesc:
            # For deserialization consistency (TODO annotation / refactor)
            return FieldDesc.serialize(value=value, endian=endian, cache=cache)

        handler = DataSerializer.handlers[field.field_type]
        try:
            len(value)
        except TypeError:
            value = (value, )

        if isinstance(value, (str, bytes, typing.Mapping)):
            value = (value, )

        serialized = []
        if field.array_type.has_serialization_size:
            serialized.extend(Size.serialize(len(value), endian=endian))

        for single_value in value:
            serialized.extend(
                handler.serialize(field=field, value=single_value,
                                  endian=endian, bitset=bitset, cache=cache)
            )

        return serialized

    @classmethod
    def deserialize(cls,
                    field: FieldDesc,
                    data: bytes, *,
                    endian: Endian,
                    bitset: Optional[BitSet] = None,
                    cache: Optional[CacheContext] = None,
                    count: int = 1,
                    ) -> Deserialized:

        if field is FieldDesc:
            # For deserialization consistency (TODO annotation / refactor)
            return FieldDesc.deserialize(data=data, endian=endian, cache=cache,
                                         named=False)
        if field is BitSet:
            # For deserialization consistency (TODO annotation / refactor)
            return BitSet.deserialize(data=data, endian=endian)

        # print('\n\n', ' '.join(hex(c)[2:].zfill(2) for c in data[:20]))
        offset = 0

        if field.array_type.has_serialization_size:
            count, data, off = Size.deserialize(data, endian=endian)
            offset += off
        else:
            count = field.size if field.size is not None else 1

        handler = DataSerializer.handlers[field.field_type]
        array_based = issubclass(handler, ArrayBasedDataSerializer)

        # Minimal set here:
        deserialize = functools.partial(handler.deserialize, endian=endian)
        if array_based:
            loops = 1
            deserialize = functools.partial(deserialize, field=field,
                                            bitset=bitset, cache=cache,
                                            count=count)
        else:
            loops = count
            deserialize = functools.partial(
                handler.deserialize, field=field, endian=endian, bitset=bitset,
                cache=cache,
            )

        value = []
        for _ in range(loops):
            # print('\n\n', ' '.join(hex(c)[2:].zfill(2) for c in data[:20]))
            # print('reading', _, field, handler)
            item, data, off = deserialize(data=data)
            # print('reading', _, item, 'took', off, 'bytes')
            offset += off
            value.append(item)

        if array_based:
            if field.array_type == FieldArrayType.scalar:
                # [array([0, 1, 2])] -> array([0, 1, 2])
                value = value[0][0]
            else:
                # [array([0])] -> 0
                value = value[0]
        elif field.array_type == FieldArrayType.scalar:
            # if not isinstance(value, (dict, str, bytes)):
            value = value[0]

        return Deserialized(data=value, buffer=data, offset=offset)
