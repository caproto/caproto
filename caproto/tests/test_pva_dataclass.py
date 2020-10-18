import array
import logging
import textwrap
import typing
from typing import List

import pytest

import caproto
import caproto.docs

pytest.importorskip('caproto.pva')

from dataclasses import asdict  # isort: skip

import caproto.pva.ioc_examples.group  # isort: skip
import caproto.pva.ioc_examples.normative  # isort: skip

from caproto import pva  # isort: skip


logger = logging.getLogger(__name__)


def test_basic():
    @pva.pva_dataclass
    class TimeStamp:
        secondsPastEpoch: pva.Int64
        nanoseconds: pva.Int32
        userTag: pva.Int32

    expected = textwrap.dedent(
        '''\
        struct TimeStamp
            int64 secondsPastEpoch
            int32 nanoseconds
            int32 userTag
        '''.rstrip()
    )

    print('summary')
    print(TimeStamp._pva_struct_.summary())
    print('expected')
    print(expected)

    assert TimeStamp._pva_struct_.summary() == expected
    assert TimeStamp().nanoseconds == 0


def test_basic_array():
    @pva.pva_dataclass
    class TimeStampArray:
        secondsPastEpoch: typing.List[pva.Int64]
        nanoseconds: typing.List[pva.Int32]
        userTag: typing.List[pva.Int32]

    expected = textwrap.dedent(
        '''\
        struct TimeStampArray
            int64[] secondsPastEpoch
            int32[] nanoseconds
            int32[] userTag
        '''.rstrip()
    )

    print('summary')
    print(TimeStampArray._pva_struct_.summary())
    print('expected')
    print(expected)

    assert TimeStampArray._pva_struct_.summary() == expected
    assert TimeStampArray().nanoseconds == []


def test_nesting_dataclasses():
    @pva.pva_dataclass
    class TimeStamp:
        secondsPastEpoch: pva.Int64
        nanoseconds: pva.Int32
        userTag: pva.Int32

    @pva.pva_dataclass
    class Alarm:
        severity: pva.Int32
        status: pva.Int32
        message: pva.String

    @pva.pva_dataclass
    class exampleStructure:
        value: typing.List[pva.Int32]
        timeStamp: TimeStamp
        alarm: Alarm

    expected = textwrap.dedent(
        '''\
        struct exampleStructure
            int32[] value
            struct TimeStamp timeStamp
                int64 secondsPastEpoch
                int32 nanoseconds
                int32 userTag
            struct Alarm alarm
                int32 severity
                int32 status
                string message
        '''.rstrip()
    )
    # union valueUnion
    #     string stringValue
    #     int32 intValue
    #     float64 doubleValue
    # any variantUnion

    print('summary')
    print(exampleStructure._pva_struct_.summary())
    print('expected')
    print(expected)

    assert exampleStructure._pva_struct_.summary() == expected

    # Check that the defaults actually work:
    assert exampleStructure().timeStamp.nanoseconds == 0
    assert exampleStructure().alarm.message == ''


def test_union():
    @pva.pva_dataclass
    class exampleStructure:
        value: typing.Union[pva.Int32, pva.String]

    expected = textwrap.dedent(
        '''\
        struct exampleStructure
            union value
                int32 Int32
                string String
        '''.rstrip()
    )

    print('summary')
    print(exampleStructure._pva_struct_.summary())
    print('expected')
    print(expected)

    assert exampleStructure._pva_struct_.summary() == expected

    # Check that the defaults actually work:
    assert exampleStructure().value.Int32 == 0
    assert exampleStructure().value.String is None


