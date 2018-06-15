import sys
import logging
import textwrap

from array import array
from collections import namedtuple

from .types import (FieldDesc, FieldArrayType, type_name_to_type,
                    variant_type_map)
from .definition_line import definition_line_to_info
from .utils import ThreadsafeCounter


logger = logging.getLogger(__name__)


WalkWithValueTuple = namedtuple('WalkWithValueTuple',
                                ('field_desc', 'keys', 'variable',
                                 'value', 'parent', 'fd_byte',
                                 'depth'))

SelectedUnionValue = namedtuple('SelectedUnionValue', ('selector',
                                                       'union', 'value'))

VariantValue = namedtuple('SelectedUnionValue', ('field_desc', 'value'))


def summarize_field_info(info, user_types, values=None, depth=0,
                         nested_types=None, truncate=200, *,
                         field_name=''):
    'Yields descriptive summary of field desc -> (depth, string)'
    if values is None:
        values = {}

    if nested_types is None:
        nested_types = info.get('nested_types', {})

    if 'type_name' not in info:
        raise ValueError('Required key type_name unset. '
                         'Keys: {}'.format(info.keys()))

    type_name = info['type_name']
    array_type = info['array_type']

    if array_type == FieldArrayType.fixed_array:
        index_fmt = '[{}]'
        array_desc = index_fmt.format(info['size'])
    elif array_type == FieldArrayType.bounded_array:
        index_fmt = '<{}>'
        array_desc = index_fmt.format(info['size'])
    elif array_type == FieldArrayType.variable_array:
        array_desc, index_fmt = '[]', '[{}]'
    else:
        array_desc, index_fmt = '', ''

    if field_name in values:
        value = ' = {!r}'.format(values[field_name])
        values = values[field_name]
        if truncate is not None:
            if len(value) > 2 * truncate:
                value = '{}(...){}'.format(value[:truncate], value[-truncate:])
    else:
        value, values = '', {}

    if type_name in ('struct', 'union'):
        struct_name = info['struct_name']
        if (array_type != FieldArrayType.scalar and
                isinstance(values, (list, tuple))):

            for idx, value in enumerate(values):
                desc = ('{struct_name} {name}{index_desc}'
                        ''.format(struct_name=struct_name,
                                  index_desc=index_fmt.format(idx),
                                  name=field_name, value=value))
                yield (depth, desc)

                fields = get_definition_from_namespaces(
                    info, nested_types, user_types)['fields']

                for field_name_, field in fields.items():
                    yield from summarize_field_info(
                        field, user_types=user_types, values=value,
                        nested_types=nested_types, depth=depth + 1,
                        field_name=field_name_)

        else:
            value = ''
            desc = ('{struct_name}{array_desc} {name}{value}'
                    ''.format(struct_name=struct_name, array_desc=array_desc,
                              name=field_name, value=value))
            yield (depth, desc)

            fields = get_definition_from_namespaces(
                info, nested_types, user_types)['fields']

            for field_name, field in fields.items():
                yield from summarize_field_info(field, user_types=user_types,
                                                values=values,
                                                nested_types=nested_types,
                                                depth=depth + 1,
                                                field_name=field_name)

    elif type_name in ('bounded_string', ):
        # TODO ?
        yield (depth, '{type_name}<TODO>{array_desc} {name}{value}'
               ''.format(type_name=type_name, array_desc=array_desc,
                         name=field_name, value=value))
    else:
        yield (depth, '{type_name}{array_desc} {name}{value}'
               ''.format(type_name=type_name, array_desc=array_desc,
                         name=field_name,
                         value=value))


def print_field_info(info, user_types, values=None, *, file=sys.stdout):
    'Print out field description summary, with values if included'
    for depth, info in summarize_field_info(info, user_types=user_types,
                                            values=values):
        print('    ' * depth, info, file=file)


def get_definition_from_namespaces(fd, *namespaces):
    if 'ref_namespace' not in fd:
        return fd

    struct_name = fd['struct_name']
    for namespace in namespaces:
        if namespace and struct_name in namespace:
            return namespace[struct_name]

    raise KeyError('Structure {!r} not defined'.format(struct_name))


def parse_repr_lines(text):
    'Hierarchy of lists/tuples from indented lines'
    if isinstance(text, (list, tuple)):
        text = '\n'.join(text)

    text = textwrap.dedent(text)
    lines = text.split('\n')

    indent = 0
    root = []
    stack = [(0, root)]
    current = root

    for line in lines:
        if not line.strip():
            continue

        line_indent = len(line) - len(line.strip())
        if line_indent > indent:
            parent = current.pop(-1)
            new = []
            stack.append((line_indent, new))
            current.append((parent, new))
            current = new
            indent = line_indent
        elif line_indent < indent:
            while line_indent < indent:
                indent, current = stack.pop(-1)
            stack.append((indent, current))
        current.append(line.strip())

    return root


