from array import array
import binascii
import copy
import logging
import pytest

from numpy.testing import assert_array_almost_equal
from pprint import pprint
from collections import OrderedDict

from caproto.pva.types import FieldArrayType
from caproto.pva import (deserialize_introspection_data, SerializeCache)
from caproto import pva


logger = logging.getLogger(__name__)


def _fromhex(s):
    s = ''.join(s.strip().split('\n'))
    s = s.replace(' ', '')
    return binascii.unhexlify(s)


status_example = _fromhex(
    "FF010A4C6F77206D656D6F727900022A4661696C656420746F20"
    "6765742C2064756520746F20756E657870656374656420657863"
    "657074696F6EDB6A6176612E6C616E672E52756E74696D654578"
    "63657074696F6E0A096174206F72672E65706963732E63612E63"
    "6C69656E742E6578616D706C652E53657269616C697A6174696F"
    "6E4578616D706C65732E7374617475734578616D706C65732853"
    "657269616C697A6174696F6E4578616D706C65732E6A6176613A"
    "313138290A096174206F72672E65706963732E63612E636C6965"
    "6E742E6578616D706C652E53657269616C697A6174696F6E4578"
    "616D706C65732E6D61696E2853657269616C697A6174696F6E45"
    "78616D706C65732E6A6176613A313236290A"
)


def test_status_example():
    from caproto.pva.messages import (StatusBE, StatusType)

    buf = bytearray(status_example)

    print('\n- status 1')
    status, buf, consumed = StatusBE.deserialize(buf)
    assert StatusType(status.status_type) == StatusType.OK
    assert consumed == 1

    print('\n- status 2')
    status, buf, consumed = StatusBE.deserialize(buf)
    assert StatusType(status.status_type) == StatusType.WARNING
    assert consumed == 13

    print('\n- status 3')
    status, buf, consumed = StatusBE.deserialize(buf)
    assert StatusType(status.status_type) == StatusType.ERROR
    assert consumed == 264


introspection_lines = [
    ('string name', dict(type_name='string', name='name',
                         array_type=FieldArrayType.scalar,
                         ),
     {},
     ),
    ('string[] name', dict(type_name='string', name='name',
                           array_type=FieldArrayType.variable_array,
                           ),
     {},
     ),
    ('string[20] name', dict(type_name='string', name='name',
                             array_type=FieldArrayType.fixed_array,
                             size=20,
                             ),
     {},
     ),
    ('string<20> name', dict(type_name='string', name='name',
                             array_type=FieldArrayType.bounded_array,
                             size=20,
                             ),
     {},
     ),

    # TODO: note that bounded string arrays are not supported in the C++
    # version
    ('bounded_string name', dict(type_name='bounded_string', name='name',
                                 array_type=FieldArrayType.scalar,
                                 ),
     {},
     ),
    ('struct_t name', dict(type_name='struct', name='name',
                           array_type=FieldArrayType.scalar,
                           struct_name='struct_t',
                           ),
     {},
     ),
    ('struct_t name', dict(type_name='struct', name='name',
                           array_type=FieldArrayType.scalar,
                           struct_name='struct_t',
                           ),
     dict(has_fields=True),
     ),
    ('struct_t name', dict(type_name='struct', name='name',
                           array_type=FieldArrayType.scalar,
                           struct_name='struct_t',
                           ref_namespace='nested',
                           ),
     dict(has_fields=False,
          nested_types={'struct_t': dict(type_name='struct',
                                         struct_name='struct_t')}
          ),
     ),
    ('struct_t name', dict(type_name='struct', name='name',
                           array_type=FieldArrayType.scalar,
                           struct_name='struct_t',
                           ref_namespace='user',
                           ),
     dict(has_fields=False,
          user_types={'struct_t': dict(type_name='struct',
                                       struct_name='struct_t')}
          ),
     ),

]

@pytest.mark.parametrize("line, expected_info, kw",
                         introspection_lines)
def test_single_introspection_line(line, expected_info, kw):
    call_kw = dict(nested_types={}, user_types={}, has_fields=False)
    call_kw.update(kw)

    info = pva.definition_line_to_info(line, **call_kw)
    assert info == expected_info


