import array

import pytest

import caproto as ca
from caproto._dbr import DBR_TIME_CHAR


def make_channels(cli_circuit, srv_circuit, data_type, data_count, name='a'):
    cid = cli_circuit.new_channel_id()
    sid = srv_circuit.new_channel_id()

    cli_channel = ca.ClientChannel(name, cli_circuit, cid)
    srv_channel = ca.ServerChannel(name, srv_circuit, cid)
    req = cli_channel.create()
    cli_circuit.send(req)
    commands, num_bytes_needed = srv_circuit.recv(bytes(req))
    for command in commands:
        srv_circuit.process_command(command)
    res = srv_channel.create(data_type, data_count, sid)
    srv_circuit.send(res)
    commands, num_bytes_needed = cli_circuit.recv(bytes(res))
    for command in commands:
        cli_circuit.process_command(command)
    return cli_channel, srv_channel


@pytest.mark.parametrize('notify', [False, True])
@pytest.mark.parametrize('data_type', [
    None, ca.ChannelType.CHAR, ca.ChannelType.TIME_CHAR,
])
@pytest.mark.parametrize('value', [0, 1, 255])
def test_write_char_scalar(circuit_pair, backends, notify, data_type, value):
    client, server = circuit_pair
    channel, _ = make_channels(client, server, ca.ChannelType.CHAR, 1)

    metadata = (DBR_TIME_CHAR(status=1, severity=2)
                if data_type == ca.ChannelType.TIME_CHAR else None)
    request = channel.write(value, data_type=data_type, metadata=metadata,
                            notify=notify)
    (received,), _ = server.recv(*(bytes(buf) for buf in client.send(request)))
    server.process_command(received)

    expected_type = ca.WriteNotifyRequest if notify else ca.WriteRequest
    assert isinstance(received, expected_type)
    assert received.data_type == (data_type or ca.ChannelType.CHAR)
    assert received.data_count == 1
    assert list(received.data) == [value]
    if metadata is not None:
        assert bytes(received.metadata) == bytes(metadata)


@pytest.mark.parametrize('notify', [False, True])
@pytest.mark.parametrize('data', [
    b'\x00\xff', '\x00\xff', [0, 255], (0, 255), array.array('B', [0, 255]),
])
def test_write_char_sequence(circuit_pair, backends, notify, data):
    client, server = circuit_pair
    channel, _ = make_channels(client, server, ca.ChannelType.CHAR, 8)

    request = channel.write(data, notify=notify)
    (received,), _ = server.recv(*(bytes(buf) for buf in client.send(request)))
    server.process_command(received)

    assert received.data_type == ca.ChannelType.CHAR
    assert received.data_count == 2
    assert list(received.data) == [0, 255]


@pytest.mark.parametrize('notify', [False, True])
def test_write_numpy_char_scalar(circuit_pair, backends, notify):
    numpy = pytest.importorskip('numpy')
    client, server = circuit_pair
    channel, _ = make_channels(client, server, ca.ChannelType.CHAR, 1)

    request = channel.write(numpy.uint8(255), notify=notify)
    (received,), _ = server.recv(*(bytes(buf) for buf in client.send(request)))
    server.process_command(received)

    assert received.data_count == 1
    assert list(received.data) == [255]


@pytest.mark.parametrize('notify', [False, True])
@pytest.mark.parametrize('data_type, value, expected', [
    (ca.ChannelType.INT, -5, -5),
    (ca.ChannelType.LONG, 70000, 70000),
    (ca.ChannelType.DOUBLE, 1.25, 1.25),
    (ca.ChannelType.STRING, 'value', b'value'),
    (ca.ChannelType.STRING, b'value', b'value'),
])
def test_write_scalar(circuit_pair, backends, notify, data_type, value, expected):
    client, server = circuit_pair
    channel, _ = make_channels(client, server, data_type, 1)

    request = channel.write(value, notify=notify)
    (received,), _ = server.recv(*(bytes(buf) for buf in client.send(request)))
    server.process_command(received)

    assert received.data_type == data_type
    assert received.data_count == 1
    assert list(received.data) == [expected]


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
        circuit.send(ca.VersionRequest(
            version=ca.DEFAULT_PROTOCOL_VERSION, priority=2))


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
    (command,), _ = circuit.recv(bytes(com))
    with pytest.raises(ca.RemoteProtocolError):
        circuit.process_command(command)

    # Receive an event with an unknown subscriptionid.
    com = ca.EventAddResponse(data=(1,), data_type=5, data_count=1,
                              status=1, subscriptionid=1)
    (command,), _ = circuit.recv(bytes(com))
    with pytest.raises(ca.RemoteProtocolError):
        circuit.process_command(command)


