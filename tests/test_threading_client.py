import sys
import socket
import logging

from caproto.threading.client import (SocketThread, Context, SharedBroadcaster)
import caproto as ca
import pytest


def setup_module(module):
    from conftest import start_repeater
    start_repeater()


def teardown_module(module):
    from conftest import stop_repeater
    stop_repeater()


@pytest.fixture(scope='function')
def socket_thread_fixture():

    class _DummyTargetObj:
        def __init__(self):
            self.disconnected = False
            self.payloads = []

        def disconnect(self):
            self.disconnected = True

        def received(self, bytes_recv, address):
            if len(bytes_recv):
                self.payloads.append(bytes_recv)
            return 0

    a, b = socket.socketpair()

    d = _DummyTargetObj()

    st = SocketThread(a, d)

    return a, b, d, st


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


def test_socket_server_close(socket_thread_fixture):
    a, b, d, st = socket_thread_fixture
    b.send(b'aardvark')
    b.close()

    st.thread.join()

    assert d.payloads[0] == b'aardvark'
    assert len(d.payloads) == 1
    assert d.disconnected
    assert not st.thread.is_alive()


def test_socket_poison(socket_thread_fixture):
    a, b, d, st = socket_thread_fixture

    st.poison_ev.set()
    st.thread.join()

    assert not st.thread.is_alive()


def test_socket_client_close(socket_thread_fixture):
    a, b, d, st = socket_thread_fixture

    a.close()
    st.thread.join()

    assert not st.thread.is_alive()


def test_socket_thread_obj_die():

    class _DummyTargetObj:
        def disconnect(self):
            ...

        def received(self, bytes_recv, address):
            ...

    # can not use the fixture here, it seems to keep a ref to
    # the object
    a, b = socket.socketpair()
    # do not even keep a local, pytest seems to grab it
    st = SocketThread(a, _DummyTargetObj())
    b.send(b'abc')
    st.thread.join()

    assert not st.thread.is_alive()


def test_channel_kill_client_socket(cntx):
    str_pv = 'Py:ao1.DESC'
    cntx.search(str_pv)
    chan = cntx.create_channel(str_pv)
    chan.read()
    assert chan.connected
    assert chan.circuit.connected
    chan.circuit.socket.close()
    chan.circuit.sock_thread.thread.join()
    assert not chan.connected
    assert not chan.circuit.connected
    with pytest.raises(ca.LocalProtocolError):
        chan.read()


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

    st = chan.circuit.sock_thread.thread
    ct = chan.circuit.command_thread

    cntx.disconnect()
    print('joining sock thread', end='...')
    sys.stdout.flush()
    st.join()
    print('joined')

    print('joining command thread', end='...')
    sys.stdout.flush()
    ct.join()
    print('joined')

    assert not chan.connected
    assert not chan.circuit.connected
    assert not cntx.circuits
    assert not ct.is_alive()
    assert not st.is_alive()

    with pytest.raises(ca.LocalProtocolError):
        chan.read()

    cntx.register()
    chan = bootstrap()
    is_happy(chan, cntx)
