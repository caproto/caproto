import threading
import logging
import time

import pytest
import curio

try:
    import catvs
    import catvs.server
except ImportError:
    catvs = None


logger = logging.getLogger(__name__)


def server_thread(context):
    async def server():
        print('running')
        return await context.run(log_pv_names=True)

    print('calling curio.run')
    curio.run(server)


@pytest.fixture(scope='function')
def catvs_ioc():
    from caproto.ioc_examples.verify_with_catvs import CatvsIOC
    from caproto.curio.server import Context

    pvgroup = CatvsIOC(prefix='')
    context = Context(pvgroup.pvdb, ['127.0.0.1'])
    thread = threading.Thread(target=server_thread, daemon=True,
                              args=(context, ))
    thread.start()

    while getattr(context, 'port', None) is None:
        logger.info('Waiting on catvs test server...')
        time.sleep(0.1)

    port = context.port
    logger.info('catvs test server started up on port %d', port)
    time.sleep(0.5)
    return pvgroup, context, thread


def hacked_setup(test_inst, port):
    test_inst.testport = port
    if isinstance(test_inst, catvs.util.TestMixinClient):
        catvs.util.TestMixinClient.setUp(test_inst)
    if isinstance(test_inst, catvs.util.TestMixinServer):
        catvs.util.TestMixinServer.setUp(test_inst)


def hacked_teardown(test_inst):
    ...


@pytest.mark.skipif(catvs is None, reason='catvs unavailable')
def test_catvs(catvs_ioc):
    from catvs.server.test_chan import TestChannel

    pvgroup, context, server_thread = catvs_ioc

    test_inst = TestChannel()
    hacked_setup(test_inst, context.port)
    tests = [(attr, getattr(test_inst, attr))
             for attr in dir(test_inst)
             if attr.startswith('test_')]

    for name, test in tests:
        print('Running', name)
        test()
