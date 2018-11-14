# TODO: all of this needs to be tested with the pyepics PVs as well
#   ... on top of the normal ugly suite of pyepics tests

import collections
import functools
import caproto
import caproto._utils
import caproto.threading.client
import time
import socket
import getpass
import threading

from caproto.threading.client import (Context, SharedBroadcaster, Batch,
                                      ContextDisconnectedError)
from caproto import ChannelType
import caproto as ca
import pytest

from .conftest import default_setup_module as setup_module  # noqa
from .conftest import default_teardown_module as teardown_module  # noqa


def test_go_idle(context, ioc):
    pv, = context.get_pvs(ioc.pvs['str'])
    pv.wait_for_connection(timeout=10)
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
    pv.wait_for_connection(timeout=10)
    assert pv.connected

    pv.read()
    context.disconnect()
    assert not pv.connected

    with pytest.raises(ContextDisconnectedError):
        pv, = context.get_pvs(ioc.pvs['str'])


def test_put_complete(backends, context, ioc):
    pv, = context.get_pvs(ioc.pvs['int'])
    pv.wait_for_connection(timeout=10)
    assert pv.connected

    # start in a known initial state
    pv.write((0, ), wait=True)
    pv.read()

    responses = []

    def cb(response):
        responses.append(response)

    with pytest.raises(ValueError):
        pv.write((1, ), notify=False, wait=True)

    with pytest.raises(ValueError):
        pv.write((1, ), notify=False, callback=cb)

    with pytest.raises(ValueError):
        pv.write((1, ), notify=False, wait=True, callback=cb)

    # put and wait
    pv.write((1, ), wait=True)
    result = pv.read()
    assert result.data[0] == 1

    # put and do not wait with callback
    pv.write((4, ), wait=False, callback=cb)
    while not responses:
        time.sleep(0.1)
    pv.read().data == 4


def test_specified_port(monkeypatch, context, ioc):
    pv, = context.get_pvs(ioc.pvs['float'])
    pv.wait_for_connection(timeout=10)

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
    new_context = Context(shared_broadcaster)
    pv1, = new_context.get_pvs(ioc.pvs['float'])
    pv1.wait_for_connection()
    assert pv1.connected
    pv1.read()
    new_context.disconnect()


@pytest.fixture(scope='function')
def shared_broadcaster(request):
    sb = SharedBroadcaster()

    def cleanup():
        sb.disconnect()
        assert not sb._command_thread.is_alive()
        assert not sb.selector.thread.is_alive()
        assert not sb._retry_unanswered_searches_thread.is_alive()

    request.addfinalizer(cleanup)
    return sb


@pytest.fixture(scope='function')
def context(request, shared_broadcaster):
    context = Context(broadcaster=shared_broadcaster)
    sb = shared_broadcaster

    def cleanup():
        print('*** Cleaning up the context!')
        context.disconnect()
        assert not context._process_search_results_thread.is_alive()
        assert not context._activate_subscriptions_thread.is_alive()
        assert not context.selector.thread.is_alive()
        sb.disconnect()
        assert not sb._command_thread.is_alive()
        assert not sb.selector.thread.is_alive()
        assert not sb._retry_unanswered_searches_thread.is_alive()

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
        pv.wait_for_connection(timeout=10)
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
        pv.wait_for_connection(timeout=10)
        assert pv.connected
    # Wait to confirm that the subscription produced a new response.
    while not collector:
        time.sleep(0.05)

    # Clean up.
    second_ioc.process.terminate()
    second_ioc.process.wait()


def test_subscriptions(ioc, context):
    cntx = context

    pv, = cntx.get_pvs(ioc.pvs['int'])
    pv.wait_for_connection(timeout=10)

    monitor_values = []

    def callback(command, **kwargs):
        assert isinstance(command, ca.EventAddResponse)
        monitor_values.append(command.data[0])

    sub = pv.subscribe()
    sub.add_callback(callback)
    time.sleep(0.2)  # Wait for EventAddRequest to be sent and processed.
    pv.write((1, ), wait=True)
    pv.write((2, ), wait=True)
    pv.write((3, ), wait=True)
    time.sleep(0.2)  # Wait for the last update to be processed.
    sub.clear()
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
        pv.wait_for_connection(timeout=10)


