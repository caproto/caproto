#!/usr/bin/env python3
from textwrap import dedent

import caproto as ca
from caproto.asyncio.client import Context
from caproto.server import PVGroup, ioc_arg_parser, pvproperty, run


class MirrorClientIOC(PVGroup):
    """
    An IOC which mirrors the value, timestamp, and alarm status of a given PV
    into the `mirrored` pvproperty.

    With the default configuration, this IOC assumes that the PV "simple:A"
    exists on some external IOC.

    The "simple" IOC may be started before or after this IOC.  If the server
    goes down, the client will automatically reconnect when available.

    Scalar PVs
    ----------
    mirrored (float, analog input)
    """

    mirrored = pvproperty(value=0.0, record='ai')

    def __init__(self, pv_to_mirror, *args, **kwargs):
        self.pv_to_mirror = pv_to_mirror
        super().__init__(*args, **kwargs)

    async def __ainit__(self, async_lib):
        print('* `__ainit__` startup hook called')

        # Create an asyncio client context:
        ctx = Context()

        # Loop and grab items from the queue one at a time
        async for event, context, data in ctx.monitor(self.pv_to_mirror):
            if event == 'subscription':
                print('* Client pushed a new value in the queue')
                print(f'\tValue={data.data} {data.metadata}')

                # Mirror the value, status, severity, and timestamp:
                await self.mirrored.write(data.data,
                                          timestamp=data.metadata.timestamp,
                                          status=data.metadata.status,
                                          severity=data.metadata.severity)
            elif event == 'connection':
                print(f'* Client connection state changed: {data}')
                if data == 'disconnected':
                    # Raise an alarm - our client PV is disconnected.
                    await self.mirrored.write(
                        self.mirrored.value,
                        status=ca.AlarmStatus.LINK,
                        severity=ca.AlarmSeverity.MAJOR_ALARM
                    )


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='mirror:',
        desc=dedent(MirrorClientIOC.__doc__),
        supported_async_libs=('asyncio', ),
    )

    ioc = MirrorClientIOC('simple:A', **ioc_options)
    run(ioc.pvdb, startup_hook=ioc.__ainit__, **run_options)
