#!/usr/bin/env python3
from caproto.server import PVSpec, ioc_arg_parser, run


async def put_handler(instance, value):
    print(f"You wrote {value} to {instance.pvname}.")


pv_a = PVSpec(
    name="a",
    value=1,
    record='bi',
    doc='An integer',
    put=put_handler,
)

pv_b = PVSpec(
    name="b",
    value=2.0,
    record='ai',
    doc='A float',
    put=put_handler,
)

pv_c = PVSpec(
    name="c",
    value=[1, 2, 3],
    record='waveform',
    doc='An array of integers',
    put=put_handler,
)


pvdb = {
    pvspec.name: pvspec.create(group=None)
    for pvspec in [pv_a, pv_b, pv_c]
}

if __name__ == '__main__':
    print("pvdb contents:", pvdb)

    ioc_options, run_options = ioc_arg_parser(
        default_prefix='pvspec:',
        desc="A simple IOC without using the PVGroup-style class syntax."
    )

    # It's up to you to add on the prefix and support any other ioc_options:
    pvdb = {
        ioc_options['prefix'] + name: data
        for name, data in pvdb.items()
    }
    run(pvdb, **run_options)
