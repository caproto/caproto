import pytest
import caproto as ca


def test_counter_wraparound(client_circuit):
    circuit = client_circuit

    MAX = 2**16
    for i in range(MAX + 2):
        assert i % MAX == circuit.new_channel_id()
        assert i % MAX == circuit.new_subscriptionid()
        assert i % MAX == circuit.new_ioid()


def test_circuit_properties():
    host = '127.0.0.1'
    port = 5555
    prio = 1

    circuit = ca.VirtualCircuit(ca.CLIENT, (host, port), prio)
    circuit.host == host
    circuit.port == port
    circuit.key == ((host, port), prio)

    # CLIENT circuit needs to know its prio at init time
    with pytest.raises(ca.CaprotoRuntimeError):
        ca.VirtualCircuit(ca.CLIENT, host, None)

    # SERVER circuit does not
    srv_circuit = ca.VirtualCircuit(ca.SERVER, (host, port), None)

    # 'key' is not defined until prio is defined
    with pytest.raises(ca.CaprotoRuntimeError):
        srv_circuit.key
    srv_circuit.priority = prio
    srv_circuit.key

def test_unknown_id_errors(client_circuit):
    circuit = client_circuit

    # Read a channel that does not exist.
    com = ca.ReadNotifyRequest(data_type=5, data_count=1, sid=1, ioid=1)
    with pytest.raises(ca.LocalProtocolError):
        circuit.send(com)

    # Receive a reading with an unknown ioid.
    com = ca.ReadNotifyResponse(values=(1,), data_type=5, data_count=1, ioid=1,
                                status=1)
    circuit.recv(bytes(com))
    with pytest.raises(ca.RemoteProtocolError):
        circuit.next_command()

    # Receive an event with an unknown subscriptionid.
    com = ca.EventAddResponse(values=(1,), data_type=5, data_count=1,
                              status_code=1, subscriptionid=1)
    circuit.recv(bytes(com))
    with pytest.raises(ca.RemoteProtocolError):
        circuit.next_command()

def test_mismatched_event_add_responses(client_channel):
    circuit = client_channel.circuit

    # Send an EventAddRequest and test legal and illegal responses.
    req = ca.EventAddRequest(data_type=5, data_count=1, sid=10,
                             subscriptionid=1, low=0, high=0, to=0, mask=0)
    circuit.send(req)

    # Good response
    res = ca.EventAddResponse(values=(1,), data_type=5, data_count=1,
                              status_code=1, subscriptionid=1)
    circuit.recv(bytes(res))
    circuit.next_command()

    # Bad response
    res = ca.EventAddResponse(values=(1,), data_type=6, data_count=1,
                              status_code=1, subscriptionid=1)
    circuit.recv(bytes(res))
    with pytest.raises(ca.RemoteProtocolError):
        circuit.next_command()

    # Bad response
    res = ca.EventAddResponse(values=([1, 2]), data_type=5, data_count=2,
                              status_code=1, subscriptionid=1)
    circuit.recv(bytes(res))
    with pytest.raises(ca.RemoteProtocolError):
        circuit.next_command()
