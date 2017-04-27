import socket
import logging
import time
from multiprocessing import Process

from caproto.threading.client import SocketThread, Context
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
def socket_thread_fixture():

    class _DummyTargetObj:
        def __init__(self):
            self.disconnected = False
            self.payloads = []

        def disconnect(self):
            self.disconnected = True

        def next_command(self, bytes_recv, address):
            self.payloads.append(bytes_recv)

    a, b = socket.socketpair()

    d = _DummyTargetObj()

    st = SocketThread(a, d)

    return a, b, d, st


@pytest.fixture(scope='function')
def cntx(request):
    cntx = Context()
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
    cntx.search(str_pv)
    chan = cntx.create_channel(str_pv)
    chan.read()
    assert chan.connected
    assert chan.circuit.connected
    assert cntx.registered
    cntx.disconnect()
    cntx.sock_thread.thread.join()
    assert not chan.connected
    assert not chan.circuit.connected
    assert not cntx.registered

    assert not chan.circuit.sock_thread.thread.is_alive()
    assert not cntx.sock_thread.thread.is_alive()
    with pytest.raises(ca.LocalProtocolError):
        chan.read()

    with pytest.raises(ca.LocalProtocolError):
        cntx.search(str_pv)