introspection_examples = [

    (_fromhex(
         "FD0001800B74696D655374616D705F74"  # .... .tim eSta mp_t
         "03107365636F6E64735061737445706F"  # ..se cond sPas tEpo
         "6368230B6E616E6F5365636F6E647322"  # ch#. nano Seco nds"
         "077573657254616722"                # .use rTag "
      ),
     {'array_type': FieldArrayType.scalar,
      'fields': OrderedDict(
                 [('secondsPastEpoch',
                   {'array_type': FieldArrayType.scalar,
                    'name': 'secondsPastEpoch',
                    'type_name': 'long',
                    }),
                  ('nanoSeconds',
                   {'array_type': FieldArrayType.scalar,
                    'name': 'nanoSeconds',
                    'type_name': 'int',
                    }),
                  ('userTag',
                   {'array_type': FieldArrayType.scalar,
                    'name': 'userTag',
                    'type_name': 'int',
                    }),
                  ]),
      'struct_name': 'timeStamp_t',
      'name': 'timeStamp_t',
      'type_name': 'struct',
      'nested_types': ('timeStamp_t', ),  # NOTE: modified
      },

     ),

    (_fromhex(
         "FD000180106578616D706C6553747275"  # .... .exa mple Stru
         "6374757265070576616C75652810626F"  # ctur e..v alue (.bo
         "756E64656453697A6541727261793010"  # unde dSiz eArr ay0.
         "0E666978656453697A65417272617938"  # .fix edSi zeAr ray8
         "040974696D655374616D70FD00028006"  # ..ti meSt amp. ....
         "74696D655F7403107365636F6E647350"  # time _t.. seco ndsP
         "61737445706F6368230B6E616E6F7365"  # astE poch #.na nose
         "636F6E64732207757365725461672205"  # cond s".u serT ag".
         "616C61726DFD00038007616C61726D5F"  # alar m... ..al arm_
         "74030873657665726974792206737461"  # t..s ever ity" .sta
         "74757322076D657373616765600A7661"  # tus" .mes sage `.va
         "6C7565556E696F6EFD00048100030B73"  # lueU nion .... ...s
         "7472696E6756616C75656008696E7456"  # trin gVal ue`. intV
         "616C7565220B646F75626C6556616C75"  # alue ".do uble Valu
         "65430C76617269616E74556E696F6EFD"  # eC.v aria ntUn ion.
         "000582"                            # ...
     ),

     {'array_type': FieldArrayType.scalar,
      'fields': OrderedDict([('value',
                              {'array_type': FieldArrayType.variable_array,
                               'name': 'value',
                               'type_name': 'byte',
                               }),
                             ('boundedSizeArray',
                              {'array_type': FieldArrayType.bounded_array,
                               'name': 'boundedSizeArray',
                               'size': 16,
                               'type_name': 'byte',
                               }),
                             ('fixedSizeArray',
                              {'array_type': FieldArrayType.fixed_array,
                               'name': 'fixedSizeArray',
                               'size': 4,
                               'type_name': 'byte',
                               }),
                             ('timeStamp',
                              {'array_type': FieldArrayType.scalar,
                               'fields': OrderedDict([('secondsPastEpoch',
                                                       {'array_type': FieldArrayType.scalar,
                                                        'name': 'secondsPastEpoch',
                                                        'type_name': 'long',
                                                        }),
                                                      ('nanoseconds',
                                                       {'array_type': FieldArrayType.scalar,
                                                        'name': 'nanoseconds',
                                                        'type_name': 'int',
                                                        }),
                                                      ('userTag',
                                                       {'array_type': FieldArrayType.scalar,
                                                        'name': 'userTag',
                                                        'type_name': 'int',
                                                        })]),
                               'name': 'timeStamp',
                               'struct_name': 'time_t',
                               'type_name': 'struct',
                               }),
                             ('alarm',
                              {'array_type': FieldArrayType.scalar,
                               'fields': OrderedDict([('severity',
                                                       {'array_type': FieldArrayType.scalar,
                                                        'name': 'severity',
                                                        'type_name': 'int',
                                                        }),
                                                      ('status',
                                                       {'array_type': FieldArrayType.scalar,
                                                        'name': 'status',
                                                        'type_name': 'int',
                                                        }),
                                                      ('message',
                                                       {'array_type': FieldArrayType.scalar,
                                                        'name': 'message',
                                                        'type_name': 'string',
                                                        })]),
                               'name': 'alarm',
                               'struct_name': 'alarm_t',
                               'type_name': 'struct',
                               }),
                             ('valueUnion',
                              {'array_type': FieldArrayType.scalar,
                               'fields': OrderedDict([('stringValue',
                                                       {'array_type': FieldArrayType.scalar,
                                                        'name': 'stringValue',
                                                        'type_name': 'string',
                                                        }),
                                                      ('intValue',
                                                       {'array_type': FieldArrayType.scalar,
                                                        'name': 'intValue',
                                                        'type_name': 'int',
                                                        }),
                                                      ('doubleValue',
                                                       {'array_type': FieldArrayType.scalar,
                                                        'name': 'doubleValue',
                                                        'type_name': 'double',
                                                        })]),
                               'name': 'valueUnion',
                               'struct_name': 'union',
                               'type_name': 'union',
                               }),
                             ('variantUnion',
                              {'array_type': FieldArrayType.scalar,
                               'name': 'variantUnion',
                               'type_name': 'any',
                               })]),
      'name': 'exampleStructure',
      'struct_name': 'exampleStructure',
      'type_name': 'struct',

      # NOTE: modified:
      'nested_types': ('exampleStructure', 'time_t', 'alarm_t'),
      }
     ),
]


