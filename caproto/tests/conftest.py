import curio
import functools
import os
import pytest
import signal
import subprocess
import sys
import time
from types import SimpleNamespace
import uuid

import caproto as ca
import caproto.benchmarking  # noqa
from caproto.sync.client import get
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

    if module_name == '--script':
        print(f'Running script {args}')
    else:
        print(f'Running {module_name}')
    os.environ['COVERAGE_PROCESS_START'] = '.coveragerc'

    p = subprocess.Popen([sys.executable, '-m', 'caproto.tests.example_runner',
                          module_name] + list(args),
                         stdout=stdout, stderr=stderr, stdin=stdin,
                         env=os.environ)

    def stop_ioc():
        if p.poll() is None:
            print('Sending Ctrl-C to the example IOC')
            p.send_signal(signal.SIGINT)
            print('Waiting on process...')
            p.wait()
            print('IOC has exited')
        else:
            print('Example IOC has already exited')

    if request is not None:
        request.addfinalizer(stop_ioc)

    if pv_to_check:
        poll_readiness(pv_to_check)

    return p


def poll_readiness(pv_to_check, attempts=15):
    print(f'Checking PV {pv_to_check}')
    for attempt in range(attempts):
        try:
            get(pv_to_check, timeout=1)
        except TimeoutError:
            continue
        else:
            break
    else:
        raise TimeoutError(f"ioc fixture failed to start in "
                           f"{attempts} seconds (pv: {pv_to_check})")


def run_softioc(request, db):
    db_text = ca.benchmarking.make_database(db)
    ioc_handler = ca.benchmarking.IocHandler()
    ioc_handler.setup_ioc(db_text=db_text, max_array_bytes='10000000')

    request.addfinalizer(ioc_handler.teardown)

    (pv_to_check, _), *_ = db
    poll_readiness(pv_to_check)
    return ioc_handler


@pytest.fixture(scope='function')
def prefix():
    'Random PV prefix for a server'
    return str(uuid.uuid4())[:8] + ':'


@pytest.fixture(params=['caproto', 'epics-base'], scope='function')
def ioc(request):
    'A fixture that runs more than one IOC: caproto, epics'
    # Get a new prefix for each IOC type:
    prefix_ = prefix()
    if request.param == 'caproto':
        name = 'Caproto type varieties example'
        pvs = dict(int=prefix_ + 'int',
                   float=prefix_ + 'pi',
                   str=prefix_ + 'str',
                   enum=prefix_ + 'enum',
                   )
        process = run_example_ioc('caproto.ioc_examples.type_varieties',
                                  request=request,
                                  pv_to_check=pvs['float'],
                                  args=(prefix_,))
    elif request.param == 'epics-base':
        name = 'Waveform and standard record IOC'
        db = {
            ('{}waveform'.format(prefix_), 'waveform'):
                dict(FTVL='LONG', NELM=4000),
            ('{}float'.format(prefix_), 'ai'): dict(VAL=1),
            ('{}enum'.format(prefix_), 'bi'):
                dict(VAL=1, ZNAM="zero", ONAM="one"),
            ('{}str'.format(prefix_), 'stringout'): dict(VAL='test'),
            ('{}int'.format(prefix_), 'longout'): dict(VAL=1),
        }

        handler = run_softioc(request, db)
        process = handler.processes[-1]
        pvs = {pv[len(prefix_):]: pv
               for pv, rtype in db
               }
    ret = SimpleNamespace(process=process,
                          type=request.param,
                          prefix=prefix_,
                          name=name,
                          pvs=pvs)
    return ret


def start_repeater():
    global _repeater_process
    if _repeater_process is not None:
        return

    print('Spawning repeater process')
    _repeater_process = run_example_ioc('--script',
                                        args=['caproto-repeater', '--verbose'],
                                        request=None,
                                        pv_to_check=None)
    time.sleep(1.0)


def stop_repeater():
    global _repeater_process
    if _repeater_process is None:
        return

    print('[Repeater] Sending Ctrl-C to the repeater')
    _repeater_process.send_signal(signal.SIGINT)
    _repeater_process.wait()
    _repeater_process = None
    print('[Repeater] Repeater exited')



def default_setup_module(module):
    print('-- default module setup {} --'.format(module.__name__))
    start_repeater()


def default_teardown_module(module):
    print('-- default module teardown {} --'.format(module.__name__))
    stop_repeater()


@pytest.fixture(scope='function')
def curio_server(prefix):
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

    # tack on a unique prefix
    caget_pvdb = {prefix + key: value
                  for key, value in caget_pvdb.items()}

    async def _server(pvdb):
        port = find_next_tcp_port(host=SERVER_HOST)
        print('Server will be on', (SERVER_HOST, port))
        ctx = server.Context(SERVER_HOST, port, pvdb, log_level='DEBUG')
        try:
            await ctx.run()
        except server.ServerExit:
            print('ServerExit caught; exiting')
        except Exception as ex:
            print('Server failed', ex)
            raise

    async def run_server(client, *, pvdb=caget_pvdb):
        server_task = await curio.spawn(_server, pvdb, daemon=True)

        try:
            if hasattr(client, 'wait'):
                # NOTE: wrapped by threaded_in_curio_wrapper
                await curio.run_in_thread(client)
                await client.wait()
            else:
                await client()
        except server.ServerExit:
            ...
        finally:
            await server_task.cancel()

    return run_server, prefix, caget_pvdb


async def get_curio_context(log_level='DEBUG'):
    broadcaster = caproto.curio.client.SharedBroadcaster(log_level=log_level)

    await broadcaster.register()
    return caproto.curio.client.Context(broadcaster, log_level=log_level)


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


def environment_epics_version():
    'Return the reported environment being tested on'
    if 'EPICS_BASE' in os.environ and 'BASE' in os.environ:
        base = os.environ['BASE']
        if base.startswith('R'):
            major, minor = base[1:].split('.')[:2]
            return int(major), int(minor)
