import logging
import pytest
import curio

import caproto as ca
from .conftest import default_setup_module as setup_module  # noqa
from .conftest import default_teardown_module as teardown_module  # noqa
from . import conftest


@pytest.mark.parametrize('backend', ['curio', 'trio'])
def test_create_many_channels(backend):
    logging.getLogger('caproto.{}.client'.format(backend)).setLevel('DEBUG')

    async def client_test(context):
        if context is None:
            context = await conftest.get_curio_context()
        return await context.create_many_channels(*pvnames,
                                                  wait_for_connection=True)

    pvnames = ['Py:ao1', 'Py:ao2', 'Py:ao3', 'Py:ao4']

    if backend == 'curio':
        channels = curio.run(client_test, None)
    elif backend == 'trio':
        channels = conftest.run_with_trio_context(client_test)

    print('got channels:', channels)
    connected_channels = [ch for ch in channels.values()
                          if ch.channel.states[ca.CLIENT] is ca.CONNECTED]
    assert len(connected_channels) == len(pvnames)


@pytest.mark.parametrize('backend', ['curio', 'trio'])
def test_create_many_channels_with_bad_pv(backend):
    async def client_test(context):
        if context is None:
            context = await conftest.get_curio_context()
        return await context.create_many_channels(*pvnames,
                                                  wait_for_connection=True,
                                                  move_on_after=2)

    pvnames = ['Py:ao1', 'Py:ao2', 'Py:ao3', 'nonexistent_pv']

    if backend == 'curio':
        channels = curio.run(client_test, None)
    elif backend == 'trio':
        channels = conftest.run_with_trio_context(client_test)

    assert 'nonexistent_pv' not in channels
    assert len(channels) == 3
