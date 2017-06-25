import logging

from caproto.threading.client import (SharedBroadcaster, Context, logger)


def main(pv1="XF:31IDA-OP{Tbl-Ax:X1}Mtr.VAL",
         pv2="XF:31IDA-OP{Tbl-Ax:X2}Mtr.VAL"):
    '''Simple example which connects to two motorsim PVs (by default).

    It tests reading, writing, and subscriptions.
    '''

    shared_broadcaster = SharedBroadcaster()

    # Some user function to call when subscriptions receive data.
    called = []

    def user_callback(command):
        print("Subscription has received data: {}".format(command))
        called.append(True)

    ctx = Context(broadcaster=shared_broadcaster, log_level='DEBUG')
    ctx.register()
    ctx.search(pv1)
    ctx.search(pv2)
    # Send out connection requests without waiting for responses...
    chan1 = ctx.create_channel(pv1)
    chan2 = ctx.create_channel(pv2)
    # Set up a function to call when subscriptions are received.
    chan1.register_user_callback(user_callback)

    reading = chan1.read()
    print('reading:', reading)
    chan1.subscribe()
    chan2.read()
    chan1.unsubscribe(0)
    chan1.write((5,))
    reading = chan1.read()
    assert reading.data == 5
    print('reading:', reading)
    chan1.write((6,))
    reading = chan1.read()
    assert reading.data == 6
    print('reading:', reading)
    chan2.disconnect()
    chan1.disconnect()
    assert called


if __name__ == '__main__':
    logger.setLevel('DEBUG')
    logging.basicConfig()
    main()
