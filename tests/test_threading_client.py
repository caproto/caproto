import sys
import socket
import logging
import time
import threading

from multiprocessing import Process

from caproto.threading.client import (Context, SharedBroadcaster,
                                      _condition_with_timeout)
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


def test_condition_timeout():
    condition = threading.Condition()

    def spinner():
        for j in range(50):
            time.sleep(.01)
            with condition:
                condition.notify_all()

    thread = threading.Thread(target=spinner)

    with pytest.raises(TimeoutError):
        thread.start()
        start_time = time.time()
        _condition_with_timeout(lambda: False,
                                condition,
                                .1)
    end_time = time.time()
    assert .2 > end_time - start_time > .1


def test_condition_timeout_pass():
    condition = threading.Condition()
    ev = threading.Event()

    def spinner():
        for j in range(5):
            time.sleep(.01)
            with condition:
                condition.notify_all()
        ev.set()
        with condition:
            condition.notify_all()

    thread = threading.Thread(target=spinner)

    thread.start()
    start_time = time.time()
    _condition_with_timeout(lambda: ev.is_set(),
                            condition,
                            .1)
    end_time = time.time()
    assert .1 > end_time - start_time > .05
