import array
import functools
import logging
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from types import SimpleNamespace

import pytest

import caproto as ca
import caproto.asyncio  # noqa
import caproto.benchmarking  # noqa
import caproto.threading  # noqa
from caproto.sync.client import read

_repeater_process = None

REPEATER_PORT = 5065
SERVER_HOST = '0.0.0.0'
# make the logs noisy
logger = logging.getLogger('caproto')
logger.setLevel('DEBUG')
# except for the broadcaster
bcast_logger = logging.getLogger('caproto.bcast')
bcast_logger.setLevel('INFO')

array_types = (array.array,)
try:
    import numpy
except ImportError:
    pass
else:
    array_types = array_types + (numpy.ndarray,)


# Don't import these from numpy because we do not assume that numpy is
# installed.


def assert_array_equal(arr1, arr2):
    assert len(arr1) == len(arr2)
    for i, j in zip(arr1, arr2):
        assert i == j


def assert_array_almost_equal(arr1, arr2):
    assert len(arr1) == len(arr2)
    for i, j in zip(arr1, arr2):
        assert abs(i - j) < 1e-6


def run_example_ioc(module_name, *, request, pv_to_check, args=None,
                    stdin=None, stdout=None, stderr=None, very_verbose=True):
    '''Run an example IOC by module name as a subprocess

    Parameters
    ----------
    module_name : str
    request : pytest request
    pv_to_check : str
    args : list, optional
    '''
    if args is None:
        args = []

    if module_name == '--script':
        logger.debug(f'Running script {args}')
    else:
        logger.debug(f'Running {module_name}')

    if '-vvv' not in args and very_verbose:
        args = list(args) + ['-vvv']

    os.environ['COVERAGE_PROCESS_START'] = '.coveragerc'

    p = subprocess.Popen([sys.executable, '-um', 'caproto.tests.example_runner',
                          module_name] + list(args),
                         stdout=stdout, stderr=stderr, stdin=stdin,
                         env=os.environ)

    def stop_ioc():
        if p.poll() is None:
            if sys.platform != 'win32':
                logger.debug('Sending Ctrl-C to the example IOC')
                p.send_signal(signal.SIGINT)
                logger.debug('Waiting on process...')

            try:
                p.wait(timeout=1)
            except subprocess.TimeoutExpired:
                logger.debug('IOC did not exit in a timely fashion')
                p.terminate()
                logger.debug('IOC terminated')
            else:
                logger.debug('IOC has exited')
        else:
            logger.debug('Example IOC has already exited')

    if request is not None:
        request.addfinalizer(stop_ioc)

    if pv_to_check:
        looks_like_areadetector = 'areadetector' in module_name
        if looks_like_areadetector:
            poll_timeout, poll_attempts = 5.0, 5
        else:
            poll_timeout, poll_attempts = 1.0, 5

        poll_readiness(pv_to_check, timeout=poll_timeout,
                       attempts=poll_attempts, process=p)

    return p


def poll_readiness(pv_to_check, attempts=5, timeout=1, process=None):
    logger.debug(f'Checking PV {pv_to_check}')
    start_repeater()
    for _attempt in range(attempts):
        if process is not None and process.returncode is not None:
            raise TimeoutError(f'IOC process exited: {process.returncode}')

        try:
            read(pv_to_check, timeout=timeout, repeater=False)
        except (TimeoutError, ConnectionRefusedError):
            continue
        else:
            break
    else:
        raise TimeoutError(f"ioc fixture failed to start in "
                           f"{attempts * timeout} seconds (pv: {pv_to_check})")


def run_softioc(request, db, additional_db=None, **kwargs):
    db_text = ca.benchmarking.make_database(db)

    if additional_db is not None:
        db_text = '\n'.join((db_text, additional_db))

    err = None
    for _attempt in range(3):
        ioc_handler = ca.benchmarking.IocHandler()
        ioc_handler.setup_ioc(db_text=db_text, max_array_bytes='10000000',
                              **kwargs)

        (pv_to_check, _), *_ = db
        try:
            poll_readiness(pv_to_check, process=ioc_handler.processes[0])
        except TimeoutError as err_:
            err = err_
            ioc_handler.teardown()
        else:
            request.addfinalizer(ioc_handler.teardown)
            return ioc_handler
    else:
        # ran out of retry attempts
        raise err


