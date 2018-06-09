import pytest
np = pytest.importorskip('numpy')
import time
import logging
import contextlib
import curio

import caproto as ca
from .conftest import default_setup_module, default_teardown_module
from .conftest import get_curio_context, run_with_trio_context
from . import _asv_shim


ioc_handler = None
logger = logging.getLogger('caproto')


def setup_module(module):
    default_setup_module(module)
    global ioc_handler

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


def teardown_module(module):
    default_teardown_module(module)
    if ioc_handler is not None:
        ioc_handler.teardown()


@contextlib.contextmanager
def temporary_pyepics_access(pvname, **kwargs):
    import epics
    pv = epics.PV(pvname, **kwargs)
    assert pv.wait_for_connection(), 'unable to connect to {}'.format(pv)
    yield pv
    epics.ca.initial_context = None
    epics.ca.clear_cache()


@contextlib.contextmanager
def bench_pyepics_get_speed(pvname, *, initial_value=None, log_level='DEBUG'):
    with temporary_pyepics_access(pvname, auto_monitor=False) as pv:
        def pyepics():
            value = pv.get(use_monitor=False)
            if initial_value is not None:
                assert len(value) == len(initial_value)

        if initial_value is not None:
            pv.put(initial_value, wait=True)
        yield pyepics
        logger.debug('Disconnecting pyepics pv %s', pv)
        pv.disconnect()


def _setup_threading_client(log_level):
    from caproto.threading.client import (PV, SharedBroadcaster, Context)
    logging.getLogger('caproto').setLevel(log_level)
    shared_broadcaster = SharedBroadcaster()
    context = Context(broadcaster=shared_broadcaster)
    return shared_broadcaster, context, PV


@contextlib.contextmanager
def bench_threading_get_speed(pvname, *, initial_value=None,
                              log_level='ERROR'):
    shared_broadcaster, context, PV = _setup_threading_client(log_level)

    def threading():
        value = pv.read().data
        if initial_value is not None:
            assert len(value) == len(initial_value)

    pv, = context.get_pvs(pvname)
    pv.wait_for_connection()

    if initial_value is not None:
        pv.write(initial_value, wait=True)
    yield threading
    context.disconnect()


@contextlib.contextmanager
def bench_curio_get_speed(pvname, *, initial_value=None, log_level='DEBUG'):
    logging.getLogger('caproto').setLevel(log_level)
    kernel = curio.Kernel()

    async def curio_setup():
        ctx = await get_curio_context()

        logger.debug('Searching for %s...', pvname)
        await ctx.search(pvname)
        logger.debug('... found!')
        chan = await ctx.create_channel(pvname)
        await chan.wait_for_connection()
        logger.debug('Connected to %s', pvname)

        if initial_value is not None:
            logger.debug('Writing initial value')
            await chan.write(initial_value, notify=True)
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

    try:
        yield curio_client
    finally:
        logger.debug('Shutting down the kernel')
        kernel.run(shutdown=True)
        logger.debug('Done')


@pytest.mark.parametrize('waveform_size', [4000, 8000, 50000, 1000000])
@pytest.mark.parametrize('backend', ['pyepics', 'curio', 'threading'])
@pytest.mark.parametrize('log_level', ['INFO'])
def test_waveform_get(benchmark, waveform_size, backend, log_level):
    pvname = 'wfioc:wf{}'.format(waveform_size)
    logging.getLogger('caproto').setLevel(log_level)

    context = {'pyepics': bench_pyepics_get_speed,
               'curio': bench_curio_get_speed,
               'threading': bench_threading_get_speed
               }[backend]

    val = list(range(waveform_size))
    with context(pvname, initial_value=val) as bench_fcn:
        benchmark(bench_fcn)


@contextlib.contextmanager
def bench_pyepics_put_speed(pvname, *, value, log_level='DEBUG'):
    with temporary_pyepics_access(pvname, auto_monitor=False) as pv:
        def pyepics():
            pv.put(value, wait=True)

        yield pyepics

        np.testing.assert_array_almost_equal(pv.get(), value)

        logger.debug('Disconnecting pyepics pv %s', pv)
        pv.disconnect()


@contextlib.contextmanager
def bench_threading_put_speed(pvname, *, value, log_level='ERROR'):
    shared_broadcaster, context, PV = _setup_threading_client(log_level)

    def threading():
        pv.write(value, wait=True)

    pv, = context.get_pvs(pvname)
    pv.wait_for_connection()

    yield threading

    np.testing.assert_array_almost_equal(pv.read().data, value)

    context.disconnect()
    logger.debug('Done')


