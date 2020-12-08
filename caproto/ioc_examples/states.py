#!/usr/bin/env python3
from caproto.server import pvproperty, PVGroup, ioc_arg_parser, run


class StateIOC(PVGroup):
    value = pvproperty(value=1)
    disable_state = pvproperty(value=False)
    enable_state = pvproperty(value=False)

    def __init__(self, *args, **kwargs):
        self.states = {'my_stately_state': False}
        super().__init__(*args, **kwargs)
        self._value = 0

    @pvproperty()
    async def my_stately_state(self, instance):
        return self.states['my_stately_state']

    @value.scan(period=0.1)
    async def value(self, instance, async_lib):
        'Periodically update the value'
        # update the ChannelData instance and notify any subscribers
        self._value = (self._value + 1) % 10
        await instance.write(value=self._value)

    @disable_state.putter
    async def disable_state(self, instance, value):
        async with self.update_state('my_stately_state', False):
            ...

    @enable_state.putter
    async def enable_state(self, instance, value):
        async with self.update_state('my_stately_state', True):
            ...


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='state:',
        desc="")
    ioc = StateIOC(**ioc_options)
    run(ioc.pvdb, **run_options)
