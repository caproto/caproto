import array
import sys
from ._dbr import (ChannelType, DbrStringArray,
                   native_int_types, native_float_types)
from ._backend import Backend, register_backend


type_map = {
    ChannelType.STRING: 'B',  # TO DO
    ChannelType.INT: 'h',
    ChannelType.FLOAT: 'f',
    ChannelType.ENUM: 'H',
    ChannelType.CHAR: 'b',
    ChannelType.LONG: 'i',
    ChannelType.DOUBLE: 'd',

    ChannelType.STSACK_STRING: 'b',
    ChannelType.CLASS_NAME: 'b',

    ChannelType.PUT_ACKS: 'H',  # ushort_t
    ChannelType.PUT_ACKT: 'H',
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

    dt = type_map[native_type]
    arr = array.array(dt, value)
    print('epics to python', value, arr, auto_byteswap)
    if sys.byteorder == 'little' and auto_byteswap:
        arr.byteswap()
    return arr


def python_to_epics(dtype, values, *, byteswap=True, convert_from=None):
    'Convert values from_dtype -> to_dtype'
    print('python to epics', values, byteswap)
    if isinstance(values, array.array):
        if byteswap:
            values.byteswap()
        return values

    if dtype == ChannelType.STRING:
        return DbrStringArray(values).tobytes()

    if convert_from is not None:
        if convert_from in native_float_types and dtype in native_int_types:
            values = [int(v) for v in values]

    arr = array.array(type_map[dtype], values)
    if byteswap:
        arr.byteswap()
    return arr


def _setup():
    from ._dbr import native_types, DBR_TYPES
    import ctypes

    for _type in set(native_types) - set([ChannelType.STRING]):
        _size = ctypes.sizeof(DBR_TYPES[_type])
        assert array.array(type_map[_type]).itemsize == _size

    try:
        import numpy
    except ImportError:
        array_types = (array.ArrayType, )
    else:
        array_types = (array.ArrayType, numpy.ndarray)

    return Backend(name='array',
                   array_types=array_types,
                   type_map=type_map,
                   epics_to_python=epics_to_python,
                   python_to_epics=python_to_epics,
                   )


register_backend(_setup())