def test_two_iocs_one_pv(ioc_factory, context):
    # If two IOCs answer a search requestion, the Channel Access spec says we
    # should establish the VirtualCircuit with whoever answers first and ignore
    # the second one.
    first_ioc = ioc_factory()
    second_ioc = ioc_factory()
    assert first_ioc.pvs == second_ioc.pvs
    pv_name, *_others = first_ioc.pvs.values()
    pv, = context.get_pvs(pv_name)
    pv.wait_for_connection(timeout=10)
    time.sleep(0.2)  # By now both IOC will have answered.
    # Exercise it a bit as a smoke test of sorts.
    pv.read()
    pv.write((3,))
    first_ioc.process.terminate()
    second_ioc.process.terminate()
    first_ioc.process.wait()
    second_ioc.process.wait()


def test_multiple_subscriptions_one_server(ioc, context):
    pvs = context.get_pvs(*ioc.pvs.values())
    for pv in pvs:
        pv.wait_for_connection(timeout=10)
    collector = collections.defaultdict(list)

    def collect(sub, response):
        collector[sub].append(response)

    subs = [pv.subscribe() for pv in pvs]
    cbs = {sub: functools.partial(collect, sub) for sub in subs}
    for sub, cb in cbs.items():
        sub.add_callback(cb)
    time.sleep(0.2)
    for sub, responses in collector.items():
        assert len(responses) == 1
    assert len(pv.circuit_manager.subscriptions) == len(pvs) > 1


def test_subscription_objects_are_reused(ioc, context):
    pv, = context.get_pvs(ioc.pvs['int'])

    pv.wait_for_connection(timeout=10)
    sub = pv.subscribe(data_type=0)
    sub_redundant = pv.subscribe(data_type=0)  # should return `sub` again
    sub_different = pv.subscribe(data_type=1)  # different args -- new sub

    assert sub is sub_redundant
    assert sub is not sub_different

    # Attach a callback so that these subs are activated and enter the
    # Context's cache.

    def f(item):
        ...

    sub.add_callback(f)
    sub_redundant.add_callback(f)
    sub_different.add_callback(f)
    time.sleep(0.2)  # Wait for EventAddRequest to be sent and processed.
    actual_cached_subs = set(pv.circuit_manager.subscriptions.values())
    assert actual_cached_subs == set([sub, sub_different])


def test_unsubscribe_all(ioc, context):
    pv, = context.get_pvs(ioc.pvs['int'])
    pv.wait_for_connection(timeout=10)
    sub0 = pv.subscribe(data_type=0)
    sub1 = pv.subscribe(data_type=1)

    collector = []

    def f(response):
        collector.append(response)

    sub0.add_callback(f)
    sub1.add_callback(f)
    time.sleep(0.2)  # Wait for EventAddRequest to be sent and processed.

    pv.write((123,))
    pv.write((456,))
    time.sleep(0.2)  # Wait for the updates to process.
    assert len(collector) == 6
    pv.unsubscribe_all()
    # Unsubscribing is synchronous -- no need to sleep here.
    collector.clear()
    # These should be ignored:
    pv.write((123,))
    pv.write((456,))
    assert len(collector) == 0
    assert not sub0.callbacks
    assert not sub1.callbacks


def test_timeout(ioc, context):
    pv, = context.get_pvs(ioc.pvs['int'])
    pv.wait_for_connection(timeout=10)

    # Check that timeout=None is allowed.
    pv.write((1, ), timeout=None)

    responses = []

    def cb(response):
        responses.append(response)

    # This may or may not raise a TimeoutError depending on who wins the race.
    # The important thing is that the callback should _never_ be processed.
    try:
        # TODO add custom monotonic_time function in caproto._utils
        pv.write((2, ), timeout=-1, callback=cb)
    except TimeoutError:
        pass
    # Wait and make sure that the callback is not called.
    time.sleep(0.2)
    assert not responses


@pytest.fixture(params=[1, 4, 16])
def thread_count(request):
    return request.param


@pytest.fixture(params=[f'iter{i}' for i in range(1, 3)])
def multi_iterations(request):
    return request.param