@contextlib.contextmanager
def bench_curio_put_speed(pvname, *, value, log_level='DEBUG'):
    logging.getLogger('caproto').setLevel(log_level)
    kernel = curio.Kernel()

    async def curio_setup():
        ctx = await get_curio_context()

        logger.debug('Searching for %s...', pvname)
        await ctx.search(pvname)
        logger.debug('... found!')
        chan = await ctx.create_channel(pvname)
        await chan.wait_for_connection()
        logger.debug('Connected to %s', pvname)
        return chan

    def curio_client():
        async def put():
            await chan.write(value, notify=True)
        kernel.run(put())

    chan = kernel.run(curio_setup())

    assert chan.channel.states[ca.CLIENT] is ca.CONNECTED, 'Not connected'

    try:
        yield curio_client

        async def check():
            reading = await chan.read()
            np.testing.assert_array_almost_equal(reading.data, value)

        kernel.run(check())
    finally:
        logger.debug('Shutting down the kernel')
        kernel.run(shutdown=True)
        logger.debug('Done')


@pytest.mark.parametrize('waveform_size', [4000, 8000, 50000, 1000000])
@pytest.mark.parametrize('backend', ['pyepics', 'curio', 'threading'])
@pytest.mark.parametrize('log_level', ['INFO'])
def test_waveform_put(benchmark, waveform_size, backend, log_level):
    pvname = 'wfioc:wf{}'.format(waveform_size)
    logging.getLogger('caproto').setLevel(log_level)

    context = {'pyepics': bench_pyepics_put_speed,
               'curio': bench_curio_put_speed,
               'threading': bench_threading_put_speed
               }[backend]

    value = list(range(waveform_size))
    with context(pvname, value=value) as bench_fcn:
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

    epics.ca.initial_context = None
    epics.ca.clear_cache()

    try:
        yield pyepics
    finally:
        for pv in pvs:
            pv.disconnect()

        epics.ca.initial_context = None
        epics.ca.clear_cache()


@contextlib.contextmanager
def bench_threading_many_connections(pv_names, *, initial_value=None,
                                     log_level='DEBUG'):
    shared_broadcaster, context, PV = _setup_threading_client(log_level)
    pvs = []

    def threading():
        nonlocal pvs

        pvs = context.get_pvs(*pv_names)
        while not all(pv.connected for pv in pvs):
            time.sleep(0.01)

    try:
        yield threading
    finally:
        context.disconnect()
    logger.debug('Done')


@contextlib.contextmanager
def bench_curio_many_connections(pv_names, *, initial_value=None,
                                 log_level='DEBUG'):
    logging.getLogger('caproto').setLevel(log_level)

    async def test():
        ctx = await get_curio_context()
        channels = await ctx.create_many_channels(*pv_names,
                                                  wait_for_connection=True,
                                                  move_on_after=20)

        connected_channels = [ch for ch in channels.values()
                              if ch.channel.states[ca.CLIENT] is ca.CONNECTED]
        assert len(connected_channels) == len(pv_names)

    def curio_client():
        with curio.Kernel() as kernel:
            kernel.run(test)

    yield curio_client


@contextlib.contextmanager
def bench_trio_many_connections(pv_names, *, initial_value=None,
                                log_level='DEBUG'):
    async def test(context):
        logging.getLogger('caproto').setLevel(log_level)
        channels = await context.create_many_channels(
            *pv_names, wait_for_connection=True,
            move_on_after=10)

        connected_channels = [ch for ch in channels.values()
                              if ch.channel.states[ca.CLIENT] is ca.CONNECTED]
        assert len(connected_channels) == len(pv_names)

    def trio_test():
        run_with_trio_context(test)

    yield trio_test
    logger.debug('Done')


@pytest.mark.parametrize('connection_count', [5, 100, 500])
@pytest.mark.parametrize('pv_format', ['connections:{}'])
@pytest.mark.parametrize('backend', ['pyepics', 'curio', 'trio', 'threading'])
@pytest.mark.parametrize('log_level', ['INFO'])
def test_many_connections_same_ioc(benchmark, backend, connection_count,
                                   pv_format, log_level):
    context = {'pyepics': bench_pyepics_many_connections,
               'curio': bench_curio_many_connections,
               'threading': bench_threading_many_connections,
               'trio': bench_trio_many_connections,
               }[backend]

    pv_names = [pv_format.format(i) for i in range(connection_count)]
    logging.getLogger('caproto').setLevel(log_level)
    with context(pv_names) as bench_fcn:
        benchmark(bench_fcn)
