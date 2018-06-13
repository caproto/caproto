#!/usr/bin/env python3
from caproto.server import pvproperty, PVGroup, ioc_arg_parser, run
from collections import namedtuple


class StateIOC(PVGroup):
    states = dict(state=False)
    # NOTE: it may make more sense to have a threading.Event (etc) such that
    # the remaining sync modes can be supported
    value = pvproperty(value=[1])
    toggle_state = pvproperty(value=[False])
    states = namedtuple('States', 'a')(a=False)

    @value.startup
    async def value(self, instance, async_lib):
        'Periodically update the value'
        while True:
            for i in range(10):
                # update the ChannelData instance and notify any subscribers
                await instance.write(value=[i])
                # Let the async library wait for the next iteration
                await async_lib.library.sleep(0.25)

    @toggle_state.putter
    async def toggle_state(self, instance, value):
        async with self.update_state('a', not self.states.a):
            ...


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='state:',
        desc="")
    ioc = StateIOC(**ioc_options)
    run(ioc.pvdb, **run_options)