class _SerializationHelper:
    def __init__(self, category, input_value, endian, cache=None):
        self.category = category
        self.input_value = input_value
        self.serialized = None
        self.endian = endian
        self.cache = cache or pva.CacheContext()

    def to_wire(self):
        self.serialized = b''.join(pva.to_wire(self.category, self.input_value,
                                               endian=self.endian))
        return self.serialized

    def from_wire(self):
        assert self.serialized is not None
        return pva.from_wire(self.category, self.serialized, endian=self.endian,
                             cache=self.cache).data

    def round_trip(self):
        self.to_wire()
        return self.from_wire()

    def from_wire_as_dataclass(self):
        obj = self.from_wire()
        dataclass_instance = pva.dataclass_from_field_desc(obj.interface)()
        pva.fill_dataclass(dataclass_instance, obj.data)
        return dataclass_instance


@pva.pva_dataclass
class _Struct01:
    a: pva.Int64
    b: pva.Int32
    c: pva.Int32


@pva.pva_dataclass
class _Struct02:
    a: pva.Float32
    b: pva.Float64
    c: pva.Boolean


@pva.pva_dataclass
class _Struct03:
    a: pva.Int8
    b: pva.Int16
    c: pva.Int32
    d: pva.UInt8
    e: pva.UInt16
    f: pva.UInt32


@pva.pva_dataclass
class _Struct04:
    a: pva.String
    b: pva.String
    c: pva.String


@pva.pva_dataclass
class _Struct05:
    a: pva.Int32
    b: _Struct01


@pva.pva_dataclass
class _Struct06:
    a: pva.Int32
    b: _Struct01
    c: _Struct01


@pva.pva_dataclass
class _Struct07:
    a: List[pva.Int32]
    b: _Struct01


@pva.pva_dataclass
class _Struct08:
    a: typing.Union[pva.Int32, pva.String]
    b: pva.Int64


@pva.pva_dataclass
class _Struct09:
    a: typing.Any
    b: pva.Int64


@pytest.mark.parametrize(
    'endian', [pytest.param(pva.LITTLE_ENDIAN, id='LE'),
               pytest.param(pva.BIG_ENDIAN, id='BE')]
)
@pytest.mark.parametrize(
    'structure, args',
    [
        pytest.param(_Struct01, (1, 2, 3), id='Struct01_a'),
        pytest.param(_Struct01, (65536, 44, 165536), id='Struct01_b'),
        pytest.param(_Struct02, (99.0, 22.0, 0), id='Struct02_a'),
        pytest.param(_Struct02, (65536.0, 44.0, 1), id='Struct02_b'),
        pytest.param(_Struct03, (-127, -32767, -2147483647,
                                 255, 65535, 4294967295),
                     id='Struct03_a_signed_unsigned'),
        pytest.param(_Struct04, ('string', 'two', 'three'),
                     id='Struct04'),
        pytest.param(_Struct05, (505, {'a': 1, 'b': 2, 'c': 3}),
                     id='Struct05'),

        # Note: for the following, lists are accepted (of course) but the
        # assertion fails comparing list <-> array, so use array to start with.
        pytest.param(_Struct07, (array.array('i', range(50)),
                                 {'a': 8, 'b': 9, 'c': 10},
                                 ),
                     id='Struct07'),

        # The dataclass helper fills in the non-selected ones:
        pytest.param(_Struct08, ({'Int32': None, 'String': 'testing'}, 808),
                     id='Struct08'),

        pytest.param(_Struct09, (5, 909),
                     id='Struct09_int'),
        pytest.param(_Struct09, ('abc', 909),
                     id='Struct09_str'),
        pytest.param(_Struct09, (1.0, 909),
                     id='Struct09_float'),
        pytest.param(_Struct09, (_Struct01(1, 2, 3), 909),
                     id='Struct09_struct',
                     ),
        pytest.param(_Struct09, (None, 909),
                     id='Struct09_none',
                     ),

        pytest.param(_Struct09, (array.array('i', [5, 6, 7]), 909),
                     id='Struct09_array_int'),
        pytest.param(_Struct09, (['abc', 'def', 'ghi'], 909),
                     id='Struct09_array_str'),
        pytest.param(_Struct09, (array.array('d', [1.0, 2.0, 3.0]), 909),
                     id='Struct09_array_float'),
    ]
)
def test_roundtrip_field_desc_and_data(endian, structure, args):
    helper = _SerializationHelper(pva.FieldDescAndData,
                                  pva.FieldDescAndData(data=structure(*args)),
                                  endian=endian)
    assert asdict(helper.round_trip().data) == asdict(helper.input_value.data)
    print('Serialized:', helper.serialized)
    # assert helper.from_wire().interface == helper.input_value.interface
    assert hash(helper.from_wire().interface) == hash(helper.input_value.interface)