@pytest.mark.parametrize("example_name, data_idx",
                         [('fielddesc example 1 - timestamp', 0),
                          ('fielddesc example 2 - exampleStructure', 1),
                          ])
def test_fielddesc_examples(example_name, data_idx):
    cache = SerializeCache({}, {}, {}, {})
    data, expected_info = introspection_examples[data_idx]
    info, buf, offset = deserialize_introspection_data(
        data, endian='<', cache=cache)

    # don't let the output get too messy here - these dicts refer to the rest
    # of the structure anyway
    info['nested_types'] = tuple(info['nested_types'].keys())
    expected = len(data)
    assert offset == expected

    from pprint import pprint
    pprint(info, width=74)
    assert info == expected_info

    pva.print_field_info(info, user_types={})
    # pva.summarize_field_info(info)  # TODO check



repr_tests = [
    # timestamp example
    ('''
struct timeStamp_t
    long secondsPastEpoch
    int nanoSeconds
    int userTag'''.strip(),

     # - list hierarchy
     [('struct timeStamp_t', ['long secondsPastEpoch',
                              'int nanoSeconds', 'int userTag'])],
     # - expected
     introspection_examples[0][1],
     ),

    # exampleStructure
    ('''
 struct exampleStructure
    byte[] value
    byte<16> boundedSizeArray
    byte[4] fixedSizeArray
    time_t timeStamp
        long secondsPastEpoch
        int nanoseconds
        int userTag
    alarm_t alarm
        int severity
        int status
        string message
    union valueUnion
        string stringValue
        int intValue
        double doubleValue
    any variantUnion
    '''.strip(),

     # - list hierarchy
     [('struct exampleStructure',
      ['byte[] value',
       'byte<16> boundedSizeArray',
       'byte[4] fixedSizeArray',
       ('time_t timeStamp',
        ['long secondsPastEpoch', 'int nanoseconds', 'int userTag']),
       ('alarm_t alarm', ['int severity', 'int status', 'string message']),
       ('union valueUnion',
        ['string stringValue', 'int intValue', 'double doubleValue']),
       'any variantUnion']
       )],
     introspection_examples[1][1],
     ),
]

@pytest.mark.parametrize("lines, expected_hierarchy, expected_structure",
                         repr_tests)
def test_structure_from_repr(lines, expected_hierarchy, expected_structure):
    hierarchy = pva.parse_repr_lines(lines)
    print()
    pprint(hierarchy)
    assert hierarchy == expected_hierarchy

    generated = pva.structure_from_repr(hierarchy)
    generated['nested_types'] = tuple(generated['nested_types'].keys())
    pprint(generated)
    assert generated == expected_structure

    namespace = {}
    pva.update_namespace_with_definitions(namespace, [lines])
    struct_name = expected_structure['struct_name']
    assert struct_name in namespace
    # TODO
    # assert tuple(nested_types.keys()) == ()



