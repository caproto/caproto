'''PVRequest parsing

Reference: http://epics-pvdata.sourceforge.net/informative/pvRequest.html

PVRequests come in the form of either:

    1. A full definition
        'record[option,...]
         field(fieldDef,...)
         putField(fieldDef,...)
         getField(fieldDef,...)
         '
    2. A set of FieldDefs
        'fieldDef,...'

where FieldDefs are of the form:

    1. 'fullFieldName'
    2. 'fullFieldName[option,...]'
    3. 'fullFieldName{request}' - a recursive definition.

This had a full
'''

import typing
from collections import namedtuple

from parsimonious.grammar import Grammar, NodeVisitor

from ._core import FieldArrayType, FieldType
from ._fields import (SimpleField, StructuredField, _children_from_field_list,
                      _descendents_from_field_list)

_Record = namedtuple('Record', 'options')
_FieldCategory = namedtuple('FieldCategory', 'name fields')
_FieldDef = namedtuple('FieldDef', 'field_name options request')
_Option = namedtuple('Option', 'name value')
_ParsedPVRequest = namedtuple('PVRequest', 'record field getField putField')


pvrequest_grammar = Grammar(r"""
    PVRequest       = (record / field_category / field_def)*

    category_name   = ("field" / "getField" / "putField")
    field_category  = category_name "(" field_def* ")" ","?

    record          = "record" options ","?
    field_def       = identifier options? subfield? ","?
    options         = "[" single_option* "]"
    single_option   = identifier "=" value ","?
    subfield        = "{" PVRequest "}"

    identifier      = ~"[a-z_][a-z_0-9]*"i ("." identifier+)?
    value           = ( identifier / ~"[0-9\.]+" )
    """)


class PVRequestToStructureVisitor(NodeVisitor):
    grammar = pvrequest_grammar

    def visit_PVRequest(self, node, visited_children):
        req_kw = dict(record=None,
                      field=[],
                      getField=None,
                      putField=None)
        for child in visited_children:
            child = child[0]
            if isinstance(child, _Record):
                req_kw['record'] = child
            elif isinstance(child, _FieldCategory):
                if child.fields:
                    if child.name == 'field':
                        req_kw['field'].extend(child.fields)
                    else:
                        req_kw[child.name] = child.fields
            else:
                req_kw['field'].append(child)

        return _ParsedPVRequest(**req_kw)

    def visit_subfield(self, node, visited_children):
        _, pvreq, _ = visited_children
        return pvreq

    def visit_(self, node, visited_children):
        return visited_children or node

    def visit_record(self, node, visited_children):
        _, options, _ = visited_children
        return _Record(options=options)

    def visit_field_def(self, node, visited_children):
        identifier, option, subfield, comma = visited_children
        option = option[0] if isinstance(option, list) else None
        subfield = subfield[0] if isinstance(subfield, list) else None

        # due to excessive * usage?
        return _FieldDef(field_name=identifier,
                         options=option,
                         request=subfield,
                         )

    def visit_options(self, node, visited_children):
        _, options, _ = visited_children
        if not isinstance(options, list) and options.text == '':
            options = None
        return options

    def visit_single_option(self, node, visited_children):
        identifier, _equals, value, _comma = visited_children
        return _Option(name=identifier, value=value)

    def visit_field_category(self, node, visited_children):
        name, _, field_defs, _, _ = visited_children
        if not isinstance(field_defs, list) and field_defs.text == '':
            field_defs = None
        return _FieldCategory(name=name, fields=field_defs)

    def visit_category_name(self, node, visited_children):
        return node.text

    def visit_identifier(self, node, visited_children):
        return node.text

    def visit_value(self, node, visited_children):
        return node.text


# field_options = dict(
#     array=FieldOption(valid_for=_scalar_arrays,
#                       arg_map={
#                           1: namedtuple('ArraySlice1', 'start'),
#                           2: namedtuple('ArraySlice2', 'start end'),
#                           3: namedtuple('ArraySlice3', 'start increment end'),
#                       },
#                       valid_args=None,
#                       ),
#     deadband=FieldOption(valid_for=scalar_type_names,
#                          arg_map={
#                              2: namedtuple('Deadband', 'abs_rel value'),
#                          },
#                          valid_args={'abs_rel': {'abs', 'rel'}},
#                          ),
#     timestamp=FieldOption(valid_for='timeStamp_t',
#                           arg_map={
#                               1: namedtuple('Timestamp', 'option'),
#                           },
#                           valid_args={'option': {'current', 'copy'}},
#                           ),
#     ignore=_BoolFieldOption('ignore'),
#     causeMonitor=_BoolFieldOption('cause_monitor'),
#     algorithm=FieldOption(valid_for='all',
#                           arg_map={
#                               1: namedtuple('Ignore', 'option'),
#                           },
#                           valid_args={1: {'onPut', 'onChange',
#                                           'deadband', 'periodic'}},
#                           ),
# )


