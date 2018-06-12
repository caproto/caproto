#!/usr/bin/env python3
from caproto.server import pvproperty, PVGroup, ioc_arg_parser, run


class StateIOC(PVGroup):
    states = dict(state=False)
    # NOTE: it may make more sense to have a threading.Event (etc) such that
    # the remaining sync modes can be supported
    value = pvproperty(value=[1])
    toggle_state = pvproperty(value=[False])
    state = pvproperty(value=[False], read_only=True)

    @value.startup
    async def value(self, instance, async_lib):
        'Periodically update the value'
        while True:
            for i in range(10):
                # update the ChannelData instance and notify any subscribers
                await instance.write(value=[i])
                # Let the async library wait for the next iteration
                await async_lib.library.sleep(0.5)

    @toggle_state.putter
    async def toggle_state(self, instance, value):
        self.states['state'] = not self.states['state']
        await self.state.write(value=self.states['state'])


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='state:',
        desc="")
    ioc = StateIOC(**ioc_options)
    run(ioc.pvdb, **run_options)
