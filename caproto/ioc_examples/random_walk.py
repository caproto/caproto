#!/usr/bin/env python3
import random
from textwrap import dedent

from caproto.server import PVGroup, ioc_arg_parser, pvproperty, run


class RandomWalkIOC(PVGroup):
    """
    This example contains a PV ``x`` that takes random steps at an update rate
    controlled by a second PV, ``dt``.
    """
    dt = pvproperty(value=3.0, doc="Delta time [sec]")
    x = pvproperty(value=0.0, doc="The random float value")

    @x.startup
    async def x(self, instance, async_lib):
        """This is a startup hook which periodically updates the value."""
        while True:
            # Grab the current value from `self.x` and compute the next value:
            x = self.x.value + 2. * random.random() - 1.0

            # Update the ChannelData instance and notify any subscribers:
            await instance.write(value=x)

            # Let the async library wait for the next iteration
            await async_lib.sleep(self.dt.value)


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='random_walk:',
        desc=dedent(RandomWalkIOC.__doc__))
    ioc = RandomWalkIOC(**ioc_options)
    run(ioc.pvdb, **run_options)
