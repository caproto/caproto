"""
Field description (and other primitives) serialization helpers.
"""

import dataclasses
import logging
import textwrap
import typing
from dataclasses import field
from struct import pack, unpack
from typing import Dict, List, Optional, Tuple, Type, Union

from . import _core as core
from ._core import (CacheContext, CoreSerializable, CoreSerializableWithCache,
                    CoreStatelessSerializable, Deserialized, Endian,
                    FieldArrayType, FieldDescByte, FieldType, StatusType,
                    TypeCode)

serialization_logger = logging.getLogger('caproto.pva.serialization')


@dataclasses.dataclass(frozen=True)
class FieldDesc(CoreSerializableWithCache):
    """
    A frozen dataclass which represents a single field - whether it be a struct
    or a basic data type.
    """

    name: str
    field_type: FieldType
    array_type: FieldArrayType
    size: Optional[int] = 1
    metadata: Dict = field(default_factory=dict, hash=False, repr=False)

    def serialize(self, endian: Endian, cache=None) -> List[bytes]:
        raise NotImplementedError(
            "Implemented in SimpleField, StructuredField only."
        )

    @classmethod
    def deserialize(cls,
                    data: bytes,
                    *,
                    endian: Endian,
                    cache: Optional[CacheContext] = None,
                    name: Optional[str] = None,
                    ) -> Deserialized:
        """
        Implemented generically here as the recipient may not know the
        type of field description will be coming in - that is, a SimpleField or
        StructuredField.

        This contrasts with `serialize` which is only implemented specially for
        subclasses of :class:`FieldDesc`.
        """
        data = memoryview(data)
        interface_id = None
        offset = 0

        type_code = data[0]

        if type_code == TypeCode.NULL_TYPE_CODE:
            return Deserialized(data=None, buffer=data[1:], offset=1)

        if type_code == TypeCode.FULL_TAGGED_ID_TYPE_CODE:
            # TODO: type of tag is unclear?
            raise NotImplementedError('FULL_TAGGED_ID_TYPE_CODE')

        if type_code in {TypeCode.ONLY_ID_TYPE_CODE,
                         TypeCode.FULL_WITH_ID_TYPE_CODE}:
            # Consume the type code here:
            data = data[1:]
            offset += 1

            interface_id, data, off = Identifier.deserialize(
                data, endian=endian)
            offset += off

            if type_code == TypeCode.ONLY_ID_TYPE_CODE:
                if cache is None:
                    raise RuntimeError(
                        f'Cache not specified; cannot determine type code '
                        f'{interface_id}'
                    )

                intf = cache.ours[interface_id]
                return Deserialized(data=intf.as_new_name(name), buffer=data,
                                    offset=offset)

            # otherwise, fall through...

        fd, _, _ = FieldDescByte.deserialize(data)
        field_cls = typing.cast(
            Type[FieldDesc],
            StructuredField if fd.field_type.is_complex else SimpleField
        )

        intf, data, off = field_cls.deserialize(
            data, endian=endian, cache=cache, name=name)
        offset += off

        if interface_id is not None and cache is not None:
            cache.ours[interface_id] = intf

        return Deserialized(data=intf, buffer=data, offset=offset)

    def summary(self) -> str:
        return ''

    def fields_by_bitset(self, bitset: 'BitSet'):
        """Implemented in StructuredField only."""

    def as_new_name(self, name):
        if name == self.name:
            return self
        return dataclasses.replace(self, name=name)


@dataclasses.dataclass(frozen=True)
class SimpleField(FieldDesc):
    """
    A non-structured field description, containing one or more primitive
    values.
    """

    def serialize(self, endian: Endian, cache=None) -> List[bytes]:
        buf = [bytes(FieldDescByte.from_field(self))]
        if self.array_type.has_field_desc_size:
            buf.extend(Size.serialize(self.size, endian=endian))
        return buf

    @classmethod
    def deserialize(cls,
                    data: bytes,
                    *,
                    endian: Endian,
                    cache: CacheContext,
                    name: Optional[str] = None,
                    ) -> Deserialized:
        """
        Deserialize a simple field (i.e., not structured field).
        """

        fd, data, offset = FieldDescByte.deserialize(data)
        assert not fd.field_type.is_complex

        if fd.array_type.has_field_desc_size:
            size, data, off = Size.deserialize(data, endian=endian)
            offset += off
        else:
            size = 1

        inst = SimpleField(
            name=name or '',
            field_type=fd.field_type,
            size=size,
            array_type=fd.array_type,
        )
        return Deserialized(data=inst, buffer=data, offset=offset)

    def summary(self, *, value='') -> str:
        array_desc = self.array_type.summary_with_size(self.size)
        return f'{self.field_type.name}{array_desc} {self.name}{value}'


