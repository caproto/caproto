import array
from inspect import isclass

import pytest

from .._utils import ConversionDirection
from .._dbr import ChannelType, DbrStringArray
from .. import backend
from .conftest import (array_types, assert_array_almost_equal)


FROM_WIRE = ConversionDirection.FROM_WIRE
TO_WIRE = ConversionDirection.TO_WIRE

STRING = ChannelType.STRING
INT = ChannelType.INT
FLOAT = ChannelType.FLOAT
ENUM = ChannelType.ENUM
CHAR = ChannelType.CHAR
LONG = ChannelType.LONG
DOUBLE = ChannelType.DOUBLE

PUT_ACKT = ChannelType.PUT_ACKT
PUT_ACKS = ChannelType.PUT_ACKS

STSACK_STRING = ChannelType.STSACK_STRING
CLASS_NAME = ChannelType.CLASS_NAME


@pytest.mark.parametrize('ntype', (STSACK_STRING, CLASS_NAME))
def test_special_types(backends, ntype):
    in_value = expected_value = 0.2
    out_value = backend.convert_values(
        values=in_value, from_dtype=ntype, to_dtype=ntype, direction=FROM_WIRE)

    assert out_value == expected_value

    with pytest.raises(ValueError):
        out_value = backend.convert_values(
            values=in_value, from_dtype=ntype, to_dtype=STRING,
            direction=FROM_WIRE)


def run_conversion_test(values, from_dtype, to_dtype, expected,
                        *, direction, string_encoding=None, enum_strings=None,
                        count=1):
    def _test():
        print(f'--- {direction} ---')
        print(f'Convert: {from_dtype.name} {values!r} -> {to_dtype.name} '
              f'(str encoding: {string_encoding})')
        print(f'Expecting: {expected!r}')
        converted = backend.convert_values(
            values, from_dtype=from_dtype, to_dtype=to_dtype,
            string_encoding=string_encoding, enum_strings=enum_strings,
            direction=direction, auto_byteswap=False)
        print(f'Converted: {converted!r}')
        return converted

    if direction == FROM_WIRE:
        # TODO: data_count not correct here, but largely unused
        values = backend.epics_to_python(values, from_dtype,
                                         data_count=count,
                                         auto_byteswap=True,
                                         )

    if isclass(expected) and issubclass(expected, Exception):
        with pytest.raises(expected):
            _test()
    else:
        returned = _test()
        if isinstance(returned, array.array):
            assert returned.typecode == backend.type_map[to_dtype]
            print(f'array to list {returned} -> {returned.tolist()}'
                  f' ({returned.typecode})')
            returned = returned.tolist()
        elif isinstance(returned, array_types):
            assert returned.dtype == backend.type_map[to_dtype]
            print(f'numpy to list {returned} -> {returned.tolist()}'
                  f' ({returned.dtype})')
            returned = returned.tolist()

        try:
            assert returned == expected
        except AssertionError:
            assert_array_almost_equal(returned, expected)


# ---- STRING CONVERSION ----
# ** encoding
no_encoding = dict(string_encoding=None)
ascii_encoding = dict(string_encoding='ascii')
enum_strs = dict(enum_strings=['aa', 'bb', 'cc'],
                 string_encoding='ascii')

# TO WIRE: channeldata stores STRING -> caget of DTYPE
string_to_wire_tests = [
    [STRING, STRING, b'abc', [b'abc'], no_encoding],
    [STRING, STRING, 'abc', [b'abc'], ascii_encoding],
    [STRING, INT, "12", [12], no_encoding],
    [STRING, FLOAT, "1.2", [1.2], no_encoding],
    [STRING, ENUM, 'bb', [1], enum_strs],

    # we have string b'1' in ChannelString. send to client.
    # client should see a list of [int('1')]
    [STRING, CHAR, b'1', [1], no_encoding],
    [STRING, CHAR, '1', [1], ascii_encoding],
    [STRING, LONG, "1", [1], no_encoding],
    [STRING, DOUBLE, "1.2", [1.2], no_encoding],

    [STRING, ENUM, 'bad', ValueError, enum_strs],
    [STRING, ENUM, b'bad', ValueError, enum_strs],  # enum data must be str
    [STRING, INT, "x", ValueError, no_encoding],  # no encoding
    [STRING, CHAR, b'abc', ValueError, no_encoding],
    [STRING, CHAR, 'abc', ValueError, ascii_encoding],
    [STRING, LONG, "x", ValueError, no_encoding],
    [STRING, DOUBLE, "x", ValueError, no_encoding],

    # non-native types
    [ChannelType.STS_STRING, FLOAT, "1.2", ValueError, no_encoding],
    [ChannelType.STS_STRING, ChannelType.STS_FLOAT, "1.2", ValueError, no_encoding],
]


