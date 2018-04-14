import array
from inspect import isclass

import pytest
import numpy as np
from numpy.testing import assert_array_almost_equal

from .._data import convert_values, ConversionDirection
from .._dbr import (ChannelType, DbrStringArray, _numpy_map,
                    _array_type_code_map, USE_NUMPY)


FROM_WIRE = ConversionDirection.FROM_WIRE
TO_WIRE = ConversionDirection.TO_WIRE

STRING = ChannelType.STRING
INT = ChannelType.INT
FLOAT = ChannelType.FLOAT
ENUM = ChannelType.ENUM
CHAR = ChannelType.CHAR
LONG = ChannelType.LONG
DOUBLE = ChannelType.DOUBLE

STS_STRING = ChannelType.STS_STRING
STS_INT = ChannelType.STS_INT
STS_FLOAT = ChannelType.STS_FLOAT
STS_ENUM = ChannelType.STS_ENUM
STS_CHAR = ChannelType.STS_CHAR
STS_LONG = ChannelType.STS_LONG
STS_DOUBLE = ChannelType.STS_DOUBLE

TIME_STRING = ChannelType.TIME_STRING
TIME_INT = ChannelType.TIME_INT
TIME_FLOAT = ChannelType.TIME_FLOAT
TIME_ENUM = ChannelType.TIME_ENUM
TIME_CHAR = ChannelType.TIME_CHAR
TIME_LONG = ChannelType.TIME_LONG
TIME_DOUBLE = ChannelType.TIME_DOUBLE

# GR_STRING = ChannelType.GR_STRING  # not implemented by EPICS
GR_INT = ChannelType.GR_INT
GR_FLOAT = ChannelType.GR_FLOAT
GR_ENUM = ChannelType.GR_ENUM
GR_CHAR = ChannelType.GR_CHAR
GR_LONG = ChannelType.GR_LONG
GR_DOUBLE = ChannelType.GR_DOUBLE

# CTRL_STRING = ChannelType.CTRL_STRING  # not implemented by EPICS
CTRL_INT = ChannelType.CTRL_INT
CTRL_FLOAT = ChannelType.CTRL_FLOAT
CTRL_ENUM = ChannelType.CTRL_ENUM
CTRL_CHAR = ChannelType.CTRL_CHAR
CTRL_LONG = ChannelType.CTRL_LONG
CTRL_DOUBLE = ChannelType.CTRL_DOUBLE

PUT_ACKT = ChannelType.PUT_ACKT
PUT_ACKS = ChannelType.PUT_ACKS

STSACK_STRING = ChannelType.STSACK_STRING
CLASS_NAME = ChannelType.CLASS_NAME


@pytest.mark.parametrize('ntype', (STSACK_STRING, CLASS_NAME))
def test_special_types(ntype):
    # should pass,
    in_value = expected_value = 0.2
    out_value = convert_values(values=in_value, from_dtype=ntype,
                               to_dtype=ntype, direction=FROM_WIRE)

    assert out_value == expected_value

    with pytest.raises(ValueError):
        out_value = convert_values(values=in_value, from_dtype=ntype,
                                   to_dtype=STRING, direction=FROM_WIRE)


def run_conversion_test(values, from_dtype, to_dtype, expected,
                        *, direction, string_encoding=None, enum_strings=None):
    def _test():
        print(f'--- {direction} ---')
        print(f'Convert: {from_dtype.name} {values!r} -> {to_dtype.name} '
              f'(str encoding: {string_encoding})')
        print(f'Expecting: {expected!r}')
        converted = convert_values(values, from_dtype=from_dtype,
                                   to_dtype=to_dtype,
                                   string_encoding=string_encoding,
                                   enum_strings=enum_strings,
                                   direction=direction)
        print(f'Converted: {converted!r}')
        return converted

    if direction == FROM_WIRE:
        if from_dtype == ChannelType.STRING:
            values = DbrStringArray(values)
        elif USE_NUMPY:
            values = np.array(values, dtype=_numpy_map[from_dtype])
        else:
            values = array.array(_array_type_code_map[from_dtype], values)

    if isclass(expected) and issubclass(expected, Exception):
        with pytest.raises(expected):
            _test()
    else:
        returned = _test()
        if isinstance(returned, array.array):
            assert returned.typecode == _array_type_code_map[to_dtype]
            print(f'array to list {returned} -> {returned.tolist()}'
                  f' ({returned.typecode})')
            returned = returned.tolist()
        elif isinstance(returned, np.ndarray):
            assert returned.dtype == _numpy_map[to_dtype]
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
string_encoding_tests = [
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

    [STRING, INT, "x", ValueError, no_encoding],  # no encoding
    [STRING, CHAR, b'abc', ValueError, no_encoding],
    [STRING, CHAR, 'abc', ValueError, ascii_encoding],
    [STRING, LONG, "x", ValueError, no_encoding],
    [STRING, DOUBLE, "x", ValueError, no_encoding],
]


