"""
Create a new PVAccess-compatible dataclass given a type-annotated class, and
vice-versa.
"""

import dataclasses
import inspect
import typing

from . import _typing_compat as typing_compat
from ._annotations import (annotation_default_values, annotation_type_map,
                           type_to_annotation)
from ._core import FieldArrayType, FieldType
from ._fields import (BitSet, FieldDesc, SimpleField, StructuredField,
                      _children_from_field_list, _descendents_from_field_list)


def new_struct(fields: dict,
               struct_name: str = '',
               parent: typing.Optional[StructuredField] = None,
               name: str = '',
               array_type: FieldArrayType = FieldArrayType.scalar,
               size: typing.Optional[int] = None,
               field_type=FieldType.struct,
               ) -> StructuredField:
    return StructuredField(
        field_type=field_type,
        array_type=array_type,
        name=name,
        struct_name=struct_name,
        metadata={'parent': parent},
        children=_children_from_field_list(fields.values()),
        descendents=_descendents_from_field_list(fields.values()),
        size=size,
    )


def _field_from_annotation(attr, annotation,
                           array_type=FieldArrayType.scalar,
                           parent=None):
    annotation = annotation_type_map.get(annotation, annotation)
    if isinstance(annotation, FieldType):
        return SimpleField(
            field_type=annotation,
            array_type=array_type,
            name=attr,
            size=None,
        )

    if hasattr(annotation, '_pva_struct_'):
        struct = annotation._pva_struct_
        return new_struct(
            struct.children,
            struct_name=struct.struct_name,
            name=attr,
            array_type=array_type,
            parent=parent,
        )


def _get_union_from_annotation(attr, annotation,
                               array_type=FieldArrayType.scalar):
    """
    We get::

        attr = typing.Union[option1, option2]

    We create::

        @pva_dataclass
        class attr:
            option1
            option2

    And then change it to a FieldType.union.

    The annotation has no access to the dynamically created dataclass.  So, add
    in metadata to refer back to that.  It can then be used for instantiating a
    new dataclass.
    """

    def _get_name(arg):
        if hasattr(arg, 'name'):
            return arg.name
        if hasattr(arg, '__name__'):
            return arg.__name__
        return arg.__class__.__name__

    options = [
        (_get_name(arg), arg)
        for idx, arg in enumerate(typing_compat.get_args(annotation))
    ]

    union_class = pva_dataclass(
        dataclasses.make_dataclass(cls_name=attr, fields=options),
        union=True,
    )

    union_class._pva_struct_.metadata['union_dataclass'] = union_class
    return union_class


def _get_pva_fields_from_annotations(cls: type) -> dict:
    pva_fields = {}

    for attr, annotation in typing.get_type_hints(cls).items():
        origin = typing_compat.get_origin(annotation)
        if origin is list:
            array_type = FieldArrayType.variable_array
            args = typing_compat.get_args(annotation)
            try:
                annotation, = args
            except ValueError:
                raise ValueError(
                    f'Array annotation only allows one type. Got: {args}'
                ) from None
        elif origin is typing.Union:
            union_cls = _get_union_from_annotation(attr, annotation)
            pva_fields[attr] = union_cls._pva_struct_
            continue
        else:
            array_type = FieldArrayType.scalar

        pva_fields[attr] = _field_from_annotation(
            attr=attr, annotation=annotation, array_type=array_type
        )

    return pva_fields


def _get_default_by_field(attr: str,
                          field: FieldDesc,
                          annotation) -> dataclasses.Field:
    dcls_field = dataclasses.field()

    if field.array_type == FieldArrayType.scalar:
        if field.field_type == FieldType.struct:
            dcls_field.default_factory = lambda item=annotation: item()
        elif field.field_type == FieldType.union:
            # TODO this isn't quite right
            union_dcls = field.metadata['union_dataclass']

            def union_init(*, dcls=union_dcls):
                kwargs = {}
                items = enumerate(typing.get_type_hints(dcls).items())
                for idx, (attr, annotation) in items:
                    print(idx, attr, annotation)
                    kwargs[attr] = None
                return union_dcls(**kwargs)

            dcls_field.default_factory = union_init
        else:
            dcls_field.default = annotation_default_values[field.field_type]
    else:
        dcls_field.default_factory = list
        dcls_field.default = dataclasses.MISSING
    dcls_field.name = attr
    return dcls_field


