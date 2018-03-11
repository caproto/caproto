import curio
import functools
import os
import pytest
import signal
import subprocess
import sys
import time
import uuid

import caproto as ca
import caproto.asyncio
import caproto.asyncio.repeater
import caproto.benchmarking  # noqa
from caproto._cli import get
import caproto.curio  # noqa
import caproto.curio.client  # noqa
import caproto.curio.server  # noqa
import caproto.threading  # noqa
import caproto.threading.client  # noqa
from caproto.curio.server import find_next_tcp_port
import caproto.curio.server as server


str_alarm_status = ca.ChannelAlarm(
    status=ca.AlarmStatus.READ,
    severity=ca.AlarmSeverity.MINOR_ALARM,
    alarm_string='alarm string',
)


_repeater_process = None

REPEATER_PORT = 5065
SERVER_HOST = '0.0.0.0'


def run_example_ioc(module_name, *, request, pv_to_check, args=None,
                    stdin=None, stdout=None, stderr=None):
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

    print(f'Running {module_name}')
    os.environ['COVERAGE_PROCESS_START'] = '.coveragerc'

    # p = subprocess.Popen([sys.executable, '-m', module_name] + args,
    p = subprocess.Popen([sys.executable, '-m', 'caproto.tests.example_runner',
                          module_name] + args,
                         stdout=stdout, stderr=stderr, stdin=stdin,
                         env=os.environ)

    def stop_ioc():
        print(f'Sending Ctrl-C to the example IOC')
        p.send_signal(signal.SIGINT)
        p.wait()

    request.addfinalizer(stop_ioc)

    print(f'Checking PV {pv_to_check}')
    for attempt in range(5):
        try:
            get(pv_to_check, timeout=1.0, verbose=True)
        except TimeoutError:
            print(f'Still trying to connect to {pv_to_check}')
            continue
        else:
            break
    else:
        raise TimeoutError("ioc fixture failed to start in 5 seconds.")

@pytest.fixture(scope='function')
def prefix():
    'Random PV prefix for a server'
    return str(uuid.uuid4())[:8] + ':'


@pytest.fixture(scope='function')
def ioc(request):
    # TODO Randomly generate a prefix and return it.
    # TODO Use a special server specifically for tests.
    return run_example_ioc('caproto.ioc_examples.type_varieties',
                           request=request, pv_to_check='pi')


def start_repeater():
    global _repeater_process
    if _repeater_process is not None:
        return

    print('Spawning repeater process')
    full_repeater_path = os.path.abspath(ca.asyncio.repeater.__file__)
    _repeater_process = subprocess.Popen([sys.executable, full_repeater_path],
                                         env=os.environ)
    print('Started')

    print('Waiting for the repeater to start up...')
    time.sleep(2)


def stop_repeater():
    global _repeater_process
    if _repeater_process is None:
        return

    print('Killing repeater process')
    _repeater_process.terminate()
    print('Waiting')
    _repeater_process.wait()
    print('OK')
    _repeater_process = None


def default_setup_module(module):
    print('-- default module setup {} --'.format(module.__name__))
    start_repeater()


def default_teardown_module(module):
    print('-- default module teardown {} --'.format(module.__name__))
    stop_repeater()


@pytest.fixture(scope='function')
def curio_server():
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
        'char': ca.ChannelChar(value=b'3',
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

    async def run_server():
        port = find_next_tcp_port(host=SERVER_HOST)
        print('Server will be on', (SERVER_HOST, port))
        ctx = server.Context(SERVER_HOST, port, caget_pvdb, log_level='DEBUG')
        try:
            await ctx.run()
        except Exception as ex:
            print('Server failed', ex)
            raise
        finally:
            print('Server exiting')

    return run_server, caget_pvdb


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


# Import the pytest-benchmark -> asv shim if both are available
try:
    __import__('pytest_benchmark')
    __import__('asv')
except ImportError as ex:
    print('{} is missing'.format(ex))
else:
    from ._asv_shim import get_conftest_globals
    globals().update(**get_conftest_globals())


def threaded_in_curio_wrapper(fcn):
    '''Run a threaded test with curio support

    Usage
    -----
    Wrap the threaded function using this wrapper, call the wrapped function
    using `curio.run_in_thread` and then await wrapped_function.wait() inside
    the test kernel.
    '''
    uqueue = curio.UniversalQueue()

    @functools.wraps(fcn)
    def wrapped():
        try:
            fcn()
        except Exception as ex:
            uqueue.put(ex)
        else:
            uqueue.put(None)

    async def wait():
        'Wait for the test function completion'
        res = await uqueue.get()
        if res is not None:
            raise res

    wrapped.wait = wait
    return wrapped


