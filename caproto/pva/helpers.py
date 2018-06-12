import copy
import datetime

from .. import epics_timestamp_to_unix
from .introspection import (structure_from_repr,
                            summarize_field_info,
                            create_value_dict_from_field_desc,
                            )
from . import serialization
from . import types

from collections import OrderedDict


class _FrozenBase:
    @property
    def frozen(self):
        return self.get('_frozen_', False)

    def freeze(self):
        self['_frozen_'] = True

    def __delitem__(self, key):
        if self.frozen:
            raise RuntimeError('Frozen dictionary cannot be modified')
        return super().__delitem__(key)

    def __setitem__(self, key, value):
        if self.frozen:
            raise RuntimeError('Frozen dictionary cannot be modified')
        return super().__setitem__(key, value)


class FrozenDict(_FrozenBase, dict):
    'A dictionary that can be frozen after initialization'


class FrozenOrderedDict(_FrozenBase, OrderedDict):
    'An OrderedDict that can be frozen after initialization'


def freeze_field_desc(fd, nested_types=None):
    'Returns a FrozenDict version of a FieldDesc'
    if isinstance(fd, _FrozenBase):
        return fd

    elif not isinstance(fd, (OrderedDict, dict)):
        return fd

    ret = (FrozenOrderedDict(fd)
           if isinstance(fd, OrderedDict)
           else FrozenDict(fd))

    if nested_types is not None and 'struct_name' in fd:
        struct_name = fd['struct_name']
        is_default = struct_name in ('union', 'structure')
        if not is_default and 'ref_namespace' not in fd:
            nested_types[struct_name] = ret

    if 'fields' in fd:
        if nested_types is None:
            nested_types = {}
        ret['fields'] = OrderedDict(
            (field_name, freeze_field_desc(field, nested_types=nested_types))
            for field_name, field in fd['fields'].items())

        if 'nested_types' in ret:
            ret['nested_types'] = nested_types

    # can cache hashes around here somewhere
    ret.freeze()

    return ret


class FieldDescHelper:
    def __init__(self, fd, *, user_types=None, value_class=None):
        if value_class is None:
            value_class = StructuredValueBase

        self.user_types = user_types
        self.value_class = value_class

        if isinstance(fd, (list, str)):
            fd = structure_from_repr(fd, user_types=user_types)

        if not isinstance(fd, _FrozenBase):
            fd = freeze_field_desc(fd)

        self._fd = fd
        self._value_dict = create_value_dict_from_field_desc(
            self.field_desc, user_types=self.user_types)

        self._repr = '\n'.join(
            '{}{}'.format('    ' * level, info)
            for level, info in summarize_field_info(
                    self._fd, user_types=self.user_types, truncate=None))

    @property
    def field_desc(self):
        return self._fd

    def serialize(self, *, endian, cache, instruct_to_cache=True):
        return serialization.serialize_introspection_data(
            self._fd, endian=endian, cache=cache,
            instruct_to_cache=instruct_to_cache,
        )

    def deserialize_data(self, buf, *, endian, cache):
        data_dict, buf, offset = serialization.deserialize_data(
            self._fd, buf, endian=endian, cache=cache,
        )

        value_inst = self.new_value(data_dict)
        return types.Decoded(data=value_inst, buffer=buf, offset=offset)

    def __repr__(self):
        return self._repr

    def repr_with_values(self, values):
        root_key = self._fd.get('struct_name', '')
        if root_key:
            values = {root_key: values}
        return '\n'.join(
            '{}{}'.format('    ' * level, info)
            for level, info in summarize_field_info(
                    self._fd, values=values, user_types=self.user_types,
                    truncate=None, field_name=root_key,
            ))

    def new_value(self, value_dict=None):
        'Create a new StructuredValue instance'
        return self.value_class(self, user_types=self.user_types,
                                value_dict=value_dict)


class UnionSelectorItem:
    def __init__(self, parent, key, fd):
        self.parent = parent
        self.key = key
        self.fd = fd
        self.options = tuple(self.fd['fields'].keys())

    @property
    def value(self):
        selector = self.parent[self.key]['_selector_']
        return self.options[selector]

    @value.setter
    def value(self, value):
        if isinstance(value, int) and 0 <= value < len(self.options):
            ...
        elif value in self.options:
            value = self.options.index(value)
        else:
            raise ValueError('Selector must be an integer or one of {!r}'
                             ''.format(self.options))

        self.parent[self.key]['_selector_'] = value


class StructuredValueItem:
    def __init__(self, parent, key, fd):
        self.parent = parent
        self.key = key
        self.fd = fd

    @property
    def value(self):
        return self.parent[self.key]

    @value.setter
    def value(self, value):
        self.parent[self.key] = value
        # TODO: validate value

    def update(self, value):
        if self.fd['type_name'] in ('struct', 'union'):
            self.parent[self.key].update(**value)
        else:
            self.value = value


class StructuredValueBase:
    def __init__(self, field_desc, *, user_types=None, value_dict=None):
        if not isinstance(field_desc, FieldDescHelper):
            field_desc = FieldDescHelper(field_desc, user_types=user_types)

        self._fd = field_desc
        self._item_cache = {}
        self._values = (copy.deepcopy(self._fd._value_dict)
                        if value_dict is None
                        else value_dict)

    def serialize(self, *, endian, cache, bitset=None):
        return serialization.serialize_data(
            self._fd.field_desc, self._values, endian=endian, cache=cache,
        )

    @property
    def field_desc(self):
        'The field description associated with the value'
        return self._fd

    def __repr__(self):
        return self._fd.repr_with_values(self._values)

    def __getitem__(self, key):
        if not key:
            raise ValueError('Invalid key')

        try:
            return self._item_cache[key]
        except KeyError:
            ...

        fd = self._fd.field_desc
        value = self._values
        key_parts = key.split('.')
        for key_part in key_parts:
            parent_fd = fd
            parent_value = value

            try:
                fields = parent_fd['fields']
                fd = fields[key_part]
            except KeyError:
                if 'fields' not in parent_fd:
                    raise KeyError('Invalid key {!r}: not a structure'
                                   ''.format(key_part))
                raise KeyError('Invalid key {!r}: valid keys: {}'
                               ''.format(key_part, ', '.join(fields.keys())))

            try:
                value = parent_value[key_part]
            except KeyError:
                raise KeyError('Key {!r} not found in value dictionary'
                               ''.format(key_part))
            except TypeError:
                raise TypeError('Dictionary expected, found {!r} for key {!r}'
                                ''.format(type(parent_value).__name__,
                                          key_part))

        item_cls = (UnionSelectorItem if fd['type_name'] == 'union'
                    else StructuredValueItem)
        item = item_cls(parent_value, key_parts[-1], fd=fd)
        self._item_cache[key] = item
        return item

    def __setitem__(self, key, value):
        sv = self[key]
        sv.value = value

    def __contains__(self, key):
        return key in self._values

    def update(self, **kw):
        for key, value in kw.items():
            sv = self[key]
            sv.update(value)

    @property
    def timestamp(self):
        if 'timeStamp' not in self:
            raise ValueError('Does not contain standard timestamp')

        ts = self['timeStamp'].value
        posix_timestamp = ts['secondsPastEpoch'] + ts['nanoseconds'] * 1e-9
        return datetime.datetime.fromtimestamp(posix_timestamp)
