import sys
import socket
import time
import threading

from caproto.threading.client import (Context, SharedBroadcaster)
import caproto as ca
import pytest


def setup_module(module):
    from conftest import start_repeater
    start_repeater()


def teardown_module(module):
    from conftest import stop_repeater
    stop_repeater()


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
    cntx.register()

    def cleanup():
        cntx.disconnect()

    request.addfinalizer(cleanup)
    return cntx


def test_context_disconnect(cntx):
    str_pv = 'Py:ao1.DESC'

    def bootstrap():
        cntx.search(str_pv)
        chan = cntx.create_channel(str_pv)
        assert chan.connected
        assert chan.circuit.connected
        return chan

    def is_happy(chan, cntx):
        chan.read()
        assert chan.connected
        assert chan.circuit.connected
        assert cntx.broadcaster.registered
        assert cntx.circuits

    chan = bootstrap()
    is_happy(chan, cntx)

    cntx.disconnect()

    sys.stdout.flush()

    assert not chan.connected
    assert not chan.circuit.connected
    assert not cntx.circuits

    with pytest.raises(ca.LocalProtocolError):
        chan.read()

    cntx.register()
    chan = bootstrap()
    is_happy(chan, cntx)
