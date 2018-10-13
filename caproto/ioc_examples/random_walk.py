#!/usr/bin/env python3
import random
from caproto.server import pvproperty, PVGroup, ioc_arg_parser, run


class RandomWalkIOC(PVGroup):
    dt = pvproperty(value=3.0)
    x = pvproperty(value=0.0)

    @x.startup
    async def x(self, instance, async_lib):
        'Periodically update the value'
        while True:
            # compute next value
            x = self.x.value + 2 * random.random() - 1

            # update the ChannelData instance and notify any subscribers
            await instance.write(value=x)

            # Let the async library wait for the next iteration
            await async_lib.library.sleep(self.dt.value)


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='random_walk:',
        desc='Run an IOC with a random-walking value.')
    ioc = RandomWalkIOC(**ioc_options)
    run(ioc.pvdb, **run_options)
