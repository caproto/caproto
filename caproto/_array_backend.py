import array
import ctypes
import sys
from ._backend import Backend, register_backend, convert_values
from ._dbr import (ChannelType, DbrStringArray, native_int_types,
                   native_float_types, native_types, DBR_TYPES)


default_endian = ('>' if sys.byteorder == 'big'
                  else '<')


class Array(array.ArrayType):
    'Simple array.array subclass which tracks endianness'
    __dict__ = {}

    def __init__(self, type_code, values, *, endian=default_endian):
        self.endian = endian
        super().__init__()

    def __getitem__(self, slice_):
        sliced = super().__getitem__(slice_)
        if isinstance(slice_, int):
            # This is just a single value, numerical or string.
            return sliced
        else:
            # This is an array.ArrayType. We have to propagate the endianness.
            return Array(self.typecode, sliced, endian=self.endian)

    def byteswap(self):
        self.endian = {'<': '>',
                       '>': '<'}[self.endian]
        super().byteswap()


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
    if isinstance(value, memoryview):
        value = value.cast(dt)

    arr = Array(dt, value, endian='>')
    if default_endian == '<' and auto_byteswap:
        arr.byteswap()
    return arr


def python_to_epics(dtype, values, *, byteswap=True, convert_from=None):
    'Convert values from_dtype -> to_dtype'
    if dtype == ChannelType.STRING:
        return DbrStringArray(values).tobytes()

    typecode = type_map[dtype]
    endian = getattr(values, 'endian', default_endian)
    if isinstance(values, array.array):
        if typecode == values.typecode and byteswap and endian == '>':
            # Everything matches up - use the array as-is
            return values

        # Otherwise, convert to a list and process further below
        values = values.tolist()

    if convert_from in native_float_types and dtype in native_int_types:
        values = [int(v) for v in values]

    # Make a new array with the system endianness
    endian = default_endian
    arr = Array(typecode, values, endian=endian)
    if byteswap and endian != '>':
        # Byteswap if it's not big endian
        arr.byteswap()
    return arr


def _setup():
    # Sanity check: array item size should match struct size.
    for _type in set(native_types) - set([ChannelType.STRING]):
        _size = ctypes.sizeof(DBR_TYPES[_type])
        assert array.array(type_map[_type]).itemsize == _size

    try:
        import numpy
    except ImportError:
        array_types = (Array, array.ArrayType, DbrStringArray)
    else:
        array_types = (Array, array.ArrayType, numpy.ndarray, DbrStringArray)

    return Backend(name='array',
                   array_types=array_types,
                   type_map=type_map,
                   epics_to_python=epics_to_python,
                   python_to_epics=python_to_epics,
                   convert_values=convert_values,
                   )


register_backend(_setup())