def test_mismatched_event_add_responses(circuit_pair):
    cli_channel, srv_channel = make_channels(*circuit_pair, 5, 1)
    circuit, _ = circuit_pair

    # Send an EventAddRequest and test legal and illegal responses.
    req = ca.EventAddRequest(data_type=5, data_count=1, sid=0,
                             subscriptionid=1, low=0, high=0, to=0, mask=0)
    circuit.send(req)

    # Good response
    res = ca.EventAddResponse(data=(1,), data_type=5, data_count=1,
                              status=1, subscriptionid=1)
    (command,), _ = circuit.recv(bytes(res))
    circuit.process_command(command)

    # Bad response -- wrong data_type
    res = ca.EventAddResponse(data=(1,), data_type=6, data_count=1,
                              status=1, subscriptionid=1)
    (command,), _ = circuit.recv(bytes(res))
    with pytest.raises(ca.RemoteProtocolError):
        circuit.process_command(command)

    # Bad response -- wrong data_count
    res = ca.EventAddResponse(data=(1, 2), data_type=5, data_count=2,
                              status=1, subscriptionid=1)
    (command,), _ = circuit.recv(bytes(res))
    with pytest.raises(ca.RemoteProtocolError):
        circuit.process_command(command)

    # Bad request -- wrong sid for this subscriptionid
    req = ca.EventCancelRequest(data_type=5, sid=1, subscriptionid=1)
    with pytest.raises(ca.LocalProtocolError):
        circuit.send(req)


def test_empty_datagram():
    broadcaster = ca.Broadcaster(ca.CLIENT)
    commands = broadcaster.recv(b'', ('127.0.0.1', 6666))
    assert commands == []
    # TODO this is an API change from NEED_DATA, but I don't think it's
    # necessarily wrong as these empty broadcast messages are a lack of
    # actual commands


def test_extract_address():
    old_style = ca.SearchResponse(port=6666, ip='1.2.3.4', cid=0,
                                  version=ca.DEFAULT_PROTOCOL_VERSION)
    old_style.header.parameter1 = 0xffffffff
    old_style.sender_address = ('5.6.7.8', 6666)
    new_style = ca.SearchResponse(port=6666, ip='1.2.3.4', cid=0,
                                  version=ca.DEFAULT_PROTOCOL_VERSION)
    ca.extract_address(old_style) == '1.2.3.4'
    ca.extract_address(new_style) == '5.6.7.8'


def test_register_convenience_method():
    broadcaster = ca.Broadcaster(ca.CLIENT)
    broadcaster.register()


def test_broadcaster_checks():
    b = ca.Broadcaster(ca.CLIENT)
    # Similar to check below, not all clients provide the version before
    # the search request so we forgive this one as well
    # with pytest.raises(ca.LocalProtocolError):
    #     b.send(ca.SearchRequest(name='LIRR', cid=0,
    #                             version=ca.DEFAULT_PROTOCOL_VERSION))

    b.send(ca.RepeaterRegisterRequest('1.2.3.4'))
    res = ca.RepeaterConfirmResponse('5.6.7.8')
    commands = b.recv(bytes(res), ('5.6.7.8', 6666))
    assert commands[0] == res
    b.process_commands(commands)

    req = ca.SearchRequest(name='LIRR', cid=0,
                           version=ca.DEFAULT_PROTOCOL_VERSION)
    # commented out for same reason as above and below
    # with pytest.raises(ca.LocalProtocolError):
    #     b.send(req)
    b.send(ca.VersionRequest(priority=0,
                             version=ca.DEFAULT_PROTOCOL_VERSION), req)

    res = ca.SearchResponse(port=6666, ip='1.2.3.4', cid=0,
                            version=ca.DEFAULT_PROTOCOL_VERSION)
    addr = ('1.2.3.4', 6666)
    commands = b.recv(bytes(res), addr)
    # see changes to _broadcaster.py.  Apparently rsrv does not always conform
    # to the protocol and include a version response before search responsesq
    # with pytest.raises(ca.RemoteProtocolError):
    #     b.process_commands(commands)
    # commands = b.recv(bytes(ca.VersionResponse(version=ca.DEFAULT_PROTOCOL_VERSION)) + bytes(res), addr)
    b.process_commands(commands)  # this gets both


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
    (req_received,), _ = srv_circuit.recv(*buffers_to_send)
    srv_circuit.process_command(req_received)
    srv_circuit.send(ca.ErrorResponse(original_request=req_received,
                                      cid=srv_channel.cid,
                                      status=42,
                                      error_message='Tom missed the train.'))


