import asyncio
import caproto as ca
from caproto.asyncio.client import Context


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
        print(f"Sync subscription has received data: {command.data}")

    async def user_async_callback(pv, command):
        print(f"Subscription has received data: {command.data}")
        called_with.append(command)
        called.set()

    ctx = Context()
    chan1, chan2 = await ctx.get_pvs(pv1, pv2)

    # TODO debug subscriptions when num_iters > 1:
    for _ in range(1):
        async with chan1.subscribe() as sub:
            sub.add_callback(user_async_callback)
            sub.add_callback(user_callback)

            async for value in sub:
                ctx.broadcaster.results.print_debug_information()

                print('* Subscription value from async for:')
                print(value.data)
                break  # TODO: don't leave this commented while committing, ... ok?

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

        print('last heard', chan1.time_since_last_heard())
        await chan2.go_idle()
        await chan1.go_idle()

    assert called
    print('Done')


if __name__ == '__main__':
    ca.config_caproto_logging(level='DEBUG')
    ca.asyncio.utils.run(main(), debug=False)
