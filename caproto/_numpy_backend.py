import ctypes
from ._backend import Backend, register_backend, convert_values
from ._dbr import (ChannelType, DbrStringArray, native_types, DBR_TYPES)

try:
    import numpy as np
except ImportError:
    np = None


type_map = {
    ChannelType.INT: '>i2',
    ChannelType.FLOAT: '>f4',
    ChannelType.ENUM: '>u2',
    ChannelType.LONG: '>i4',
    ChannelType.DOUBLE: '>f8',
    ChannelType.STRING: 'S40',
    ChannelType.CHAR: 'B',
    ChannelType.STSACK_STRING: 'u8',
    ChannelType.CLASS_NAME: 'u8',
    ChannelType.PUT_ACKT: '>u2',
    ChannelType.PUT_ACKS: '>u2',
}


if np is not None:
    # Make the dtypes ahead of time
    type_map = {ch_type: np.dtype(dtype)
                for ch_type, dtype in type_map.items()
                }


def epics_to_python(value, native_type, data_count, *, auto_byteswap=True):
    '''Convert from a native EPICS DBR type to a builtin Python type

    Notes:
     - A waveform of characters is just a bytestring.
     - A waveform of strings is an array whose elements are fixed-length (40-
       character) strings.
     - Enums are just integers that happen to have special significance.
     - Everything else is, straightforwardly, an array of numbers.
    '''

    if native_type == ChannelType.STRING:
        return DbrStringArray.frombuffer(value, data_count)

    # Return an ndarray
    dt = type_map[native_type]
    return np.frombuffer(value, dtype=dt)


def python_to_epics(dtype, values, *, byteswap=True, convert_from=None):
    'Convert python builtin values to epics CA'
    # NOTE: ignoring byteswap, storing everything as big-endian
    if dtype == ChannelType.STRING:
        return DbrStringArray(values).tobytes()
    elif dtype == ChannelType.CHAR:
        if isinstance(values, bytes):
            return values
        elif len(values) and isinstance(values[0], bytes):
            assert len(values) == 1, "expected b'...', [b'...'], or [...]"
            return values[0]

    return np.asarray(values).astype(type_map[dtype])


def _setup():
    # Sanity check: array item size should match struct size.
    for _type in set(native_types) - set([ChannelType.STRING]):
        _size = ctypes.sizeof(DBR_TYPES[_type])
        assert type_map[_type].itemsize == _size

    return Backend(name='numpy',
                   array_types=(np.ndarray, DbrStringArray),
                   type_map=type_map,
                   epics_to_python=epics_to_python,
                   python_to_epics=python_to_epics,
                   convert_values=convert_values,
                   )


if np is not None:
    register_backend(_setup())
