import logging
import subprocess
import sys

from caproto.threading.client import SharedBroadcaster, Context


def main(pvname1='int', pvname2='str'):
    '''Simple example which connects to two motorsim PVs (by default).

    It tests reading, writing, and subscriptions.
    '''

    shared_broadcaster = SharedBroadcaster()
    ctx = Context(broadcaster=shared_broadcaster)

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
    value1, value2 = [val + 1 for val in reading.data], reading.data

    pv1.write(value1, timeout=5)
    reading = pv1.read()
    print(f'wrote {value1} and read back: {reading.data}')

    pv1.write(value2, timeout=5)
    reading = pv1.read()
    print(f'wrote {value2} and read back: {reading.data}')

    # Clean up the subscription
    sub.clear()

    pv2.go_idle()
    pv1.go_idle()

    print('The subscription callback saw the following data:')
    for command in called:
        print(f'    * {command.data}')


if __name__ == '__main__':
    logging.getLogger('caproto').setLevel('DEBUG')
    p = subprocess.Popen([sys.executable, '-um',
                         'caproto.ioc_examples.type_varieties'])
    try:
        main()
    finally:
        p.kill()
