import logging

import curio

import caproto as ca
from .epics_test_utils import run_caget


REPEATER_PORT = 5065


def test_sync_repeater(ioc):
    logging.getLogger('caproto').setLevel(logging.DEBUG)
    logging.basicConfig()

    async def check_repeater():
        for pv in (ioc.pvs['float'], ioc.pvs['str']):
            data = await run_caget('curio', pv)
            print(data)

        udp_sock = ca.bcast_socket()
        for i in range(3):
            print('Sending repeater register request ({})'.format(i + 1))
            udp_sock.sendto(bytes(ca.RepeaterRegisterRequest('0.0.0.0')),
                            ('127.0.0.1', REPEATER_PORT))

        await curio.sleep(1)

    with curio.Kernel() as kernel:
        kernel.run(check_repeater)
