#!/usr/bin/env python3
from caproto import ChannelType
from caproto.server import PVGroup, ioc_arg_parser, pvproperty, run


class ArrayIOC(PVGroup):
    """Simple examples of scalar and array-valued pvproperties."""
    scalar_int = pvproperty(
        value=1,
        doc="A scalar integer",
    )
    scalar_int2 = pvproperty(
        value=[2],
        doc="A scalar integer - as len([2]) == 1",
    )
    array_int = pvproperty(
        value=3,
        max_length=5,
        doc="An integer array. Initial value is [3], 4 more values will fit."
    )
    scalar_float = pvproperty(
        value=1.01,
        precision=5,
        doc="A scalar float (implicit max_length=1)",
    )
    array_float = pvproperty(
        value=3.01,
        max_length=5,
        precision=5,
        doc="A float array. Initial value is [3.01], 4 more values will fit.",
    )

    scalar_string = pvproperty(
        value='string1',
        dtype=ChannelType.STRING,
        doc="A normal string, holding up to 40 characters."
    )
    array_string = pvproperty(
        value=['string1', 'string2'],
        max_length=5,
        dtype=ChannelType.STRING,
        doc="An array of up to 5 strings. String arrays are not normally used."
    )

    byte = pvproperty(
        value=b'byte0123',
        max_length=10,
        doc='A byte array (no encoding) of up to 10 characters.',
    )
    char = pvproperty(
        value='char0123',
        string_encoding='latin-1',
        max_length=10,
        doc='A string with latin-1 encoding of up to 10 characters.',
    )
    enum = pvproperty(
        value='no',
        enum_strings=['no', 'yes'],
        dtype=ChannelType.ENUM,
        record='bi',
        doc='A scalar enum',
    )

    @scalar_int.scan(period=1)
    async def scalar_int(self, instance, async_lib):
        print(
            'The current values are:',
            self.scalar_int.value,
            self.scalar_int2.value,
            self.array_int.value
        )


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='arr:',
        desc=ArrayIOC.__doc__)
    ioc = ArrayIOC(**ioc_options)
    run(ioc.pvdb, **run_options)
