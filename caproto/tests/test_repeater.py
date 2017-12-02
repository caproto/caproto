import logging
import time
import threading
import asyncio

import curio

import caproto as ca
from .epics_test_utils import run_caget


REPEATER_PORT = 5065


def test_repeater():
    from caproto.asyncio.repeater import main
    logging.getLogger('caproto').setLevel(logging.DEBUG)
    logging.basicConfig()

    loop = asyncio.get_event_loop()

    def run_repeater():
        asyncio.set_event_loop(loop)
        main()

    thread_repeater = threading.Thread(target=run_repeater)
    thread_repeater.start()
    threads = [thread_repeater]

    try:
        print('Waiting for the repeater to start up...')
        time.sleep(2)

        async def check_repeater():
            for pv in ("XF:31IDA-OP{Tbl-Ax:X1}Mtr.VAL",
                       "XF:31IDA-OP{Tbl-Ax:X2}Mtr.VAL",
                       ):
                data = await run_caget(pv)
                print(data)

            udp_sock = ca.bcast_socket()
            for i in range(3):
                print('Sending repeater register request ({})'.format(i + 1))
                udp_sock.sendto(bytes(ca.RepeaterRegisterRequest('0.0.0.0')),
                                ('127.0.0.1', REPEATER_PORT))

            await curio.sleep(1)

        with curio.Kernel() as kernel:
            kernel.run(check_repeater)

    finally:
        print('Stopping the event loop')
        loop.call_soon_threadsafe(loop.stop)

        for th in threads:
            print('Joining the thread')
            th.join()

        print('Closing the event loop')
        loop.close()

        print('Setting a new event loop')
        # new event loop for other tests
        asyncio.set_event_loop(asyncio.new_event_loop())
        print('Done')