repr_with_data = [
    ('''
structure my_struct
    byte[] value = [1,2,3]
    byte<16> boundedSizeArray = [4,5,6,7,8]
    byte[4] fixedSizeArray = [9,10,11,12]
    timeStamp_t timeStamp
        long secondsPastEpoch = 0x1122334455667788
        uint nanoSeconds = 0xAABBCCDD
        uint userTag = 0xEEEEEEEE
    alarm_t alarm
        int severity = 0x11111111
        int status = 0x22222222
        string message = "Allo, Allo!"
    union valueUnion = 1
        string not_selected = "test"
        uint selected = 0x33333333
    any variantUnion = "String inside variant union."
'''.strip(),
     # TODO_DOCS: example is strictly speaking incorrect, the value 0xAABBCCDD
     # will not fit in an int32, so changed to uint for now
     # NOTE: selector added as 'value' after union
     (_fromhex('03010203' '05040506' '0708090A' '0B0C1122'  # .... .... .... ..."
               '33445566' '7788AABB' 'CCDDEEEE' 'EEEE1111'  # 3DUf w... .... ....
               '11112222' '22220B41' '6C6C6F2C' '20416C6C'  # .."" "".A llo,  All
               '6F210133' '33333360' '1C537472' '696E6720'  # o!.3 333` .Str ing
               '696E7369' '64652076' '61726961' '6E742075'  # insi de v aria nt u
               '6E696F6E' '2E')),                           # nion .
     pva.BIG_ENDIAN,
     ),

]


@pytest.mark.parametrize("repr_text, expected_serialized, endian", repr_with_data)
def test_serialize_from_repr(repr_text, expected_serialized, endian):
    print()
    # print(repr(repr_text))
    hierarchy = pva.parse_repr_lines(repr_text)
    print('\n- hierarchy')
    pprint(hierarchy)

    generated = pva.structure_from_repr(hierarchy)
    print('\n- generated field description')
    pprint(generated)

    full_value_dict = pva.field_description_to_value_dict(
        generated, user_types={})

    def scrub_union_values(d):
        'Remove the _selector_ key and sub-fields'
        for k, v in d.items():
            if isinstance(v, dict):
                if '_selector_' in v:
                    union_keys = list(v.keys())[1:]  # first is _selector_
                    selected = union_keys[v['_selector_']]
                    remove_keys = set(union_keys) - {'_selector_', selected}
                    for key in remove_keys:
                        del v[key]
                else:
                    scrub_union_values(v)
        return d

    expected_value_dict = scrub_union_values(copy.deepcopy(full_value_dict))
    print('expected', expected_value_dict)

    cache = SerializeCache({}, {}, {}, {})
    serialized = pva.serialize_data(generated, full_value_dict,
                                    endian=endian, cache=cache)
    assert serialized == expected_serialized

    values, buf, offset = pva.deserialize_data(generated, serialized,
                                               cache=cache, endian=endian)

    print('\n- expected value dictionary')
    pprint(expected_value_dict)
    print('\n- values deserialized')
    pprint(values)
    for key, value in values.items():
        if isinstance(value, array):
            values[key] = value.tolist()
    assert values == expected_value_dict


struct_with_values_repr = '''
struct testStruct
    byte[] value = [1,2,3]
    byte<16> boundedSizeArray = [4,5,6,7,8]
    byte[4] fixedSizeArray = [9,10,11,12]
    timeStamp_t timeStamp
        long secondsPastEpoch = 0x1122334455667788
        uint nanoSeconds = 0xAABBCCDD
        uint userTag = 0xEEEEEEEE
    alarm_t alarm
        int severity = 0x11111111
        int status = 0x22222222
        string message = "Allo, Allo!"
    union valueUnion = 1
        string not_selected = "test"
        uint selected = 0x33333333
    any variantUnion = "String inside variant union."
    alarm_t[] alarms = [(1, 2, 'a'), (3, 4, 'b')]
'''


