import pytest
import caproto as ca


@pytest.fixture(scope='function')
def circuit(request):
    host = '127.0.0.1'
    port = 5555
    prio = 1
    circuit = ca.VirtualCircuit(ca.CLIENT, (host, port), prio)
    return circuit