@pytest.mark.parametrize('from_dtype, to_dtype, values, expected, kwargs',
                         string_to_wire_tests)
def test_string_to_wire(backends, from_dtype, to_dtype, values, expected,
                        kwargs):
    run_conversion_test(values=values, from_dtype=from_dtype,
                        to_dtype=to_dtype, expected=expected,
                        direction=TO_WIRE, **kwargs)


no_encoding = dict(string_encoding=None)
ascii_encoding = dict(string_encoding='ascii')
enum_strs = dict(enum_strings=['aa', 'bb', 'cc'],
                 string_encoding='ascii')

# FROM WIRE: client wrote STRING -> store in DTYPE
string_decoding_tests = [
    [STRING, STRING, b'abc', [b'abc'], no_encoding],
    [STRING, STRING, b'abc', ['abc'], ascii_encoding],
    [STRING, INT, b"1", [1], ascii_encoding],
    [STRING, FLOAT, b"1.2", [1.2], ascii_encoding],
    [STRING, ENUM, b'bb', [1], enum_strs],
    # we received string b'1' from wire. expect to convert this to
    # a ChannelChar. Should store: [int('1')]
    [STRING, CHAR, b'1', [1], ascii_encoding],
    [STRING, CHAR, b'2', [2], ascii_encoding],
    [STRING, LONG, b"3", [3], ascii_encoding],
    [STRING, DOUBLE, b"1.2", [1.2], ascii_encoding],

    [STRING, INT, b"x", ValueError, no_encoding],  # no encoding
    [STRING, ENUM, b'bad', ValueError, enum_strs],
    [STRING, CHAR, b'abc', ValueError, no_encoding],
    [STRING, CHAR, b'abc', ValueError, ascii_encoding],
    [STRING, LONG, b"x", ValueError, no_encoding],
    [STRING, DOUBLE, b"x", ValueError, no_encoding],
]


@pytest.mark.parametrize('from_dtype, to_dtype, values, expected, kwargs',
                         string_decoding_tests)
def test_string_from_wire(backends, from_dtype, to_dtype, values, expected,
                          kwargs):
    run_conversion_test(values=values, from_dtype=from_dtype,
                        to_dtype=to_dtype, expected=expected,
                        direction=FROM_WIRE, **kwargs)


# ---- STRING ARRAY CONVERSION ----
# ** encoding
no_encoding = dict(string_encoding=None, enum_strings=['abc', 'def', 'ghi'])
ascii_encoding = dict(string_encoding='ascii', enum_strings=['abc', 'def',
                                                             'ghi'])

# TO WIRE: channeldata stores STRING ARRAY -> caget of DTYPE
string_array_to_wire_tests = [
    [STRING, STRING, ['abc', 'def'], ValueError, no_encoding],
    [STRING, STRING, ['abc', 'def'], [b'abc', b'def'], ascii_encoding],
    [STRING, INT, ['1', b'2', '3'], [1, 2, 3], no_encoding],
    [STRING, INT, ['1', '2', 'abc'], ValueError, no_encoding],
    [STRING, FLOAT, ['1.2', '2.3'], [1.2, 2.3], no_encoding],

    [STRING, CHAR, [b'1', '2'], [1, 2], no_encoding],
    [STRING, CHAR, ['1', '2'], [1, 2], ascii_encoding],
    [STRING, LONG, ['1', '2'], [1, 2], no_encoding],
    [STRING, DOUBLE, ['1.2', '3.4'], [1.2, 3.4], no_encoding],

    [STRING, ENUM, ['bad', 'bad'], ValueError, ascii_encoding],
    [STRING, ENUM, [b'bad', b'bad'], ValueError, ascii_encoding],
    [STRING, INT, ['x', 'x'], ValueError, no_encoding],  # no encoding
    [STRING, CHAR, [b'abc', b'cdef'], ValueError, no_encoding],
    [STRING, CHAR, ['abc', 'def'], ValueError, ascii_encoding],
    [STRING, LONG, ['x', 'y'], ValueError, no_encoding],
    [STRING, DOUBLE, ['x', 'y'], ValueError, no_encoding],
]


@pytest.mark.parametrize('from_dtype, to_dtype, values, expected, kwargs',
                         string_array_to_wire_tests)
def test_string_array_to_wire(backends, from_dtype, to_dtype, values, expected,
                              kwargs):
    run_conversion_test(values=values, from_dtype=from_dtype,
                        to_dtype=to_dtype, expected=expected,
                        direction=TO_WIRE, **kwargs)


# FROM WIRE: client wrote STRING -> store in DTYPE

def no_encoding(count):
    return dict(string_encoding=None, count=count,
                enum_strings=['abc', 'def', 'ghi'])


def ascii_encoding(count):
    return dict(string_encoding='ascii', count=count,
                enum_strings=['abc', 'def', 'ghi'])