@pytest.fixture(scope='function')
def prefix():
    'Random PV prefix for a server'
    return str(uuid.uuid4())[:8] + ':'


def _epics_base_ioc(prefix, request):
    if not ca.benchmarking.has_softioc():
        pytest.skip('no softIoc')
    name = 'Waveform and standard record IOC'
    db = {
        ('{}waveform'.format(prefix), 'waveform'):
            dict(FTVL='LONG', NELM=4000),
        ('{}float'.format(prefix), 'ai'): dict(VAL=3.14),
        ('{}enum'.format(prefix), 'bi'):
            dict(VAL=1, ZNAM="a", ONAM="b"),
        ('{}str'.format(prefix), 'stringout'): dict(VAL='test'),
        ('{}int'.format(prefix), 'longout'): dict(VAL=1),
        ('{}int2'.format(prefix), 'longout'): dict(VAL=1),
        ('{}int3'.format(prefix), 'longout'): dict(VAL=1),
    }

    macros = {'P': prefix}
    handler = run_softioc(request, db,
                          additional_db=ca.benchmarking.PYEPICS_TEST_DB,
                          macros=macros)

    process = handler.processes[-1]

    exit_lock = threading.RLock()
    monitor_output = []

    def ioc_monitor():
        process.wait()
        with exit_lock:
            monitor_output.extend([
                '***********************************',
                '********IOC process exited!********',
                f'******* Returned: {process.returncode} ******',
                '***********************************',
            ])

            stdout, stderr = process.communicate()
            if process.returncode != 0:
                if stdout is not None:
                    lines = [f'[Server-stdout] {line}'
                             for line in stdout.decode('latin-1').split('\n')]
                    monitor_output.extend(lines)

                if stderr is not None:
                    lines = [f'[Server-stderr] {line}'
                             for line in stdout.decode('latin-1').split('\n')]
                    monitor_output.extend(lines)

    def ioc_monitor_output():
        with exit_lock:
            if monitor_output:
                logger.debug('IOC monitor output:')
                for line in monitor_output:
                    logger.debug(line)

    request.addfinalizer(ioc_monitor_output)

    threading.Thread(target=ioc_monitor).start()
    pvs = {pv[len(prefix):]: pv
           for pv, rtype in db
           }

    return SimpleNamespace(process=process, prefix=prefix, name=name, pvs=pvs,
                           type='epics-base')


def _caproto_ioc(prefix, request):
    name = 'Caproto type varieties example'
    pvs = dict(int=prefix + 'int',
               int2=prefix + 'int2',
               int3=prefix + 'int3',
               float=prefix + 'pi',
               str=prefix + 'str',
               enum=prefix + 'enum',
               waveform=prefix + 'waveform',
               chararray=prefix + 'chararray',
               empty_string=prefix + 'empty_string',
               empty_bytes=prefix + 'empty_bytes',
               empty_char=prefix + 'empty_char',
               empty_float=prefix + 'empty_float',
               )
    process = run_example_ioc('caproto.ioc_examples.type_varieties',
                              request=request,
                              pv_to_check=pvs['float'],
                              args=('--prefix', prefix,))
    return SimpleNamespace(process=process, prefix=prefix, name=name, pvs=pvs,
                           type='caproto')


caproto_ioc = pytest.fixture(scope='function')(_caproto_ioc)
epics_base_ioc = pytest.fixture(scope='function')(_epics_base_ioc)


@pytest.fixture(params=['caproto', 'epics-base'], scope='function')
def ioc_factory(prefix, request):
    'A fixture that runs more than one IOC: caproto, epics'
    # Get a new prefix for each IOC type:
    if request.param == 'caproto':
        return functools.partial(_caproto_ioc, prefix, request)
    elif request.param == 'epics-base':
        return functools.partial(_epics_base_ioc, prefix, request)


@pytest.fixture(params=['caproto', 'epics-base'], scope='function')
def ioc(prefix, request):
    'A fixture that runs more than one IOC: caproto, epics'
    # Get a new prefix for each IOC type:
    if request.param == 'caproto':
        ioc_ = _caproto_ioc(prefix, request)
    elif request.param == 'epics-base':
        ioc_ = _epics_base_ioc(prefix, request)

    return ioc_


