import os
import sys
import pytest
import subprocess
import time

import caproto as ca
import caproto.asyncio
import caproto.asyncio.repeater
import caproto.benchmarking  # noqa
import caproto.curio  # noqa
import caproto.curio.client  # noqa
import caproto.curio.server  # noqa
import caproto.threading  # noqa
import caproto.threading.client  # noqa


_repeater_process = None


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
    from _asv_shim import get_conftest_globals
    globals().update(**get_conftest_globals())
