import binascii
import logging
import textwrap
import typing
from array import array
from typing import List, Union

import pytest
from numpy.testing import assert_array_almost_equal

pytest.importorskip('caproto.pva')

from caproto import pva
from caproto.pva._fields import FieldArrayType, FieldType

logger = logging.getLogger(__name__)


def _fromhex(s):
    s = ''.join(s.strip().split('\n'))
    s = s.replace(' ', '')
    return binascii.unhexlify(s)


def round_trip(obj, endian, **kwargs):
    serialized = b''.join(obj.serialize(endian=endian, **kwargs))
    round_tripped, _, consumed = type(obj).deserialize(serialized,
                                                       endian=endian, **kwargs)
    assert consumed == len(serialized)
    return round_tripped, serialized


def round_trip_value(cls, value, endian, **kwargs):
    serialized = b''.join(cls.serialize(value, endian=endian, **kwargs))
    round_tripped, _, consumed = cls.deserialize(serialized, endian=endian,
                                                 **kwargs)
    assert consumed == len(serialized)
    return round_tripped, serialized


@pytest.mark.parametrize(
    'endian', [pytest.param(pva.LITTLE_ENDIAN, id='LE'),
               pytest.param(pva.BIG_ENDIAN, id='BE')]
)
@pytest.mark.parametrize(
    'value, expected_length',
    [(None, 1),
     (0, 1),
     (255, 1 + 4),
     (256, 1 + 4),
     (int(2 ** 31 - 2), 1 + 4),
     (int(2 ** 32), 1 + 4 + 8),
     (int(2 ** 63), 1 + 4 + 8),
     (pva.MAX_INT32, 1 + 4 + 8)
     ]
)
def test_size_roundtrip(endian, value, expected_length):
    roundtrip_value, serialized = round_trip_value(pva.Size, value, endian=endian)
    assert len(serialized) == expected_length
    assert value == roundtrip_value
    print(serialized, value)


@pytest.mark.parametrize(
    'endian', [pytest.param(pva.LITTLE_ENDIAN, id='LE'),
               pytest.param(pva.BIG_ENDIAN, id='BE')]
)
def test_status_utilities(endian):
    assert pva.Status.create_success().status == pva.StatusType.OK
    err = pva.Status.create_error(message='test', call_tree='test2')
    assert err.status == pva.StatusType.ERROR
    assert err.message == 'test'
    assert err.call_tree == 'test2'

    rt_err, _ = round_trip(err, endian=endian)
    assert err.message == rt_err.message
    assert err.call_tree == rt_err.call_tree
    assert err.status == rt_err.status


def test_status_example():
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

    buf = bytearray(status_example)

    print('\n- status 1')
    status, buf, consumed = pva.Status.deserialize(buf, endian=pva.BIG_ENDIAN)
    assert status.status == pva.StatusType.OK
    assert consumed == 1

    print('\n- status 2')
    status, buf, consumed = pva.Status.deserialize(buf, endian=pva.BIG_ENDIAN)
    assert status.status == pva.StatusType.WARNING
    assert consumed == 13

    print('\n- status 3')
    status, buf, consumed = pva.Status.deserialize(buf, endian=pva.BIG_ENDIAN)
    assert status.status == pva.StatusType.ERROR
    assert consumed == 264


