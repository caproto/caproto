#!/usr/bin/env python3
import random

from caproto.server import PVGroup, SubGroup, ioc_arg_parser, pvproperty, run


class MySubGroup(PVGroup):
    """Example group of PVs, where the prefix is defined on instantiation."""

    def __init__(self, *args, max_value, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_value = max_value

    rand = pvproperty(
        value=1,
        name="random",
        doc="A random value between 1 and self.max_value.",
    )

    @rand.scan(period=2.0, stop_on_error=False, use_scan_field=False)
    async def rand(self, instance, async_lib):
        print(
            f'{instance.pvname} a random value in [1, {self.max_value}]'
        )
        await instance.write(value=random.randint(1, self.max_value))


class MyPVGroup(PVGroup):
    'Example group of PVs, a mix of pvproperties and subgroups'

    # Create two subgroups:
    group1 = SubGroup(MySubGroup, prefix="group1:", max_value=5)
    group2 = SubGroup(MySubGroup, prefix='group2:', max_value=20)

    # And a third one, using the decorator pattern:
    @SubGroup(prefix='group3:')
    class group3(PVGroup):
        nested_rand = pvproperty(
            value=1,
            name="random",
            doc="A random value between 1 and self.max_value.",
        )

        @nested_rand.scan(period=2.0, stop_on_error=False, use_scan_field=False)
        async def nested_rand(self, instance, async_lib):
            max_value = 10
            print(
                f'{instance.pvname} random value from 1 to {max_value}'
            )
            await instance.write(value=random.randint(1, max_value))


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='subgroups:',
        desc='Run an IOC with groups of groups of PVs.')
    ioc = MyPVGroup(**ioc_options)
    run(ioc.pvdb, **run_options)
