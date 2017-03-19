import signal
import os
import time
from multiprocessing import Process


def test_synchronous_client():
    from caproto.examples.synchronous_client import main
    p = Process(target=main)
    p.start()
    time.sleep(2)
    # By now the example should be subscribed and waiting for Ctrl+C.
    os.kill(p.pid, signal.SIGINT)
    p.join()


def test_curio_client():
    from caproto.examples.curio_client import main
    p = Process(target=main)
    p.start()
    p.join()