def test_field_desc_to_value_dict():
    hierarchy = pva.parse_repr_lines(struct_with_values_repr)
    fd = pva.structure_from_repr(hierarchy, user_types=pva.basic_types)

    value_dict_expected = OrderedDict([
        ('value', [1, 2, 3]),
        ('boundedSizeArray', [4, 5, 6, 7, 8]),
        ('fixedSizeArray', [9, 10, 11, 12]),
        ('timeStamp', OrderedDict(
            [('secondsPastEpoch', 0x1122334455667788),
             ('nanoSeconds', 0xAABBCCDD),
             ('userTag', 0xEEEEEEEE),
             ])
         ),
        ('alarm', OrderedDict(
            [('severity', 0x11111111),
             ('status', 0x22222222),
             ('message', "Allo, Allo!"),
             ])
         ),
        ('valueUnion', OrderedDict(
            [('_selector_', 1),
             ('not_selected', "test"),
             ('selected', 0x33333333),
             ]
            )
         ),
        ('variantUnion', "String inside variant union."),
        ('alarms', [
            OrderedDict([('severity', 1),
                         ('status', 2),
                         ('message', "a"),
                         ]),

            OrderedDict([('severity', 3),
                         ('status', 4),
                         ('message', "b"),
                         ]),
            ]
         ),
    ])

    print(fd['nested_types'])
    pva.print_field_info(fd, user_types=pva.basic_types)

    value_dict_out = pva.field_description_to_value_dict(
        fd, user_types=pva.basic_types)

    pprint(value_dict_out)
    assert value_dict_out == value_dict_expected
    return fd
    # pprint(value_dict_out)


@pytest.mark.parametrize(
    "type_name, value, array_type",
    [('long', 1, FieldArrayType.scalar),
     ('long', [1, 2, 3], FieldArrayType.variable_array),
     ('bool', True, FieldArrayType.scalar),
     ('bool', [True, True, False], FieldArrayType.variable_array),
     ('double', 1.0, FieldArrayType.scalar),
     ('double', [2.0, 2.0, 3.0], FieldArrayType.variable_array),
     ('double', array('d', [2.0, 2.0, 3.0]), FieldArrayType.variable_array),
     ('string', 'abcdefghi', FieldArrayType.scalar),
     ('string', ['abc', 'def'], FieldArrayType.variable_array),
     ]
)
def test_variant_types_and_serialization(type_name, value, array_type):
    name = 'name'
    fd = pva.variant_desc_from_value(name, value)
    assert fd['type_name'] == type_name
    assert fd['array_type'] == array_type
    assert fd['name'] == name

    cache = SerializeCache({}, {}, {}, {})
    for endian in (pva.LITTLE_ENDIAN, pva.BIG_ENDIAN):
        serialized = pva.serialize_data(fd, value, cache=cache, endian=endian)
        print(type_name, name, value, '->', serialized)

        res = pva.deserialize_data(fd, serialized, cache=cache, endian=endian)
        deserialized, buf, offset = res

        assert len(buf) == 0
        assert offset == len(serialized)
        if type_name == 'string':
            assert deserialized == value
        else:
            assert_array_almost_equal(deserialized, value)


# def test_serialization_roundtrip():