def structure_from_repr(hier, *, nested_types=None, user_types=None, depth=0):
    'Generate a field description structure from its string representation'
    if isinstance(hier, str):
        hier = parse_repr_lines(hier)

    if user_types is None:
        user_types = {}
    if nested_types is None:
        nested_types = {}

    ret = {}
    for idx, entry in enumerate(hier):
        if isinstance(entry, (list, tuple)):
            entry, children = entry
        else:
            children = None

        top_entry = (idx == 0 and depth == 0)
        if top_entry:
            items = entry.split(' ')
            struct_name = items.pop(0)
            # TODO i don't believe it's strictly correct to call it the
            # struct_name here - just name according to the repr structure
            if len(items) == 2:
                assert items[0] == 'struct'
                struct_name = name = items[1]
            elif len(items) == 1:
                struct_name = name = items[0]
            else:
                raise ValueError('Unexpected identifier(s): {} '
                                 '(from: {!r})'.format(items[2:], entry))

            einfo = dict(
                name=name,
                struct_name=struct_name,
                type_name='struct',
                array_type=FieldArrayType.scalar,
                # size=1,
            )
        else:
            einfo = definition_line_to_info(
                entry, nested_types, user_types, has_fields=children)

        for key in ('name', 'type_name', 'array_type', 'size', 'value',
                    'struct_name', 'ref_namespace'):
            if key in einfo and einfo[key] is not None:
                ret[key] = einfo[key]

        if children:
            fields = {}
            ret['fields'] = fields
            struct_name = ret['struct_name']
            # TODO: _default_names from .serialization
            if struct_name not in ('union', 'structure'):
                nested_types[struct_name] = ret

            for child in children:
                child_st = structure_from_repr([child], user_types=user_types,
                                               nested_types=nested_types,
                                               depth=depth + 1)
                fields[child_st['name']] = child_st

        elif 'ref_namespace' in einfo:
            type_name = ret['struct_name']
            logger.debug('(Field %r references %s type)',
                         ret['name'],
                         ('nested' if type_name in nested_types
                          else 'user-defined'))

    if depth > 0:
        return ret
    else:
        ret['nested_types'] = nested_types
        return ret


def update_namespace_with_definitions(namespace, definitions, *, logger=None):
    'Update dictionary of type definitions, given a list of structure reprs'

    if logger is None:
        logger = globals()['logger']

    for defn in definitions:
        lines = defn.strip().split('\n')
        hierarchy = parse_repr_lines(lines)
        struct = structure_from_repr(hierarchy, user_types=namespace)

        struct_name = struct['struct_name']
        namespace[struct_name] = struct

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug('Added struct: %s', struct_name)
            for depth, line in summarize_field_info(struct,
                                                    user_types=namespace):
                logger.debug('%s%s', '    ' * depth, line)


def field_descriptor_has_value(parent, fd, array_type=None):
    'Does a field descriptor have an associated value?'
    if 'fields' in fd:
        if array_type is None:
            # referenced types may have a different array type than the
            # original
            array_type = fd['array_type']

        # TODO: unions have a selector value
        # if fd['type_name'] == 'union':
        #     return True

        if array_type != FieldArrayType.scalar:
            # array types should have a list of dicts
            return True

        return False

    return True


def walk_field_description(fd, parent=None):
    'Yields (dotted.name, field_descriptor_dict)'
    if fd is None:
        return

    if parent is None:
        parent = ()

    keys = parent + (fd['name'], )

    yield keys, parent, fd

    if 'fields' in fd:
        for field_name, field in fd['fields'].items():
            yield from walk_field_description(field, parent=keys)


def field_description_to_value_dict(fd, user_types, nested_types=None):
    'Take in a field description and return a hierarchical value dictionary'
    # TODO: remove - values should not be mixed in type definitions
    if nested_types is None:
        nested_types = fd.get('nested_types', {})

    values = {}

    full_def = get_definition_from_namespaces(fd, nested_types, user_types)

    if 'fields' not in full_def:
        return fd.get('value', None)

    if fd['array_type'] == FieldArrayType.scalar:
        values = {}
        if fd['type_name'] == 'union':
            values['_selector_'] = fd['value']
        for name, child_fd in full_def['fields'].items():
            values[name] = field_description_to_value_dict(
                child_fd, user_types, nested_types=nested_types)
        return values

    # For array types of structures, a list of dicts makes sense. Will not
    # support transposed version.
    field_names = list(full_def['fields'].keys())
    return [dict([field, v]
                 for field, v in zip(field_names, single_value))
            for single_value in fd['value']]


