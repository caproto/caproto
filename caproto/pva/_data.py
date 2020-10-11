import array
import ctypes
import dataclasses
import functools
import typing
from typing import (Dict, FrozenSet, Iterable, List, Optional, Sequence, Set,
                    Tuple, Type, Union)

from . import _core as core
from ._core import (CoreSerializable, CoreSerializableWithCache,
                    CoreStatelessSerializable, Deserialized, Endian,
                    FieldArrayType, FieldType, TypeCode,
                    _ArrayBasedDataSerializer, _DataSerializer)
from ._dataclass import (PvaStruct, dataclass_from_field_desc,
                         fields_to_bitset, fill_dataclass, get_pv_structure,
                         is_pva_dataclass, is_pva_dataclass_instance)
from ._fields import (BitSet, CacheContext, FieldDesc, SimpleField, Size,
                      String, StructuredField)
from ._pvrequest import PVRequestStruct


class SerializationFailure(Exception):
    ...


class DataSerializer(_DataSerializer):
    """
    Tracks subclasses which handle certain data types for serialization.

    Classes specify either a ``set`` of ``FieldType``s.
    """

    handlers: Dict[Union[FieldType, type], Type[_DataSerializer]] = {}

    def __init_subclass__(cls, handles: Set[FieldType]):
        super().__init_subclass__()
        for handle in handles:
            DataSerializer.handlers[handle] = cls


class StringFieldData(DataSerializer,
                      handles={FieldType.string, FieldType.bounded_string}):
    """
    Data serializer for run-length encoded strings.

    Wraps :class:`String` to support the :class:`DataSerializer` interface.
    """

    @classmethod
    def serialize(cls,
                  field: FieldDesc,
                  value: Union[str, List[str]],
                  endian: Endian,
                  bitset: Optional[BitSet] = None,
                  cache: Optional[CacheContext] = None,
                  ) -> List[bytes]:
        return String.serialize(value, endian=endian)

    @classmethod
    def deserialize(cls,
                    field: FieldDesc,
                    data: bytes,
                    *,
                    endian: Endian,
                    bitset: Optional[BitSet] = None,
                    cache: Optional[CacheContext] = None,
                    ) -> Deserialized:
        return String.deserialize(data, endian=endian)


class ArrayBasedDataSerializer(_ArrayBasedDataSerializer):
    """
    A data serializer which works not on an element-by-element basis, but
    rather with an array of elements.  Used for arrays of basic data types.
    """

    def __init_subclass__(cls, handles: Set[FieldType]):
        super().__init_subclass__()
        for handle in handles:
            DataSerializer.handlers[handle] = cls


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
                  value: Union[float, int, bool, Sequence[Union[float, int, bool]]],
                  endian: Endian,
                  bitset: Optional[BitSet] = None,
                  cache: Optional[CacheContext] = None,
                  ) -> List[Union[bytes, array.array]]:
        if not isinstance(value, Iterable):
            value = typing.cast(Sequence[Union[float, int, bool]],
                                (value, ))

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
                    data: bytes,
                    count: int,
                    *,
                    endian: Endian,
                    bitset: Optional[BitSet] = None,
                    cache: Optional[CacheContext] = None,
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


