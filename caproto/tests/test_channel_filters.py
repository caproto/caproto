import threading
import time

import pytest

from ..threading.client import Context


@pytest.fixture(scope='function')
def context(request):
    context = Context()

    def cleanup():
        sb = context.broadcaster
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


@pytest.mark.parametrize('filter, expected',
                         [('[4]', [5]),
                          ('[:3]', [1, 1, 2, 3]),
                          ('[2:3]', [2, 3]),
                          ('[2:2:6]', [2, 5, 13]),
                          ('{"arr": {"s": 3, "e": 3}}', [3]),
                          ('{"arr": {"s": 0, "e": 3}}', [1, 1, 2, 3]),
                          ('{"arr": {"s": 2, "e": 3}}', [2, 3]),
                          ('{"arr": {"s": 2, "e": 6, "i": 2}}', [2, 5, 13])
                          ])
def test_array_filter(request, prefix, context, filter, expected, type_varieties_ioc):
    pv_name = type_varieties_ioc.pvs["fib"]

    pv, = context.get_pvs(pv_name + '.' + filter)
    pv.wait_for_connection()
    event = threading.Event()

    subscription_reading = None

    def cb(_, reading):
        nonlocal subscription_reading
        subscription_reading = reading
        event.set()

    # Test read.
    reading = pv.read()
    cb(None, reading)
    # Test subscribe.
    sub = pv.subscribe()
    event.clear()
    sub.add_callback(cb)
    # Wait for callback to process.
    event.wait(timeout=2)
    assert subscription_reading is not None
    assert list(subscription_reading.data) == expected


def test_ts_filter(request, prefix, context, type_varieties_ioc):
    pv_name = type_varieties_ioc.pvs["fib"]

    # Access one element.
    pv, = context.get_pvs(pv_name)
    ts_pv, = context.get_pvs(pv_name + '.{"ts": {}}')
    pv.wait_for_connection()
    ts_pv.wait_for_connection()

    # Check that proc_time is stable across subsequent reads.
    proc_time = pv.read(data_type='time').metadata.timestamp
    time.sleep(0.05)
    assert proc_time == pv.read(data_type='time').metadata.timestamp

    event = threading.Event()

    def cb(_, reading):
        assert reading.metadata.timestamp != proc_time
        event.set()
    # Test read.
    reading = ts_pv.read(data_type='time')
    cb(None, reading)
    # Test subscribe.
    sub = pv.subscribe(data_type='time')
    event.clear()
    sub.add_callback(cb)
    # Wait for callback to process.
    event.wait(timeout=2)


MANY = object()


# TO DO --- These really should not be flaky!
@pytest.mark.xfail
@pytest.mark.parametrize('filter, initial, on, off',
                         [('{"before": "my_stately_state"}', 1, 1, 1),
                          ('{"after": "my_stately_state"}', 1, 1, 1),
                          ('{"first": "my_stately_state"}', 1, 1, 1),
                          ('{"last": "my_stately_state"}', 1, 1, 1),
                          ('{"while": "my_stately_state"}', 1, MANY, 1),
                          ('{"unless": "my_stately_state"}', MANY, 1, MANY),
                          ])
def test_sync_filter(request, prefix, context, filter, initial, on, off, states_ioc):
    responses = []

    def cache(_, response):
        print('* response:', response.data)
        responses.append(response)

    def check_length(expected):
        if expected is MANY:
            assert len(responses) > 1, 'Expected many responses'
        else:
            assert len(responses) == expected, \
                'Expected an exact number of responses'

    value, disable_state, enable_state = context.get_pvs(
        states_ioc.pvs["value"] + "." + filter,
        states_ioc.pvs["disable_state"],
        states_ioc.pvs["enable_state"],
    )

    for pv in (value, disable_state, enable_state):
        pv.wait_for_connection()

    sub = value.subscribe()

    # state is off
    sub.add_callback(cache)
    time.sleep(0.5)
    sub.clear()
    check_length(initial)
    responses.clear()

    # state is on
    enable_state.write((1,))
    sub.add_callback(cache)
    time.sleep(0.5)
    sub.clear()
    check_length(on)
    responses.clear()

    # state is off
    disable_state.write((1,))
    sub.add_callback(cache)
    time.sleep(0.5)
    sub.clear()
    check_length(off)
    responses.clear()


@pytest.mark.parametrize('filter, expected',
                         [('{"dbnd": {"abs": 0.001}}', [3.14, 3.15, 3.16]),
                          ('{"dbnd": {"abs": 0.015}}', [3.14, 3.16]),
                          ('{"dbnd": {"abs": 1}}', [3.14]),
                          # TODO Cover more interesting cases.
                          ])
def test_dbnd_filter(request, type_varieties_ioc, context, filter, expected):

    responses = []

    def cache(_, response):
        responses.append(response)

    pv, = context.get_pvs(type_varieties_ioc.pvs['float'] + '.' + filter)
    pv.wait_for_connection()

    sub = pv.subscribe()
    sub.add_callback(cache)
    time.sleep(0.2)
    pv.write((3.15,))
    pv.write((3.16,))
    time.sleep(0.2)
    assert [res.data[0] for res in responses] == expected