def _multithreaded_exec(test_func, thread_count, *, start_timeout=10,
                        end_timeout=20):
    threads = {}
    return_values = {i: None for i in range(thread_count)}
    start_barrier = threading.Barrier(parties=thread_count + 1)
    end_barrier = threading.Barrier(parties=thread_count + 1)

    def thread_wrapper(thread_id):
        try:
            print(f'* thread {thread_id} entered *')
            start_barrier.wait(timeout=start_timeout)

            try:
                return_values[thread_id] = test_func(thread_id)
            except Exception as ex:
                print(f'* thread {thread_id} failed: {ex.__class__.__name__} {ex}')
                return_values[thread_id] = ex

            end_barrier.wait(timeout=end_timeout)
            print(f'* thread {thread_id} exiting *')
        except threading.BrokenBarrierError as ex:
            return_values[thread_id] = ex

    for i in range(thread_count):
        threads[i] = threading.Thread(target=thread_wrapper,
                                      args=(i, ),
                                      daemon=True)
        threads[i].start()

    try:
        # Start all the threads at the same time
        start_barrier.wait(timeout=start_timeout)
    except threading.BrokenBarrierError:
        raise RuntimeError('Start barrier synchronization failed')

    try:
        # Wait until all threads have completed
        end_barrier.wait(timeout=end_timeout)
    except threading.BrokenBarrierError:
        raise RuntimeError('End barrier synchronization failed')

    ex = None
    for thread_id in range(thread_count):
        threads[thread_id].join(timeout=0.1)
        ret_val = return_values[thread_id]
        print(f'Result {thread_id} {ret_val}')
        if isinstance(ret_val, Exception):
            ex = ret_val

    if ex is not None:
        raise ex

    return [return_values[thread_id] for thread_id in range(thread_count)]


def test_multithreaded_many_get_pvs(ioc, context, thread_count,
                                    multi_iterations):
    def _test(thread_id):
        pv, = context.get_pvs(ioc.pvs['int'])
        pv.wait_for_connection(timeout=10)

        pvs[thread_id] = pv
        return pv.connected

    pvs = {}
    for connected in _multithreaded_exec(_test, thread_count):
        assert connected

    assert len(set(pvs.values())) == 1


def test_multithreaded_many_wait_for_connection(ioc, context, thread_count,
                                                multi_iterations):
    def _test(thread_id):
        pv.wait_for_connection(timeout=10)
        return pv.connected

    pv, = context.get_pvs(ioc.pvs['int'])

    for connected in _multithreaded_exec(_test, thread_count):
        assert connected


def test_multithreaded_many_read(ioc, context, thread_count,
                                 multi_iterations):
    def _test(thread_id):
        data_id = thread_id % max(data_types)
        pv.wait_for_connection(timeout=10)
        value = pv.read(data_type=data_types[data_id])
        values[data_id] = value
        return (data_id, value)

    pv, = context.get_pvs(ioc.pvs['int'])
    values = {}

    data_types = {0: ChannelType.INT,
                  1: ChannelType.STS_INT,
                  2: ChannelType.CTRL_INT,
                  3: ChannelType.GR_INT
                  }

    for data_id, value in _multithreaded_exec(_test, thread_count):
        assert value.data_type == data_types[data_id]


def test_multithreaded_many_write(ioc, context, thread_count,
                                  multi_iterations):
    def _test(thread_id):
        pv.wait_for_connection(timeout=10)
        ret = pv.write(data=[thread_id], wait=True)
        time.sleep(0.2)  # Wait for EventAddResponse to be received, processed.
        return ret

    pv, = context.get_pvs(ioc.pvs['int'])
    values = []

    def callback(command):
        values.append(command.data.tolist()[0])

    sub = pv.subscribe()
    sub.add_callback(callback)
    time.sleep(0.2)  # Wait for EventAddRequest to be sent and processed.

    _multithreaded_exec(_test, thread_count)
    assert set(values[1:]) == set(range(thread_count))

    sub.clear()


@pytest.mark.xfail
def test_multithreaded_many_subscribe(ioc, context, thread_count,
                                      multi_iterations):
    def _test(thread_id):
        if thread_id == 0:
            init_barrier.wait(timeout=10)
            print('-- write thread initialized --')
            pv.write((1, ), wait=True)
            time.sleep(0.01)
            pv.write((2, ), wait=True)
            time.sleep(0.01)
            pv.write((3, ), wait=True)
            time.sleep(0.2)
            print('-- write thread hit sub barrier --')
            sub_ended_barrier.wait(timeout=10)
            print('-- write thread exiting --')
            return [initial_value, 1, 2, 3]

        values[thread_id] = []

        def callback(command):
            print(thread_id, command)
            values[thread_id].append(command.data.tolist()[0])

        sub = pv.subscribe()
        sub.add_callback(callback)
        # Wait <= 20 seconds until first EventAddResponse is received.
        for i in range(200):
            if values[thread_id]:
                break
            time.sleep(0.1)
        else:
            raise Exception(f"{thread_id} never saw initial EventAddResponse")
        # print(thread_id, sub)
        init_barrier.wait(timeout=20)
        # Everybody here? On my signal... SEND UPDATES!! Ahahahahaha!
        # Destruction!!
        # Wait <= 20 seconds until three more EventAddResponses are received.
        for i in range(200):
            if len(values[thread_id]) == 4:
                break
            time.sleep(0.1)
        else:
            raise Exception(f"{thread_id} only got {len(values[thread_id])}"
                            f"EventAddResponses.")
        sub_ended_barrier.wait(timeout=20)

        sub.clear()
        return values[thread_id]

    values = {}
    init_barrier = threading.Barrier(parties=thread_count + 1)
    sub_ended_barrier = threading.Barrier(parties=thread_count + 1)

    pv, = context.get_pvs(ioc.pvs['int'])
    pv.wait_for_connection(timeout=10)
    initial_value = pv.read().data.tolist()[0]

    print()
    print()
    print(f'initial value is: {initial_value!r}')
    try:
        results = _multithreaded_exec(_test, thread_count + 1)
    except threading.BrokenBarrierError:
        if init_barrier.broken:
            print(f'Init barrier broken!')
        if sub_ended_barrier.broken:
            print(f'Sub_ended barrier broken!')
        raise

    for value_list in results:
        assert len(value_list) == 4
        assert list(value_list) == [initial_value, 1, 2, 3]


