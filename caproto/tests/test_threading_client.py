# TODO: all of this needs to be tested with the pyepics PVs as well
#   ... on top of the normal ugly suite of pyepics tests

import caproto
import caproto._utils
import caproto.threading.client
import time
import socket
import getpass

from caproto.threading.client import (Context, SharedBroadcaster,
                                      ContextDisconnectedError)
import caproto as ca
import pytest


def test_go_idle(context, ioc):
    pv, = context.get_pvs(ioc.pvs['str'])
    pv.wait_for_connection()
    assert pv.connected
    print(pv.read())

    pv.go_idle()
    # Wait for this to be processed.
    while pv.connected:
        time.sleep(0.1)

    pv.read()
    assert pv.connected


def test_context_disconnect_is_terminal(context, ioc):
    pv, = context.get_pvs(ioc.pvs['str'])
    pv.wait_for_connection()
    assert pv.connected

    pv.read()
    context.disconnect()
    assert not pv.connected

    with pytest.raises(ContextDisconnectedError):
        pv, = context.get_pvs(ioc.pvs['str'])


def test_put_complete(backends, context, ioc):
    pv, = context.get_pvs(ioc.pvs['float'])
    pv.wait_for_connection()
    assert pv.connected

    # start in a known initial state
    pv.write((0.0, ), wait=True)
    pv.read()

    responses = []

    def cb(response):
        responses.append(response)

    # put and wait
    pv.write((0.1, ), wait=True)
    result = pv.read()
    assert result.data[0] == 0.1

    # put and do not wait with callback
    pv.write((0.4, ), wait=False, cb=cb)
    while not responses:
        time.sleep(0.1)
    pv.read().data == 0.4


def test_specified_port(monkeypatch, context, ioc):
    pv, = context.get_pvs(ioc.pvs['float'])
    pv.wait_for_connection()

    circuit = pv.circuit_manager.circuit
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
    new_context = Context(shared_broadcaster, log_level='DEBUG')
    pv1, = new_context.get_pvs(ioc.pvs['float'])
    pv1.wait_for_connection()
    assert pv1.connected
    pv1.read()
    new_context.disconnect()


@pytest.fixture(scope='function')
def shared_broadcaster(request):
    return SharedBroadcaster(log_level='DEBUG')


@pytest.fixture(scope='function')
def context(request, shared_broadcaster):
    context = Context(broadcaster=shared_broadcaster, log_level='DEBUG')

    def cleanup():
        print('*** Cleaning up the context!')
        context.disconnect()

    request.addfinalizer(cleanup)
    return context


def test_server_crash(context, ioc_factory):
    first_ioc = ioc_factory()

    # TODO
    # This exposes a bug where the socket dies on send. To be solved
    # separately.
    if first_ioc.type == 'epics-base':
        raise pytest.skip()

    # The factory function does not return until readiness is confirmed.
    pvs = context.get_pvs(*first_ioc.pvs.values())
    # Wait for everything to connect.
    for pv in pvs:
        pv.wait_for_connection()
    # Kill the IOC!
    first_ioc.process.terminate()
    first_ioc.process.wait()
    # Start the ioc again (it has the same prefix).
    second_ioc = ioc_factory()
    for pv in pvs:
        pv.wait_for_connection()
        assert pv.connected


def test_subscriptions(ioc, context):
    cntx = context

    pv, = cntx.get_pvs(ioc.pvs['float'])
    pv.wait_for_connection()

    monitor_values = []

    def callback(command, **kwargs):
        assert isinstance(command, ca.EventAddResponse)
        monitor_values.append(command.data[0])

    sub = pv.subscribe()
    sub.add_callback(callback)
    pv.write((1, ), wait=True)
    pv.write((2, ), wait=True)
    pv.write((3, ), wait=True)

    for i in range(3):
        if pv.read().data[0] == 3:
            time.sleep(0.2)
            break
        else:
            time.sleep(0.2)

    assert monitor_values[1:] == [1, 2, 3]


def test_client_and_host_name(shared_broadcaster):
    ctx = Context(broadcaster=shared_broadcaster, host_name='foo')
    assert ctx.host_name == 'foo'

    ctx = Context(broadcaster=shared_broadcaster, client_name='bar')
    assert ctx.client_name == 'bar'

    # test defaults
    ctx = Context(broadcaster=shared_broadcaster)
    assert ctx.host_name == socket.gethostname()
    assert ctx.client_name == getpass.getuser()