def start_repeater():
    global _repeater_process
    if _repeater_process is not None:
        return

    logger.info('Spawning repeater process')
    _repeater_process = run_example_ioc('--script',
                                        args=['caproto-repeater'],
                                        request=None,
                                        pv_to_check=None)
    time.sleep(1.0)


def stop_repeater():
    global _repeater_process
    if _repeater_process is None:
        return

    logger.info('[Repeater] Sending Ctrl-C to the repeater')
    if sys.platform == 'win32':
        _repeater_process.terminate()
    else:
        _repeater_process.send_signal(signal.SIGINT)
    _repeater_process.wait()
    _repeater_process = None
    logger.info('[Repeater] Repeater exited')


def default_setup_module(module):
    logger.info('-- default module setup {} --'.format(module.__name__))
    start_repeater()


def default_teardown_module(module):
    logger.info('-- default module teardown {} --'.format(module.__name__))
    stop_repeater()


@pytest.fixture(scope='function')
def pvdb_from_server_example():
    alarm = ca.ChannelAlarm(
        status=ca.AlarmStatus.READ,
        severity=ca.AlarmSeverity.MINOR_ALARM,
        alarm_string='alarm string',
    )

    pvdb = {
        'pi': ca.ChannelDouble(value=3.14,
                               lower_disp_limit=3.13,
                               upper_disp_limit=3.15,
                               lower_alarm_limit=3.12,
                               upper_alarm_limit=3.16,
                               lower_warning_limit=3.11,
                               upper_warning_limit=3.17,
                               lower_ctrl_limit=3.10,
                               upper_ctrl_limit=3.18,
                               precision=5,
                               units='doodles',
                               alarm=alarm,
                               ),
        'enum': ca.ChannelEnum(value='b',
                               enum_strings=['a', 'b', 'c', 'd'],
                               ),
        'enum2': ca.ChannelEnum(value='bb',
                                enum_strings=['aa', 'bb', 'cc', 'dd'],
                                ),
        'int': ca.ChannelInteger(value=96,
                                 units='doodles',
                                 ),
        'char': ca.ChannelByte(value=b'3',
                               units='poodles',
                               lower_disp_limit=33,
                               upper_disp_limit=35,
                               lower_alarm_limit=32,
                               upper_alarm_limit=36,
                               lower_warning_limit=31,
                               upper_warning_limit=37,
                               lower_ctrl_limit=30,
                               upper_ctrl_limit=38,
                               ),
        'bytearray': ca.ChannelByte(value=b'1234567890' * 2),
        'chararray': ca.ChannelChar(value=b'1234567890' * 2),
        'str': ca.ChannelString(value='hello',
                                string_encoding='latin-1',
                                alarm=alarm),
        'str2': ca.ChannelString(value='hello',
                                 string_encoding='latin-1',
                                 alarm=alarm),
        'stra': ca.ChannelString(value=['hello', 'how is it', 'going'],
                                 string_encoding='latin-1'),
    }

    return pvdb


