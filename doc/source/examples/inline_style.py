#!/usr/bin/env python3
from caproto.curio.high_level_server import pvproperty, PVGroupBase
import random


class InlineStyleIOC(PVGroupBase):
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

    # Instantiate the IOC, assigning a prefix for the PV names.
    ioc = InlineStyleIOC(prefix=sys.argv[1])
    print('PVs:', list(ioc.pvdb))
    
    # Run IOC using curio.
    curio.run(start_server(ioc.pvdb))