pvrequests = [
    ["field(value)",
     _fromhex(
         'fd010080000105'
         '6669656c64fd02008000010576616c75'  # field.......valu
         '65fd0300800000'                    # e......
     ),
     # TODO: looks like we have to be smart about caching even empty
     #       structs
     ],

    "record[]field()getField()putField()",
    "record[a=b,x=y]field(a) getField(a)putField(a)",
    "field(a.b[x=y])",
    "field(a.b{c.d})",
    "field(a.b[x=y]{c.d})",
    "field(a.b[x=y]{c.d[x=y]})",
    ["record[a=b,c=d] field(a.a[a=b]{C.D[a=b]},b.a[a=b]{E,F})",
     _fromhex(
        'fd 01 00 80 00 02 06'
        '72 65 63 6f 72 64 fd 02 00 80 00 01 08 5f 6f 70'  # record......._op
        '74 69 6f 6e 73 fd 03 00 80 00 02 01 61 60 01 63'  # tions.......a`.c
        '60 05 66 69 65 6c 64 fd 04 00 80 00 02 01 61 fd'  # `.field.......a.
        '05 00 80 00 01 01 61 fd 06 00 80 00 02 08 5f 6f'  # ......a......._o
        '70 74 69 6f 6e 73 fd 07 00 80 00 01 01 61 60 01'  # ptions.......a`.
        '43 fd 08 00 80 00 01 01 44 fd 09 00 80 00 01 08'  # C.......D.......
        '5f 6f 70 74 69 6f 6e 73 fe 07 00 01 62 fd 0a 00'  # _options....b...
        '80 00 01 01 61 fd 0b 00 80 00 03 08 5f 6f 70 74'  # ....a......._opt
        '69 6f 6e 73 fe 07 00 01 45 fd 0c 00 80 00 00 01'  # ions....E.......
        '46 fe 0c 00                                    '  # F....

        # TODO check serialized data (values):
        # 01 62 01 64 01 62 01 62 01 62
     ),
     ],
    "alarm,timeStamp,power.value",
    "record[process=true]field(alarm,timeStamp,power.value)",
    ("record[process=true]"
     "field(alarm,timeStamp[algorithm=onChange,causeMonitor=false],"
     "power{value,alarm})"),
    ("record[int=2,float=3.14159]"
     "field(alarm,timeStamp[shareData=true],power.value)"),
    ("record[process=true,xxx=yyy]"
     "getField(alarm,timeStamp,power{value,alarm},"
     "current{value,alarm},voltage{value,alarm})"
     "putField(power.value)"
     ),
    ("field(alarm,timeStamp,supply{"
     "zero{voltage.value,current.value,power.value},"
     "one{voltage.value,current.value,power.value}"
     "})"),
    ("record[process=true,xxx=yyy]"
     "getField(alarm,timeStamp,power{value,alarm},"
     "current{value,alarm},voltage{value,alarm},"
     "ps0{alarm,timeStamp,power{value,alarm},current{value,alarm},voltage{value,alarm}},"
     "ps1{alarm,timeStamp,power{value,alarm},current{value,alarm},voltage{value,alarm}})"
     "putField(power.value)"
     ),
    "a{b{c{d}}}",
    "field(alarm.status,alarm.severity)",

]


pvrequests_with_bad_syntax = [
    "a{b[c}d]",

    ("record[process=true,xxx=yyy]"
     "putField(power.value)"
     "getField(alarm,timeStamp,power{value,alarm},"
     "current{value,alarm},voltage{value,alarm},"
     "ps0{alarm,timeStamp,power{value,alarm},current{value,alarm},voltage{value,alarm}},"
     "ps1{alarm,timeStamp,power{value,alarm},current{value,alarm},voltage{value,alarm}"
     ")"),

    "record[process=true,power.value",

    # TODO: i don't know why this is supposed to be an expected failure
    # "field(alarm.status,alarm.severity)",
    ":field(record[process=false]power.value)",
]


@pytest.mark.parametrize("request", pvrequests_with_bad_syntax)
@pytest.mark.xfail(strict=True)
def test_pvrequests_bad_syntax(request):
    from caproto.pva.pvrequest import parse_pvrequest
    parsed = parse_pvrequest(request)
    print(pva.pvrequest_to_string(parsed))
    request = request.replace(' ', '')
    print('stringified', pva.pvrequest_to_string(parsed))
    struct = pva.pvrequest_to_structure(parsed)
    pva.print_field_info(struct, user_types={})