def variant_desc_from_value(name, value):
    'Name and native Python value -> field description dictionary'
    if isinstance(value, (tuple, list, array)):
        type_name = variant_type_map[type(value[0])]
        array_name = '[]'
    else:
        type_name = variant_type_map[type(value)]
        array_name = ''

    # create the field desc on the fly
    return definition_line_to_info(
        '{}{} {}'.format(type_name, array_name, name),
        nested_types={}, user_types={}, has_fields=False)


def walk_field_description_with_values(fd, values, user_types, *, keys=None,
                                       depth=0, root=None, parent=None,
                                       allow_none=False):
    'Ignores structures and unselected union fields'
    if fd is None:
        return

    if root is None:
        root = fd

    if keys is None:
        keys = ()

    array_type = fd['array_type']
    fd = get_definition_from_namespaces(fd, root.get('nested_types', {}),
                                        user_types)
    has_value = field_descriptor_has_value(parent, fd, array_type)

    if has_value:
        if isinstance(values, dict) and not allow_none:
            raise ValueError('Attribute {} should have a value'
                             ''.format('.'.join(keys)))
        # elif array_type and not isinstance(values, (list, array, tuple...

        type_name = fd['type_name']
        if type_name == 'any':
            if values is None:
                if not allow_none:
                    raise ValueError('Variant {!r} must have a value'
                                     ''.format(fd['name']))
            else:
                values = VariantValue(
                    field_desc=variant_desc_from_value(fd['name'], values),
                    value=values)
            # TODO will need to support passing in user-defined structures

        type_, type_specific = type_name_to_type[type_name]
        fd_byte = FieldDesc(type_specific, array_type, type_)
        yield WalkWithValueTuple(field_desc=fd, keys=keys,
                                 variable='.'.join(keys), value=values,
                                 parent=parent, fd_byte=fd_byte,
                                 depth=depth)

        if array_type:
            # only support an array value here - ignore the rest of the fields
            return

    type_name = fd['type_name']

    if 'fields' in fd:
        fields = fd['fields']

        if type_name == 'union' and not values and not allow_none:
            raise ValueError('Union must have a selector (or set allow_none)')

        if type_name == 'union' and values:
            selector = values['_selector_']
            sel_key, sel_field = tuple(fields.items())[selector]
            fields = [(sel_key, sel_field)]

            value = SelectedUnionValue(selector=selector,
                                       union=fd,
                                       value=values[sel_key])

            yield from walk_field_description_with_values(
                fd=sel_field, values=value, user_types=user_types,
                keys=keys + (fd['name'], ),
                depth=depth + 1, root=root, parent=fd,
                allow_none=allow_none)

        else:
            fields = fields.items()

            for field_name, field in fields:
                if values is not None:
                    value = values[field_name]
                else:
                    if not allow_none:
                        raise ValueError('Field {!r} must have a value'
                                         ''.format(field_name))
                    value = None

                yield from walk_field_description_with_values(
                    field, value, user_types,
                    keys=keys + (field_name, ),
                    depth=depth + 1, root=root, parent=fd,
                    allow_none=allow_none)


def bitset_fill(bitset, interface, *, user_types):
    '''
    Fill a bitset according to a field interface

    Take, For example, the following field interface and its corresponding
    bitset bits:

        [  0]  struct epics:nt/NTScalarArray:1.0
        [  1]   double value
        [  2]   struct alarm
        [  3]    int severity
        [  4]    int status
        [  5]    string message
        [  6]   struct timeStamp
        [  7]    long secondsPastEpoch
        [  8]    int nanoseconds
        [  9]    int userTag

    Specifying 0 in the bitset would select the entire structure - obviating
    the need for a bitset entirely. Selecting 2 (alarm) implies that 3, 4, and
    5 (severity, status, message) are also selected.  The "fill" operation will
    take those implications and return a fully-specified bitset.

    Parameters
    ----------
    bitset : set
    interface : dict
    user_types : dict
    '''

    if bitset is None or 0 in bitset:
        return None

    last_depth = -1
    parent_stack = []
    output_bitset = set(bitset)

    debug_flag = logger.isEnabledFor(logging.DEBUG)

    for item in walk_field_description_with_bitset(
            interface, bitset, user_types=user_types, only_selected=False):
        indent = ' ' * item.depth
        fd = item.field_desc
        bitset_index = item.value
        name = fd['name']
        type_name = fd['type_name']

        while last_depth > item.depth:
            # moving back up the stack
            parent_stack.pop(-1)
            last_depth -= 1

        try:
            parent_name, parent_id, parent_selected = parent_stack[-1]
        except IndexError:
            parent_name, parent_id, parent_selected = '', -1, False

        if item.depth == last_depth and parent_id == bitset_index - 1:
            # parent was an empty struct
            parent_stack.pop(-1)
            parent_name, parent_id, parent_selected = parent_stack[-1]

        # if the parent item is selected, this item is also selected
        if parent_selected:
            output_bitset.add(bitset_index)

        # next entries
        if type_name in ('struct', ):
            parent_stack.append((name, bitset_index,
                                 bitset_index in output_bitset))

        last_depth = item.depth

        if debug_flag:
            if bitset_index in output_bitset and bitset_index in bitset:
                marker = '* '
            elif bitset_index in output_bitset:
                marker = '*F'

            marker = '*' if bitset_index in output_bitset else ' '
            logger.debug('%s [%3d] %s %s %s.%s', marker, bitset_index, indent,
                         type_name, parent_name, name)

    return output_bitset


