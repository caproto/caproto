import signal
import os
import time
from multiprocessing import Process


def test_synchronous_client():
    from caproto.examples.synchronous_client import main

    pid = os.getpid()

    def sigint(delay):
        time.sleep(delay)
        # By now the example should be subscribed and waiting for Ctrl+C.
        os.kill(pid, signal.SIGINT)

    p = Process(target=sigint, args=(2,))
    p.start()
    main()
    p.join()


def test_curio_client():
    from caproto.examples.curio_client import main
    main()
