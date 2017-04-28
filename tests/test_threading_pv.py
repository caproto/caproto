import socket
import logging
import time
from multiprocessing import Process

from caproto.threading.client import PVContext
import caproto as ca
import pytest


def setup_module(module):
    global _repeater_process
    from caproto.asyncio.repeater import main
    logging.getLogger('caproto').setLevel(logging.DEBUG)
    logging.basicConfig()

    _repeater_process = Process(target=main)
    _repeater_process.start()

    print('Waiting for the repeater to start up...')
    time.sleep(2)


def teardown_module(module):
    global _repeater_process
    print('teardown_module: killing repeater process')
    _repeater_process.terminate()
    _repeater_process = None


@pytest.fixture(scope='function')
def cntx(request):
    cntx = PVContext()

    def cleanup():
        cntx.disconnect()

    request.addfinalizer(cleanup)

    return cntx


def test_pv_disconnect_reconnect(cntx):
    str_pv = 'Py:ao1.DESC'
    pv = cntx.get_pv(str_pv)
    pv.get()
    pv.disconnect()
    assert not pv.connected
    pv.get()
    assert pv.connected


def test_cntx_disconnect_reconnect(cntx):
    str_pv = 'Py:ao1.DESC'
    pv = cntx.get_pv(str_pv)
    pv.get()
    cntx.disconnect()
    assert not pv.connected
    assert not cntx.registered

    pv = cntx.get_pv(str_pv)
    pv.get()
    assert pv.connected
    assert cntx.registered
