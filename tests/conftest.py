import pytest
import caproto as ca


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
    for buffer in buffers_to_send:
        srv_circuit.recv(buffer)
    srv_circuit.next_command()
    buffers_to_send = srv_circuit.send(ca.VersionResponse(version=version))
    for buffer in buffers_to_send:
        cli_circuit.recv(buffer)
    cli_circuit.next_command()
    return cli_circuit, srv_circuit