def _is_string_or_single_valued_string_list(item) -> bool:
    """Is ``item`` like: ['str'] or 'str'?"""
    # While this is simple enough in concept, it's confusing enough to
    # call for its own super-verbose utility function
    if not isinstance(item, Iterable):
        return False

    if not isinstance(item[0], (str, bytes)):
        return False
    return len(item) == 1 or isinstance(item, (str, bytes))


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

    _NULL_TYPE = [bytes([TypeCode.NULL_TYPE_CODE])]

    @classmethod
    def field_from_value(cls, value: typing.Any, *, name: str = '') -> FieldDesc:
        'Name and native Python value -> field description dictionary'
        if _is_string_or_single_valued_string_list(value):
            return SimpleField(
                name=name,
                field_type=FieldType.string,
                size=1,
                array_type=FieldArrayType.scalar,
            )

        if isinstance(value, Iterable):
            if len(value) > 1:
                return SimpleField(
                    name=name,
                    field_type=cls.type_map[type(value[0])],
                    size=len(value),
                    array_type=FieldArrayType.variable_array,
                )

            value = value[0]

        assert value is not None

        if is_pva_dataclass_instance(value):
            return get_pv_structure(value).as_new_name(name)

        if is_pva_dataclass(value):
            raise ValueError(
                f'Must use an instantiated dataclass, got {value}'
            )

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
        if value is None or value == (None, ):  # hmm
            return cls._NULL_TYPE

        new_field = cls.field_from_value(value)
        if isinstance(new_field, StructuredField):
            serialized = new_field.serialize(endian=endian, cache=None)
        else:
            serialized = new_field.serialize(endian=endian)

        serialized += to_wire(new_field, value=value, endian=endian,
                              bitset=None, cache=cache)
        return serialized

    @classmethod
    def deserialize(cls,
                    field: FieldDesc,
                    data: bytes, *,
                    endian: Endian,
                    bitset: Optional[BitSet] = None,
                    cache: Optional[CacheContext] = None,
                    ) -> Deserialized:

        any_field, data, offset = FieldDesc.deserialize(
            data, endian=endian, cache=cache)
        if any_field is None:
            return Deserialized(data=None, buffer=data, offset=offset)

        value, data, off = from_wire(any_field, data=data, endian=endian,
                                     bitset=None, cache=cache)
        offset += off

        if any_field.field_type.is_complex:
            dataclass_instance = dataclass_from_field_desc(any_field)()
            fill_dataclass(dataclass_instance, value)
            return Deserialized(data=dataclass_instance, buffer=data,
                                offset=offset)

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
        found_keys = [key for key in set(value).intersection(possible_keys)
                      if value.get(key, None) is not None]
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
            to_wire(child, value=value[key], endian=endian, bitset=None,
                    cache=cache)
        )
        return serialized

    @classmethod
    def deserialize(cls,
                    field: FieldDesc,
                    data: bytes, *,
                    endian: Endian,
                    bitset: Optional[BitSet] = None,
                    cache: Optional[CacheContext] = None,
                    ) -> Deserialized:
        field = typing.cast(StructuredField, field)
        index, data, offset = Size.deserialize(data, endian=endian)
        if index is None:
            return Deserialized(data=None, buffer=data, offset=offset)

        selected_key, selected_field = list(field.children.items())[index]
        value = {}.fromkeys(field.children)
        value[selected_key], data, off = from_wire(
            selected_field, data=data, endian=endian, bitset=None, cache=cache)

        offset += off
        return Deserialized(data=value, buffer=data, offset=offset)


