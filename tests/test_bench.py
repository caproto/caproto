import pytest
import time
import logging
import contextlib
import numpy as np
import curio

import caproto as ca


ioc_handler = None
logger = logging.getLogger(__name__)


def setup_module():
    global ioc_handler

    import _asv_shim
    logging.basicConfig()
    logger.setLevel('DEBUG')
    _asv_shim.logger.setLevel('DEBUG')
    logging.getLogger('benchmarks.util').setLevel('DEBUG')
    logging.getLogger('caproto').setLevel('INFO')

    waveform_db = {
        ('wfioc:wf{}'.format(sz), 'waveform'): dict(FTVL='LONG', NELM=sz)
        for sz in (4000, 8000, 50000, 1000000)
    }

    many_connections_db = {
        ('connections:{}'.format(i), 'ao'): dict(VAL=i)
        for i in range(1000)
    }

    full_db = dict()
    full_db.update(many_connections_db)
    full_db.update(waveform_db)

    db_text = ca.benchmarking.make_database(full_db)

    ioc_handler = ca.benchmarking.IocHandler(logger=logger)
    ioc_handler.setup_ioc(db_text=db_text, max_array_bytes='10000000')
    # give time for the server to startup
    time.sleep(1.0)


def teardown_module():
    if ioc_handler is not None:
        ioc_handler.teardown()


@contextlib.contextmanager
def temporary_pyepics_access(pvname, **kwargs):
    import epics
    pv = epics.PV(pvname, **kwargs)
    assert pv.wait_for_connection(), 'unable to connect to {}'.format(pv)
    yield pv
    epics.ca.clear_cache()


@contextlib.contextmanager
def bench_pyepics_get_speed(pvname, *, initial_value=None, log_level='DEBUG'):
    with temporary_pyepics_access(pvname) as pv:
        def pyepics():
            value = pv.get(use_monitor=False)
            if initial_value is not None:
                assert len(value) == len(initial_value)

        if initial_value is not None:
            pv.put(initial_value, wait=True)
        yield pyepics
        logger.debug('Disconnecting pyepics pv %s', pv)
        pv.disconnect()


@contextlib.contextmanager
def bench_threading_get_speed(pvname, *, initial_value=None, log_level='ERROR'):
    from caproto.threading.client import (PV, SharedBroadcaster,
                                          Context as ThreadingContext)

    shared_broadcaster = SharedBroadcaster()
    context = ThreadingContext(broadcaster=shared_broadcaster,
                               log_level=log_level)

    def threading():
        value = pv.get(use_monitor=False)
        if initial_value is not None:
            assert len(value) == len(initial_value)

    pv = PV(pvname, auto_monitor=False, context=context)
    if initial_value is not None:
        pv.put(initial_value, wait=True)
    yield threading
    logger.debug('Disconnecting threading pv %s', pv)
    pv.disconnect()
    logger.debug('Disconnecting shared broadcaster %s', shared_broadcaster)
    shared_broadcaster.disconnect()
    logger.debug('Done')


@contextlib.contextmanager
def bench_curio_get_speed(pvname, *, initial_value=None, log_level='DEBUG'):
    kernel = curio.Kernel()

    async def curio_setup():
        logger.debug('Registering...')
        broadcaster = ca.curio.client.SharedBroadcaster(log_level=log_level)
        await broadcaster.register()
        ctx = ca.curio.client.Context(broadcaster, log_level=log_level)
        logger.debug('Registered')

        logger.debug('Searching for %s...', pvname)
        await ctx.search(pvname)
        logger.debug('... found!')
        chan = await ctx.create_channel(pvname)
        await chan.wait_for_connection()
        logger.debug('Connected to %s', pvname)

        if initial_value is not None:
            logger.debug('Writing initial value')
            await chan.write(initial_value)
            logger.debug('Wrote initial value')
        logger.debug('Init complete')
        return chan

    def curio_client():
        async def get():
            reading = await chan.read()
            if initial_value is not None:
                assert len(reading.data) == len(initial_value)
        kernel.run(get())

    chan = kernel.run(curio_setup())

    assert chan.channel.states[ca.CLIENT] is ca.CONNECTED, 'Not connected'

    yield curio_client

    logger.debug('Shutting down the kernel')
    kernel.run(shutdown=True)
    logger.debug('Done')


@pytest.mark.parametrize('waveform_size', [4000, 8000, 50000])
@pytest.mark.parametrize('backend', ['pyepics', 'curio', 'threading'])
@pytest.mark.parametrize('log_level', ['INFO'])
def test_waveform_get(benchmark, waveform_size, backend, log_level):
    pvname = 'wfioc:wf{}'.format(waveform_size)
    ca.benchmarking.set_logging_level(logging.DEBUG, logger=logger)

    context = {'pyepics': bench_pyepics_get_speed,
               'curio': bench_curio_get_speed,
               'threading': bench_threading_get_speed
               }[backend]

    val = list(range(waveform_size))
    with context(pvname, initial_value=val, log_level=log_level) as bench_fcn:
        benchmark(bench_fcn)


@contextlib.contextmanager
def bench_pyepics_put_speed(pvname, *, value, log_level='DEBUG'):
    with temporary_pyepics_access(pvname) as pv:
        def pyepics():
            pv.put(value, wait=True)

        yield pyepics

        np.testing.assert_array_almost_equal(pv.get(), value)

        logger.debug('Disconnecting pyepics pv %s', pv)
        pv.disconnect()


