import pytest
import caproto as ca


@pytest.fixture(scope='function')
def client_circuit(request):
    host = '127.0.0.1'
    port = 5555
    prio = 1
    circuit = ca.VirtualCircuit(ca.CLIENT, (host, port), prio)
    return circuit


@pytest.fixture(scope='function')
def client_channel(request):
    host = '127.0.0.1'
    port = 5555
    prio = 1
    cid = 1
    sid = 10
    data_type = 5
    data_count = 1
    cli_circuit = ca.VirtualCircuit(ca.CLIENT, (host, port), prio)
    srv_circuit = ca.VirtualCircuit(ca.SERVER, (host, port), prio)
    cli_channel = ca.ClientChannel('name', cli_circuit, cid)
    srv_channel = ca.ServerChannel('name', srv_circuit, cid)
    req = cli_channel.create()
    cli_circuit.send(req)
    srv_circuit.recv(bytes(req))
    srv_circuit.next_command()
    res = srv_channel.create(data_type, data_count, sid)
    srv_circuit.send(res)
    cli_circuit.recv(bytes(res))
    cli_circuit.next_command()
    return cli_channel
