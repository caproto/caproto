import socket

from caproto.threading.client import SocketThread
import pytest


@pytest.fixture
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
