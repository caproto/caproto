#!/usr/bin/env python3
from textwrap import dedent

import caproto as ca
from caproto.server import PVGroup, ioc_arg_parser, pvproperty, run


class TimestampIOC(PVGroup):
    """
    An IOC that shows how to control writing exact EPICS timestamps, with
    integral seconds and nanoseconds.

    Note that these raw timestamps use the EPICS epoch, and not the unix one.

    Scalar PVs
    ----------
    update (int)
        A trigger to update ``value``.

    value (int)
        This is updated after a put to ``update``.
    """
    update = pvproperty(
        value=0,
        doc='Trigger to update ``value``',
    )
    value = pvproperty(
        value=1,
        doc='Value with custom timestamp, updated after a put to ``update``',
        read_only=True,
    )

    @update.putter
    async def update(self, instance, value):
        # I insist my timestamp is correct! This is a **raw** EPICS timestamp
        # that uses the EPICS epoch and not the unix one.
        timestamp = ca.TimeStamp.now()
        timestamp.nanoSeconds = 2 ** 16 - 1
        await self.value.write(value, timestamp=timestamp)


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='raw:timestamp:',
        desc=dedent(TimestampIOC.__doc__))
    ioc = TimestampIOC(**ioc_options)
    run(ioc.pvdb, **run_options)