str_two = DbrStringArray([b'abc', b'def'])
str_three = DbrStringArray([b'abc', b'def', b'ghi'])
str_three_numbers = DbrStringArray([b'1', b'2', b'3'])

string_array_from_wire = [
    [STRING, STRING, str_two.tobytes(), ['abc', 'def'], ascii_encoding(count=2)],
    [STRING, STRING, str_three.tobytes(), ['abc', 'def'], ascii_encoding(count=2)],
    [STRING, STRING, str_three.tobytes(), ['abc', 'def', 'ghi'], ascii_encoding(count=3)],
    [STRING, INT, str_two.tobytes(), ValueError, ascii_encoding(count=2)],
    [STRING, FLOAT, str_two.tobytes(), ValueError, ascii_encoding(count=2)],
    [STRING, ENUM, str_two.tobytes(), [0, 1], ascii_encoding(count=2)],
    [STRING, CHAR, str_two.tobytes(), ValueError, ascii_encoding(count=2)],
    [STRING, LONG, str_two.tobytes(), ValueError, ascii_encoding(count=2)],
    [STRING, DOUBLE, str_two.tobytes(), ValueError, ascii_encoding(count=2)],

    [STRING, INT, str_three_numbers.tobytes(), [1, 2, 3], ascii_encoding(count=3)],
    [STRING, FLOAT, str_three_numbers.tobytes(), [1, 2, 3], ascii_encoding(count=3)],
    [STRING, ENUM, str_three_numbers.tobytes(), ValueError, ascii_encoding(count=3)],
    [STRING, CHAR, str_three_numbers.tobytes(), [1, 2, 3], ascii_encoding(count=3)],
    [STRING, LONG, str_three_numbers.tobytes(), [1, 2, 3], ascii_encoding(count=3)],
    [STRING, DOUBLE, str_three_numbers.tobytes(), [1, 2, 3], ascii_encoding(count=3)],
]


@pytest.mark.parametrize('from_dtype, to_dtype, values, expected, kwargs',
                         string_array_from_wire)
def test_string_array_from_wire(backends, from_dtype, to_dtype, values,
                                expected, kwargs):
    run_conversion_test(values=values, from_dtype=from_dtype,
                        to_dtype=to_dtype, expected=expected,
                        direction=FROM_WIRE, **kwargs)


# ---- CHAR CONVERSION ----

no_encoding = dict(string_encoding=None)
ascii_encoding = dict(string_encoding='ascii')
enum_strs = dict(enum_strings=['aa', 'bb', 'cc'])
str_three = DbrStringArray([b'a', b'b', b'c'])
str_three_nums = DbrStringArray([b'0', b'1', b'2'])


# TO WIRE: channeldata stores CHAR -> caget of DTYPE
char_to_wire = [
    [CHAR, STRING, [b'abc'], list(str_three), no_encoding],
    [CHAR, STRING, ['abc'], list(str_three), ascii_encoding],
    [CHAR, STRING, [0, 1, 2], list(str_three_nums), ascii_encoding],
    [CHAR, INT, ['1'], ValueError, no_encoding],  # string w/o encoding
    [CHAR, INT, [b'1'], [ord(b'1')], no_encoding],
    [CHAR, INT, [1], [1], no_encoding],
    [CHAR, FLOAT, [5], [5.0], no_encoding],
    [CHAR, FLOAT, ["1.2"], [ord('1'), ord('.'), ord('2')], ascii_encoding],
    [CHAR, ENUM, ['aa'], [ord('a')] * 2, ascii_encoding],
    [CHAR, CHAR, [b'1'], [ord(b'1')], no_encoding],
    [CHAR, CHAR, ['1'], [ord(b'1')], ascii_encoding],
    [CHAR, CHAR, [b'abc'], [ord('a'), ord('b'), ord('c')], no_encoding],
    [CHAR, CHAR, ['abc'], [ord('a'), ord('b'), ord('c')], ascii_encoding],
    [CHAR, LONG, [b"1"], [ord('1')], no_encoding],
    [CHAR, LONG, [b"x"], [ord('x')], ascii_encoding],
    [CHAR, DOUBLE, ["1.2"], [ord('1'), ord('.'), ord('2')], ascii_encoding],
    [CHAR, DOUBLE, [b"x"], [ord('x')], no_encoding],
]


@pytest.mark.parametrize('from_dtype, to_dtype, values, expected, kwargs',
                         char_to_wire)
def test_char_to_wire(backends, from_dtype, to_dtype, values, expected, kwargs):
    run_conversion_test(values=values, from_dtype=from_dtype,
                        to_dtype=to_dtype, expected=expected,
                        direction=TO_WIRE, **kwargs)