def test_batch_read(context, ioc):
    pvs = context.get_pvs(ioc.pvs['int'], ioc.pvs['int2'], ioc.pvs['int3'])
    for pv in pvs:
        pv.wait_for_connection(timeout=10)
    results = {}

    def stash_result(name, response):
        results[name] = response.data

    with Batch() as b:
        for pv in pvs:
            b.read(pv, functools.partial(stash_result, pv.name))
    time.sleep(0.1)
    assert set(results) == set(pv.name for pv in pvs)


def test_batch_write(context, ioc):
    pvs = context.get_pvs(ioc.pvs['int'], ioc.pvs['int2'], ioc.pvs['int3'])
    for pv in pvs:
        pv.wait_for_connection(timeout=10)
    results = {}

    def stash_result(name, response):
        results[name] = response

    with Batch() as b:
        for pv in pvs:
            b.write(pv, [4407], functools.partial(stash_result, pv.name))
    time.sleep(0.1)
    assert set(results) == set(pv.name for pv in pvs)
    for pv in pvs:
        assert list(pv.read().data) == [4407]


def test_batch_write_no_callback(context, ioc):
    pvs = context.get_pvs(ioc.pvs['int'], ioc.pvs['int2'], ioc.pvs['int3'])
    for pv in pvs:
        pv.wait_for_connection(timeout=10)
    with Batch() as b:
        for pv in pvs:
            b.write(pv, [4407])
    time.sleep(0.1)
    for pv in pvs:
        assert list(pv.read().data) == [4407]


def test_write_accepts_scalar(context, ioc):
    int_pv, str_pv = context.get_pvs(ioc.pvs['int'], ioc.pvs['str'])
    for pv in (int_pv, str_pv):
        pv.wait_for_connection(timeout=10)
    int_pv.write(17, wait=True)
    assert list(int_pv.read().data) == [17]
    str_pv.write('caprotoss', wait=True)
    assert list(str_pv.read().data) == [b'caprotoss']


def test_events_off_and_on(ioc, context):
    pv, = context.get_pvs(ioc.pvs['int'])
    pv.wait_for_connection(timeout=10)

    monitor_values = []

    def callback(command, **kwargs):
        assert isinstance(command, ca.EventAddResponse)
        monitor_values.append(command.data[0])

    sub = pv.subscribe()
    sub.add_callback(callback)
    time.sleep(0.2)  # Wait for EventAddRequest to be sent and processed.
    pv.write((1, ), wait=True)
    pv.write((2, ), wait=True)
    pv.write((3, ), wait=True)
    time.sleep(0.2)  # Wait for the last update to be processed.

    for i in range(3):
        if pv.read().data[0] == 3:
            time.sleep(0.2)
            break
        else:
            time.sleep(0.2)

    assert monitor_values[1:] == [1, 2, 3]

    pv.circuit_manager.events_off()
    time.sleep(0.2)  # Wait for EventsOffRequest to be processed.
    pv.write((4, ), wait=True)
    pv.write((5, ), wait=True)
    pv.write((6, ), wait=True)
    time.sleep(0.2)  # Wait for the last update to be processed.
    pv.circuit_manager.events_on()
    time.sleep(0.2)  # Wait for EventsOnRequest to be processed.
    # The last update, 6, should be sent at this time.

    pv.write((7, ), wait=True)
    pv.write((8, ), wait=True)
    pv.write((9, ), wait=True)

    for i in range(3):
        if pv.read().data[0] == 7:
            time.sleep(0.2)
            break
        else:
            time.sleep(0.2)

    assert monitor_values[1:] == [1, 2, 3, 6, 7, 8, 9]
