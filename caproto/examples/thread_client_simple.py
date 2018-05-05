import logging
import subprocess
import sys

from caproto.threading.client import (SharedBroadcaster, Context, logger)


def main(pvname1='pi', pvname2='str',
         log_level='DEBUG'):
    '''Simple example which connects to two motorsim PVs (by default).

    It tests reading, writing, and subscriptions.
    '''

    shared_broadcaster = SharedBroadcaster()
    ctx = Context(broadcaster=shared_broadcaster, log_level=log_level)

    # Some user function to call when subscriptions receive data.
    called = []

    def user_callback(command):
        print("Subscription has received data: {}".format(command))
        called.append(command)

    pv1, pv2 = ctx.get_pvs(pvname1, pvname2)
    pv1.wait_for_connection()
    pv2.wait_for_connection()

    # Read and subscribe to pv1
    reading = pv1.read()
    print(f'{pv1} read back: {reading}')
    sub = pv1.subscribe()
    sub.add_callback(user_callback)
    print(f'{pv2} read back: {pv2.read()}')

    # Test writing a couple values:
    value1, value2 = reading.data + 1, reading.data

    pv1.write((value1, ), timeout=5)
    reading = pv1.read()
    assert reading.data == value1
    print(f'wrote {value1} and read back: {reading}')

    pv1.write((value2, ), timeout=5)
    reading = pv1.read()
    assert reading.data == value2
    print(f'wrote {value2} and read back: {reading}')

    # Clean up the subscription
    sub.clear()

    pv2.go_idle()
    pv1.go_idle()
    assert called

    print('The subscription callback saw the following data:')
    for command in called:
        print(f'    * {command.data}')


if __name__ == '__main__':
    logger.setLevel('DEBUG')
    logging.basicConfig()
    p = subprocess.Popen([sys.executable, '-m',
                         'caproto.ioc_examples.type_varieties'])
    try:
        main()
    finally:
        p.kill()