@pytest.mark.parametrize(
    'endian', [pytest.param(pva.LITTLE_ENDIAN, id='LE'),
               pytest.param(pva.BIG_ENDIAN, id='BE')]
)
@pytest.mark.parametrize(
    'structure, args, bitset',
    [
        pytest.param(_Struct01, (1, 2, 3), pva.BitSet({0}), id='Struct01_a'),
        pytest.param(_Struct01, (1, 2, 3), pva.BitSet({1}), id='Struct01_b'),
        pytest.param(_Struct01, (1, 2, 3), pva.BitSet({2}), id='Struct01_c'),
        pytest.param(_Struct01, (1, 2, 3), pva.BitSet({3}), id='Struct01_d'),
        # TODO: more
    ]
)
def test_roundtrip_data_with_bitset(endian, structure, args, bitset):
    value = pva.DataWithBitSet(bitset=bitset, data=structure(*args))
    helper = _SerializationHelper(value,
                                  value,
                                  endian=endian)
    assert helper.round_trip().data == helper.input_value.data
    print('Serialized:', helper.serialized)
    assert helper.from_wire().bitset == bitset


def test_get_pv_structure():
    assert pva.get_pv_structure(_Struct01) is _Struct01._pva_struct_

    with pytest.raises(ValueError):
        assert pva.get_pv_structure(None)


def test_fields_to_bitset_bad_input():
    with pytest.raises(ValueError):
        pva.fields_to_bitset(None, {})


@pytest.mark.parametrize(
    'structure, fields, expected_bitset, expected_options',
    [
        pytest.param(
            _Struct01(1, 2, 3),
            {'a': {'_options': {'test': 'true'}}},

            pva.BitSet({1}),
            {'a': {'test': 'true'}},

            id='Struct01_a_options'
        ),

        pytest.param(
            _Struct01(1, 2, 3),
            {'a': {}},

            pva.BitSet({1}),
            {},

            id='Struct01_a_no_options'
        ),

        pytest.param(
            _Struct07(a=[1, 2], b=_Struct01(1, 2, 3)),
            {'b': {'a': {}, 'c': {}}},

            pva.BitSet({3, 5}),
            {'b': {}},

            id='Struct07_b_no_options'
        ),

        pytest.param(
            _Struct07(a=[1, 2], b=_Struct01(1, 2, 3)),
            {'b': {'a': {'_options': {'q': '5'}}, 'b': {}}},

            pva.BitSet({3, 4}),
            {'b': {'a': {'q': '5'}}},

            id='Struct07_b_options'
        ),
    ]
)
def test_fields_to_bitset(structure, fields, expected_bitset, expected_options):
    print(pva.get_pv_structure(structure).summary())
    bitset = pva.fields_to_bitset(structure, field_dict=fields)
    assert bitset == expected_bitset
    assert bitset.options == expected_options


@pytest.fixture(
    params=[
        caproto.pva.ioc_examples.group.MyIOC,
        caproto.pva.ioc_examples.normative.NormativeIOC,
    ]
)
def pvagroup_cls(request):
    return request.param


def test_get_info_smoke(pvagroup_cls):
    info = caproto.docs.utils.get_pvgroup_info(
        pvagroup_cls.__module__, pvagroup_cls.__name__)
    assert info is not None
    assert len(info['pvproperty'])
