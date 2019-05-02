#!/usr/bin/env python3
from caproto.server import pvproperty, PVGroup, ioc_arg_parser, run
from caproto import ChannelType


class ArrayIOC(PVGroup):
    # Define a scalar integer (implicit max_length=1)
    scalar_int = pvproperty(value=1)
    # Define a scalar integer, using the old syntax (implicit max_length=1)
    scalar_int2 = pvproperty(value=[2])
    # Define an integer array. Initial value is [3], 4 more values will fit.
    array_int = pvproperty(value=3, max_length=5)

    # Define a scalar integer (implicit max_length=1)
    scalar_float = pvproperty(value=1.01, precision=5)
    # Define an integer array. Initial value is [3], 4 more values will fit.
    array_float = pvproperty(value=3.01, max_length=5, precision=5)

    # Strings can be arrays, but this is generally not used:
    scalar_string = pvproperty(value='string1', dtype=ChannelType.STRING)
    array_string = pvproperty(value=['string1', 'string2'], max_length=5,
                              dtype=ChannelType.STRING)

    # BYTE, CHAR cannot be arrays - max_length refers to the string length:
    byte = pvproperty(value=b'byte0123', max_length=10)
    char = pvproperty(value='char0123', string_encoding='latin-1',
                      max_length=10)
    # ENUM should not be used as an array type:
    enum = pvproperty(value='no', enum_strings=['no', 'yes'],
                      dtype=ChannelType.ENUM)

    @scalar_int.scan(period=1)
    async def scalar_int(self, instance, async_lib):
        print('values',
              self.scalar_int.value,
              self.scalar_int2.value,
              self.array_int.value)


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='arr:',
        desc='Examples of array- and scalar-valued pvproperties')
    ioc = ArrayIOC(**ioc_options)
    run(ioc.pvdb, **run_options)