def _get_defaults_to_add(cls: type, pva_fields: typing.Dict[str, FieldDesc]):
    defaults = {}
    for attr, annotation in typing.get_type_hints(cls).items():
        try:
            pva_field = pva_fields[attr]
        except KeyError:
            # ?
            continue

        if not hasattr(cls, attr):
            # No default defined
            defaults[attr] = _get_default_by_field(attr, pva_field, annotation)

    return defaults


def pva_dataclass(_cls: typing.Optional[type] = None, *,
                  add_defaults: bool = True,
                  union: bool = False):
    """
    Create a new PVAccess-compatible dataclass given a type-annotated class.

    Parameters
    ----------
    _cls : type
        The class.

    add_defaults : bool, optional
        Add default values for easy instantiation of the data class. Supports
        sub-structures as well.
    """

    def wrap(cls: type) -> type:
        pva_fields = _get_pva_fields_from_annotations(cls)
        if add_defaults:
            for attr, default in _get_defaults_to_add(cls, pva_fields).items():
                setattr(cls, attr, default)
        dcls = dataclasses.dataclass(cls)
        dcls._pva_struct_ = new_struct(
            pva_fields,
            struct_name=cls.__name__,
            field_type=FieldType.union if union else FieldType.struct,
        )
        return dcls

    if _cls is None:
        return wrap

    return wrap(_cls)


def array_of(item: typing.Union[SimpleField, StructuredField, FieldType, type],
             *,
             array_type=FieldArrayType.variable_array,
             size=None,
             name=None,
             ) -> FieldDesc:
    # Obsolete due to List[] annotation?
    if isinstance(item, FieldType):
        return SimpleField(
            field_type=item,
            array_type=array_type,
            name=name or '',
            size=size,
        )
    if isinstance(item, SimpleField):
        return SimpleField(
            field_type=item.field_type,
            array_type=array_type,
            name=name or item.name,
            size=size,
        )
    if isinstance(item, StructuredField):
        struct = item
    else:
        struct = item._pva_struct_

    return new_struct(
        struct.children,
        struct_name=struct.struct_name,
        name=name or struct.name,
        array_type=array_type,
        size=size,
    )


class PvaStruct(type):
    """
    An alternative wrapper for pva dataclasses, using metaclasses instead.

    Preliminary API; may be removed.
    """

    def __new__(cls, name, bases, classdict):
        return pva_dataclass(type.__new__(cls, name, bases, dict(classdict)))


def dataclass_from_field_desc(field: FieldDesc) -> type:
    """
    Take a field description, and make a pva_dataclass out of it.

    Parameters
    ----------
    field : FieldDesc
        The field description.

    Returns
    -------
    datacls : type
        The generated dataclass.
    """
    # Use a roundabout approach - create a class, add annotations, and
    # use `pva_dataclass` machinery to do the heavy lifting.
    cls = type(field.struct_name or field.name, (), {})

    annotations = {}
    cls.__annotations__ = annotations

    for attr, child in field.children.items():
        if child.field_type in {FieldType.struct, FieldType.union}:
            annotation_type = dataclass_from_field_desc(child)
        else:
            annotation_type = type_to_annotation[child.field_type]

        if child.array_type == FieldArrayType.variable_array:
            annotation_type = typing.List[annotation_type]

        annotations[attr] = annotation_type

    return pva_dataclass(cls)


def is_pva_dataclass(obj) -> bool:
    """
    Is ``obj`` a dataclass?
    """
    return inspect.isclass(obj) and hasattr(obj, '_pva_struct_')


def is_pva_dataclass_instance(obj) -> bool:
    """
    Is ``obj`` a dataclass?
    """
    return not inspect.isclass(obj) and hasattr(obj, '_pva_struct_')


def fill_dataclass(instance: object, value: dict) -> BitSet:
    """
    Fill a dataclass instance given a dictionary.

    Returns a BitSet indicating the fields that were set.
    """
    if not is_pva_dataclass_instance(instance):
        print(instance, hasattr(instance, '_pva_struct_'))
        raise ValueError(f'{instance} is not a pva dataclass')

    bitset = BitSet({})
    pva_struct = instance._pva_struct_
    children = list(pva_struct.children)

    for key, v in value.items():
        try:
            bitset_index = children.index(key) + 1
        except KeyError:
            raise KeyError(f'Key {key} not found in structure '
                           f'{pva_struct.struct_name}')

        if isinstance(v, dict):
            child_bitset = fill_dataclass(getattr(instance, key), value=v)
            bitset |= child_bitset.offset_by(bitset_index)
        else:
            setattr(instance, key, v)
            bitset.add(bitset_index)

    return bitset
