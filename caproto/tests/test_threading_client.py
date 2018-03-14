import sys

from caproto.threading.client import (Context, SharedBroadcaster)
import caproto as ca
import pytest

from .conftest import default_setup_module as setup_module  # noqa
from .conftest import default_teardown_module as teardown_module  # noqa
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


def test_user_disconnection():
    ctx = Context(SharedBroadcaster())
    pv, = ctx.get_pvs(pvnames.double_pv)
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
