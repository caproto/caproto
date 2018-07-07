import os
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

import caproto as ca
from caproto.ioc_examples.verify_with_catvs import CatvsIOC

logger = logging.getLogger(__name__)
# logging.getLogger('caproto').setLevel('DEBUG')


def server_thread(context):
    async def server():
        return await context.run(log_pv_names=True)

    kernel = curio.Kernel()
    kernel.run(server)


@pytest.fixture(params=['curio'],  # 'trio', 'asyncio', 'epics-base'],
                scope='function')
def catvs_ioc(request):
    from caproto.curio.server import Context

    pvgroup = CatvsIOC(prefix='')

    # NOTE: catvs expects server tcp_port==udp_port, so make a weak attempt
    # here to avoid clashing between servers
    port = list(ca.random_ports(1))[0]

    try:
        # The environment variale only needs to e set for the initializer of
        # Context.
        os.environ['EPICS_CA_SERVER_PORT'] = str(port)
        context = Context(pvgroup.pvdb, ['127.0.0.1'])
    finally:
        os.environ['EPICS_CA_SERVER_PORT'] = '5064'

    thread = threading.Thread(target=server_thread, daemon=True,
                              args=(context, ))
    thread.start()

    def stop_server():
        context.log.setLevel('INFO')
        context.stop()

    request.addfinalizer(stop_server)

    while getattr(context, 'port', None) is None:
        logger.info('Waiting on catvs test server...')
        time.sleep(0.1)

    tcp_port = context.port
    udp_port = context.ca_server_port
    logger.info('catvs test server started up on port %d (udp port %d)',
                tcp_port, udp_port)
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
        from catvs.server.test_search import TestSearchTCP, TestSearchUDP
        return sum((get_tests(cls)
                    for cls in [TestChannel, TestScalar, TestArray,
                                TestSearchTCP, TestSearchUDP]),
                   [])

    all_tests = get_all_tests()


SKIPPED = ('TestScalar-test_get_bad',
           'TestScalar-test_put',
           'TestArray-test_monitor_three_fixed',
           'TestArray-test_monitor_zero_dynamic',
           'TestArray-test_put',
           )


@pytest.mark.skipif(catvs is None, reason='catvs unavailable')
@pytest.mark.parametrize('test_class, test_name', all_tests)
def test_catvs(catvs_ioc, test_class, test_name):
    if f'{test_class.__name__}-{test_name}' in SKIPPED:
        pytest.skip("known difference in behavior with epics-base")

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

    port = (context.ca_server_port if 'udp' in test_name.lower()
            else context.port)
    hacked_setup(test_inst, port)
    test_func = getattr(test_inst, test_name)
    test_func()
