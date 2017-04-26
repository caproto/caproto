import pytest
import caproto as ca


def make_channels(cli_circuit, srv_circuit, data_type, data_count):
    cid = 0
    sid = 0
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
    return cli_channel, srv_channel


def test_counter_wraparound(circuit_pair):
    circuit, _ = circuit_pair
    broadcaster = ca.Broadcaster(ca.CLIENT)

    MAX = 2**16
    for i in range(MAX + 2):
        assert i % MAX == circuit.new_channel_id()
        assert i % MAX == circuit.new_subscriptionid()
        assert i % MAX == circuit.new_ioid()
        assert i % MAX == broadcaster.new_search_id()

def test_counter_skipping(circuit_pair):
    circuit, _ = circuit_pair
    broadcaster = ca.Broadcaster(ca.CLIENT)

    broadcaster.unanswered_searches[0] = 'placeholder'
    broadcaster.unanswered_searches[2] = 'placeholder'
    assert broadcaster.new_search_id() == 1
    assert list(broadcaster.unanswered_searches) == [0, 2]
    assert broadcaster.new_search_id() == 3

    circuit.channels[2] = 'placeholder'
    assert circuit.new_channel_id() == 0
    assert circuit.new_channel_id() == 1
    # should skip 2
    assert circuit.new_channel_id() == 3

    circuit._ioids[0] = 'placeholder'
    # should skip 0
    circuit.new_ioid() == 1

    circuit.event_add_commands[0] = 'placeholder'
    # should skip 0
    circuit.new_subscriptionid() == 1


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

    # VersionRequest priority must match prio set above.
    with pytest.raises(ca.LocalProtocolError):
        circuit.send(ca.VersionRequest(version=13, priority=2))


def test_broadcaster():
    with pytest.raises(ca.CaprotoValueError):
        ca.Broadcaster(our_role=None)


def test_unknown_id_errors(circuit_pair):
    circuit, _ = circuit_pair

    # Read a channel that does not exist.
    com = ca.ReadNotifyRequest(data_type=5, data_count=1, sid=1, ioid=1)
    with pytest.raises(ca.LocalProtocolError):
        circuit.send(com)

    # Receive a reading with an unknown ioid.
    com = ca.ReadNotifyResponse(data=(1,), data_type=5, data_count=1, ioid=1,
                                status=1)
    circuit.recv(bytes(com))
    with pytest.raises(ca.RemoteProtocolError):
        circuit.next_command()

    # Receive an event with an unknown subscriptionid.
    com = ca.EventAddResponse(data=(1,), data_type=5, data_count=1,
                              status_code=1, subscriptionid=1)
    circuit.recv(bytes(com))
    with pytest.raises(ca.RemoteProtocolError):
        circuit.next_command()


def test_mismatched_event_add_responses(circuit_pair):
    cli_channel, srv_channel = make_channels(*circuit_pair, 5, 1)
    circuit, _ = circuit_pair

    # Send an EventAddRequest and test legal and illegal responses.
    req = ca.EventAddRequest(data_type=5, data_count=1, sid=0,
                             subscriptionid=1, low=0, high=0, to=0, mask=0)
    circuit.send(req)

    # Good response
    res = ca.EventAddResponse(data=(1,), data_type=5, data_count=1,
                              status_code=1, subscriptionid=1)
    circuit.recv(bytes(res))
    circuit.next_command()

    # Bad response
    res = ca.EventAddResponse(data=(1,), data_type=6, data_count=1,
                              status_code=1, subscriptionid=1)
    circuit.recv(bytes(res))
    with pytest.raises(ca.RemoteProtocolError):
        circuit.next_command()

    # Bad response
    res = ca.EventAddResponse(data=(1, 2), data_type=5, data_count=2,
                              status_code=1, subscriptionid=1)
    circuit.recv(bytes(res))
    with pytest.raises(ca.RemoteProtocolError):
        circuit.next_command()


def test_empty_datagram():
    broadcaster = ca.Broadcaster(ca.CLIENT)
    broadcaster.recv(b'', ('127.0.0.1', 6666))
    assert broadcaster.next_command() is ca.NEED_DATA


def test_extract_address():
    old_style = ca.SearchResponse(port=6666, ip='1.2.3.4', cid=0, version=13)
    old_style.header.parameter1 = 0xffffffff
    old_style.sender_address = ('5.6.7.8', 6666)
    new_style = ca.SearchResponse(port=6666, ip='1.2.3.4', cid=0, version=13)
    ca.extract_address(old_style) == '1.2.3.4'
    ca.extract_address(new_style) == '5.6.7.8'
