import pytest
import queue
import caproto as ca


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