def _new_struct(fields, struct_name='', name=''):
    struct = PVRequestStruct(
        field_type=FieldType.struct,
        array_type=FieldArrayType.scalar,
        name=name,
        struct_name=struct_name,
        metadata={},
        children=_children_from_field_list(fields.values()),
        descendents=_descendents_from_field_list(fields.values()),
        size=None,
    )
    struct.values = {
        name: getattr(child, 'values', {})
        for name, child in struct.children.items()
    }
    return struct


def _new_options(options):
    struct = _new_struct(
        {opt.name: SimpleField(
            field_type=FieldType.string,
            array_type=FieldArrayType.scalar,
            name=opt.name,
            size=None,
        ) for opt in options},
        name='_options',
    )
    struct.values = dict(options)
    return struct


class _PVRequestNode:
    """Tree node to create structures from the bottom-up."""

    def __init__(self, name, field_def=None, root=False):
        self.name = name
        self.children = {}
        self.field_def = field_def
        self.root = root
        if field_def is not None:
            field_def = field_def._replace(field_name=name)

    def add_item(self, name, item):
        first, *rest = name.split('.')
        if len(rest) == 0:
            assert first not in self.children, 'dupe?'
            self.children[first] = _PVRequestNode(first, field_def=item)
            return

        if first not in self.children:
            self.children[first] = _PVRequestNode(name=first)

        self.children[first].add_item('.'.join(rest), item)

    def to_structure(self):
        fields = {}
        for name, node in self.children.items():
            if node.field_def is not None:
                ret = PVRequestStruct._from_parsed(node.field_def)
                ret = _new_struct(dict(ret.children),
                                  struct_name=ret.struct_name, name=name)
                fields[name] = ret
            else:
                fields[name] = node.to_structure()

        return _new_struct(fields=fields, name=self.name)

    def __repr__(self):
        return f'<Node {self.name} {self.children}>'


class PVRequestStruct(StructuredField):
    _pv_request_to_structure = PVRequestToStructureVisitor()
    values: typing.Dict[str, typing.Union[typing.Dict, str]]

    @classmethod
    def from_string(cls, req):
        req = cls._pv_request_to_structure.parse(req.replace(' ', ''))
        return cls._from_parsed(req)

    @classmethod
    def _from_field_def(cls, req, outer_name=''):
        fields = {}
        if req.options:
            fields['_options'] = _new_options(req.options)

        if req.request:
            if any(getattr(req.request, other, None)
                   for other in ('record', 'getField', 'putField')):
                raise ValueError('Unsupported full nested PVRequest '
                                 'specification {}'.format(req.request))

            sub_struct = cls._from_parsed(req.request)
            # confusing mix here: top sub_structure just has fields
            # ('record', 'field', ...), we want the fields of
            # 'top_struct.field'
            if 'field' in sub_struct.children:
                fields.update(**sub_struct.children['field'].children)

        ret = _new_struct(fields, struct_name=outer_name)
        return ret

    @classmethod
    def _from_parsed_pvrequest(cls, req, outer_name=''):
        fields = {}
        if req.record is not None:
            record_fields = {}
            if req.record.options:
                record_fields['_options'] = _new_options(req.record.options)
                # TODO value thrown away
            fields['record'] = _new_struct(record_fields, name='record')

        for category in ('field', 'getField', 'putField'):
            cat_fields = getattr(req, category, None)
            if cat_fields is None or not len(cat_fields):
                continue

            root = _PVRequestNode(name=category, root=True)
            for field_def in cat_fields:
                root.add_item(field_def.field_name, field_def)

            fields[category] = root.to_structure()

        return _new_struct(fields=fields, name=outer_name)

    @classmethod
    def _from_parsed(cls, req, outer_name=''):
        'PVRequest namedtuple -> PVStructure description'
        if isinstance(req, _FieldDef):
            return cls._from_field_def(req, outer_name=outer_name)
        if isinstance(req, _ParsedPVRequest):
            return cls._from_parsed_pvrequest(req, outer_name=outer_name)
        raise TypeError(str(type(req)))
