import pytest
import caproto as ca


def make_channels(cli_circuit, srv_circuit, data_type, data_count, name='a'):
    cid = cli_circuit.new_channel_id()
    sid = srv_circuit.new_channel_id()

    cli_channel = ca.ClientChannel(name, cli_circuit, cid)
    srv_channel = ca.ServerChannel(name, srv_circuit, cid)
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

    # Bad response -- wrong data_type
    res = ca.EventAddResponse(data=(1,), data_type=6, data_count=1,
                              status_code=1, subscriptionid=1)
    circuit.recv(bytes(res))
    with pytest.raises(ca.RemoteProtocolError):
        circuit.next_command()

    # Bad response -- wrong data_count
    res = ca.EventAddResponse(data=(1, 2), data_type=5, data_count=2,
                              status_code=1, subscriptionid=1)
    circuit.recv(bytes(res))
    with pytest.raises(ca.RemoteProtocolError):
        circuit.next_command()

    # Bad request -- wrong sid for this subscriptionid
    req = ca.EventCancelRequest(data_type=5, sid=1, subscriptionid=1)
    with pytest.raises(ca.LocalProtocolError):
        circuit.send(req)


def test_empty_datagram():
    broadcaster = ca.Broadcaster(ca.CLIENT)
    broadcaster.recv(b'', ('127.0.0.1', 6666))
    addr, command = broadcaster.next_command()
    assert command is None
    # TODO this is an API change from NEED_DATA, but I don't think it's
    # necessarily wrong as these empty broadcast messages are a lack of
    # actual commands


def test_extract_address():
    old_style = ca.SearchResponse(port=6666, ip='1.2.3.4', cid=0, version=13)
    old_style.header.parameter1 = 0xffffffff
    old_style.sender_address = ('5.6.7.8', 6666)
    new_style = ca.SearchResponse(port=6666, ip='1.2.3.4', cid=0, version=13)
    ca.extract_address(old_style) == '1.2.3.4'
    ca.extract_address(new_style) == '5.6.7.8'


def test_register_convenience_method():
    broadcaster = ca.Broadcaster(ca.CLIENT)
    broadcaster.register()


def test_broadcaster_checks():
    b = ca.Broadcaster(ca.CLIENT)
    with pytest.raises(ca.LocalProtocolError):
        b.send(ca.SearchRequest(name='LIRR', cid=0, version=13))

    b.send(ca.RepeaterRegisterRequest('1.2.3.4'))
    res = ca.RepeaterConfirmResponse('5.6.7.8')
    b.recv(bytes(res), ('5.6.7.8', 6666))
    assert b.next_command()[1] == res

    req = ca.SearchRequest(name='LIRR', cid=0, version=13)
    with pytest.raises(ca.LocalProtocolError):
        b.send(req)
    b.send(ca.VersionRequest(priority=0, version=13), req)

    res = ca.SearchResponse(port=6666, ip='1.2.3.4', cid=0, version=13)
    addr = ('1.2.3.4', 6666)
    b.recv(bytes(res), addr)
    with pytest.raises(ca.RemoteProtocolError):
        b.next_command()
    b.recv(bytes(ca.VersionResponse(version=13)) + bytes(res), addr)
    b.next_command()  # this gets both


def test_methods(circuit_pair):
    # testing lines in channel convenience methods not otherwise covered
    cli_circuit, srv_circuit = circuit_pair
    cli_channel1, srv_channel1 = make_channels(*circuit_pair, 5, 1, name='a')
    cli_channel2, srv_channel2 = make_channels(*circuit_pair, 5, 1, name='b')

    # smoke test
    srv_channel1.version()
    srv_channel1.create_fail()

    # Subscribe to two channels on the same circuit.
    req1 = cli_channel1.subscribe()
    cli_circuit.send(req1)
    req2 = cli_channel2.subscribe()
    cli_circuit.send(req2)
    req3 = cli_channel2.subscribe()
    cli_circuit.send(req3)

    # Non-existent subscriptionid
    with pytest.raises(ca.CaprotoKeyError):
        cli_circuit.send(cli_channel1.unsubscribe(67))
    # Wrong channel's subscriptionid (req3 but cli_channel1)
    with pytest.raises(ca.CaprotoValueError):
        cli_circuit.send(cli_channel1.unsubscribe(req3.subscriptionid))


def test_error_response(circuit_pair):
    cli_circuit, srv_circuit = circuit_pair
    cli_channel, srv_channel = make_channels(*circuit_pair, 5, 1, name='a')
    req = cli_channel.read()
    buffers_to_send = cli_circuit.send(req)
    srv_circuit.recv(*buffers_to_send)
    req_received = srv_circuit.next_command()
    srv_circuit.send(ca.ErrorResponse(original_request=req_received,
                                      cid=srv_channel.cid,
                                      status_code=42,
                                      error_message='Tom missed the train.'))