@pytest.fixture(scope='function')
def curio_server(prefix):
    str_alarm_status = ca.ChannelAlarm(
        status=ca.AlarmStatus.READ,
        severity=ca.AlarmSeverity.MINOR_ALARM,
        alarm_string='alarm string',
    )

    caget_pvdb = {
        'pi': ca.ChannelDouble(value=3.14,
                               lower_disp_limit=3.13,
                               upper_disp_limit=3.15,
                               lower_alarm_limit=3.12,
                               upper_alarm_limit=3.16,
                               lower_warning_limit=3.11,
                               upper_warning_limit=3.17,
                               lower_ctrl_limit=3.10,
                               upper_ctrl_limit=3.18,
                               precision=5,
                               units='doodles',
                               ),
        'enum': ca.ChannelEnum(value='b',
                               enum_strings=['a', 'b', 'c', 'd'],
                               ),
        'int': ca.ChannelInteger(value=33,
                                 units='poodles',
                                 lower_disp_limit=33,
                                 upper_disp_limit=35,
                                 lower_alarm_limit=32,
                                 upper_alarm_limit=36,
                                 lower_warning_limit=31,
                                 upper_warning_limit=37,
                                 lower_ctrl_limit=30,
                                 upper_ctrl_limit=38,
                                 ),
        'char': ca.ChannelByte(value=b'3',
                               units='poodles',
                               lower_disp_limit=33,
                               upper_disp_limit=35,
                               lower_alarm_limit=32,
                               upper_alarm_limit=36,
                               lower_warning_limit=31,
                               upper_warning_limit=37,
                               lower_ctrl_limit=30,
                               upper_ctrl_limit=38,
                               ),
        'str': ca.ChannelString(value='hello',
                                alarm=str_alarm_status,
                                reported_record_type='caproto'),
    }

    # tack on a unique prefix
    caget_pvdb = {prefix + key: value
                  for key, value in caget_pvdb.items()}

    # Hide these imports so that the other fixtures are usable by other
    # libraries (e.g. ophyd) without the experimental dependencies.
    import curio

    import caproto.curio

    async def _server(pvdb):
        ctx = caproto.curio.server.Context(pvdb)
        try:
            await ctx.run()
        except caproto.curio.server.ServerExit:
            logger.info('ServerExit caught; exiting')
        except Exception as ex:
            logger.error('Server failed: %s %s', type(ex), ex)
            raise

    async def run_server(client, *, pvdb=caget_pvdb):
        server_task = await curio.spawn(_server, pvdb, daemon=True)

        try:
            await client()
        except caproto.curio.server.ServerExit:
            ...
        finally:
            await server_task.cancel()

    return run_server, prefix, caget_pvdb


@pytest.fixture(scope='function',
                params=['curio', 'trio', 'asyncio'])
def server(request):

    def curio_runner(pvdb, client, *, threaded_client=False):
        # Hide these imports so that the other fixtures are usable by other
        # libraries (e.g. ophyd) without the experimental dependencies.
        import curio

        import caproto.curio

        async def server_main():
            try:
                ctx = caproto.curio.server.Context(pvdb)
                await ctx.run()
            except caproto.curio.server.ServerExit:
                logger.info('Server exited normally')
            except Exception as ex:
                logger.error('Server failed: %s %s', type(ex), ex)
                raise

        async def run_server_and_client():
            try:
                server_task = await curio.spawn(server_main)
                # Give this a couple tries, akin to poll_readiness.
                for _ in range(15):
                    try:
                        if threaded_client:
                            await threaded_in_curio_wrapper(client)()
                        else:
                            await client()
                    except TimeoutError:
                        continue
                    else:
                        break
                else:
                    raise TimeoutError("ioc failed to start")
            finally:
                await server_task.cancel()

        with curio.Kernel() as kernel:
            kernel.run(run_server_and_client)

    def trio_runner(pvdb, client, *, threaded_client=False):
        # Hide these imports so that the other fixtures are usable by other
        # libraries (e.g. ophyd) without the experimental dependencies.
        import trio

        import caproto.trio

        async def trio_server_main(task_status):
            try:
                ctx = caproto.trio.server.Context(pvdb)
                task_status.started(ctx)
                await ctx.run()
            except Exception as ex:
                logger.error('Server failed: %s %s', type(ex), ex)
                raise

        async def run_server_and_client():
            async with trio.open_nursery() as test_nursery:
                server_context = await test_nursery.start(trio_server_main)
                # Give this a couple tries, akin to poll_readiness.
                for _ in range(15):
                    try:
                        if threaded_client:
                            await trio.to_thread.run_sync(client)
                        else:
                            await client(test_nursery, server_context)
                    except TimeoutError:
                        continue
                    else:
                        break
                server_context.stop()
                # don't leave the server running:
                test_nursery.cancel_scope.cancel()

        trio.run(run_server_and_client)

    def asyncio_runner(pvdb, client, *, threaded_client=False):
        import asyncio

        async def asyncio_server_main():
            try:
                ctx = caproto.asyncio.server.Context(pvdb)
                await ctx.run()
            except Exception as ex:
                logger.error('Server failed: %s %s', type(ex), ex)
                raise

        async def run_server_and_client(loop):
            tsk = loop.create_task(asyncio_server_main())
            # Give this a couple tries, akin to poll_readiness.
            for _ in range(15):
                try:
                    if threaded_client:
                        await loop.run_in_executor(client)
                    else:
                        await client()
                except TimeoutError:
                    continue
                else:
                    break
            tsk.cancel()
            await asyncio.wait((tsk, ))

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_server_and_client(loop))

    if request.param == 'curio':
        curio_runner.backend = 'curio'
        return curio_runner
    elif request.param == 'trio':
        trio_runner.backend = 'trio'
        return trio_runner
    elif request.param == 'asyncio':
        asyncio_runner.backend = 'asyncio'
        return asyncio_runner


