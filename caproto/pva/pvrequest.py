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
'''

import sys

from .types import FieldArrayType
from collections import (namedtuple, OrderedDict)

from parsimonious.grammar import Grammar, NodeVisitor

Record = namedtuple('Record', 'options')
FieldCategory = namedtuple('FieldCategory', 'name fields')
FieldDef = namedtuple('FieldDef', 'field_name options request')
Option = namedtuple('Option', 'name value')
PVRequest = namedtuple('PVRequest', 'record field getField putField')

pvrequest_grammar = Grammar(
    """
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
            if isinstance(child, Record):
                req_kw['record'] = child
            elif isinstance(child, FieldCategory):
                if child.fields:
                    if child.name == 'field':
                        req_kw['field'].extend(child.fields)
                    else:
                        req_kw[child.name] = child.fields
            else:
                req_kw['field'].append(child)

        return PVRequest(**req_kw)

    def visit_subfield(self, node, visited_children):
        _, pvreq, _ = visited_children
        return pvreq

    def visit_(self, node, visited_children):
        return visited_children or node

    def visit_record(self, node, visited_children):
        _, options, _ = visited_children
        return Record(options=options)

    def visit_field_def(self, node, visited_children):
        identifier, option, subfield, comma = visited_children
        option = option[0] if isinstance(option, list) else None
        subfield = subfield[0] if isinstance(subfield, list) else None

        # due to excessive * usage?
        return FieldDef(field_name=identifier,
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
        return Option(name=identifier, value=value)

    def visit_field_category(self, node, visited_children):
        name, _, field_defs, _, _ = visited_children
        if not isinstance(field_defs, list) and field_defs.text == '':
            field_defs = None
        return FieldCategory(name=name, fields=field_defs)

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


def summarize_pvrequest(req, level=0):
    if isinstance(req, PVRequest):
        yield level, 'PVRequest'
        for field, value in zip(PVRequest._fields, req):
            if value is not None:
                yield level, field
                yield from summarize_pvrequest(value, level + 1)
    elif isinstance(req, list):
        for item in req:
            yield from summarize_pvrequest(item, level)
    else:
        yield level, str(req)


def print_pvrequest(items, *, file=sys.stdout):
    print('PVRequest')
    for level, info in summarize_pvrequest(items):
        print('{} {}'.format(' ' * level, info), file=file)


def pvrequest_to_structure(req, level=0, name=None):
    'PVRequest namedtuple -> PVStructure description'
    def new_struct(fields, struct_name='structure', **additional):
        return dict(type_name='struct',
                    array_type=FieldArrayType.scalar,
                    struct_name=struct_name,
                    fields=fields,
                    name='',
                    **additional)

    def new_string(name, array_type=FieldArrayType.scalar):
        return dict(type_name='string',
                    array_type=array_type,
                    name=name)

    def add_options(parent_fields, options):
        option_fields = OrderedDict()
        parent_fields['_options'] = new_struct(option_fields)
        for opt in options:
            option_fields[opt.name] = new_string(opt.name)

    if isinstance(req, FieldDef):
        fields = OrderedDict()
        ret = new_struct(fields, struct_name=name)
        if req.options:
            add_options(fields, req.options)
        if req.request:
            if any(getattr(req.request, other, None)
                   for other in ('record', 'getField', 'putField')):
                raise ValueError('Unsupported full nested PVRequest '
                                 'specification {}'.format(req.request))

            sub_struct = pvrequest_to_structure(req.request, level=level + 1,
                                                name=None)
            # confusing mix here: top sub_structure just has fields
            # ('record', 'field', ...), we want the fields of
            # 'top_struct.field'
            if 'fields' in sub_struct and len(sub_struct['fields']):
                sub_struct_field = sub_struct['fields']['field']
                for name, field_desc in sub_struct_field['fields'].items():
                    assert name not in fields, 'Duplicate field name'
                    fields[name] = field_desc
        return ret

    if not isinstance(req, PVRequest):
        raise TypeError('{}'.format(type(req)))

    # The remainder deals with PVRequests
    fields = OrderedDict()
    ret = new_struct(fields=fields, nested_types={})

    record = req.record
    if record is not None:
        record_fields = OrderedDict()
        fields['record'] = new_struct(record_fields)
        if record.options:
            add_options(record_fields, record.options)

    def find_or_create_parent(parent_fields, parts):
        base, remaining = parts[0], parts[1:]
        if not remaining:
            return parent_fields
        if base not in parent_fields:
            parent_fields[base] = new_struct(OrderedDict())
        return find_or_create_parent(parent_fields[base]['fields'],
                                     remaining)

    for category in ('field', 'getField', 'putField'):
        cat_fields = getattr(req, category, None)
        if cat_fields is not None and len(cat_fields):
            cat_struct_fields = OrderedDict()
            fields[category] = new_struct(cat_struct_fields)
            for field_def in cat_fields:
                field_name = field_def.field_name
                parts = field_name.split('.')
                # field name will only be the last dotted element
                field_name = parts[-1]
                parent_fields = find_or_create_parent(cat_struct_fields, parts)
                assert field_name not in parent_fields, 'Duplicate field name'
                parent_fields[field_name] = pvrequest_to_structure(
                    field_def, level=level + 1,
                    name='structure')

    return ret


def pvrequest_to_string(req):
    'PVRequest -> request string'
    # record[process=true,xxx=yyy]field(alarm,timeStamp[causeMonitor=true],power.value)
    ret = []
    if isinstance(req, PVRequest):
        record = req.record
        if any((record, req.getField, req.putField)):
            if record is not None:
                options = (','.join(pvrequest_to_string(opt)
                                    for opt in record.options)
                           if record.options
                           else '')

                ret.extend(['record[', options, ']'])
            for category in ('field', 'getField', 'putField'):
                fields = getattr(req, category, None)
                if fields is not None and len(fields):
                    ret.extend([category, '(',
                                ','.join(pvrequest_to_string(field)
                                         for field in fields),
                                ')'
                                ])
        else:
            ret.append(','.join(pvrequest_to_string(field)
                                for field in req.field))
    elif isinstance(req, FieldDef):
        ret = ['{}'.format(req.field_name)]
        if req.options:
            ret.extend(['[', ','.join(pvrequest_to_string(opt)
                                      for opt in req.options),
                        ']'
                        ])
        if req.request:
            ret.extend(['{', pvrequest_to_string(req.request), '}'])

    elif isinstance(req, Option):
        return '{}={}'.format(req.name, req.value)
    else:
        return req

    return ''.join(ret)


_pv_request_to_structure = PVRequestToStructureVisitor()


def parse_pvrequest(req):
    'Parse a PVRequest into appropriate namedtuples'
    return _pv_request_to_structure.parse(req.replace(' ', ''))


def pvrequest_string_to_structure(request):
    'Given a PVRequest string, return a PVData structure'
    parsed = parse_pvrequest(request)
    return pvrequest_to_structure(parsed)