@pytest.mark.parametrize('from_dtype, to_dtype, values, expected, kwargs',
                         string_encoding_tests)
def test_string_encoding(from_dtype, to_dtype, values, expected, kwargs):
    run_conversion_test(values=values, from_dtype=from_dtype,
                        to_dtype=to_dtype, expected=expected,
                        direction=TO_WIRE, **kwargs)


# ** decoding (i.e., string caput of string to database)
no_encoding = dict(string_encoding=None)
ascii_encoding = dict(string_encoding='ascii')
enum_strs = dict(enum_strings=['aa', 'bb', 'cc'],
                 string_encoding='ascii')

# FROM WIRE: client wrote STRING -> store in DTYPE
string_decoding_tests = [
    [STRING, STRING, [b'abc'], [b'abc'], no_encoding],
    [STRING, STRING, [b'abc'], ['abc'], ascii_encoding],
    [STRING, INT, [b"1"], [1], ascii_encoding],
    [STRING, FLOAT, [b"1.2"], [1.2], ascii_encoding],
    [STRING, ENUM, [b'bb'], [1], enum_strs],
    # we received string b'1' from wire. expect to convert this to
    # a ChannelChar. Should store: [int('1')]
    [STRING, CHAR, [b'1'], [1], ascii_encoding],
    [STRING, CHAR, [b'2'], [2], ascii_encoding],
    [STRING, LONG, [b"3"], [3], ascii_encoding],
    [STRING, DOUBLE, [b"1.2"], [1.2], ascii_encoding],

    [STRING, INT, [b"x"], ValueError, no_encoding],  # no encoding
    [STRING, ENUM, [b'bad'], ValueError, enum_strs],
    [STRING, CHAR, [b'abc'], ValueError, no_encoding],
    [STRING, CHAR, [b'abc'], ValueError, ascii_encoding],
    [STRING, LONG, [b"x"], ValueError, no_encoding],
    [STRING, DOUBLE, [b"x"], ValueError, no_encoding],
]


@pytest.mark.parametrize('from_dtype, to_dtype, values, expected, kwargs',
                         string_decoding_tests)
def test_string_decoding(from_dtype, to_dtype, values, expected, kwargs):
    run_conversion_test(values=values, from_dtype=from_dtype,
                        to_dtype=to_dtype, expected=expected,
                        direction=FROM_WIRE, **kwargs)


# ---- CHAR CONVERSION ----

no_encoding = dict(string_encoding=None)
ascii_encoding = dict(string_encoding='ascii')
enum_strs = dict(enum_strings=['aa', 'bb', 'cc'])

# TO WIRE: channeldata stores CHAR -> caget of DTYPE
char_tests = [
    [CHAR, STRING, [b'abc'], [ord('a'), ord('b'), ord('c')], no_encoding],
    [CHAR, STRING, ['abc'], [b'a', b'b', b'c'], ascii_encoding],
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
                         char_tests)
def test_char(from_dtype, to_dtype, values, expected, kwargs):
    run_conversion_test(values=values, from_dtype=from_dtype,
                        to_dtype=to_dtype, expected=expected,
                        direction=TO_WIRE, **kwargs)


no_encoding = dict(string_encoding=None)
ascii_encoding = dict(string_encoding='ascii')
enum_strs = dict(enum_strings=['aa', 'bb', 'cc'])

# FROM WIRE: client wrote CHAR -> store in DTYPE
char_from_wire_tests = [
    [CHAR, STRING, list(b'abc'), ['abc'], ascii_encoding],
    [CHAR, INT, [1], [1], no_encoding],
    [CHAR, FLOAT, [5], [5.0], no_encoding],
    [CHAR, ENUM, [1], [1], no_encoding],
    # like channelbytes (no encoding)
    [CHAR, CHAR, list(b'abc'), list(b'abc'), no_encoding],
    # like channelchar (with encoding)
    [CHAR, CHAR, list(b'abc'), ['abc'], ascii_encoding],
    [CHAR, LONG, [ord(b"x")], [ord('x')], no_encoding],
    [CHAR, DOUBLE, [ord(b"x")], [ord('x')], no_encoding],
]


@pytest.mark.parametrize('from_dtype, to_dtype, values, expected, kwargs',
                         char_from_wire_tests)
def test_char_from_wire(from_dtype, to_dtype, values, expected, kwargs):
    run_conversion_test(values=values, from_dtype=from_dtype,
                        to_dtype=to_dtype, expected=expected,
                        direction=FROM_WIRE, **kwargs)
