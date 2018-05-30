#!/usr/bin/env python3
import logging
import sys
import random

from caproto.benchmarking import set_logging_level
from caproto.curio.server import start_server
from caproto.server import pvproperty, PVGroup


class RandomWalkIOC(PVGroup):
    delta_t = pvproperty(value=[3.0])
    x = pvproperty(value=[0.0])

    @x.startup
    async def x(self, instance, async_lib):
        'Periodically update the value'
        while True:
            # compute next value
            x, = self.x.value
            x += random.random()

            # update the ChannelData instance and notify any subscribers
            await instance.write(value=[x])

            # Let the async library wait for the next iteration
            await async_lib.library.sleep(self.delta_t.value[0])


if __name__ == '__main__':
    # usage: random_walk.py [PREFIX]
    import curio

    try:
        prefix = sys.argv[1]
    except IndexError:
        prefix = 'random_walk:'

    set_logging_level(logging.DEBUG)
    ioc = RandomWalkIOC(prefix=prefix, macros={})
    print(list(ioc.pvdb))
    curio.run(start_server, ioc.pvdb)
