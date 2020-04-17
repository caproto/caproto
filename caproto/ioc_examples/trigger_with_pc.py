#!/usr/bin/env python3
from caproto.server import (pvproperty, PVGroup,
                            ioc_arg_parser, run)
from caproto import ChannelType
import numpy as np
from textwrap import dedent
import contextvars
import functools
import random
import sys

internal_process = contextvars.ContextVar('internal_process',
                                          default=False)


def no_reentry(func):
    @functools.wraps(func)
    async def inner(*args, **kwargs):
        if internal_process.get():
            return
        try:
            internal_process.set(True)
            return (await func(*args, **kwargs))
        finally:
            internal_process.set(False)

    return inner


class TriggeredIOC(PVGroup):
    """
    A triggered IOC with put-completion support


    Scalar PVs
    ----------
    exposure_time : float
        The simulated exposure time

    acquire : {'idle', 'acquiring'}
        The acquire button, put-complete will indicate when done.

    reading : float
        Random number, updates when 'acquisition' finishes.

    gain : float
        Sets the range of the random number for the reading.

    enabled : {'off', 'on'}

    wait : float
    wait_time : int
    """

    gain = pvproperty(value=2.0)
    exposure_time = pvproperty(value=2.0)
    reading = pvproperty(value=0.1, alarm_group='acq')

    acquire = pvproperty(value='idle',
                         enum_strings=['idle', 'acquiring'],
                         dtype=ChannelType.ENUM,
                         alarm_group='acq')

    enabled = pvproperty(value='on',
                         enum_strings=['off', 'on'],
                         dtype=ChannelType.ENUM,
                         alarm_group='acq')

    @acquire.putter
    @no_reentry
    async def acquire(self, instance, value):
        if self.enabled.value == 'off':
            raise RuntimeError("Device must be enabled")
        if not instance.ev.is_set():
            await instance.ev.wait()
            return 'idle'

        if value == 'acquiring':
            instance.ev.clear()
            try:
                await instance.write(1)

                await instance.async_lib.library.sleep(
                    self.exposure_time.value)

                await self.reading.write(np.random.rand())

            finally:
                instance.ev.set()

        return 'idle'

    @acquire.startup
    async def acquire(self, instance, async_lib):
        # monkey patch the instance like whoa
        instance.async_lib = async_lib
        instance.ev = async_lib.Event()
        instance.ev.set()

    wait = pvproperty(value=2.0)
    wait_time = pvproperty(value=0)

    @wait.startup
    async def wait(self, instance, async_lib):
        instance.async_lib = async_lib

    @wait.getter
    async def wait(self, instance):
        sleep_time = random.randint(0, 15)
        await self.wait_time.write(sleep_time)
        await instance.async_lib.library.sleep(sleep_time)
        return sleep_time

    fatal = pvproperty(value=0)

    @fatal.putter
    async def fatal(self, val):
        sys.exit(0)


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='trigger_with_pc:',
        desc=dedent(TriggeredIOC.__doc__))
    ioc = TriggeredIOC(**ioc_options)
    run(ioc.pvdb, **run_options)
