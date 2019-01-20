"""
This is separate from the test_pyepics_compat file because it does
not use the pyepics test IOCs and can safely be run in parallel.
"""

import pytest
from .conftest import default_setup_module as setup_module  # noqa
from .conftest import default_teardown_module as teardown_module  # noqa
from caproto.threading.pyepics_compat import get_pv
from caproto.threading.client import (Context, SharedBroadcaster)


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
    ret = pv.get()
    assert list(ret) == []
