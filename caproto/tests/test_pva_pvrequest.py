import binascii
import textwrap

import pytest

pytest.importorskip('caproto.pva')

from caproto import pva

try:
    import parsimonious
except ImportError:
    parsimonious = None
    requires_parsimonious = pytest.mark.xfail(
        reason='Optional dependency parsimonious not installed')
else:
    requires_parsimonious = lambda func: func  # noqa: E731


def _fromhex(s):
    s = ''.join(s.strip().split('\n'))
    s = s.replace(' ', '')
    return binascii.unhexlify(s)


pvrequests = [
    pytest.param([
        "field(value)",
        _fromhex(
            'fd010080000105'
            '6669656c64fd02008000010576616c75'  # field.......valu
            '65fd0300800000'                    # e......
        ),
        # TODO: looks like we have to be smart about caching even empty
        #       structs
    ],
    ),

    pytest.param("field(a,b,c)", id='verybasic'),
    pytest.param("record[]field()getField()putField()"),
    pytest.param("record[a=b,x=y]field(a) getField(a)putField(a)"),
    pytest.param("field(a.b[x=y])"),
    pytest.param("field(a.b{c.d})"),
    pytest.param("field(a.b[x=y]{c.d})"),
    pytest.param("field(a.b[x=y]{c.d[x=y]})"),

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
    pytest.param("alarm,timeStamp,power.value"),
    pytest.param("record[process=true]field(alarm,timeStamp,power.value)"),
    pytest.param(
        "record[process=true]"
        "field(alarm,timeStamp[algorithm=onChange,causeMonitor=false],"
        "power{value,alarm})"
    ),
    pytest.param(
        "record[int=2,float=3.14159]"
        "field(alarm,timeStamp[shareData=true],power.value)"
    ),
    pytest.param(
        "record[process=true,xxx=yyy]"
        "getField(alarm,timeStamp,power{value,alarm},"
        "current{value,alarm},voltage{value,alarm})"
        "putField(power.value)"
    ),
    pytest.param(
        "field(alarm,timeStamp,supply{"
        "zero{voltage.value,current.value,power.value},"
        "one{voltage.value,current.value,power.value}"
        "})"
    ),
    pytest.param(
        "record[process=true,xxx=yyy]"
        "getField(alarm,timeStamp,power{value,alarm},"
        "current{value,alarm},voltage{value,alarm},"
        "ps0{alarm,timeStamp,power{value,alarm},current{value,alarm},voltage{value,alarm}},"
        "ps1{alarm,timeStamp,power{value,alarm},current{value,alarm},voltage{value,alarm}})"
        "putField(power.value)"
    ),
    pytest.param("a{b{c{d}}}"),
    pytest.param("field(alarm.status,alarm.severity)"),

]


@requires_parsimonious
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


@requires_parsimonious
@pytest.mark.parametrize("req", pvrequests_with_bad_syntax)
@pytest.mark.xfail(strict=True)
def test_pvrequests_bad_syntax(req):
    pva.PVRequestStruct.from_string(req)


@requires_parsimonious
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


@pytest.mark.parametrize(
    'pvrequest, expected', [
        pytest.param(
            "field()",
            textwrap.dedent(
                """\
                 struct
                     struct field
                """.rstrip()
            ),
            id='everything'
        ),
        pytest.param(
            "field(a,b,c)",
            textwrap.dedent(
                """\
                 struct
                     struct field
                         struct a
                         struct b
                         struct c
                """.rstrip()
            ),
            id='verybasic'
        ),
        pytest.param(
            "field(a)getField(b)putField(c)",
            textwrap.dedent("""\
            struct
                struct field
                    struct a
                struct getField
                    struct b
                struct putField
                    struct c
            """.rstrip()),
            id='all_categories'
        ),
    ],
)
def test_parse_by_regex(pvrequest, expected):
    parsed = pva._pvrequest._parse_by_regex(pvrequest)
    struct = pva._pvrequest.PVRequestStruct._from_parsed(parsed)
    assert struct == pva.PVRequestStruct.from_string(pvrequest)

    print('parsed:')
    print(struct.summary())
    print('expected:')
    print(expected)
    assert textwrap.dedent(struct.summary()) == expected