def bitset_repr(bitset, interface, *, user_types=None, only_selected=False):
    if user_types is None:
        user_types = {}

    for item in walk_field_description_with_bitset(
            interface, bitset, user_types=user_types,
            only_selected=only_selected):
        indent = ' ' * item.depth
        fd = item.field_desc
        name = fd['name']
        type_name = fd['type_name']
        bitset_index = item.value
        marker = ('*' if bitset is None or bitset_index in bitset
                  else ' ')
        yield f'{marker} [{bitset_index:-3d}] {indent} {type_name} {name}'


def walk_field_description_with_bitset(
        fd, bitset, user_types, *, keys=None, depth=0, root=None, parent=None,
        bitset_counter=None, only_selected=True):
    'Ignores structures and unselected union fields'
    if fd is None:
        return

    if root is None:
        root = fd

    if keys is None:
        keys = ()

    array_type = fd['array_type']
    fd = get_definition_from_namespaces(fd, root.get('nested_types', {}),
                                        user_types)
    # has_value = field_descriptor_has_value(parent, fd, array_type)

    if bitset_counter is None:
        bitset_counter = ThreadsafeCounter(initial_value=0)
    else:
        bitset_counter()

    selected = bitset is None or bitset_counter.value in bitset

    if not only_selected or (only_selected and selected):
        type_name = fd['type_name']
        type_, type_specific = type_name_to_type[type_name]
        fd_byte = FieldDesc(type_specific, array_type, type_)
        yield WalkWithValueTuple(field_desc=fd, keys=keys,
                                 variable='.'.join(keys),
                                 value=bitset_counter.value, parent=parent,
                                 fd_byte=fd_byte, depth=depth)

    if array_type:
        # only support an array value here - ignore the rest of the fields
        return

    type_name = fd['type_name']

    if 'fields' not in fd:
        return

    fields = fd['fields']

    if type_name == 'union' and selected:
        raise NotImplementedError('TODO bitset with union')
        # yield from walk_field_description_with_bitset(
        #     fd=sel_field, values=value, user_types=user_types,
        #     keys=keys + (fd['name'], ),
        #     depth=depth + 1, root=root, parent=fd,
        #     index=index)

    else:
        for field_name, field in fields.items():
            yield from walk_field_description_with_bitset(
                field, bitset, user_types, keys=keys + (field_name, ),
                depth=depth + 1, root=root, parent=fd,
                bitset_counter=bitset_counter, only_selected=only_selected)


def create_value_dict_from_field_desc(fd, user_types):
    'Create a value dictionary from a field description'
    value_dict = {}
    for item in walk_field_description_with_values(fd, values=None,
                                                   user_types=user_types,
                                                   allow_none=True):
        # TODO very inefficient, should be recursive/stack-based
        parent = value_dict
        for key in item.keys[:-1]:
            try:
                parent = parent[key]
            except KeyError:
                new_parent = {}
                parent[key] = new_parent
                parent = new_parent

        array_type = item.fd_byte.array_type

        key = item.keys[-1]
        parent[key] = (None if array_type == FieldArrayType.scalar
                       else [])

    return value_dict


def generate_hash(desc, *, cache, level=0, skip_keys=None):
    'Generate FieldDesc hash'
    if skip_keys is None:
        skip_keys = {'fields', 'nested_types', '_hash_', '_locked_',
                     '_selector_'}
    tupled = tuple((key, value)
                   if key not in skip_keys and
                   not isinstance(value, dict)
                   else (key, generate_hash(value, cache=cache,
                                            level=level + 1,
                                            skip_keys=skip_keys))
                   for key, value in sorted(desc.items())
                   )

    # Hash collisions are likely for nearly identical types referencing
    # different namespaces; so add id() of user_types namespace
    if level == 0:
        return hash((id(cache.user_types), ) + tupled)
    return hash(tupled)


# TODO: type checking from pvData notes:
#   - Duplicate field name checks
#   - field names must start with [A-Za-z_], no empty strings
#   - Remaining characters may include 0-9 as well, no others
#   - pvData doesn't support fixed/bounded struct arrays
#   - Redefinition of nested struct (?)
#   -
