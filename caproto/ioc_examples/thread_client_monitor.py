#!/usr/bin/env python3
import caproto as ca

import caproto.threading.client
from caproto.server import pvproperty, PVGroup, ioc_arg_parser, run

from textwrap import dedent


class ThreadClientIOC(PVGroup):
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

    @mirrored.startup
    async def mirrored(self, instance, async_lib):
        print('* `mirrored` startup hook called')

        # Create a queue that can be used to bridge the threading client and
        # the async server:
        queue = async_lib.ThreadsafeQueue()

        # Create a threading context and grab our PV:
        self.thread_context = caproto.threading.client.Context()

        def add_to_queue(sub, event_add_response):
            queue.put(('subscription', event_add_response))

        def connection_state_callback(pv, state):
            queue.put(('connection', state))

        pv, = self.thread_context.get_pvs(
            self.pv_to_mirror, timeout=None,
            connection_state_callback=connection_state_callback)

        sub = pv.subscribe(data_type='time')
        sub.add_callback(add_to_queue)

        # Loop and grab items from the queue one at a time
        while True:
            event, info = await queue.async_get()
            if event == 'subscription':
                print('* Threading client pushed a new value in the queue')
                print(f'\tValue={info.data} {info.metadata}')

                # Mirror the value, status, severity, and timestamp:
                await self.mirrored.write(info.data,
                                          timestamp=info.metadata.timestamp,
                                          status=info.metadata.status,
                                          severity=info.metadata.severity)
            elif event == 'connection':
                print(f'* Threading client connection state changed: {info}')
                if info == 'disconnected':
                    # Raise an alarm - our client PV is disconnected.
                    await self.mirrored.write(
                        self.mirrored.value,
                        status=ca.AlarmStatus.LINK,
                        severity=ca.AlarmSeverity.MAJOR_ALARM)


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='mirror:',
        desc=dedent(ThreadClientIOC.__doc__))

    ioc = ThreadClientIOC('simple:A', **ioc_options)
    run(ioc.pvdb, **run_options)