Descendent = Tuple[str, 'FieldDesc']


@dataclasses.dataclass(frozen=True)
class StructuredField(FieldDesc):
    """
    A structured field description, containing one or more children, which in
    turn may be structured or simple.
    """

    struct_name: str = ''
    children: Dict[str, FieldDesc] = field(repr=False, hash=False,
                                           default_factory=dict)
    descendents: Tuple[Descendent, ...] = field(repr=False, hash=True,
                                                default_factory=tuple)

    def serialize_cache_update(self, endian: Endian, cache: Optional[CacheContext]):
        if cache is None or cache.theirs is None:
            return True, []

        hash_key = hash(self)
        if hash_key in cache.theirs:
            identifier = Identifier.serialize(
                cache.theirs[hash_key], endian=endian)
            return False, [bytes([TypeCode.ONLY_ID_TYPE_CODE])] + identifier

        if cache.theirs:
            # TODO: LRU cache with only 65k entries
            id_ = max(cache.theirs.values()) + 1
        else:
            id_ = 1

        cache.theirs[hash_key] = id_
        identifier = Identifier.serialize(id_, endian=endian)
        return True, [bytes([TypeCode.FULL_WITH_ID_TYPE_CODE])] + identifier

    def serialize(self, endian: Endian, cache: Optional[CacheContext]) -> List[bytes]:
        '''Serialize field description introspection data.'''
        include_all, buf = self.serialize_cache_update(
            endian=endian, cache=cache)
        if not include_all:
            return buf

        buf.extend(FieldDescByte.from_field(self).serialize(endian))
        if self.field_type != FieldType.any:
            buf.extend(String.serialize(self.struct_name, endian=endian))
            buf.extend(Size.serialize(len(self.children), endian=endian))

            for name, child in self.children.items():
                buf.extend(String.serialize(name, endian=endian))
                buf.extend(child.serialize(endian=endian, cache=cache))

        return buf

    @classmethod
    def deserialize(cls, data: bytes, *, endian: Endian,
                    cache: CacheContext,
                    name=None) -> Deserialized:
        fd, data, offset = FieldDescByte.deserialize(data)

        field_type = fd.field_type
        array_type = fd.array_type
        assert field_type.is_complex

        if array_type.has_field_desc_size:
            size, data, off = Size.deserialize(data, endian=endian)
            offset += off
        else:
            size = 1

        if field_type == FieldType.any:
            struct = cls(
                field_type=field_type,
                array_type=array_type,
                size=size,
                name=name,
                struct_name='',
                children={},
                descendents=tuple(),
            )
            return Deserialized(data=struct, buffer=data, offset=offset)

        if array_type == FieldArrayType.variable_array:
            st, data, off = FieldDesc.deserialize(data, endian=endian, cache=cache)
            offset += off
            return Deserialized(dataclasses.replace(st, array_type=array_type,
                                                    name=name),
                                buffer=data, offset=offset)

        struct_name, data, off = String.deserialize(data, endian=endian)
        offset += off

        num_fields, data, off = Size.deserialize(data, endian=endian)
        offset += off

        fields = []
        for _ in range(num_fields):
            child_name, data, off = String.deserialize(data, endian=endian)
            offset += off

            st, data, off = FieldDesc.deserialize(data, endian=endian,
                                                  cache=cache, name=child_name)
            offset += off
            fields.append(st)

        struct_name = struct_name or ''  # or field_type.name
        struct = cls(
            field_type=field_type,
            array_type=array_type,
            size=size,
            name=name or struct_name,
            struct_name=struct_name,
            children=_children_from_field_list(fields),
            descendents=_descendents_from_field_list(fields),
        )

        return Deserialized(data=struct, buffer=data, offset=offset)

    def summary(self, *, value='') -> str:
        array_desc = self.array_type.summary_with_size(self.size)
        sname = self.struct_name
        if sname and sname != self.name and sname != 'any':  # TODO
            type_name = f'{self.field_type.name} {self.struct_name}'
        else:
            type_name = self.field_type.name
        res = [f'{type_name}{array_desc} {self.name}{value}'.rstrip()]
        for child in self.children.values():
            res.append(textwrap.indent(child.summary(), prefix='    '))
        return '\n'.join(res)

    def to_dataclass(self) -> type:
        """
        Create a pva dataclass from this FieldDesc.

        Returns
        -------
        cls : type
            The new data class.
        """
        from ._dataclass import dataclass_from_field_desc  # noqa
        return dataclass_from_field_desc(self)


