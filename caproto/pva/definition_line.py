import ast
from collections import namedtuple

from parsimonious.grammar import Grammar, NodeVisitor, Optional, OneOf

from .types import (FieldType, ComplexType, FieldArrayType)
from .types import (type_names, type_name_to_type)


class DefinitionLine(namedtuple('DefinitionLine',
                                'type_name array_info name value')):
    def __str__(self):
        line = f'{self.type_name}{self.array_info} {self.name}'
        if self.value is not None:
            return f'{line} = {self.value!r}'
        return line


class ArrayTypeAndSize(namedtuple('ArrayTypeAndSize',
                                  'array_type size')):
    def format_index(self, index):
        try:
            if index is None:
                index = ''

            return {
                FieldArrayType.fixed_array: '[{}]',
                FieldArrayType.bounded_array: '<{}>',
                FieldArrayType.variable_array: '[{}]',
            }[self.array_type].format(index)
        except KeyError:
            # scalar
            return ''

    def __str__(self):
        return self.format_index(self.size)


definition_line_grammar = Grammar(
    """
    definition_line = _ type_name _ array_info _ name _ value?
    type_name       = identifier
    name            = identifier
    value           = "=" _ ~r".*$"
    array_info      = ( fixed_array / bounded_array / variable_array )?
    fixed_array     = "[" array_size "]"
    variable_array  = "[" _ "]"
    bounded_array   = "<" array_size ">"
    array_size      = _ ~r"[1-9][0-9]*" _
    identifier      = ~"[a-z_][a-z_0-9]*"i

    # whitespace
    _               = ~r"\s*"
    """
)


class DefinitionLineVisitor(NodeVisitor):
    grammar = definition_line_grammar

    def generic_visit(self, node, visited_children):
        if isinstance(node.expr, Optional):
            # top-level optionals come here ('value?' etc.)
            return (visited_children[0] if visited_children
                    else None)
        elif isinstance(node.expr, OneOf):
            return visited_children[0]

        return node.text or visited_children or None

    def visit_definition_line(self, node, visited_children):
        type_name, array_info, name, value = visited_children[1::2]
        return DefinitionLine(type_name=type_name, array_info=array_info,
                              name=name, value=value)

    def visit_type_name(self, node, visited_children):
        return visited_children[0]

    visit_name = visit_type_name

    def visit_value(self, node, visited_children):
        equals, _, value_string = visited_children
        return (ast.literal_eval(value_string)
                if value_string else None)

    def visit_array_info(self, node, visited_children):
        if not node.text:
            return ArrayTypeAndSize(array_type=FieldArrayType.scalar,
                                    size=None)
        return visited_children[0]

    def visit_array_size(self, node, visited_children):
        return int(node.text)

    def visit_fixed_array(self, node, visited_children):
        _, array_size, _ = visited_children
        return ArrayTypeAndSize(array_type=FieldArrayType.fixed_array,
                                size=array_size)

    def visit_bounded_array(self, node, visited_children):
        _, array_size, _ = visited_children
        return ArrayTypeAndSize(array_type=FieldArrayType.bounded_array,
                                size=array_size)

    def visit_variable_array(self, node, visited_children):
        return ArrayTypeAndSize(array_type=FieldArrayType.variable_array,
                                size=None)

    def visit_identifier(self, node, visited_children):
        return node.text

    def visit__(self, node, visited_children):
        'Whitespace'


definition_line_visitor = DefinitionLineVisitor()


def info_from_namespace(parsed, nested_types, user_types):
    'FieldDesc information for a parsed line as part of a nested or user type'
    type_name = parsed.type_name

    # types defined in the struct take precedence
    type_dict = (nested_types if type_name in nested_types
                 else user_types)

    # user-defined type with name as listed
    reference_info = type_dict[type_name]

    info = {
        'ref_namespace': ('nested' if type_name in nested_types else 'user'),
        'name': parsed.name,
        # array type may have changed, so include it from the parsed version:
        'array_type': parsed.array_info.array_type,
        'struct_name': reference_info['struct_name'],
        'type_name': reference_info['type_name'],
    }

    if parsed.value is not None:
        info['value'] = parsed.value
    return info


def definition_line_to_info(line, nested_types, user_types, has_fields):
    'One line of format "[type_name][array_info] [name]" to fielddesc info'
    line = line.strip()
    if ' ' not in line:
        raise ValueError(f'Type name and attribute name required: {line!r}')

    parsed = definition_line_visitor.parse(line)
    type_name = parsed.type_name
    array_info = parsed.array_info

    try:
        field_type, type_specific = type_name_to_type[type_name]
    except KeyError:
        if not has_fields:
            if type_name in user_types or type_name in nested_types:
                return info_from_namespace(parsed, nested_types, user_types)
            else:
                # empty structure, fall through
                ...

        # has_fields -> defining new structure within the parent structure
        field_type, type_specific = (FieldType.complex, ComplexType.structure)

    info = dict(name=parsed.name,
                type_name=type_name,
                array_type=array_info.array_type,
                )

    if parsed.value is not None:
        info['value'] = parsed.value

    if array_info.size is not None:
        info['size'] = array_info.size

    if field_type == FieldType.complex:
        info['type_name'] = type_names[(field_type, type_specific)]
        if type_specific in (ComplexType.union, ComplexType.structure):
            info['struct_name'] = type_name

    return info