class StructFieldData(DataSerializer, handles={FieldType.struct}):
    """
    Struct field data - not to be confused with introspection/structure
    definition information.

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
        child_bitset: Optional[BitSet] = None

        for index, child in bitset_index_to_child:
            if child.field_type in {FieldType.struct, FieldType.union}:
                # Child may have bits selected
                child_bitset = bitset.offset_by(-index)
            elif index not in bitset and 0 not in bitset:
                continue
            else:
                child_bitset = None

            if isinstance(value, typing.Mapping):
                child_value = value[child.name]
            else:
                child_value = getattr(value, child.name)

            serialized.extend(
                to_wire(child, value=child_value, endian=endian,
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
                    ) -> Deserialized:
        field = typing.cast(StructuredField, field)
        if bitset is None:
            bitset = BitSet({0})

        offset = 0
        if field.array_type == FieldArrayType.variable_array:
            present, data, off = Size.deserialize(data, endian=endian)
            offset += off
            if present == 0:
                # Not present
                return Deserialized(data=None, buffer=data, offset=offset)
            if present != 1:
                raise ValueError(f'Unexpected presence byte: {present}')

        bitset_index_to_child = [
            (field.descendents.index((name, child)) + 1, child)
            for name, child in field.children.items()
        ]
        value = {}
        child_bitset: Optional[BitSet] = None
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

            value[child.name], data, off = from_wire(
                child, data=data, endian=endian,
                cache=cache, bitset=child_bitset
            )
            offset += off

        return Deserialized(data=value, buffer=data, offset=offset)


class DataWithBitSet(CoreSerializableWithCache):
    """
    Pair of Data, described by ``field`` (FieldDesc), and BitSet.

    Serializes the BitSet first, and then the Data that goes along with it.

    Parameters
    ----------
    bitset : BitSet
    interface : FieldDesc
    data :

    Note
    ----
    To serialize, ``[bitset, interface, data]`` are all required.
    To deserialize, ``interface`` must be specified, and ``[bitset, data]``
    will be filled in.
    """

    def __init__(self,
                 bitset: BitSet = None,
                 interface: FieldDesc = None,
                 data=None,
                 ):
        if is_pva_dataclass_instance(data):
            data = typing.cast(PvaStruct, data)
            interface = get_pv_structure(data)
        elif is_pva_dataclass(data):
            interface = get_pv_structure(data)
            data = None
        elif isinstance(data, StructuredField):
            # TODO it doesn't make sense to allow everything here
            interface = data
            data = None

        if bitset is None:
            bitset = BitSet({0})

        self.bitset = bitset
        self.interface = interface
        self.data = data

    def __repr__(self):
        return (
            f'{self.__class__.__name__}(data={self.data}, '
            f'interface={self.interface}, bitset={self.bitset})'
        )

    def serialize(self, endian: Endian,
                  cache: Optional[CacheContext] = None) -> List[bytes]:
        serialized = []
        assert self.bitset is not None
        assert self.interface is not None
        assert self.data is not None
        serialized.extend(self.bitset.serialize(endian=endian))
        serialized.extend(to_wire(self.interface, value=self.data,
                                  endian=endian, bitset=self.bitset,
                                  cache=cache))
        return serialized

    def deserialize(self,
                    data: bytes, *,
                    endian: Endian,
                    cache: Optional[CacheContext] = None,
                    ) -> Deserialized:
        assert self.interface is not None
        self.bitset, data, offset = BitSet.deserialize(data, endian=endian)
        self.data, data, off = from_wire(self.interface, data=data,
                                         endian=endian, bitset=self.bitset,
                                         cache=cache)
        offset += off

        # TODO: dataclass instance return here doesn't make sense; a
        # nested dictionary for updating the structure does.
        return Deserialized(data=self, buffer=data, offset=offset)


class FieldDescAndData(CoreSerializableWithCache):
    """
    A field description and associated data.

    Parameters
    ----------
    interface : FieldDesc
    data :

    Note
    ----
    To serialize, ``[interface, data]`` are both required.
    To deserialize, no arguments are required.
    """

    _field_class = FieldDesc
    interface: Optional[FieldDesc]
    data: Optional[PvaStruct]

    def __init__(self, interface: Union[FieldDesc, PvaStruct, None] = None,
                 data=None):
        if is_pva_dataclass_instance(data):
            data = typing.cast(PvaStruct, data)
            interface = get_pv_structure(data)
        elif is_pva_dataclass(interface):
            interface = typing.cast(PvaStruct, interface)
            interface = get_pv_structure(interface)

        self.interface = interface
        self.data = data

    def __repr__(self):
        return (
            f'{self.__class__.__name__}(data={self.data}, '
            f'interface={self.interface})'
        )

    def serialize(self,
                  endian: Endian,
                  cache: Optional[CacheContext] = None,
                  ) -> List[bytes]:
        if self.interface is None:
            return [bytes([TypeCode.NULL_TYPE_CODE])]

        assert self.data is not None

        serialized = self.interface.serialize(endian=endian, cache=cache)
        serialized.extend(to_wire(self.interface, value=self.data,
                                  endian=endian, bitset=None, cache=cache))
        return serialized

    @classmethod
    def deserialize(cls,
                    data: bytes,
                    *,
                    endian: Endian,
                    cache: Optional[CacheContext] = None,
                    ) -> Deserialized:
        field, data, offset = cls._field_class.deserialize(
            data, endian=endian, cache=cache)
        if field is None:
            value = None
            dataclass_instance = None
        else:
            value, data, off = from_wire(field, data=data, endian=endian,
                                         bitset=None, cache=cache)
            offset += off

            # TODO: caching dataclass instances? should be in CacheContext,
            # right?
            dataclass_instance = dataclass_from_field_desc(field)()
            fill_dataclass(dataclass_instance, value)

        return Deserialized(data=cls(data=dataclass_instance),
                            buffer=data,
                            offset=offset)


class PVRequest(FieldDescAndData):
    """
    A special form of FieldDescAndData, representing a PVRequest.

    Handles string to PVRequest structure translation, if required.
    """
    # TODO: why doesn't it work specifying this?
    # _field_class = PVRequestStruct

    def __init__(self, interface: FieldDesc = None,
                 data=None):
        if isinstance(data, str):
            interface = PVRequestStruct.from_string(data)
            data = interface.values

        super().__init__(interface=interface, data=data)

    def to_bitset_and_options(self, data) -> Tuple[FrozenSet[int], dict]:
        """
        Convert to a bitset and options, given the data it refers to.
        """
        pvreq_info = dataclasses.asdict(self.data)
        fields = pvreq_info.get('field', {})

        if not fields:
            # No fields? ... All fields!
            bitset = BitSet({0})
            options = {}
        else:
            bitset = fields_to_bitset(data, fields)
            options = bitset.options

        return frozenset(bitset), options


def to_wire_field(field: FieldDesc,
                  value: typing.Any,
                  endian: Endian,
                  bitset: Optional[BitSet] = None,
                  cache: Optional[CacheContext] = None,
                  ) -> List[bytes]:
    """
    Serialize ``value`` for sending over the wire, according to the given
    ``FieldDesc`` in ``field``.

    Parameters
    ----------
    field : FieldDesc
        Determines how to serialize ``value``.

    value: any
        To be serialized according to ``FieldDesc``.

    endian : Endian
        The target endianness; ``value`` assumed to be stored according to
        the system endian.

    bitset : BitSet, optional
        The associated bitset, if applicable.

    cache : CacheContext, optional
        The associated cache context, if applicable.

    Returns
    -------
    list of bytes
        The serialized data.
    """
    serialized = []
    handler = DataSerializer.handlers[field.field_type]

    if field.array_type.has_serialization_size:
        serialized.extend(Size.serialize(len(value), endian=endian))

    if (not isinstance(value, typing.Iterable) or
            isinstance(value, (bytes, str, typing.Mapping))):
        value = (value, )

    if issubclass(handler, VariantFieldData):
        # TODO: expectation of how the user should put these values?
        value = (value, )

    serialize = functools.partial(
        handler.serialize, endian=endian, field=field, bitset=bitset,
        cache=cache
    )

    for single_value in value:
        serialized.extend(serialize(value=single_value))

    return serialized


def to_wire(category,
            value: typing.Any,
            endian: Endian,
            bitset: Optional[BitSet] = None,
            cache: Optional[CacheContext] = None,
            ) -> List[bytes]:
    """
    Serialize ``value`` for sending over the wire.

    Parameters
    ----------
    category : FieldDesc, CoreSerializable, or similar
        Required for disambiguation when not obvious based on the type.

    value: any
        Special handling for CoreSerializable, CoreStatelessSerializable,
        CoreSerializableWithCache.
        Or serialized according to ``FieldDesc`` from ``category``.

    bitset : BitSet, optional
        The associated bitset, if applicable.

    cache : CacheContext, optional
        The associated cache context, if applicable.

    Returns
    -------
    list of bytes
        The serialized data.

    See Also
    --------
    :func:`to_wire_field`
    """
    if isinstance(value, CoreSerializable):
        return value.serialize(endian=endian)

    if isinstance(value, CoreStatelessSerializable):
        return value.serialize(value, endian=endian)

    if category is FieldDesc or isinstance(value, (FieldDesc, CoreSerializableWithCache)):
        if is_pva_dataclass(value) or is_pva_dataclass_instance(value):
            value = get_pv_structure(typing.cast(PvaStruct, value))
        return value.serialize(endian=endian, cache=cache)

    if not isinstance(category, FieldDesc):
        raise RuntimeError(
            f'Unhandled: {category} value={value}'
        )

    return to_wire_field(
        typing.cast(FieldDesc, category),
        value=value, endian=endian, bitset=bitset, cache=cache,
    )


@functools.singledispatch
def from_wire(category,
              data: bytes, *,
              endian: Endian,
              bitset: Optional[BitSet] = None,
              cache: Optional[CacheContext] = None,
              ) -> Deserialized:
    """
    Top-level, generic deserialization from the wire.

    Note that this ``functools.singledispatch`` to easily dispatch multiple
    categories of items into different callables.

    Parameters
    ----------
    category : CoreSerializableWithCache
        The field category.  Indicates the type of data to be read, along with
        size information, if applicable.

    data : bytes
        The data buffer to read from.

    endian : Endian
        The endianness of the data to be read.

    bitset : BitSet, optional
        The associated bitset, if applicable.

    cache : CacheContext, optional
        The associated cache context, if applicable.

    Returns
    -------
    Deserialized

    See Also
    --------
    :func:`from_wire_field_desc`
    :func:`from_wire_class`
    """


@from_wire.register(type)
def from_wire_class(cls: Union[Type[CoreSerializable],
                               Type[CoreStatelessSerializable],
                               Type[CoreSerializableWithCache]],
                    data: bytes,
                    *,
                    endian: Endian,
                    bitset: Optional[BitSet] = None,
                    cache: Optional[CacheContext] = None,
                    ) -> Deserialized:
    """
    Deserialization (from the wire) of a specific class type.

    This includes serializable classes of type :class:`CoreSerializable`,
    :class:`CoreStatelessSerializable`, and :class:`CoreSerializableWithCache`.

    Appropriately passes the required subset of keyword arguments to the given
    deserializer.

    Parameters
    ----------
    cls : CoreSerializable, CoreStatelessSerializable, or CoreSerializableWithCache
        The class to deserialize with.

    data : bytes
        The data buffer to read from.

    endian : Endian
        The endianness of the data to be read.

    cache : CacheContext, optional
        The associated cache context, if applicable.

    Returns
    -------
    Deserialized
    """
    if issubclass(cls, CoreSerializableWithCache):
        cls = typing.cast(Type[CoreSerializableWithCache], cls)
        # assert cache is not None
        return cls.deserialize(data=data, endian=endian,
                               cache=typing.cast(CacheContext, cache))

    if issubclass(cls, (CoreSerializable, CoreStatelessSerializable)):
        cls = typing.cast(Type[CoreSerializable], cls)
        return cls.deserialize(data=data, endian=endian)

    raise ValueError('Unhandled deserialization class: {cls}')


@from_wire.register(FieldDesc)
def from_wire_field_desc(field: FieldDesc,
                         data: bytes,
                         *,
                         endian: Endian,
                         bitset: Optional[BitSet] = None,
                         cache: Optional[CacheContext],
                         ) -> Deserialized:
    """
    Deserialization (from the wire) of FieldDesc data.

    Includes data from all field types, such as ``FieldType.int32``.

    Parameters
    ----------
    field : FieldDesc
        The field description information.  Indicates the type of data to be
        read, along with size information, if applicable.

    data : bytes
        The data buffer to read from.

    endian : Endian
        The endianness of the data to be read.

    bitset : BitSet, optional
        The associated bitset, if applicable.

    cache : CacheContext, optional
        The associated cache context, if applicable.

    Returns
    -------
    Deserialized
    """
    offset = 0
    handler = DataSerializer.handlers[field.field_type]

    if field.array_type.has_serialization_size:
        count, data, off = Size.deserialize(data, endian=endian)
        offset += off
    else:
        count = field.size or 1

    # print('\n\n', ' '.join(hex(c)[2:].zfill(2) for c in data[:20]))

    array_based = issubclass(handler, ArrayBasedDataSerializer)

    deserialize = functools.partial(
        handler.deserialize, endian=endian, field=field, bitset=bitset,
        cache=cache
    )
    if array_based:
        loops = 1
        deserialize = functools.partial(deserialize, count=count)
    else:
        loops = count

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


@from_wire.register(CoreSerializableWithCache)
def _(category: CoreSerializableWithCache,
      data: bytes, *,
      endian: Endian,
      bitset: Optional[BitSet] = None,
      cache: Optional[CacheContext] = None,
      ) -> Deserialized:
    return category.deserialize(data=data, endian=endian, cache=cache)