@pytest.mark.parametrize("request", pvrequests)
def test_pvrequests(request):
    from caproto.pva.pvrequest import (parse_pvrequest, print_pvrequest)
    from caproto.pva.serialization import serialize_pvrequest

    if isinstance(request, list):
        request, expected_serialized = request
    else:
        expected_serialized = None

    parsed = parse_pvrequest(request)

    print()
    print('PVRequest is', request)

    print()
    print('parsed:')
    print_pvrequest(parsed)
    # pprint.pprint(line, indent=4)
    print()
    print('Comparing original vs stringified:')
    print(request)
    print(pva.pvrequest_to_string(parsed))

    request = request.replace(' ', '')
    stringified = pva.pvrequest_to_string(parsed)
    if 'field({})'.format(stringified) == request:
        ...
    elif request == 'record[]field()getField()putField()':
        ...
        # allowed failure, this isn't useful
    else:
        assert request == stringified

    print()
    print('as a structure:')
    struct = pva.pvrequest_to_structure(parsed)

    pva.print_field_info(struct, user_types={})

    if expected_serialized is not None:
        cache = SerializeCache({}, {}, {}, {})
        info, buf, consumed = deserialize_introspection_data(
            expected_serialized, endian='<', cache=cache,
            nested_types=dict(getField={},
                              putField={},
                              )
        )

        print('expected deserialized:')
        pva.print_field_info(info, user_types={})

        assert consumed == len(expected_serialized)

        serialized = serialize_pvrequest(request, endian='<', cache=cache)
        serialized = b''.join(serialized)
        print('serialized:')
        print(serialized)
        print('expected serialized:')
        print(expected_serialized)
        assert serialized == expected_serialized


bitsets = [
    (set(),
     _fromhex('00')),
    ({0},
     _fromhex('01 01')),
    ({1},
     _fromhex('01 02')),
    ({7},
     _fromhex('01 80')),
    ({8},
     _fromhex('02 00 01')),
    ({15},
     _fromhex('02 00 80')),
    ({55},
     _fromhex('07 00 00 00  00 00 00 80')),
    ({56},
     _fromhex('08 00 00 00  00 00 00 00  01')),
    ({63},
     _fromhex('08 00 00 00  00 00 00 00  80')),
    ({64},
     _fromhex('09 00 00 00  00 00 00 00  00 01')),
    ({65},
     _fromhex('09 00 00 00  00 00 00 00  00 02')),
    ({0, 1, 2, 4},
     _fromhex('01 17')),
    ({0, 1, 2, 4, 8},
     _fromhex('02 17 01')),
    ({8, 17, 24, 25, 34, 40, 42, 49, 50},
     _fromhex('07 00 01 02  03 04 05 06')),
    ({8, 17, 24, 25, 34, 40, 42, 49, 50, 56, 57, 58},
     _fromhex('08 00 01 02  03 04 05 06  07')),
    ({8, 17, 24, 25, 34, 40, 42, 49, 50, 56, 57, 58, 67},
     _fromhex('09 00 01 02  03 04 05 06  07 08')),
    ({8, 17, 24, 25, 34, 40, 42, 49, 50, 56, 57, 58, 67, 72, 75},
     _fromhex('0A 00 01 02  03 04 05 06  07 08 09')),
    ({8, 17, 24, 25, 34, 40, 42, 49, 50, 56, 57, 58, 67, 72, 75, 81, 83},
     _fromhex('0B 00 01 02  03 04 05 06  07 08 09 0A')),
]


@pytest.mark.parametrize("bitset", bitsets)
def test_bitset(bitset):
    from caproto.pva import serialize_bitset, deserialize_bitset
    bitset, expected_serialized = bitset

    deserialized_bitset, buf, consumed = deserialize_bitset(expected_serialized, endian='<')
    assert consumed == len(expected_serialized)
    assert deserialized_bitset == bitset

    print('serialized', serialize_bitset(bitset, endian='<'))
    assert serialize_bitset(bitset, endian='<') == expected_serialized


