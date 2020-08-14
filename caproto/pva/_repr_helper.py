"""
This is a tool that allows you to re-create a FieldDesc from a pvAccess
documentation-style repr such as::

    struct my_struct
        byte[] value
        byte<16> boundedSizeArray
        byte[4] fixedSizeArray
        struct timeStamp_t timeStamp
            long secondsPastEpoch
            uint nanoSeconds
            uint userTag


(TODO: I think this should be removed entirely, or perhaps support a better
 syntax)
"""


import ast
import dataclasses
import typing

from parsimonious.grammar import Grammar, NodeVisitor, OneOf, Optional

from ._core import FieldArrayType


@dataclasses.dataclass
class DefinitionLine:
    type_name: str
    array_info: str
    name: str
    value: str

    def __str__(self):
        line = f'{self.type_name}{self.array_info} {self.name}'
        if self.value is not None:
            return f'{line} = {self.value!r}'
        return line


@dataclasses.dataclass
class ArrayTypeAndSize:
    array_type: FieldArrayType
    size: typing.Optional[int]

    def format_index(self, index):
        if index is None:
            index = ''

        return {
            FieldArrayType.fixed_array: '[{}]',
            FieldArrayType.bounded_array: '<{}>',
            FieldArrayType.variable_array: '[{}]',
        }.get(self.array_type, '').format(index)

    def __str__(self):
        return self.format_index(self.size)


definition_line_grammar = Grammar(
    r"""
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
