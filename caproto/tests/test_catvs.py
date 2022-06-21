import asyncio
import logging
import os
from typing import Any, Callable, Optional

import pytest

import caproto
import caproto.asyncio

try:
    import catvs
    import catvs.server
except ImportError:
    catvs = None

import caproto as ca
from caproto.tests.verify_with_catvs import CatvsIOC

logger = logging.getLogger(__name__)
# logging.getLogger('caproto').setLevel('DEBUG')


@pytest.fixture(scope="function", params=["asyncio"])
def catvs_ioc_runner():
    event = None

    def asyncio_runner(client: Callable, *, threaded_client: bool = False):
        async def asyncio_startup(async_lib):
            event.set()

        async def asyncio_server_main():
            orig_port = os.environ.get("EPICS_CA_SERVER_PORT", "5064")
            try:
                group = CatvsIOC(prefix="")
                os.environ["EPICS_CA_SERVER_PORT"] = str(asyncio_runner.port)
                asyncio_runner.context = caproto.asyncio.server.Context(group.pvdb)
                await asyncio_runner.context.run(startup_hook=asyncio_startup)
            except Exception as ex:
                logger.error("Server failed: %s %s", type(ex), ex)
                raise
            finally:
                os.environ["EPICS_CA_SERVER_PORT"] = orig_port

        async def run_server_and_client():
            nonlocal event
            event = asyncio.Event()
            loop = asyncio.get_running_loop()
            tsk = loop.create_task(asyncio_server_main())
            # Give this a couple tries, akin to poll_readiness.
            await event.wait()
            for _ in range(5):
                try:
                    if threaded_client:
                        await loop.run_in_executor(None, client)
                    else:
                        await client()
                except TimeoutError:
                    continue
                else:
                    break
            tsk.cancel()
            await asyncio.wait((tsk, ))

        asyncio.run(run_server_and_client())

    # NOTE: catvs expects server tcp_port==udp_port, so make a weak attempt
    # here to avoid clashing between servers
    asyncio_runner.port = list(ca.random_ports(1))[0]
    asyncio_runner.backend = "asyncio"
    return asyncio_runner


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
        from catvs.server.test_ops import TestArray, TestScalar
        from catvs.server.test_search import TestSearchTCP, TestSearchUDP
        return sum((get_tests(cls)
                    for cls in [TestChannel, TestScalar, TestArray,
                                TestSearchTCP, TestSearchUDP]),
                   [])

    all_tests = get_all_tests()


SKIPPED = (
    "TestScalar-test_get_bad",
    "TestScalar-test_put",
    "TestArray-test_monitor_three_fixed",
    "TestArray-test_monitor_zero_dynamic",
    "TestArray-test_put",
)


def assert_equal(a: Any, b: Any, msg: Optional[str] = None):
    if msg is not None:
        assert a == b, msg
    else:
        assert a == b


def assert_ca_equal(msg: str, **kwargs):
    received = dict((name, getattr(msg, name))
                    for name in kwargs)
    expected = kwargs
    assert received == expected


@pytest.mark.skipif(catvs is None, reason='catvs unavailable')
@pytest.mark.parametrize('test_class, test_name', all_tests)
def test_catvs(catvs_ioc_runner: Callable, test_class: type, test_name: str):
    if f'{test_class.__name__}-{test_name}' in SKIPPED:
        pytest.skip("known difference in behavior with epics-base")

    def client_test():
        test_inst = test_class()

        test_inst.assertEqual = assert_equal
        test_inst.assertCAEqual = assert_ca_equal

        ctx = catvs_ioc_runner.context

        port = ctx.ca_server_port if "udp" in test_name.lower() else ctx.port
        hacked_setup(test_inst, port)
        test_func = getattr(test_inst, test_name)
        print(f"Running {test_func.__name__}")
        test_func()

    catvs_ioc_runner(client_test, threaded_client=True)
