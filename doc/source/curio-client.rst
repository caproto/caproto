.. currentmodule:: caproto.curio.client

*******************
Asynchronous Client
*******************

The :mod:`caproto.curio.client` implements a Channel Access client using the
curio framework for asynchronous programming in Python, making use of Python's
new async/await syntax. Curio is not a required dependeny of caproto; you may
need to install it separately using pip:

.. code-block:: bash

    pip install curio

Here is an example. We begin with a :class:`Context` object, which can be used
to search for and create channels.

Before using you should start a CA repeater process in the background if one is
not already running. You may use the one from epics-base or one provided with
caproto as a CLI.

.. code-block:: bash

    caproto-repeater &

.. code-block:: python

    import curio
    from caproto.curio.client import Context

    async def main():
        # Connect to two motorsim PVs. Test reading, writing, and subscribing.
        pv1 = "XF:31IDA-OP{Tbl-Ax:X1}Mtr.VAL"
        pv2 = "XF:31IDA-OP{Tbl-Ax:X2}Mtr.VAL"

        # Some user function to call when subscriptions receive data.
        called = []

        def user_callback(command):
            print("Subscription has received data.")
            called.append(True)

        ctx = Context()
        await ctx.register()
        await ctx.search(pv1)
        await ctx.search(pv2)

        # Send out connection requests without waiting for responses...
        chan1 = await ctx.create_channel(pv1)
        chan2 = await ctx.create_channel(pv2)

        # Set up a function to call when subscriptions are received.
        chan1.register_user_callback(user_callback)
        # ...and then wait for all the responses.
        await chan1.wait_for_connection()
        await chan2.wait_for_connection()

        # Try reading, writing, subscribing, and unsubscribing.
        reading = await chan1.read()
        print('reading:', reading)
        await chan1.subscribe()
        await chan2.read()
        await chan1.unsubscribe(0)
        await chan1.write((5,))
        reading = await chan1.read()
        print('reading:', reading)
        await chan1.write((6,))
        reading = await chan1.read()
        print('reading:', reading)
        await chan2.disconnect()
        await chan1.disconnect()

        # Verify that our subscription collected some results.
        assert called

    curio.run(main())
