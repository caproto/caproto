#!/usr/bin/env python3
from caproto.server import pvproperty, PVGroup, ioc_arg_parser, run
from collections import namedtuple


class StateIOC(PVGroup):
    states = namedtuple('States', 'a')(a=False)
    value = pvproperty(value=[1])

    disable_state = pvproperty(value=[False])
    enable_state = pvproperty(value=[False])
    state = pvproperty(value=[False])

    @value.startup
    async def value(self, instance, async_lib):
        'Periodically update the value'
        while True:
            for i in range(10):
                # update the ChannelData instance and notify any subscribers
                await instance.write(value=[i])
                # Let the async library wait for the next iteration
                await async_lib.library.sleep(0.5)

    @disable_state.putter
    async def disable_state(self, instance, value):
        async with self.update_state('a', False):
            ...

    @enable_state.putter
    async def enable_state(self, instance, value):
        async with self.update_state('a', True):
            ...


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='state:',
        desc="")
    ioc = StateIOC(**ioc_options)
    run(ioc.pvdb, **run_options)
