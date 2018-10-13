#!/usr/bin/env python3
from caproto.server import pvproperty, PVGroup, ioc_arg_parser, run
from caproto import ChannelType


class CatvsIOC(PVGroup):
    "An IOC with two simple read/writable PVs"
    ival = pvproperty(value=42)
    aval = pvproperty(value=[0] * 5, dtype=ChannelType.INT)


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='',
        desc="Run an IOC for catvs testing")
    ioc = CatvsIOC(**ioc_options)
    run(ioc.pvdb, **run_options)
