import pytest
import caproto as ca


def next_command(obj):
    command = obj.command_queue.get_nowait()

    if command is None:
        return ca.NEED_DATA

    if isinstance(obj, ca.Broadcaster):
        obj.process_command(obj.their_role, command, history=[])
    else:
        obj.process_command(obj.their_role, command)


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
