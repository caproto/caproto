#!/usr/bin/env python3
from textwrap import dedent

import caproto as ca
import caproto.threading.client
from caproto.server import PVGroup, ioc_arg_parser, pvproperty, run

_default_thread_context = None


def get_default_thread_context():
    """Get a shared caproto threading client context."""
    global _default_thread_context
    if _default_thread_context is None:
        _default_thread_context = caproto.threading.client.Context()
    return _default_thread_context


def _monitor_pvs(*pv_names, context, queue, data_type='time'):
    """
    Monitor pv_names in the given threading context, putting events to `queue`.

    Parameters
    ----------
    *pv_names : str
        PV names to monitor.

    context : caproto.threading.client.Context
        The threading context to use.

    queue : ThreadsafeQueue
        Thread-safe queue for the current server async library.

    data_type : {'time', 'control', 'native'}
        The subscription type.

    Returns
    -------
    subscriptions : list
        List of subscription tuples, with each being:
        ``(sub, subscription_token, *callback_references)``
    """

    def add_to_queue(sub, event_add_response):
        queue.put(('subscription', sub, event_add_response))

    def connection_state_callback(pv, state):
        queue.put(('connection', pv, state))

    pvs = context.get_pvs(
        *pv_names, timeout=None,
        connection_state_callback=connection_state_callback
    )

    subscriptions = []
    for pv in pvs:
        sub = pv.subscribe(data_type=data_type)
        token = sub.add_callback(add_to_queue)
        subscriptions.append((sub, token, add_to_queue,
                              connection_state_callback))

    return subscriptions


async def monitor_pvs(*pv_names, async_lib, context=None, data_type='time'):
    """
    Monitor pv_names asynchronously, yielding events as they happen.

    Parameters
    ----------
    *pv_names : str
        PV names to monitor.

    async_lib : caproto.server.AsyncLibraryLayer
        The async library layer shim to get compatible classes from.

    context : caproto.threading.client.Context
        The threading context to use.

    data_type : {'time', 'control', 'native'}
        The subscription type.

    Yields
    -------
    event : {'subscription', 'connection'}
        The event type.

    context : str or Subscription
        For a 'connection' event, this is the PV name.  For a 'subscription'
        event, this is the `Subscription` instance.

    data : str or EventAddResponse
        For a 'subscription' event, the `EventAddResponse` holds the data and
        timestamp.  For a 'connection' event, this is one of ``{'connected',
        'disconnected'}``.
    """

    if context is None:
        context = get_default_thread_context()

    queue = async_lib.ThreadsafeQueue()
    subscriptions = _monitor_pvs(*pv_names, context=context, queue=queue,
                                 data_type=data_type)
    try:
        while True:
            event, context, data = await queue.async_get()
            yield event, context, data
    finally:
        for sub, token, *callbacks in subscriptions:
            sub.remove_callback(token)


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

        # Loop and grab items from the queue one at a time
        async for event, context, data in monitor_pvs(self.pv_to_mirror,
                                                      async_lib=async_lib):
            if event == 'subscription':
                print('* Threading client pushed a new value in the queue')
                print(f'\tValue={data.data} {data.metadata}')

                # Mirror the value, status, severity, and timestamp:
                await self.mirrored.write(data.data,
                                          timestamp=data.metadata.timestamp,
                                          status=data.metadata.status,
                                          severity=data.metadata.severity)
            elif event == 'connection':
                print(f'* Threading client connection state changed: {data}')
                if data == 'disconnected':
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
