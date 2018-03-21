import caproto
import caproto._utils
import caproto.threading.client
import sys
import time

from caproto.threading.client import Context, SharedBroadcaster
from caproto.threading.pyepics_compat import PVContext
import caproto as ca
from contextlib import contextmanager
import pytest

from . import pvnames
from .conftest import default_setup_module as setup_module  # noqa
from .conftest import default_teardown_module as teardown_module  # noqa
from . import conftest


@pytest.fixture(scope='function')
def cntx(request):
    shared_broadcaster = SharedBroadcaster()
    cntx = PVContext(shared_broadcaster, log_level='DEBUG')

    def cleanup():
        cntx.disconnect()

    request.addfinalizer(cleanup)

    return cntx


@contextmanager
def no_simulator_updates(cntx):
    '''Context manager which pauses and resumes simulator PV updating'''
    pause_pv = cntx.get_pv(pvnames.pause_pv)
    try:
        pause_pv.put(1, wait=True)
        yield
    finally:
        pause_pv.put(0, wait=True)


def test_pv_disconnect_reconnect(cntx):
    str_pv = 'Py:ao1.DESC'
    pv = cntx.get_pv(str_pv)
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

    with no_simulator_updates(cntx):
        # start in a known initial state
        pv.put(0.0, wait=True)
        pv.get()

        def cb(a):
            mutable.append(a)

        # put and wait
        pv.put(0.1, wait=True)
        result = pv.get()
        assert result == 0.1

        # put and do not wait with callback
        pv.put(0.4, wait=False, callback=cb, callback_data=('T4',))
        result = pv.get()
        assert result == 0.4
        # sleep time give callback time to process
        time.sleep(0.1)
        print('last_reading', pv._caproto_pv.last_reading)
        assert 'T4' in mutable


def test_specified_port(monkeypatch, cntx):
    pv = cntx.get_pv('Py:ao3')
    pv.wait_for_connection()
    circuit = pv._caproto_pv.circuit_manager.circuit
    address_list = list(caproto.get_address_list())
    address_list.append('{}:{}'.format(circuit.host, circuit.port))

    def get_address_list():
        return address_list

    for module in (caproto._utils, caproto, caproto.threading.client):
        if hasattr(module, 'get_address_list'):
            print('patching', module)
            monkeypatch.setattr(module, 'get_address_list', get_address_list)

    print()
    print('- address list is now:', address_list)
    shared_broadcaster = SharedBroadcaster()
    new_cntx = PVContext(shared_broadcaster, log_level='DEBUG')
    pv1 = new_cntx.get_pv('Py:ao1')
    pv1.get()
    assert pv1.connected
    new_cntx.disconnect()


@pytest.fixture(scope='module')
def shared_broadcaster(request):
    broadcaster = SharedBroadcaster()

    def cleanup():
        broadcaster.disconnect()

    request.addfinalizer(cleanup)
    return broadcaster


@pytest.fixture(scope='function')
def context(request, shared_broadcaster):
    cntx = Context(broadcaster=shared_broadcaster, log_level='DEBUG')

    def cleanup():
        print('Cleaning up the context')
        cntx.disconnect()

    request.addfinalizer(cleanup)
    return cntx


def test_context_disconnect(context):
    str_pv = f'{pvnames.double_pv}.DESC'

    def bootstrap():
        pv, = context.get_pvs(str_pv)
        pv.wait_for_connection()
        assert pv.connected
        assert pv.circuit_manager.connected
        return pv

    def is_happy(pv, context):
        pv.read()
        assert pv.connected
        assert pv.circuit_manager.connected
        # assert context.circuits

    pv = bootstrap()
    is_happy(pv, context)

    context.disconnect()

    sys.stdout.flush()

    assert not pv.connected
    assert not pv.circuit_manager

    with pytest.raises(ca.threading.client.DisconnectedError):
        pv.read()

    chan = bootstrap()
    is_happy(chan, context)


def test_user_disconnection(context):
    pv, = context.get_pvs(pvnames.double_pv)
    pv.wait_for_connection()

    # simulate connection loss (at the circuit-level, of course)
    pv.circuit_manager.disconnect()
    pv.wait_for_connection()

    sub = pv.subscribe()
    sub.add_callback(print)
    pv.disconnect()
    assert not pv.connected
    pv.reconnect()
    assert pv.connected


def test_server_crash(context, prefix, request):
    from caproto.ioc_examples import simple

    prefixes = [prefix + f'{i}:'
                for i in [0, 1, 2]]

    iocs = {}
    for prefix in prefixes:
        pv_names = list(simple.SimpleIOC(prefix=prefix).pvdb.keys())
        print(pv_names)
        pvs = context.get_pvs(*pv_names)
        proc = conftest.run_example_ioc('caproto.ioc_examples.simple',
                                        args=(prefix, ), request=request,
                                        pv_to_check=pv_names[0])
        iocs[prefix] = dict(
            process=proc,
            pv_names=pv_names,
            pvs=pvs,
        )

        [pv.wait_for_connection() for pv in pvs]

    for i, prefix in enumerate(prefixes):
        ioc = iocs[prefix]
        pvs = ioc['pvs']
        process = ioc['process']
        if i == 0:
            # kill the first IOC
            process.terminate()
            process.wait()
            time.sleep(0.5)
            for pv in pvs:
                # assert not pv.circuit_manager.connected
                assert not pv.connected
        else:
            for pv in pvs:
                assert pv.connected

    prefix = prefixes[0]
    # restart the first IOC
    ioc = iocs[prefix]
    proc = conftest.run_example_ioc('caproto.ioc_examples.simple',
                                    args=(prefix, ), request=request,
                                    pv_to_check=ioc['pv_names'][0]
                                    )

    for pv in ioc['pvs']:
        pv.wait_for_connection()