@pytest.mark.parametrize(
    "data, expected",
    [
        pytest.param(
            _fromhex(
                "FD0001800B74696D655374616D705F74"  # .... .tim eSta mp_t
                "03107365636F6E64735061737445706F"  # ..se cond sPas tEpo
                "6368230B6E616E6F5365636F6E647322"  # ch#. nano Seco nds"
                "077573657254616722"                # .use rTag "
            ),
            textwrap.dedent('''
            struct timeStamp_t
                int64 secondsPastEpoch
                int32 nanoSeconds
                int32 userTag
            '''.rstrip()),
            id='example1'
        ),

        pytest.param(
            _fromhex(
                "FD000180106578616D706C6553747275"  # .... .exa mple Stru
                "6374757265070576616C75652810626F"  # ctur e..v alue ..bo
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
            textwrap.dedent('''
                struct exampleStructure
                    byte[1] value
                    byte<16> boundedSizeArray
                    byte[4] fixedSizeArray
                    struct timeStamp
                        int64 secondsPastEpoch
                        int32 nanoseconds
                        int32 userTag
                    struct alarm
                        int32 severity
                        int32 status
                        string message
                    union valueUnion
                        string stringValue
                        int32 intValue
                        float64 doubleValue
                    any variantUnion
            '''.rstrip()),
            id='example2'
        ),
    ]
)
def test_fielddesc_examples(data, expected):
    cache = pva.CacheContext()
    info, buf, offset = pva.FieldDesc.deserialize(data, endian='<', cache=cache)

    print(info.summary() == expected)


@pva.pva_dataclass
class my_struct:
    value: List[pva.Int8]
    boundedSizeArray: pva.array_of(pva.Int8,
                                   array_type=FieldArrayType.bounded_array,
                                   size=16)
    fixedSizeArray: pva.array_of(pva.Int8,
                                 array_type=FieldArrayType.fixed_array,
                                 size=4)

    @pva.pva_dataclass
    class timeStamp_t:
        secondsPastEpoch: pva.Int64
        nanoSeconds: pva.UInt32
        userTag: pva.UInt32

    timeStamp: timeStamp_t

    @pva.pva_dataclass
    class alarm_t:
        severity: pva.Int32
        status: pva.Int32
        message: str

    alarm: alarm_t
    valueUnion: Union[str, pva.UInt32]
    variantUnion: typing.Any


repr_with_data = [
    pytest.param(
        # textwrap.dedent('''\
        # struct my_struct
        #     int8[] value
        #     int8<16> boundedSizeArray
        #     int8[4] fixedSizeArray
        #     struct timeStamp_t timeStamp
        #         int64 secondsPastEpoch
        #         uint32 nanoSeconds
        #         uint32 userTag
        #     struct alarm_t alarm
        #         int32 severity
        #         int32 status
        #         string message
        #     union valueUnion
        #         string String
        #         uint32 Uint32
        #     any variantUnion
        # '''.strip()),
        my_struct,
        {
            'value': [1, 2, 3],
            'boundedSizeArray': [4, 5, 6, 7, 8],
            'fixedSizeArray': [9, 10, 11, 12],
            'timeStamp': {
                'secondsPastEpoch': 0x1122334455667788,
                'nanoSeconds': 0xAABBCCDD,
                'userTag': 0xEEEEEEEE,
            },
            'alarm': {
                'severity': 0x11111111,
                'status': 0x22222222,
                'message': "Allo, Allo!",
            },
            'valueUnion': {
                'str': None,
                'UInt32': 0x33333333,
            },
            'variantUnion': "String inside variant union.",
        },

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
        id='first_test'
    ),

]


@pytest.mark.parametrize("struct, structured_data, expected_serialized, endian",
                         repr_with_data)
def test_serialize(struct, structured_data, expected_serialized, endian):
    field = struct._pva_struct_
    print(field.summary())

    cache = pva.CacheContext()
    serialized = pva.to_wire(field, value=structured_data, endian=endian)
    serialized = b''.join(serialized)
    assert serialized == expected_serialized

    result, buf, offset = pva.from_wire(
        field, serialized, cache=cache, endian=endian, bitset=None)

    for key, value in result.items():
        if isinstance(value, array):
            result[key] = value.tolist()

    assert result == structured_data


@pytest.mark.parametrize(
    "field_type, value, array_type",
    [(FieldType.int64, 1, FieldArrayType.scalar),
     (FieldType.int64, [1, 2, 3], FieldArrayType.variable_array),
     (FieldType.boolean, True, FieldArrayType.scalar),
     (FieldType.boolean, [True, True, False], FieldArrayType.variable_array),
     (FieldType.float64, 1.0, FieldArrayType.scalar),
     (FieldType.float64, [2.0, 2.0, 3.0], FieldArrayType.variable_array),
     (FieldType.float64, array('d', [2.0, 2.0, 3.0]), FieldArrayType.variable_array),
     (FieldType.string, 'abcdefghi', FieldArrayType.scalar),
     (FieldType.string, ['abc', 'def'], FieldArrayType.variable_array),
     ]
)
def test_variant_types_and_serialization(field_type, value, array_type):
    fd = pva.FieldDesc(name='test', field_type=field_type,
                       array_type=array_type, size=1)

    cache = pva.CacheContext()
    for endian in (pva.LITTLE_ENDIAN, pva.BIG_ENDIAN):
        serialized = pva.to_wire(fd, value=value, cache=cache, endian=endian)
        serialized = b''.join(serialized)
        print(field_type, value, '->', serialized)

        res = pva.from_wire(fd, data=serialized, cache=cache, endian=endian)
        deserialized, buf, offset = res

        assert len(buf) == 0
        assert offset == len(serialized)
        if field_type.name == 'string':
            assert deserialized == value
        else:
            assert_array_almost_equal(deserialized, value)


@pytest.mark.xfail(reason='look into details')
def test_pvrequest_test_two():
    expected_serialized = _fromhex(
        '''
        80 00 02 05 66 69 65 6c 64 80 00 01 05 76 61 6c
        75 65 80 00 00 06 72 65 63 6f 72 64 80 00 01 08
        5f 6f 70 74 69 6f 6e 73 80 00 00
        '''
    )

    # TODO: hmm, this is what we're getting instead
    # expected_serialized = b'\x80\x06record\x02\x05field\x80\x05field\x01\x05value\x80\x05value\x00\x06record\x80\x06record\x01\x08_options\x80\x08_options\x00'   # noqa

    res, _, _ = pva.PVRequest.deserialize(data=expected_serialized,
                                          endian=pva.LITTLE_ENDIAN)
    print('field desc')
    print('----------')
    print(res.interface.summary())
    print('value')
    print('-----')
    print(res.data)

    serialized = b''.join(res.serialize(endian=pva.LITTLE_ENDIAN))
    print('serialized')
    print(serialized)
    print('expected')
    print(expected_serialized)

    assert expected_serialized == serialized


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

    pytest.param([
        "record[a=b,c=d] field(a.a[a=b]{C.D[a=b]},b.a[a=b]{E,F})",
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
    ]),
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


@pytest.mark.parametrize("req", pvrequests_with_bad_syntax)
@pytest.mark.xfail(strict=True)
def test_pvrequests_bad_syntax(req):
    pva.PVRequestStruct.from_string(req)


@pytest.mark.parametrize("req", pvrequests)
def test_pvrequests(req):
    # from caproto.pva.serialization import serialize_pvrequest

    if isinstance(req, list):
        req, expected_serialized = req
    else:
        expected_serialized = None

    parsed = pva.PVRequestStruct.from_string(req)

    print()
    print('PVRequest is', req)

    print()
    print('parsed:')
    print(parsed.summary())
    print('expected', expected_serialized)
    return  # TODO

    # # pprint.pprint(line, indent=4)
    # print()
    # print('Comparing original vs stringified:')
    # print(req)
    # print(pva.pvrequest_to_string(parsed))

    # req = req.replace(' ', '')
    # stringified = pva.pvrequest_to_string(parsed)
    # if 'field({})'.format(stringified) == req:
    #     ...
    # elif req == 'record[]field()getField()putField()':
    #     ...
    #     # allowed failure, this isn't useful
    # else:
    #     assert req == stringified

    # print()
    # print('as a structure:')
    # struct = pva.pvrequest_to_structure(parsed)

    # pva.print_field_info(struct, user_types={})

    # if expected_serialized is not None:
    #     cache = SerializeCache({}, {}, {}, {})
    #     info, buf, consumed = deserialize_introspection_data(
    #         expected_serialized, endian='<', cache=cache,
    #         nested_types=dict(getField={},
    #                           putField={},
    #                           )
    #     )

    #     print('expected deserialized:')
    #     pva.print_field_info(info, user_types={})

    #     assert consumed == len(expected_serialized)

    #     serialized = serialize_pvrequest(req, endian='<', cache=cache)
    #     serialized = b''.join(serialized)
    #     print('serialized:')
    #     print(serialized)
    #     print('expected serialized:')
    #     print(expected_serialized)
    #     assert serialized == expected_serialized


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
    bitset, expected_serialized = bitset

    deserialized_bitset, buf, consumed = pva.BitSet.deserialize(
        expected_serialized, endian='<')
    assert consumed == len(expected_serialized)
    assert deserialized_bitset == bitset

    print('serialized', pva.BitSet(bitset).serialize(endian='<'))
    assert b''.join(pva.BitSet(bitset).serialize(endian='<')) == expected_serialized


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

    # NOTE: cache needed here to give interface for channels
    cache = pva.CacheContext()
    serialized = req.serialize(cache=cache)

    assert req.response_address == addr
    assert req.channel_count == 1
    assert serialized == (
        b'\x01\x00\x00\x00\x81\x00\x00\x00'
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00'
        b'\x00\xff\xff\x7f\x00\x00\x01\x90\x1f'
        b'\x01\x03tcp\x01\x00\x01\x00\x00\x00'
        b'\x10TST:image1:Array'
    )

    deserialized, buf, consumed = SearchRequestLE.deserialize(
        bytearray(serialized), cache=cache)
    assert consumed == len(serialized)
    assert deserialized.channel_count == 1
    assert deserialized.channels == [channel1]
    assert deserialized.response_address == addr

    channel2 = {'id': 0x02, 'channel_name': pv + '2'}
    req.channels = [channel1, channel2]
    serialized = req.serialize(cache=cache)
    assert req.channel_count == 2
    assert serialized == (
        b'\x01\x00\x00\x00\x81\x00\x00\x00'
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


def test_broadcaster_messages_smoke():
    bcast = pva.Broadcaster(our_role=pva.Role.SERVER, broadcast_port=5,
                            server_port=6)
    pv_to_cid, request = bcast.search(['abc', 'def'])
    request.serialize()
    response = bcast.search_response(pv_to_cid={'abc': 5, 'def': 6})
    response.serialize()
