import sys

from caproto.threading.client import (Context, SharedBroadcaster)
import caproto as ca
import pytest

from .conftest import default_setup_module as setup_module  # noqa
from .conftest import default_teardown_module as teardown_module  # noqa
from . import conftest
from . import pvnames


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
    cm1 = pv.circuit_manager
    pv.circuit_manager.disconnect()  # simulate connection loss
    pv.wait_for_connection()
    cm2 = pv.circuit_manager
    assert cm1 is not cm2

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
        break

    return

    for i, prefix in enumerate(prefixes):
        ioc = iocs[prefix]
        pvs = ioc['pvs']
        process = ioc['process']
        if i == 0:
            # kill the first IOC
            process.terminate()
            process.wait()
            for pv in pvs:
                assert not pv.connected
        else:
            for pv in pvs:
                assert pv.connected

    prefix = prefixes[0]
    # restart the first IOC
    proc = conftest.run_example_ioc('caproto.ioc_examples.simple',
                                    args=(prefix, ), request=request,
                                    pv_to_check=pvs[0])

    for pv in iocs[prefix]['pvs']:
        pv.wait_for_connection()
