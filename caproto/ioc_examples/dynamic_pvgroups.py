#!/usr/bin/env python3
from caproto.server import pvproperty, PVGroup, ioc_arg_parser, run


class IOCMain(PVGroup):
    'An IOC with several PVGroups created dynamically'
    shared_value = 5

    def __init__(self, prefix, *, groups, **kwargs):
        super().__init__(prefix, **kwargs)
        self.groups = groups


class GroupA(PVGroup):
    setpoint = pvproperty(value=10, name='')
    readback = pvproperty(value=10, name='_RBV')

    @setpoint.putter
    async def setpoint(self, instance, value):
        print('writing to setpoint the value', value)
        self.ioc.shared_value = value
        return value

    def __init__(self, prefix, *, ioc, **kwargs):
        super().__init__(prefix, **kwargs)
        self.ioc = ioc


class GroupB(PVGroup):
    setpoint = pvproperty(value=20, name='_A')
    readback = pvproperty(value=20, name='_B')

    def __init__(self, prefix, *, ioc, **kwargs):
        super().__init__(prefix, **kwargs)
        self.ioc = ioc


def create_ioc(prefix, groups_a, groups_b, **ioc_options):
    'Create groups based on prefixes passed in from groups_a, groups_b'
    groups = {}

    ioc = IOCMain(prefix=prefix, groups=groups, **ioc_options)

    for group_prefix in groups_a:
        groups[group_prefix] = GroupA(f'{prefix}{group_prefix}', ioc=ioc)

    for group_prefix in groups_b:
        groups[group_prefix] = GroupB(f'{prefix}{group_prefix}', ioc=ioc)

    for prefix, group in groups.items():
        ioc.pvdb.update(**group.pvdb)

    return ioc


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='groups:',
        desc=IOCMain.__doc__,
    )

    ioc = create_ioc(groups_a=['A1', 'A2', 'A3'],
                     groups_b=['B1', 'B2', 'B3'],
                     **ioc_options,
                     )

    run(ioc.pvdb, **run_options)
