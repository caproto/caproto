# The module global 'backend' is a SimpleNamespace. When a Backend in selected,
# its values are filled into 'backend'. At import time, a default Backend is
# registered and selected. The default depends on whether numpy is available.
import collections
import logging
from types import SimpleNamespace

from ._dbr import (ChannelType, native_float_types, native_int_types,
                   native_types, DbrStringArray)

from ._utils import ConversionDirection, CaprotoConversionError


__all__ = ('backend', 'Backend', 'register_backend', 'select_backend')
logger = logging.getLogger('caproto')


try:
    import numpy  # noqa
except ImportError:
    default_backend = 'array'
else:
    default_backend = 'numpy'


_backends = {}
_initialized = False  # Has any backend be selected yet?
Backend = collections.namedtuple(
    'Backend',
    'name convert_values epics_to_python python_to_epics type_map array_types'
)


def register_backend(new_backend):
    logger.debug('Backend %r registered', new_backend.name)
    _backends[new_backend.name] = new_backend

    # Automatically select upon registration if no backend has been selected
    # yet and this backend is the default one.
    if default_backend == new_backend.name and not _initialized:
        select_backend(new_backend.name)


def select_backend(name):
    global _initialized
    _initialized = True
    logger.debug('Selecting backend: %r', name)
    _backend = _backends[name]
    backend.backend_name = _backend.name
    backend.python_to_epics = _backend.python_to_epics
    backend.epics_to_python = _backend.epics_to_python
    backend.type_map = _backend.type_map
    backend.array_types = _backend.array_types
    backend.convert_values = _backend.convert_values


backend = SimpleNamespace(
    backend_name=None, python_to_epics=None, epics_to_python=None,
    type_map=None, array_types=None, convert_values=None,
)


def encode_or_fail(s, encoding):
    if isinstance(s, str):
        if encoding is None:
            raise CaprotoConversionError('String encoding required')
        return s.encode(encoding)
    elif isinstance(s, bytes):
        return s

    raise CaprotoConversionError('Expected string or bytes')


def decode_or_fail(s, encoding):
    if isinstance(s, bytes):
        if encoding is None:
            raise CaprotoConversionError('String encoding required')
        return s.decode(encoding)
    elif isinstance(s, str):
        return s

    raise CaprotoConversionError('Expected string or bytes')


def _preprocess_enum_values(values, to_dtype, string_encoding, enum_strings):
    if isinstance(values, (str, bytes)):
        values = [values]

    if enum_strings is None:
        raise CaprotoConversionError('enum_strings not specified')

    num_strings = len(enum_strings)

    if to_dtype == ChannelType.STRING:
        def enum_to_string(v):
            if isinstance(v, bytes):
                raise CaprotoConversionError('Enum strings must be integer or string')
            elif isinstance(v, str):
                if v not in enum_strings:
                    raise CaprotoConversionError(f'Invalid enum string: {v!r}')
                return v

            if 0 <= v < num_strings:
                return enum_strings[int(v)]
            raise CaprotoConversionError(f'Invalid enum index: {v!r} '
                                         f'count={num_strings}')
        return [enum_to_string(v) for v in values]

    def enum_to_int(v):
        if isinstance(v, bytes):
            raise CaprotoConversionError('Enum strings must be integer or string')
        elif isinstance(v, str):
            try:
                return enum_strings.index(v)
            except ValueError:
                raise CaprotoConversionError(f'Invalid enum string: {v!r}')

        if 0 <= v < num_strings:
            return int(v)
        raise CaprotoConversionError(f'Invalid enum index: {v!r} '
                                     f'count={num_strings}')

    return [enum_to_int(v) for v in values]


def _preprocess_char_from_wire(values, to_dtype, string_encoding, enum_strings):
    'From wire: pre-process EPICS CHAR data for conversion to to_dtype'
    if isinstance(values, list):
        # This is from the wire, so it has to be a single value
        bytes_from_wire = values[0]
    else:
        bytes_from_wire = values

    bytes_from_wire = bytes_from_wire.tobytes()

    if to_dtype in (ChannelType.STRING, ChannelType.CHAR):
        if not string_encoding:
            if to_dtype == ChannelType.STRING:
                return [bytes_from_wire]
            else:
                return bytes_from_wire

        values = bytes_from_wire.decode(string_encoding)
        try:
            return values[:values.index('\x00')]
        except ValueError:
            return values

    # if not converting to a string, we need a list of numbers.
    # b'bytes' -> [ord('b'), ord('y'), ...]
    return list(bytes_from_wire)


def _preprocess_char_to_wire(values, to_dtype, string_encoding, enum_strings):
    'To wire: pre-process python-stored CHAR values for conversion to to_dtype'
    if isinstance(values, list) and len(values) == 1:
        values = values[0]

    if to_dtype == ChannelType.STRING:
        # NOTE: accurate, but results in very inefficient CA response
        #       Bytes required: 40 * num_chars (i.e., 40 * len(values))
        if isinstance(values, (str, bytes)):
            # a length 3 char value is converted to 3 strings:
            # b'abc' -> [b'a', b'b', b'c']
            #  'abc' -> [b'a', b'b', b'c']
            # this is, of course, different from returning b'abc', which would
            # be converted to a single string on the wire.
            return [bytes([v]) for v in encode_or_fail(values, string_encoding)]
        else:
            # list of numbers - these will be converted as follows:
            # [1, 2, 3] -> ['1', '2', '3']
            return values

    # if not converting to a string, we need a list of numbers.
    if isinstance(values, (str, bytes)):
        if isinstance(values, str):
            values = encode_or_fail(values, string_encoding)
        # b'bytes' -> [ord('b'), ord('y'), ...]
        return list(values)

    # CHAR data is stored as integers
    try:
        values[0]
    except TypeError:
        # example: values = 5
        return [values]
    else:
        # example: values = [5, 6, 7]
        return values


