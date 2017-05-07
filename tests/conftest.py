import os
import sys
import pytest
import queue
import subprocess
import time

import caproto as ca
import caproto.asyncio.repeater


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


def next_command(obj):
    try:
        command = obj.command_queue.get_nowait()
    except queue.Empty:
        return ca.NEED_DATA
    else:
        if command is ca.DISCONNECTED:
            return

    if isinstance(obj, ca.Broadcaster):
        addr, commands = command
        if not commands:
            return ca.NEED_DATA

        history = []
        for command in commands:
            obj.process_command(obj.their_role, command, history=history)
    else:
        obj.process_command(obj.their_role, command)

    return command


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
    srv_circuit.recv(*buffers_to_send)
    next_command(srv_circuit)
    buffers_to_send = srv_circuit.send(ca.VersionResponse(version=version))
    cli_circuit.recv(*buffers_to_send)
    next_command(cli_circuit)
    return cli_circuit, srv_circuit
