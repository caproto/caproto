#!/usr/bin/env python3
from caproto.server import pvproperty, PVGroup, ioc_arg_parser, run


class StartupAndShutdown(PVGroup):
    "An IOC that prints on startup and on shutdown"
    thing = pvproperty(value=2)

    @thing.startup
    async def thing(self, instance, async_lib):
        print('starting up')
        # more useful logic goes here

    @thing.shutdown
    async def thing(self, instance, async_lib):
        print('shutting down')
        # more useful logic goes here


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='simple:',
        desc="Run an IOC that prints on startup and shutdown.")
    ioc = StartupAndShutdown(**ioc_options)
    run(ioc.pvdb, **run_options)
