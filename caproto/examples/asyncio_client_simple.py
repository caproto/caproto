import asyncio
import caproto as ca
from caproto.asyncio.client import (SharedBroadcaster, Context)


async def main(pv1="simple:A", pv2="simple:B"):
    '''
    Simple example which connects to two PVs on the simple IOC (by default).

    Start the simple IOC like so::

        python -m caproto.asyncio_client_simple

    and then run this example.

    It tests reading, writing, and subscriptions.
    '''

    # Some user function to call when subscriptions receive data.
    called_with = []
    called = asyncio.Event()

    def user_callback(pv, command):
        print("Sync subscription has received data: {}".format(command))

    async def user_async_callback(pv, command):
        print("Subscription has received data: {}".format(command))
        called_with.append(command)
        called.set()

    broadcaster = SharedBroadcaster()
    print('Registering with the repeater...')
    await broadcaster.register()
    print('Registered.')

    ctx = Context(broadcaster)
    chan1, chan2 = await ctx.get_pvs(pv1, pv2)

    async with chan1.subscribe() as sub:
        sub.add_callback(user_async_callback)
        sub.add_callback(user_callback)

        async for value in sub:
            print('* Subscription value from async for:')
            print(value)
            break

        reading = await chan1.read()

        print()
        print('reading:', chan1.channel.name, reading)
        await chan2.read()
        await called.wait()

    print('--> writing the value 5 to', chan1.channel.name)
    await chan1.write((5,), notify=True)
    reading = await chan1.read()

    print()
    print('reading:', chan1.channel.name, reading)

    print('--> writing the value 6 to', chan1.channel.name)
    await chan1.write((6,), notify=True)

    reading = await chan1.read()
    print()
    print('reading:', chan1.channel.name, reading)

    reading = await chan2.read()
    print()
    print('reading:', chan2.channel.name, reading)

    # TODO
    print('last heard', chan1.time_since_last_heard())
    await chan2.go_idle()
    await chan1.go_idle()
    assert called
    print('Done')
    await broadcaster.disconnect()
    print('Broadcaster disconnected')


if __name__ == '__main__':
    ca.config_caproto_logging(level='DEBUG')
    loop = asyncio.get_event_loop()
    asyncio.run(main(), debug=False)
