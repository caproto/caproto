import logging
import time
from multiprocessing import Process

from caproto.threading.client import PVContext
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
    cntx = PVContext(log_level='DEBUG')

    def cleanup():
        cntx.disconnect()

    request.addfinalizer(cleanup)

    return cntx


def test_pv_disconnect_reconnect(cntx):
    str_pv = 'Py:ao1.DESC'
    pv = cntx.get_pv(str_pv)
    print(pv.chid.channel.states)
    print(pv.get())
    assert pv.connected
    pv.disconnect()
    assert not pv.connected
    pv.get()
    assert pv.connected
    pv.disconnect()


def test_cntx_disconnect_reconnect(cntx):
    str_pv = 'Py:ao1.DESC'
    pv = cntx.get_pv(str_pv)
    pv.get()
    cntx.disconnect()
    assert not pv.connected

    pv = cntx.get_pv(str_pv)
    pv.get()
    assert pv.connected
    assert cntx.broadcaster.registered

    cntx.disconnect()
    assert not pv.connected
    pv.get()
    pv.disconnect()


def test_put_complete(cntx):
    pv = cntx.get_pv('Py:ao3')
    mutable = []

    # start in a known initial state
    pv.put(0.0, wait=True)
    pv.get()

    def cb(a):
        mutable.append(a)

    # put and wait
    old_value = pv.get()
    result = pv.put(0.1, wait=True)
    assert result == old_value

    # put and wait with callback (not interesting use of callback)
    old_value = pv.get()
    result = pv.put(0.2, wait=True, callback=cb, callback_data=('T2',))
    assert result == old_value
    assert 'T2' in mutable

    # put and do not wait
    ret_val = pv.put(0.3, wait=False)
    assert ret_val is None
    result = pv.get()
    print('last_reading', pv.chid.last_reading)
    assert result == 0.3

    # put and do not wait with callback
    ret_val = pv.put(0.4, wait=False, callback=cb, callback_data=('T4',))
    assert ret_val is None
    result = pv.get()
    assert result == 0.4
    # sleep time give callback time to process
    time.sleep(0.1)
    print('last_reading', pv.chid.last_reading)
    assert 'T4' in mutable