def test_search():
    # uses nonstandard array type, so custom code path
    from caproto.pva import SearchRequestLE

    addr = '127.0.0.1'
    pv = 'TST:image1:Array'

    channel1 = {'id': 0x01, 'channel_name': pv}
    req = SearchRequestLE(
        sequence_id=1,
        flags=(pva.SearchFlags.reply_required | pva.SearchFlags.unicast),
        response_address=addr,
        response_port=8080, protocols=['tcp'],
        channels=[channel1],)

    serialized = req.serialize()

    assert req.response_address == addr
    assert req.channel_count == 1
    assert serialized == (b'\x01\x00\x00\x00\x81\x00\x00\x00'
                          b'\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                          b'\x00\xff\xff\x7f\x00\x00\x01\x90\x1f'
                          b'\x01\x03tcp\x01\x00\x01\x00\x00\x00'
                          b'\x10TST:image1:Array')

    cache = SerializeCache(ours={}, theirs={},
                           user_types=pva.basic_types,
                           ioid_interfaces={})
    deserialized, buf, consumed = SearchRequestLE.deserialize(
        bytearray(serialized), cache=cache)
    assert consumed == len(serialized)
    assert deserialized.channel_count == 1
    assert deserialized.channels == [channel1]
    assert deserialized.response_address == addr

    channel2 = {'id': 0x02, 'channel_name': pv + '2'}
    req.channels = [channel1, channel2]
    serialized = req.serialize()
    assert req.channel_count == 2
    assert serialized == (b'\x01\x00\x00\x00\x81\x00\x00\x00'
                          b'\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                          b'\x00\xff\xff\x7f\x00\x00\x01\x90\x1f'
                          b'\x01\x03tcp'
                          b'\x02\x00'
                          b'\x01\x00\x00\x00'
                          b'\x10TST:image1:Array'
                          b'\x02\x00\x00\x00'
                          b'\x11TST:image1:Array2'
                          )

    deserialized, buf, consumed = SearchRequestLE.deserialize(
        bytearray(serialized), cache=cache)
    assert consumed == len(serialized)
    assert deserialized.channel_count == 2
    assert deserialized.channels == [channel1, channel2]


def test_simple_client():
    from caproto.pva.simple_client import main, search
    import socket

    pv = 'TST:image1:Array'
    try:
        socket.setdefaulttimeout(1.0)
        host, server_port = search(pv)
        data = main(host, server_port, pv)
    except (ConnectionRefusedError, socket.timeout):
        raise pytest.skip('pva server not running')
    finally:
        socket.setdefaulttimeout(None)

    print('data was', data)


@pytest.mark.parametrize("repr_text, expected_serialized, endian", repr_with_data)
def test_helper_basics(repr_text, expected_serialized, endian):
    from caproto.pva.helpers import StructuredValueBase
    user_types = {}
    pva.update_namespace_with_definitions(
        user_types,
        ['''struct alarm_t
                int severity
                int status
                string message
         ''',
         ],
        logger=logger,
    )

    print()
    print('Input structure:')

    value = StructuredValueBase(repr_text, user_types=user_types)
    fd = value.field_desc
    print('Field desc is', fd)

    print()
    value['value'] = [1, 2, 3]
    value['boundedSizeArray'] = [4, 5, 6, 7, 8]
    value['fixedSizeArray'] = [9, 10, 11, 12]
    value['timeStamp.secondsPastEpoch'] = 0x1122334455667788
    value['timeStamp.nanoSeconds'] = 0xAABBCCDD
    value['timeStamp.userTag'] = 0xEEEEEEEE
    value['alarm.severity'] = 0x11111111
    value['alarm.status'] = 0x22222222
    value['alarm.message'] = "Allo, Allo!"
    value['valueUnion'] = 'selected'
    value['valueUnion.not_selected'] = "test"
    value['valueUnion.selected'] = 0x33333333
    value['variantUnion'] = "String inside variant union."

    assert value['valueUnion'].value == 'selected'

    status_item = value['alarm.status']
    assert status_item.value == 0x22222222

    # should be the same
    assert id(value['alarm.status']) == id(status_item)

    print('Values is', value)

    # Round trip (1): serialize values as set above
    cache = SerializeCache({}, {}, {}, {})
    assert value.serialize(endian=endian, cache=cache) == expected_serialized
    print()

    # Round trip (2): deserialize into helper value instance
    new = fd.deserialize_data(bytearray(expected_serialized), endian=endian,
                              cache=cache)[0]
    print()
    print('New values is')
    print(new)

    # Round trip (3): compare serialized result of new instance
    assert new.serialize(endian=endian, cache=cache) == expected_serialized


def setup_module():
    logger.setLevel('DEBUG')
    for name in ('caproto.pva.serialization',
                 'caproto.pva.introspection',
                 ):
        logging.getLogger(name).setLevel(logging.DEBUG)
    logging.basicConfig()
