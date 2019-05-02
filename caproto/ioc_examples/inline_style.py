#!/usr/bin/env python3
from caproto.server import pvproperty, PVGroup, ioc_arg_parser, run
import random


class InlineStyleIOC(PVGroup):
    "An IOC with a read-only PV and a read-write PV with inline customization"
    @pvproperty  # default dtype is int
    async def random_int(self, instance):
        return random.randint(1, 100)

    @pvproperty(dtype=str)
    async def random_str(self, instance):
        return random.choice('abc')

    @pvproperty(value='c')  # initializes value and, implicitly, dtype
    async def A(self, instance):
        print('reading A')
        return instance.value

    @A.putter
    async def A(self, instance, value):
        print('writing to A the value', value)
        return value


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='inline_style:',
        desc='Run an IOC PVs having custom update behavior, defined "inline".')
    ioc = InlineStyleIOC(**ioc_options)
    run(ioc.pvdb, **run_options)
