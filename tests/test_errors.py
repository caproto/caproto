import pytest
import caproto as ca


def test_prio_required():
    host = '127.0.0.1'
    port = 5555
    prio = 1
    circuit = ca.VirtualCircuit(ca.CLIENT, (host, port), prio)
    circuit.host == host
    circuit.port == port
    circuit.key == ((host, port), prio)

    with pytest.raises(ca.CaprotoRuntimeError):
        ca.VirtualCircuit(ca.CLIENT, host, None)

    srv_circuit = ca.VirtualCircuit(ca.SERVER, (host, port), None)

    with pytest.raises(ca.CaprotoRuntimeError):
        srv_circuit.key
