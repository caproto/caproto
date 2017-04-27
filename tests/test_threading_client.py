import socket
import threading
from caproto.threading.client import SocketThread


def test_socket_close():
    a, b = socket.socketpair()

    class Dummy:
        def __init__(self, ev):
            self.disconnected = False
            self.payload = None
            self.ev = ev

        def disconnect(self):
            self.disconnected = True

        def next_command(self, bytes_recv, address):
            self.payload = bytes_recv

    d = Dummy(threading.Event())

    st = SocketThread(a, d)
    b.send(b'aardvark')
    b.close()

    st.thread.join()

    assert d.payload == b'aardvark'
    assert d.disconnected
    assert not st.thread.is_alive()
