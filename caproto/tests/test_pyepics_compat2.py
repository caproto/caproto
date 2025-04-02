"""
This is separate from the test_pyepics_compat file because it does
not use the pyepics test IOCs and can safely be run in parallel.
"""

import subprocess
import sys

import pytest

from caproto.threading.client import Context, SharedBroadcaster
from caproto.threading.pyepics_compat import caget, caput, get_pv

from .conftest import default_setup_module as setup_module  # noqa
from .conftest import default_teardown_module as teardown_module  # noqa
from .conftest import wait_for


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


def test_put_empty_list(context, ioc):
    pv = get_pv(ioc.pvs['waveform'], context=context)
    pv.wait_for_connection(timeout=10)
    assert pv.connected

    pv.put([], wait=True)
    ret = pv.get(use_monitor=False)
    assert ret.dtype.isnative
    assert list(ret) == []


def test_caget_caput(context, ioc):
    caput(ioc.pvs['waveform'], [1, 2, 3], wait=True, context=context)

    def new_value():
        return list(caget(ioc.pvs['waveform'], context=context)) == [1, 2, 3]

    wait_for(new_value, timeout=2)


def test_no_early_threads():
    c = """
import threading

assert len(threading.enumerate()) == 1
import caproto.threading.pyepics_compat

assert len(threading.enumerate()) == 1
pv = caproto.threading.pyepics_compat.PV("bob")
assert len(threading.enumerate()) > 1
"""

    try:
        subprocess.run([sys.executable, "-c", c], check=True, timeout=5)
    except subprocess.CalledProcessError as err:
        pytest.fail("Subprocess failed to test intended behavior\n" + str(err))


def test_native_endianess(context, ioc):
    pv = get_pv(ioc.pvs['waveform'], context=context)
    pv.wait_for_connection(timeout=10)
    assert pv.connected

    pv.put([1, 2, 3], wait=True)
    ret = pv.get(use_monitor=False)
    assert list(ret) == [1, 2, 3]
    assert ret.dtype.isnative
