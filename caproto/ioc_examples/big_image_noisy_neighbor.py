#!/usr/bin/env python3

import time
from caproto.server import pvproperty, PVGroup, ioc_arg_parser, run
import numpy as np

image_shape = (3960, 3960)


class IOInterruptIOC(PVGroup):
    t1 = pvproperty(value=2.0)
    image = pvproperty(
        value=np.random.randint(0, 256, image_shape).flatten(), dtype=float
    )

    @t1.startup
    async def t1(self, instance, async_lib):
        # Loop and grab items from the queue one at a time
        while True:
            await self.t1.write(time.monotonic())
            await async_lib.library.sleep(0.1)


if __name__ == "__main__":
    ioc_options, run_options = ioc_arg_parser(
        default_prefix="big_image:",
        desc="Run an IOC that updates via I/O interrupt on key-press events.",
    )

    ioc = IOInterruptIOC(**ioc_options)
    print(ioc.image)
    run(ioc.pvdb, **run_options)