no_encoding = dict(string_encoding=None)
ascii_encoding = dict(string_encoding='ascii')
enum_strs = dict(enum_strings=['aa', 'bb', 'cc'])

# FROM WIRE: client wrote CHAR -> store in DTYPE
char_from_wire_tests = [
    [CHAR, STRING, b'abc', ['abc'], ascii_encoding],
    [CHAR, INT, b'\x01', [1], no_encoding],
    [CHAR, FLOAT, b'\x05', [5.0], no_encoding],
    [CHAR, ENUM, b'\x01', [1], no_encoding],
    # like channelbytes (no encoding)
    [CHAR, CHAR, b'abc', b'abc', no_encoding],
    # like channelchar (with encoding)
    [CHAR, CHAR, b'abc', 'abc', ascii_encoding],
    [CHAR, LONG, b"x", [ord('x')], no_encoding],
    [CHAR, DOUBLE, b"x", [ord('x')], no_encoding],
]


@pytest.mark.parametrize('from_dtype, to_dtype, values, expected, kwargs',
                         char_from_wire_tests)
def test_char_from_wire(backends, from_dtype, to_dtype, values, expected,
                        kwargs):
    run_conversion_test(values=values, from_dtype=from_dtype,
                        to_dtype=to_dtype, expected=expected,
                        direction=FROM_WIRE, **kwargs)


# TODO: between numerical types testing (int/float/long...)


# ---- ENUM CONVERSION ----

no_encoding = dict(string_encoding=None)
ascii_encoding = dict(string_encoding='ascii')
enum_strs = dict(enum_strings=['aa', 'bb', 'cc'],
                 string_encoding='ascii')

# TO WIRE: channeldata stores CHAR -> caget of DTYPE
enum_to_wire_tests = [
    [ENUM, STRING, ['bb'], [b'bb'], enum_strs],
    [ENUM, STRING, [1], [b'bb'], enum_strs],
    [ENUM, INT, [1], [1], enum_strs],
    [ENUM, INT, ['bb'], [1], enum_strs],
    [ENUM, FLOAT, [1], [1], enum_strs],
    [ENUM, FLOAT, ['bb'], [1.0], enum_strs],
    [ENUM, CHAR, [1], [1], enum_strs],
    [ENUM, CHAR, ['bb'], [1], enum_strs],
    [ENUM, LONG, [1], [1], enum_strs],
    [ENUM, LONG, ['bb'], [1], enum_strs],
    [ENUM, DOUBLE, [1], [1.0], enum_strs],
    [ENUM, DOUBLE, ['bb'], [1.0], enum_strs],

    [ENUM, STRING, [b'abc'], ValueError, enum_strs],  # no bytes
    [ENUM, INT, [b'abc'], ValueError, enum_strs],  # no bytes
    [ENUM, INT, [10], ValueError, enum_strs],  # invalid index
    [ENUM, STRING, [10], ValueError, enum_strs],  # invalid index
    [ENUM, STRING, ['abc'], ValueError, no_encoding],  # no enum strs
    [ENUM, STRING, ['abc'], ValueError, enum_strs],  # bad string

]


@pytest.mark.parametrize('from_dtype, to_dtype, values, expected, kwargs',
                         enum_to_wire_tests)
def test_enum_to_wire(backends, from_dtype, to_dtype, values, expected, kwargs):
    run_conversion_test(values=values, from_dtype=from_dtype,
                        to_dtype=to_dtype, expected=expected,
                        direction=TO_WIRE, **kwargs)


# ---- LONG CONVERSION ----

no_encoding = dict(string_encoding=None)
ascii_encoding = dict(string_encoding='ascii')
enum_strs = dict(enum_strings=['aa', 'bb', 'cc'])

# TO WIRE: channeldata stores LONG -> caget of DTYPE
long_to_wire = [
    [LONG, STRING, 1, [b'1'], ascii_encoding],
    [LONG, STRING, [1, 2, 3], [b'1', b'2', b'3'], ascii_encoding],
    [LONG, INT, [1, 2], [1, 2], no_encoding],
    [LONG, FLOAT, [5, 2], [5.0, 2.0], no_encoding],
    [LONG, CHAR, [1, 2], [1, 2], ascii_encoding],
    [LONG, LONG, [1, 2], [1, 2], no_encoding],
    [LONG, LONG, [1, 2], [1, 2], no_encoding],
    [LONG, DOUBLE, [5, 2], [5.0, 2.0], no_encoding],
]


@pytest.mark.parametrize('from_dtype, to_dtype, values, expected, kwargs',
                         long_to_wire)
def test_long_to_wire(backends, from_dtype, to_dtype, values, expected,
                      kwargs):
    run_conversion_test(values=values, from_dtype=from_dtype,
                        to_dtype=to_dtype, expected=expected,
                        direction=TO_WIRE, **kwargs)