def _decode_string_list(values, string_encoding):
    'List of bytes, strings, values -> list of decoded strings'
    def get_value(v):
        if isinstance(v, bytes):
            if string_encoding:  # can have bytes in ChannelString
                return v.decode(string_encoding)
            return v
        elif isinstance(v, str):
            return v
        else:
            return str(v)
    return [get_value(v) for v in values]


def _encode_to_string_array(values, string_encoding):
    'List of bytes, strings, values -> DbrStringArray'
    def get_value(v):
        if isinstance(v, bytes):
            return v
        elif isinstance(v, str):
            return encode_or_fail(v, string_encoding)
        else:
            return encode_or_fail(str(v), string_encoding)
    return DbrStringArray(get_value(v) for v in values)


def _preprocess_string_from_wire(values, to_dtype, string_encoding,
                                 enum_strings):
    if to_dtype == ChannelType.STRING:
        # caller will handle string decoding
        return values

    if to_dtype == ChannelType.ENUM:
        values = [decode_or_fail(v, string_encoding)
                  if isinstance(v, bytes)
                  else v
                  for v in values]

        # conversion for when this is used: `caput enum_pv string_value`
        return _preprocess_enum_values(values, to_dtype=ChannelType.INT,
                                       string_encoding=string_encoding,
                                       enum_strings=enum_strings)
    elif to_dtype in native_int_types:
        # TODO ca_test: for enums, string arrays seem to work, but not
        # scalars?
        return [int(v) for v in values]
    elif to_dtype in native_float_types:
        return [float(v) for v in values]


def _preprocess_string_to_wire(values, to_dtype, string_encoding,
                               enum_strings):
    if isinstance(values, (str, bytes)):
        values = [values]

    # from here on, we are dealing with a list of strings/bytes
    if to_dtype == ChannelType.STRING:
        # caller will handle string encoding
        return values
    elif to_dtype == ChannelType.ENUM:
        # for enums, decode bytes -> strings
        values = [decode_or_fail(v, string_encoding)
                  if isinstance(v, bytes)
                  else v
                  for v in values]
        # conversion for when this is used: `caput enum_pv string_value`
        return _preprocess_enum_values(values, to_dtype=ChannelType.INT,
                                       string_encoding=string_encoding,
                                       enum_strings=enum_strings)
    elif to_dtype in native_int_types:
        return [int(v) for v in values]
    elif to_dtype in native_float_types:
        return [float(v) for v in values]


_custom_preprocess = {
    (ChannelType.ENUM, ConversionDirection.TO_WIRE): _preprocess_enum_values,
    (ChannelType.ENUM, ConversionDirection.FROM_WIRE): _preprocess_enum_values,
    (ChannelType.CHAR, ConversionDirection.FROM_WIRE): _preprocess_char_from_wire,
    (ChannelType.CHAR, ConversionDirection.TO_WIRE): _preprocess_char_to_wire,
    (ChannelType.STRING, ConversionDirection.FROM_WIRE): _preprocess_string_from_wire,
    (ChannelType.STRING, ConversionDirection.TO_WIRE): _preprocess_string_to_wire,
}


def convert_values(values, from_dtype, to_dtype, *, direction,
                   string_encoding='latin-1', enum_strings=None,
                   auto_byteswap=True):
    '''Convert values from one ChannelType to another

    Parameters
    ----------
    values :
    from_dtype : caproto.ChannelType
        The dtype of the values
    to_dtype : caproto.ChannelType
        The dtype to convert to
    direction : caproto.ConversionDirection
        Direction of conversion, from or to the wire
    string_encoding : str, optional
        The encoding to be used for strings
    enum_strings : list, optional
        List of enum strings, if available
    auto_byteswap : bool, optional
        If sending over the wire and using built-in arrays, the data should
        first be byte-swapped to big-endian.
    '''

    if (from_dtype in (ChannelType.STSACK_STRING, ChannelType.CLASS_NAME) or
            (to_dtype in (ChannelType.STSACK_STRING, ChannelType.CLASS_NAME))):
        if from_dtype != to_dtype:
            raise CaprotoConversionError(
                'Cannot convert values for stsack_string or class_name to '
                'other types')
        return values

    if to_dtype not in native_types or from_dtype not in native_types:
        raise CaprotoConversionError('Expecting a native type')

    if not isinstance(values, (str, bytes)):
        try:
            len(values)
        except TypeError:
            values = [values]

    try:
        preprocess = _custom_preprocess[(from_dtype, direction)]
    except KeyError:
        ...
    else:
        try:
            values = preprocess(values=values, to_dtype=to_dtype,
                                string_encoding=string_encoding,
                                enum_strings=enum_strings)
        except Exception as ex:
            raise CaprotoConversionError() from ex

        if to_dtype == ChannelType.STRING and isinstance(values, (str, bytes)):
            values = [values]

    if to_dtype == ChannelType.STRING:
        if direction == ConversionDirection.TO_WIRE:
            return _encode_to_string_array(values, string_encoding)
        else:
            return _decode_string_list(values, string_encoding)
    elif to_dtype == ChannelType.CHAR:
        if len(values):
            if string_encoding and isinstance(values[0], str):
                return values
            elif not string_encoding and isinstance(values[0], bytes):
                return values

    byteswap = (auto_byteswap and direction == ConversionDirection.TO_WIRE)
    return backend.python_to_epics(to_dtype, values, byteswap=byteswap,
                                   convert_from=from_dtype)