def _children_from_field_list(fields: typing.Iterable[FieldDesc]
                              ) -> Dict[str, 'FieldDesc']:
    """
    Get the ``children`` parameter to be used with ``StructuredField()``.
    """
    return {child.name: child for child in fields}


def _descendents_from_field_list(fields: typing.Iterable[FieldDesc]
                                 ) -> Tuple[Tuple[str, FieldDesc], ...]:
    """
    Get the ``descendents`` parameter to be used with ``StructuredField()``.
    """
    descendents = []
    for child in fields:
        descendents.append((child.name, child))
        if isinstance(child, StructuredField):
            child = typing.cast(StructuredField, child)
            if child.field_type == FieldType.union:
                ...
            elif child.array_type == FieldArrayType.variable_array:
                ...
            else:
                descendents.extend(
                    [(f'{child.name}.{attr}', desc)
                     for attr, desc in child.descendents]
                )

    return tuple(descendents)


# Look-up table for bitsets
_BITSET_LUT = [1 << i for i in range(8)]


class Identifier(CoreStatelessSerializable):
    """
    Short (int16) identifier, used in multiple places.
    """

    @classmethod
    def serialize(cls, id_: int, endian: Endian) -> List[bytes]:
        return [pack(endian + 'h', id_)]

    @classmethod
    def deserialize(cls, data: bytes, *, endian: Endian) -> Deserialized:
        # NOTE: IDs signed according to docs?
        return Deserialized(data=unpack(endian + 'h', data[:2])[0],
                            buffer=data[2:],
                            offset=2)


class Size(CoreStatelessSerializable):
    """
    A compact representation of size (or ``None``), taking roughly only the
    number of bytes required.

    Supports up to 64-bit values.
    """

    @classmethod
    def serialize(cls, size: Union[int, None], endian: Endian) -> List[bytes]:
        'Sizes/lengths are encoded in 3 ways, depending on the size'
        if size is None:
            # TODO_DOCS: this is misrepresented in the docs
            # an empty size is represented as 255 (-1)
            return [pack(endian + 'B', 255)]

        assert size >= 0, 'Negative sizes cannot be serialized'

        if size < 254:
            return [pack(endian + 'B', size)]
        if size < core.MAX_INT32:
            return [pack(endian + 'BI', 254, size)]

        return [pack(endian + 'BIQ', 254, core.MAX_INT32, size)]

    @classmethod
    def deserialize(cls, data: bytes, *, endian: Endian) -> Deserialized:
        # TODO_DOCS: this is misrepresented in the docs
        b0 = data[0]
        if b0 == 255:
            # null size
            return Deserialized(data=None, buffer=data[1:], offset=1)
        if b0 < 254:
            return Deserialized(data=b0, buffer=data[1:], offset=1)

        int32, = unpack(endian + 'I', data[1:5])
        if int32 != core.MAX_INT32:
            return Deserialized(data=int32, buffer=data[5:], offset=5)

        return Deserialized(
            data=unpack(endian + 'Q', data[5:13])[0],
            buffer=data[13:],
            offset=13
        )


class String(CoreStatelessSerializable):
    """
    A run-length encoded utf-8 string (i.e., ``[Size][utf-8 string]``).
    """
    encoding = 'utf-8'

    @classmethod
    def serialize(cls, value, endian: Endian) -> List[bytes]:
        encoded = value.encode(cls.encoding)
        return Size.serialize(len(encoded), endian) + [encoded]

    @classmethod
    def deserialize(cls, data: bytes, *, endian: Endian) -> Deserialized:
        sz, data, consumed = Size.deserialize(data, endian=endian)
        return Deserialized(
            data=str(data[:sz], cls.encoding),
            buffer=data[sz:],
            offset=consumed + sz
        )