def pytest_make_parametrize_id(config, val, argname):
    # FIX for python 3.6.3 and/or pytest 3.3.0
    if isinstance(val, bytes):
        return repr(val)


@pytest.fixture(scope='function')
def circuit_pair(request):
    host = '127.0.0.1'
    port = 5555
    priority = 1
    version = 13
    cli_circuit = ca.VirtualCircuit(ca.CLIENT, (host, port), priority)
    buffers_to_send = cli_circuit.send(ca.VersionRequest(version=version,
                                                         priority=priority))

    srv_circuit = ca.VirtualCircuit(ca.SERVER, (host, port), None)
    commands, _ = srv_circuit.recv(*buffers_to_send)
    for command in commands:
        srv_circuit.process_command(command)
    buffers_to_send = srv_circuit.send(ca.VersionResponse(version=version))
    commands, _ = cli_circuit.recv(*buffers_to_send)
    for command in commands:
        cli_circuit.process_command(command)
    return cli_circuit, srv_circuit


def threaded_in_curio_wrapper(fcn):
    '''Run a threaded test with curio support

    Usage
    -----
    Wrap the threaded function using this wrapper, call the wrapped function
    using `curio.run_in_thread` and then await wrapped_function.wait() inside
    the test kernel.
    '''
    # Hide this import so that the other fixtures are usable by other
    # libraries (e.g. ophyd) without the experimental dependencies.
    import curio
    uqueue = curio.UniversalQueue()

    def wrapped_threaded_func():
        try:
            fcn()
        except Exception as ex:
            uqueue.put(ex)
        else:
            uqueue.put(None)

    @functools.wraps(fcn)
    async def test_runner():
        'Wait for the test function completion'
        await curio.run_in_thread(wrapped_threaded_func)
        res = await uqueue.get()
        if res is not None:
            raise res

    return test_runner


@pytest.fixture(scope='function', params=['array', 'numpy'])
def backends(request):
    from caproto import backend, select_backend

    def switch_back():
        select_backend(initial_backend)

    initial_backend = backend.backend_name
    request.addfinalizer(switch_back)

    try:
        select_backend(request.param)
    except KeyError:
        raise pytest.skip(f'backend {request.param} unavailable')


def dump_process_output(prefix, stdout, stderr):
    print('-- Process stdout --')
    if stdout is not None:
        for line in stdout.decode('latin-1').split('\n'):
            print(f'[{prefix}-stdout]', line)
    print('-- Process stderr --')
    if stderr is not None:
        for line in stderr.decode('latin-1').split('\n'):
            print(f'[{prefix}-stderr]', line)
    print('--')


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    'Socket and thread debugging hook'
    from .debug import use_debug_socket, use_thread_counter

    with use_thread_counter() as (dangling_threads, thread_counter):
        with use_debug_socket() as (sockets, socket_counter):
            yield

    num_dangling = len(dangling_threads)
    num_threads = thread_counter.value

    if num_threads:
        if num_dangling:
            thread_info = ', '.join(str(thread) for thread in dangling_threads)
            logger.warning('%d thread(s) left dangling out of %d! %s',
                           num_dangling, num_threads, thread_info)
            # pytest.fail() ?
        else:
            logger.debug('%d thread(s) OK', num_threads)

    item.user_properties.append(('total_threads', num_threads))
    item.user_properties.append(('dangling_threads', num_dangling))

    num_sockets = socket_counter.value
    num_open = len(sockets)

    if num_sockets:
        if num_open:
            logger.warning('%d sockets still open of %d', num_open,
                           num_sockets)
            # pytest.fail() ?
        else:
            logger.debug('%d sockets OK', socket_counter.value)

    item.user_properties.append(('total_sockets', num_sockets))
    item.user_properties.append(('open_sockets', num_open))


@pytest.fixture(scope='session', params=list(ca.server.records.records))
def record_type_name(request):
    return request.param
