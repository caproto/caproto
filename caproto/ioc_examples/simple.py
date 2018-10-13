#!/usr/bin/env python3
from caproto.server import pvproperty, PVGroup, ioc_arg_parser, run


class SimpleIOC(PVGroup):
    "An IOC with two simple read/writable PVs"
    A = pvproperty(value=1)
    B = pvproperty(value=2)


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='simple:',
        desc="Run an IOC with two simple, uncoupled, readable/writable PVs.")
    ioc = SimpleIOC(**ioc_options)
    run(ioc.pvdb, **run_options)
