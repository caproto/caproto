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
    # The factory function does not return until readiness is confirmed.

    # TODO
    # This exposes a bug where the socket dies on send. To be solved
    # separately.
    if first_ioc.type == 'epics-base':
        raise pytest.skip()

    pvs = context.get_pvs(*first_ioc.pvs.values())
    # Set up a subscription so that we can check that it re-subscribes later.
    some_pv, *_ = pvs
    assert not some_pv.subscriptions
    sub = some_pv.subscribe()
    assert some_pv.subscriptions

    # Add a user callback so that the subscription takes effect.
    collector = []

    def collect(item):
        collector.append(item)
    sub.add_callback(collect)

    # Wait for everything to connect.
    for pv in pvs:
        pv.wait_for_connection()
    # Wait to confirm that the subscription produced a response.
    while not collector:
        time.sleep(0.05)
    # Kill the IOC!
    first_ioc.process.terminate()
    first_ioc.process.wait()

    collector.clear()

    # Start the ioc again (it has the same prefix).
    second_ioc = ioc_factory()
    for pv in pvs:
        pv.wait_for_connection()
        assert pv.connected
    # Wait to confirm that the subscription produced a new response.
    while not collector:
        time.sleep(0.05)

    # Clean up.
    second_ioc.process.terminate()
    second_ioc.process.wait()


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
    sub.unsubscribe()
    time.sleep(0.2)  # Wait for that to process...
    pv.write((4, ), wait=True)  # This update should not be received by us.

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


def test_many_priorities_same_name(ioc, context):
    pv_name, *_others = ioc.pvs.values()
    pvs = {}
    for priority in range(0, 10, 9):
        pvs[priority], = context.get_pvs(pv_name, priority=priority)
    for pv in pvs.values():
        pv.wait_for_connection()


def test_two_iocs_one_pv(ioc_factory, context):
    # If two IOCs answer a search requestion, the Channel Access spec says we
    # should establish the VirtualCircuit with whoever answers first and ignore
    # the second one.
    first_ioc = ioc_factory()
    second_ioc = ioc_factory()
    assert first_ioc.pvs == second_ioc.pvs
    pv_name, *_others = first_ioc.pvs.values()
    pv, = context.get_pvs(pv_name)
    pv.wait_for_connection()
    time.sleep(0.2)  # By now both IOC will have answered.
    # Exercise it a bit as a smoke test of sorts.
    pv.read()
    pv.write((3,))
    first_ioc.process.terminate()
    second_ioc.process.terminate()
    first_ioc.process.wait()
    second_ioc.process.wait()
