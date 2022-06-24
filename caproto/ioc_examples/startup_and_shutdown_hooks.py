#!/usr/bin/env python3
from caproto.server import (AsyncLibraryLayer, PVGroup, ioc_arg_parser,
                            pvproperty, run)


class StartupAndShutdown(PVGroup):
    """
    An IOC that shows how to use startup and shutdown hooks.
    """
    thing = pvproperty(value=2, doc="An integer-valued PV.")

    async def __ainit__(self, async_lib: AsyncLibraryLayer):
        self.log.warning("1. The IOC-level startup_hook from `run()` was called.")
        # Note that we have to pass this in to ``run()``!
        await async_lib.library.sleep(1.0)
        self.log.warning("(__ainit__ finished after sleeping)")

    @thing.startup
    async def thing(self, instance, async_lib: AsyncLibraryLayer):
        self.log.warning('2. The "thing" startup hook was called.')
        # more useful logic goes here

    @thing.shutdown
    async def thing(self, instance, async_lib: AsyncLibraryLayer):
        self.log.warning('3. The "thing" shutdown hook was called.')
        # more useful logic goes here


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='simple:',
        desc="Run an IOC that prints on startup and shutdown.")
    ioc = StartupAndShutdown(**ioc_options)
    run(ioc.pvdb, startup_hook=ioc.__ainit__, **run_options)
