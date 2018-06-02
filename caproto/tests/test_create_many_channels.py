import logging
import pytest
import curio

import caproto as ca
from .conftest import default_setup_module as setup_module  # noqa
from .conftest import default_teardown_module as teardown_module  # noqa
from . import conftest


@pytest.mark.parametrize('backend', ['curio', 'trio'])
def test_create_many_channels(ioc, backend):
    logging.getLogger('caproto.{}.client'.format(backend)).setLevel('DEBUG')

    async def client_test(context):
        if context is None:
            context = await conftest.get_curio_context()
        return await context.create_many_channels(*pvnames,
                                                  wait_for_connection=True)

    pvnames = list(ioc.pvs.values())

    if backend == 'curio':
        channels = curio.run(client_test, None)
    elif backend == 'trio':
        channels = conftest.run_with_trio_context(client_test)

    print('got channels:', channels)
    connected_channels = [ch for ch in channels.values()
                          if ch.channel.states[ca.CLIENT] is ca.CONNECTED]
    assert len(connected_channels) == len(pvnames)
    print('done')


@pytest.mark.parametrize('backend', ['curio', 'trio'])
def test_create_many_channels_with_bad_pv(ioc, backend):
    async def client_test(context):
        if context is None:
            context = await conftest.get_curio_context()
        return await context.create_many_channels(*pvnames,
                                                  wait_for_connection=True,
                                                  move_on_after=2)

    pvnames = list(ioc.pvs.values()) + ['_NONEXISTENT_PVNAME_']

    if backend == 'curio':
        channels = curio.run(client_test, None)
    elif backend == 'trio':
        channels = conftest.run_with_trio_context(client_test)

    assert '_NONEXISTENT_PVNAME_' not in channels
    assert len(channels) == len(pvnames) - 1
