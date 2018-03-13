import sys
import socket
import time
import threading

from caproto.threading.client import (Context, SharedBroadcaster)
import caproto as ca
import pytest

from .conftest import default_setup_module as setup_module  # noqa
from .conftest import default_teardown_module as teardown_module  # noqa


@pytest.fixture(scope='module')
def shared_broadcaster(request):
    broadcaster = SharedBroadcaster()

    def cleanup():
        broadcaster.disconnect()

    request.addfinalizer(cleanup)
    return broadcaster


@pytest.fixture(scope='function')
def cntx(request, shared_broadcaster):
    cntx = Context(broadcaster=shared_broadcaster, log_level='DEBUG')

    def cleanup():
        cntx.disconnect()

    request.addfinalizer(cleanup)
    return cntx


def test_context_disconnect(cntx):
    str_pv = 'Py:ao1.DESC'

    def bootstrap():
        pv, = cntx.get_pvs(str_pv)
        pv.wait_for_connection()
        assert pv.connected
        assert pv.circuit_manager.connected
        return pv

    def is_happy(pv, cntx):
        pv.read()
        assert pv.connected
        assert pv.circuit_manager.connected
        # assert cntx.circuits

    pv = bootstrap()
    is_happy(pv, cntx)

    cntx.disconnect()

    sys.stdout.flush()

    assert not pv.connected
    assert not pv.circuit_manager

    with pytest.raises(ca.LocalProtocolError):
        pv.read()

    chan = bootstrap()
    is_happy(chan, cntx)
