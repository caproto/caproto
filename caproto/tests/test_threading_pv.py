# TODO: all of this needs to be tested with the pyepics PVs as well
#   ... on top of the normal ugly suite of pyepics tests

import caproto
import caproto._utils
import caproto.threading.client
import sys
import time

from caproto.threading.client import (Context, SharedBroadcaster, PV, logger)
import caproto as ca
from contextlib import contextmanager
import pytest

from . import pvnames
from .conftest import default_setup_module # noqa
from .conftest import default_teardown_module as teardown_module  # noqa
from . import conftest


def setup_module(module):
    default_setup_module(module)
    logger.setLevel('DEBUG')


@contextmanager
def no_simulator_updates(context):
    '''Context manager which pauses and resumes simulator PV updating'''
    pause_pv, = context.get_pvs(pvnames.pause_pv)
    pause_pv.wait_for_connection()
    try:
        pause_pv.write((1, ), wait=True)
        yield
    finally:
        pause_pv.write((0, ), wait=True)


def test_pv_disconnect_reconnect(context):
    str_pv = 'sim:mtr1.DESC'
    pv, = context.get_pvs(str_pv)
    pv.wait_for_connection()
    assert pv.connected
    print(pv.read())

    pv.disconnect()
    assert not pv.connected

    pv.reconnect()
    assert pv.connected
    pv.read()
    pv.disconnect()
    assert not pv.connected


def test_context_disconnect_reconnect(context):
    str_pv = 'sim:mtr1.DESC'
    pv, = context.get_pvs(str_pv)
    pv.wait_for_connection()
    assert pv.connected

    pv.read()
    context.disconnect()
    assert not pv.connected

    pv, = context.get_pvs(str_pv)
    pv.wait_for_connection()
    assert pv.connected

    pv.read()

    context.disconnect()
    assert not pv.connected

    context.reconnect((pv.name, ))

    pv.wait_for_connection()
    assert pv.connected

    pv.read()
    pv.disconnect()

    assert not pv.connected


@pytest.mark.skipif(conftest.environment_epics_version() in [(3, 16), (7, 0)],
                    reason='pyepics simulator segfaults on 3.16/7.0 (TODO)')
def test_put_complete(context):
    pv, = context.get_pvs('Py:ao3')
    pv.wait_for_connection()
    assert pv.connected
    mutable = []

    with no_simulator_updates(context):
        # start in a known initial state
        pv.write((0.0, ), wait=True)
        pv.read()

        def cb(a):
            mutable.append(a)

        # put and wait
        pv.write((0.1, ), wait=True)
        result = pv.read()
        assert result.data[0] == 0.1

        # put and do not wait with callback
        pv.write((0.4, ), wait=False, cb=cb)
        result = pv.read()
        assert result.data[0] == 0.4
        # sleep time give callback time to process
        time.sleep(0.1)
        print('last_reading', pv.last_reading)
        assert len(mutable) == 1


def test_specified_port(monkeypatch, context):
    pv, = context.get_pvs('sim:mtr1')
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
    pv1, = new_context.get_pvs('sim:mtr1')
    pv1.wait_for_connection()
    assert pv1.connected
    pv1.read()
    new_context.disconnect()


@pytest.fixture(scope='function')
def shared_broadcaster(request):
    broadcaster = SharedBroadcaster(log_level='DEBUG')

    def cleanup():
        print('*** Broadcaster disconnecting!')
        broadcaster.disconnect()

    request.addfinalizer(cleanup)
    return broadcaster


@pytest.fixture(scope='function')
def context(request, shared_broadcaster):
    context = Context(broadcaster=shared_broadcaster, log_level='DEBUG')

    def cleanup():
        print('*** Cleaning up the context!')
        context.disconnect()

    request.addfinalizer(cleanup)
    return context


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

    with pytest.raises(ca.threading.client.DisconnectedError):
        pv.read()

    chan = bootstrap()
    is_happy(chan, context)


def test_user_disconnection(context):
    pv, = context.get_pvs(pvnames.double_pv)
    pv.wait_for_connection()

    # simulate connection loss (at the circuit-level, of course)
    pv.circuit_manager.disconnect()

    # TODO: hmm... this is not good
    pv.reconnect()
    # as users, we should just be able to call:
    # pv.wait_for_connection()

    assert pv.connected
    assert pv.circuit_manager.connected

    pv.reconnect()

    sub = pv.subscribe()
    sub.add_callback(print)
    pv.disconnect()
    assert not pv.connected
    pv.reconnect()
    assert pv.connected


def test_server_crash(context, prefix, request):
    from caproto.ioc_examples import simple

    prefixes = [prefix + f'{i}:'
                for i in [0, 1, 2]]

    iocs = {}
    for prefix in prefixes:
        print(f'\n\n* Starting up IOC with prefix: {prefix}')
        pv_names = list(simple.SimpleIOC(prefix=prefix).pvdb.keys())
        print('PV names:', pv_names)
        pvs = context.get_pvs(*pv_names)
        proc = conftest.run_example_ioc('caproto.ioc_examples.simple',
                                        args=(prefix, ), request=request,
                                        pv_to_check=pv_names[0])
        iocs[prefix] = dict(
            process=proc,
            pv_names=pv_names,
            pvs=pvs,
        )

        print('\n\nConnecting PVs:', pvs)
        assert proc.returncode is None, 'IOC exited unexpectedly'
        [pv.wait_for_connection(timeout=5.0) for pv in pvs]
        print(f'\n\n* {prefix} IOC started up, PVs connected')

    print('********************')
    print('* Killing the first IOC')
    print('********************')

    for i, prefix in enumerate(prefixes):
        ioc = iocs[prefix]
        pvs = ioc['pvs']
        process = ioc['process']
        if i == 0:
            # kill the first IOC
            process.terminate()
            process.wait()
            time.sleep(2.0)
            for pv in pvs:
                print(pv.circuit_manager)
                assert not pv.circuit_manager
                assert not pv.connected
        else:
            for pv in pvs:
                assert pv.connected

    prefix = prefixes[0]

    print('********************')
    print('* Restarting the IOC')
    print('********************')

    ioc = iocs[prefix]
    proc = conftest.run_example_ioc('caproto.ioc_examples.simple',
                                    args=(prefix, ), request=request,
                                    pv_to_check=ioc['pv_names'][0]
                                    )
    time.sleep(0.5)

    for pv in ioc['pvs']:
        pv.reconnect()
        # TODO: should just be pv.wait_for_connection()
        assert pv.connected