class BitSet(set, CoreSerializable):
    """
    A "BitSet" for marking certain fields of a structure by index.

    {0} is a special BitSet, indicating all fields are selected.
    """

    def offset_by(self, offset) -> 'BitSet':
        """
        Add the given offset to this bitset, returning a new bitset.
        """
        if 0 in self:
            # TODO: This isn't true in all cases, depends on what the caller is
            # after
            return BitSet({0})

        return BitSet({idx + offset for idx in self
                       if idx + offset >= 0}
                      )

    def __and__(self, other):
        """And/intersection with other set, with special handling for {0}."""
        if 0 in self:
            return BitSet(other)
        if 0 in other:
            return self
        return type(self)(super().__and__(other))

    def __or__(self, other):
        """Or/Union with other set, including special handling for {0}."""
        result = super().__or__(other)
        if 0 in result:
            return type(self)({0})
        return result

    def serialize(self, endian: Endian) -> List[bytes]:
        if not len(self):
            return Size.serialize(0, endian=endian)

        start = 0
        end = 7
        current = 0
        ret = bytearray()

        for bit in sorted(self):
            while bit > end:
                ret.append(current)
                current = 0
                start, end = start + 8, end + 8
            current |= _BITSET_LUT[bit - start]

        if current:
            ret.append(current)

        return Size.serialize(len(ret), endian=endian) + [ret]

    @classmethod
    def deserialize(cls, data: bytes, *, endian: Endian) -> Deserialized:
        sz, data, offset = Size.deserialize(data, endian=endian)

        byte_start = 0
        bitset = set()
        for ch in data[:sz]:
            for bit_num, mask in enumerate(_BITSET_LUT):
                if ch & mask:
                    bitset.add(byte_start + bit_num)
            byte_start += 8

        return Deserialized(data=BitSet(bitset),
                            buffer=data[sz:],
                            offset=offset + sz)


class Status(CoreSerializable):
    """A status structure, with a type and optional message and context."""

    status: StatusType
    message: Optional[str]
    call_tree: Optional[str]

    def __init__(self, status: StatusType,
                 message: Optional[str] = None,
                 call_tree: Optional[str] = None):
        self.status = StatusType(status)

        if status == StatusType.OK:
            if message is not None or call_tree is not None:
                raise ValueError(
                    'Cannot specify message or call_tree with StatusType.OK'
                )
            self.message = None
            self.call_tree = None
        else:
            self.message = message or ''
            self.call_tree = call_tree or ''

    @property
    def is_successful(self) -> bool:
        return self.status in {StatusType.OK, StatusType.OK_VERBOSE,
                               StatusType.WARNING}

    @classmethod
    def create_success(cls):
        """Convenience method to create a new StatusType.OK status object."""
        return cls(status=StatusType.OK)

    @classmethod
    def create_error(cls, message: str, call_tree: Optional[str] = None):
        """Convenience method to create a new StatusType.ERROR status."""
        return cls(status=StatusType.ERROR, message=message,
                   call_tree=call_tree)

    def __repr__(self):
        if self.message or self.call_tree:
            return (
                f'{self.__class__.__name__}({self.status.name},'
                f'message={self.message}, call_tree={self.call_tree})'
            )
        return f'{self.__class__.__name__}({self.status.name})'

    def serialize(self, endian: Endian) -> List[bytes]:
        serialized = [pack('b', int(self.status))]
        if self.status != StatusType.OK:
            serialized.extend(String.serialize(value=self.message or '',
                                               endian=endian))
            serialized.extend(String.serialize(value=self.call_tree or '',
                                               endian=endian))
        return serialized

    @classmethod
    def deserialize(cls, data: bytes, *, endian: Endian) -> Deserialized:
        status = StatusType(unpack('b', data[:1])[0])
        data = data[1:]
        offset = 1

        if status == StatusType.OK:
            message = None
            call_tree = None
        else:
            message, data, off = String.deserialize(data=data, endian=endian)
            offset += off
            call_tree, data, off = String.deserialize(data=data, endian=endian)
            offset += off

        return Deserialized(
            data=cls(status=status, message=message, call_tree=call_tree),
            buffer=data,
            offset=offset
        )
