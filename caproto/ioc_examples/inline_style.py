#!/usr/bin/env python3
from caproto.server import pvproperty, PVGroup
import random


class InlineStyleIOC(PVGroup):
    "An IOC with a read-only PV and a read-write PV with inline customization"
    @pvproperty  # default dtype is int
    async def random_int(self, instance):
        return random.randint(1, 100)

    @pvproperty(dtype=str)
    async def random_str(self, instance):
        return random.choice('abc')

    @pvproperty(value=['c'])  # initializes value and, implicitly, dtype
    async def A(self, instance):
        print('reading A')
        return instance.value

    @A.putter
    async def A(self, instance, value):
        print('writing to A the value', value)
        return value


if __name__ == '__main__':
    # usage: inline_style.py <PREFIX>
    import sys
    import curio
    from caproto.curio.server import start_server

    try:
        prefix = sys.argv[1]
    except IndexError:
        prefix = 'inline_style:'

    # Instantiate the IOC, assigning a prefix for the PV names.
    ioc = InlineStyleIOC(prefix=prefix)
    print('PVs:', list(ioc.pvdb))

    # Run IOC using curio.
    curio.run(start_server(ioc.pvdb))
