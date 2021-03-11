#!/usr/bin/env python3
from textwrap import dedent

from caproto import SkipWrite
from caproto.server import PVGroup, ioc_arg_parser, pvproperty, run


class SkipWriteIOC(PVGroup):
    """
    An IOC with a single scalar PV that uses SkipWrite.

    Scalar PVs
    ----------
    value (int)
    """
    value = pvproperty(
        value=1,
        doc='An integer - I may only have the value "85"!',
    )

    @value.putter
    async def value(self, instance, value):
        if value != 85:
            print(f"Sorry, I like the magic number 85, not {value}.")
            # verify_value=False will avoid recursion into this putter method:
            await instance.write(85, verify_value=False)

        # By default, the value returned from this method will be written into
        # `value` and the timestamp will be updated.
        # To avoid this, either:
        raise SkipWrite()
        # Or:
        # return SkipWrite


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='skip:',
        desc=dedent(SkipWriteIOC.__doc__))
    ioc = SkipWriteIOC(**ioc_options)
    run(ioc.pvdb, **run_options)