def test_create_channel_failure(circuit_pair):
    cli_circuit, srv_circuit = circuit_pair
    cid = cli_circuit.new_channel_id()
    sid = srv_circuit.new_channel_id()
    cli_channel = ca.ClientChannel('doomed', cli_circuit, cid)
    srv_channel = ca.ServerChannel('doomed', srv_circuit, cid)

    # Send and receive CreateChanRequest
    req = cli_channel.create()
    cli_circuit.send(req)
    srv_circuit.recv(bytes(req))
    srv_circuit.next_command()

    # Send and receive CreateChFailResponse.
    res = ca.CreateChFailResponse(req.cid)
    buffers_to_send = srv_circuit.send(res)
    assert srv_channel.states[ca.CLIENT] is ca.FAILED
    assert srv_channel.states[ca.SERVER] is ca.FAILED
    assert cli_channel.states[ca.CLIENT] is ca.AWAIT_CREATE_CHAN_RESPONSE
    assert cli_channel.states[ca.SERVER] is ca.SEND_CREATE_CHAN_RESPONSE
    cli_circuit.recv(*buffers_to_send)
    cli_circuit.next_command()
    assert cli_channel.states[ca.CLIENT] is ca.FAILED
    assert cli_channel.states[ca.SERVER] is ca.FAILED


def test_server_disconn(circuit_pair):
    cli_circuit, srv_circuit = circuit_pair
    cli_channel, srv_channel = make_channels(*circuit_pair, 5, 1, name='a')

    buffers_to_send = srv_circuit.send(srv_channel.disconnect())
    assert srv_channel.states[ca.CLIENT] is ca.CLOSED
    assert srv_channel.states[ca.SERVER] is ca.CLOSED
    assert cli_channel.states[ca.CLIENT] is ca.CONNECTED
    assert cli_channel.states[ca.SERVER] is ca.CONNECTED
    cli_circuit.recv(*buffers_to_send)
    cli_circuit.next_command()
    assert cli_channel.states[ca.CLIENT] is ca.CLOSED
    assert cli_channel.states[ca.SERVER] is ca.CLOSED


def test_clear(circuit_pair):
    cli_circuit, srv_circuit = circuit_pair
    cli_channel, srv_channel = make_channels(*circuit_pair, 5, 1, name='a')

    assert cli_channel.states[ca.CLIENT] is ca.CONNECTED
    assert cli_channel.states[ca.SERVER] is ca.CONNECTED

    # Send request to clear.
    buffers_to_send = cli_circuit.send(cli_channel.disconnect())
    assert cli_channel.states[ca.CLIENT] is ca.MUST_CLOSE
    assert cli_channel.states[ca.SERVER] is ca.MUST_CLOSE

    # Receive request to clear.
    srv_circuit.recv(*buffers_to_send)
    srv_circuit.next_command()
    assert srv_channel.states[ca.CLIENT] is ca.MUST_CLOSE
    assert srv_channel.states[ca.SERVER] is ca.MUST_CLOSE

    # Send confirmation.
    buffers_to_send = srv_circuit.send(srv_channel.disconnect())
    assert srv_channel.states[ca.CLIENT] is ca.CLOSED
    assert srv_channel.states[ca.SERVER] is ca.CLOSED

    # Receive confirmation.
    cli_circuit.recv(*buffers_to_send)
    cli_circuit.next_command()
    assert cli_channel.states[ca.CLIENT] is ca.CLOSED
    assert cli_channel.states[ca.SERVER] is ca.CLOSED


def test_dead_circuit(circuit_pair):
    # Connect two channels.
    cli_circuit, srv_circuit = circuit_pair
    cli_channel1, srv_channel1 = make_channels(*circuit_pair, 5, 1, name='a')
    cli_channel2, srv_channel2 = make_channels(*circuit_pair, 5, 1, name='b')

    # Check states.
    assert cli_circuit.states[ca.CLIENT] is ca.CONNECTED
    assert srv_circuit.states[ca.CLIENT] is ca.CONNECTED
    assert cli_circuit.states[ca.SERVER] is ca.CONNECTED
    assert srv_circuit.states[ca.SERVER] is ca.CONNECTED
    assert cli_channel1.states[ca.CLIENT] is ca.CONNECTED
    assert srv_channel1.states[ca.CLIENT] is ca.CONNECTED
    assert cli_channel1.states[ca.SERVER] is ca.CONNECTED
    assert srv_channel1.states[ca.SERVER] is ca.CONNECTED
    assert cli_channel2.states[ca.CLIENT] is ca.CONNECTED
    assert srv_channel2.states[ca.CLIENT] is ca.CONNECTED
    assert cli_channel2.states[ca.SERVER] is ca.CONNECTED
    assert srv_channel2.states[ca.SERVER] is ca.CONNECTED

    # Notify the circuit that its connection was dropped.
    cli_circuit.disconnect()
    srv_circuit.disconnect()

    # Check that state updates.
    assert cli_circuit.states[ca.CLIENT] is ca.DISCONNECTED
    assert srv_circuit.states[ca.CLIENT] is ca.DISCONNECTED
    assert cli_circuit.states[ca.SERVER] is ca.DISCONNECTED
    assert srv_circuit.states[ca.SERVER] is ca.DISCONNECTED
    assert cli_channel1.states[ca.CLIENT] is ca.CLOSED
    assert srv_channel1.states[ca.CLIENT] is ca.CLOSED
    assert cli_channel1.states[ca.SERVER] is ca.CLOSED
    assert srv_channel1.states[ca.SERVER] is ca.CLOSED
    assert cli_channel2.states[ca.CLIENT] is ca.CLOSED
    assert srv_channel2.states[ca.CLIENT] is ca.CLOSED
    assert cli_channel2.states[ca.SERVER] is ca.CLOSED
    assert srv_channel2.states[ca.SERVER] is ca.CLOSED