def test_create_channel_failure(circuit_pair):
    cli_circuit, srv_circuit = circuit_pair
    cid = cli_circuit.new_channel_id()
    sid = srv_circuit.new_channel_id()
    cli_channel = ca.ClientChannel('doomed', cli_circuit, cid)
    srv_channel = ca.ServerChannel('doomed', srv_circuit, sid)

    # Send and receive CreateChanRequest
    req = cli_channel.create()
    cli_circuit.send(req)
    commands, _ = srv_circuit.recv(bytes(req))
    for command in commands:
        srv_circuit.process_command(command)

    # Send and receive CreateChFailResponse.
    res = ca.CreateChFailResponse(req.cid)
    buffers_to_send = srv_circuit.send(res)
    assert srv_channel.states[ca.CLIENT] is ca.FAILED
    assert srv_channel.states[ca.SERVER] is ca.FAILED
    assert cli_channel.states[ca.CLIENT] is ca.AWAIT_CREATE_CHAN_RESPONSE
    assert cli_channel.states[ca.SERVER] is ca.SEND_CREATE_CHAN_RESPONSE
    commands, _ = cli_circuit.recv(*buffers_to_send)
    for command in commands:
        cli_circuit.process_command(command)
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
    commands, _ = cli_circuit.recv(*buffers_to_send)
    for command in commands:
        cli_circuit.process_command(command)
    assert cli_channel.states[ca.CLIENT] is ca.CLOSED
    assert cli_channel.states[ca.SERVER] is ca.CLOSED


def test_clear(circuit_pair):
    cli_circuit, srv_circuit = circuit_pair
    cli_channel, srv_channel = make_channels(*circuit_pair, 5, 1, name='a')

    assert cli_channel.states[ca.CLIENT] is ca.CONNECTED
    assert cli_channel.states[ca.SERVER] is ca.CONNECTED

    # Send request to clear.
    buffers_to_send = cli_circuit.send(cli_channel.clear())
    assert cli_channel.states[ca.CLIENT] is ca.MUST_CLOSE
    assert cli_channel.states[ca.SERVER] is ca.MUST_CLOSE

    # Receive request to clear.
    commands, _ = srv_circuit.recv(*buffers_to_send)
    for command in commands:
        srv_circuit.process_command(command)
    assert srv_channel.states[ca.CLIENT] is ca.MUST_CLOSE
    assert srv_channel.states[ca.SERVER] is ca.MUST_CLOSE

    # Send confirmation.
    buffers_to_send = srv_circuit.send(srv_channel.clear())
    assert srv_channel.states[ca.CLIENT] is ca.CLOSED
    assert srv_channel.states[ca.SERVER] is ca.CLOSED

    # Receive confirmation.
    commands, _ = cli_circuit.recv(*buffers_to_send)
    for command in commands:
        cli_circuit.process_command(command)
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
    command = cli_circuit.disconnect()
    cli_circuit.process_command(command)
    command = srv_circuit.disconnect()
    srv_circuit.process_command(command)

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


def test_circuit_equality():
    a = ca.VirtualCircuit(ca.CLIENT, ('asdf', 1234), 1)
    b = ca.VirtualCircuit(ca.CLIENT, ('asdf', 1234), 1)
    c = ca.VirtualCircuit(ca.CLIENT, ('asdf', 1234), 2)
    assert a == b != c


def test_ioid_exhaustion(circuit_pair):
    max_id = 15
    cli_circuit, srv_circuit = circuit_pair
    # make the test run faster by not doing it 2**16 times
    cli_circuit._ioid_counter.MAX_ID = max_id
    srv_circuit._ioid_counter.MAX_ID = max_id

    cli_channel, srv_channel = make_channels(*circuit_pair, 5, 1, name='a')

    data = [1]
    data_count = 1

    # if this is broken it will hang
    for _ in range(max_id + 10):
        # create a read request and serialize
        req = cli_channel.read()
        assert req.ioid < max_id
        buffers_to_send = cli_circuit.send(req)

        # set the bits to the server and create a response
        (command,), _ = srv_circuit.recv(*buffers_to_send)
        srv_circuit.process_command(command)
        assert command.ioid < max_id
        resp = srv_channel.read(data=data, data_type=command.data_type,
                                data_count=data_count, status=0,
                                ioid=command.ioid, metadata=None,
                                notify=True)
        buffers_to_send = srv_circuit.send(resp)

        # send the results back to the client
        (cmd, ), _ = cli_circuit.recv(*buffers_to_send)

        cli_circuit.process_command(cmd)

        # IMPLEMENTATION DETAIL CHECK that will fail quickly,
        # but depends on an implementation detail.
        assert len(cli_circuit._ioids) == 0
        assert len(srv_circuit._ioids) == 0


def test_enum_too_long():
    with pytest.raises(ValueError, match='The maximum enum string length is'):
        ca.ChannelEnum(enum_strings=('a' * 28,))


def test_enum_too_many():
    with pytest.raises(ValueError, match='The maximum number of enum states is'):
        ca.ChannelEnum(enum_strings='a' * 17)