@contextlib.contextmanager
def bench_threading_put_speed(pvname, *, value, log_level='ERROR'):
    from caproto.threading.client import (PV, SharedBroadcaster,
                                          Context as ThreadingContext)

    shared_broadcaster = SharedBroadcaster()
    context = ThreadingContext(broadcaster=shared_broadcaster,
                               log_level=log_level)

    def threading():
        pv.put(value, wait=True)

    pv = PV(pvname, auto_monitor=False, context=context)

    yield threading

    np.testing.assert_array_almost_equal(pv.get(), value)

    logger.debug('Disconnecting threading pv %s', pv)
    pv.disconnect()
    logger.debug('Disconnecting shared broadcaster %s', shared_broadcaster)
    shared_broadcaster.disconnect()
    logger.debug('Done')


@contextlib.contextmanager
def bench_curio_put_speed(pvname, *, value, log_level='DEBUG'):
    kernel = curio.Kernel()

    async def curio_setup():
        logger.debug('Registering...')
        broadcaster = ca.curio.client.SharedBroadcaster(log_level=log_level)
        await broadcaster.register()
        ctx = ca.curio.client.Context(broadcaster, log_level=log_level)
        logger.debug('Registered')

        logger.debug('Searching for %s...', pvname)
        await ctx.search(pvname)
        logger.debug('... found!')
        chan = await ctx.create_channel(pvname)
        await chan.wait_for_connection()
        logger.debug('Connected to %s', pvname)
        return chan

    def curio_client():
        async def put():
            await chan.write(value)
        kernel.run(put())

    chan = kernel.run(curio_setup())

    assert chan.channel.states[ca.CLIENT] is ca.CONNECTED, 'Not connected'

    yield curio_client

    async def check():
        reading = await chan.read()
        np.testing.assert_array_almost_equal(reading.data, value)

    kernel.run(check())
    logger.debug('Shutting down the kernel')
    kernel.run(shutdown=True)
    logger.debug('Done')


@pytest.mark.parametrize('waveform_size', [4000, 8000, 50000])
@pytest.mark.parametrize('backend', ['pyepics', 'curio', 'threading'])
@pytest.mark.parametrize('log_level', ['INFO'])
def test_waveform_put(benchmark, waveform_size, backend, log_level):
    pvname = 'wfioc:wf{}'.format(waveform_size)
    ca.benchmarking.set_logging_level(logging.DEBUG, logger=logger)

    context = {'pyepics': bench_pyepics_put_speed,
               'curio': bench_curio_put_speed,
               'threading': bench_threading_put_speed
               }[backend]

    value = list(range(waveform_size))
    with context(pvname, value=value, log_level=log_level) as bench_fcn:
        benchmark(bench_fcn)


@contextlib.contextmanager
def bench_pyepics_many_connections(pv_names, *, initial_value=None,
                                   log_level='DEBUG'):
    import epics

    pvs = []

    def pyepics():
        nonlocal pvs

        pvs = [epics.PV(pvname, auto_monitor=False)
               for pvname in pv_names]

        while not all(pv.connected for pv in pvs):
            time.sleep(0.01)

    epics.ca.clear_cache()

    try:
        yield pyepics
    finally:
        for pv in pvs:
            pv.disconnect()

        epics.ca.clear_cache()


@contextlib.contextmanager
def bench_threading_many_connections(pv_names, *, initial_value=None,
                                     log_level='DEBUG'):
    from caproto.threading.client import (PV, SharedBroadcaster,
                                          Context as ThreadingContext)

    shared_broadcaster = SharedBroadcaster()
    context = ThreadingContext(broadcaster=shared_broadcaster,
                               log_level=log_level)

    pvs = []

    def threading():
        nonlocal pvs

        pvs = [PV(pvname, auto_monitor=False, context=context)
               for pvname in pv_names]

        while not all(pv.connected for pv in pvs):
            time.sleep(0.01)

    try:
        yield threading
    finally:
        for pv in pvs:
            pv.disconnect()

        shared_broadcaster.disconnect()
    logger.debug('Done')


@contextlib.contextmanager
def bench_curio_many_connections(pv_names, *, initial_value=None,
                                 log_level='DEBUG'):
    kernel = curio.Kernel()

    async def test():
        broadcaster = ca.curio.client.SharedBroadcaster(
            log_level=log_level)
        await broadcaster.register()
        ctx = ca.curio.client.Context(broadcaster, log_level=log_level)

        pvs = {}
        async with curio.TaskGroup() as connect_task:
            async with curio.TaskGroup() as search_task:
                for pvname in pv_names:
                    await search_task.spawn(ctx.search, pvname)

                while True:
                    res = await search_task.next_done()
                    if res is None:
                        break
                    pvname = res.result
                    await connect_task.spawn(ctx.create_channel, pvname)

            while True:
                res = await connect_task.next_done()
                if res is None:
                    break
                curio_channel = res.result
                pvname = curio_channel.channel.name
                pvs[pvname] = curio_channel

        assert len(pvs) == len(pv_names)
        # TODO: can't successfully test as this hammers file creation; this
        # will be important to resolve...
        await curio.sleep(1)

    def curio_client():
        kernel.run(test())

    yield curio_client

    logger.debug('Shutting down the kernel')
    kernel.run(shutdown=True)
    logger.debug('Done')


@pytest.mark.parametrize('connection_count', [5])
@pytest.mark.parametrize('pv_format', ['connections:{}'])
@pytest.mark.parametrize('backend', ['curio', 'pyepics', 'threading'])
@pytest.mark.parametrize('log_level', ['INFO'])
def test_many_connections(benchmark, backend, connection_count, pv_format,
                          log_level):
    ca.benchmarking.set_logging_level(logging.DEBUG, logger=logger)

    context = {'pyepics': bench_pyepics_many_connections,
               'curio': bench_curio_many_connections,
               'threading': bench_threading_many_connections,
               }[backend]

    pv_names = [pv_format.format(i) for i in range(connection_count)]
    with context(pv_names, log_level=log_level) as bench_fcn:
        benchmark(bench_fcn)
