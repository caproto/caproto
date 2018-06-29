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
# logging.getLogger('caproto').setLevel('DEBUG')

def server_thread(context):
    async def server():
        print('running')
        return await context.run(log_pv_names=True)

    print('calling curio.run')
    kernel = curio.Kernel()
    kernel.run(server)


@pytest.fixture(params=['curio'],  # 'trio', 'asyncio', 'epics-base'],
                scope='function')
def catvs_ioc(request):
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

    def stop_server():
        context.stop()

    request.addfinalizer(stop_server)

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


if catvs is None:
    all_tests = []
else:
    def get_all_tests():
        def get_tests(cls):
            return [(cls, attr) for attr in dir(cls)
                    if attr.startswith('test_')]

        from catvs.server.test_chan import TestChannel
        from catvs.server.test_ops import TestScalar, TestArray
        return sum((get_tests(cls)
                    for cls in [TestChannel, TestScalar, TestArray]),
                   [])

    all_tests = get_all_tests()


@pytest.mark.skipif(catvs is None, reason='catvs unavailable')
@pytest.mark.parametrize('test_class, test_name', all_tests)
def test_catvs(catvs_ioc, test_class, test_name):
    pvgroup, context, server_thread = catvs_ioc

    test_inst = test_class()

    def assert_equal(a, b, msg=None):
        if msg is not None:
            assert a == b, msg
        else:
            assert a == b

    def assert_ca_equal(msg, **kwargs):
        received = dict((name, getattr(msg, name))
                        for name in kwargs)
        expected = kwargs
        assert received == expected

    test_inst.assertEqual = assert_equal
    test_inst.assertCAEqual = assert_ca_equal

    hacked_setup(test_inst, context.port)
    test_func = getattr(test_inst, test_name)
    test_func()
