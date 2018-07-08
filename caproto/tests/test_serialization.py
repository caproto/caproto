import array
import copy
import ctypes

import caproto as ca
from caproto._dbr import DBR_LONG, DBR_TIME_DOUBLE, TimeStamp
from caproto._commands import read_datagram, bytelen, Message
from caproto._headers import MessageHeader, ExtendedMessageHeader
import inspect
import pytest
from .conftest import assert_array_equal, assert_array_almost_equal


ip = '255.255.255.255'


parameter_values = {
    'address': [ip],
    'client_address': [ip],
    'ip': [ip],
    'repeater_address': [ip],

    'access_rights': [3],
    'beacon_id': [3],
    'cid': [2],
    'data_count': [1],
    'data_type': [DBR_LONG.DBR_ID],
    'error_message': ['error msg'],
    'header': [9],
    'high': [27],
    'ioid': [3],
    'low': [8],
    'mask': [3],
    'metadata': [None],
    'name': ['name'],
    'original_request': [ca.CreateChanRequest('test', 0, 1)],
    'payload': [DBR_LONG(5)],
    'port': [4321],
    'priority': [0],
    'reply': [ca.NO_REPLY],
    'server_port': [1234],
    'sid': [2],
    'status': [1],
    'subscriptionid': [5],
    'to': [7],
    'validate': [1],
    'data': [[1], ],
    'version': [13],
}

all_commands = set(ca._commands._commands) - set([Message])


def _np_hack(buf):
    try:
        return buf.tobytes()
    except AttributeError:
        return bytes(buf)


@pytest.mark.parametrize('cmd', all_commands)
def test_serialize(cmd):
    print()
    print('--- {} ---'.format(cmd))
    sig = inspect.signature(cmd)
    bind_args = {}
    for param in sig.parameters.keys():
        # TODO all combinations of those in the list
        bind_args[param] = parameter_values[param][0]

    ba = sig.bind(**bind_args)

    print(cmd, ba.arguments)
    inst = cmd(*ba.args, **ba.kwargs)

    role = (ca.CLIENT if cmd.DIRECTION is ca.REQUEST
            else ca.SERVER)

    print('inst', bytes(inst))
    print('    ', inst)
    print('    ', bytes(inst.header))
    print('    ', inst.buffers)
    print('    ', inst.header.payload_size)
    print('    dt ', inst.header.data_type)

    wire_inst = read_datagram(bytes(inst), ('addr', 0), role)[0]
    print('wire', bytes(wire_inst))
    print('    ', wire_inst)
    print('    ', bytes(wire_inst.header))
    print('    ', wire_inst.buffers)
    print('    ', wire_inst.header.payload_size)
    assert bytes(wire_inst.header) == bytes(inst.header)
    print('    dt ', wire_inst.header.data_type)
    assert wire_inst == inst

    # Smoke test properties.
    signature = inspect.signature(type(inst))
    for arg in signature.parameters:
        getattr(inst, arg)
        getattr(wire_inst, arg)
    len(inst)
    inst.nbytes


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


# Define big-endian arrays for use below in test_reads and test_writes.
int_arr = ca.Array('h', [7, 21, 2, 4, 5])
int_arr.byteswap()
float_arr = ca.Array('f', [7, 21.1, 3.1])
float_arr.byteswap()
long_arr = ca.Array('i', [7, 21, 2, 4, 5])
long_arr.byteswap()
double_arr = ca.Array('d', [7, 21.1, 3.1])
double_arr.byteswap()

payloads = [
    # data_type, data_count, data, metadata
    (ca.ChannelType.INT, 1, (7,), None),
    (ca.ChannelType.INT, 5, (7, 21, 2, 4, 5), None),
    (ca.ChannelType.INT, 5, int_arr, None),
    (ca.ChannelType.INT, 5, bytes(int_arr), None),

    (ca.ChannelType.FLOAT, 1, (7,), None),
    (ca.ChannelType.FLOAT, 3, (7, 21.1, 3.1), None),
    (ca.ChannelType.FLOAT, 3, float_arr, None),
    (ca.ChannelType.FLOAT, 3, bytes(float_arr), None),

    (ca.ChannelType.LONG, 1, (7,), None),
    (ca.ChannelType.LONG, 2, (7, 21), None),
    (ca.ChannelType.LONG, 5, long_arr, None),
    (ca.ChannelType.LONG, 5, bytes(long_arr), None),

    (ca.ChannelType.DOUBLE, 1, (7,), None),
    (ca.ChannelType.DOUBLE, 6, (7, 21.1, 7, 7, 2.1, 1.1), None),
    (ca.ChannelType.DOUBLE, 3, double_arr, None),
    (ca.ChannelType.DOUBLE, 3, bytes(double_arr), None),

    (ca.ChannelType.TIME_DOUBLE, 1, (7,),
     DBR_TIME_DOUBLE(1, 0, TimeStamp(3, 5))),
    (ca.ChannelType.TIME_DOUBLE, 1, (7,), (1, 0, TimeStamp(3, 5))),
    (ca.ChannelType.TIME_DOUBLE, 2, (7, 3.4), (1, 0, TimeStamp(3, 5))),

    (ca.ChannelType.STRING, 1, b'abc'.ljust(40, b'\x00'), None),
    (ca.ChannelType.STRING, 3, 3 * b'abc'.ljust(40, b'\x00'), None),
    (ca.ChannelType.CHAR, 1, b'z', None),
    (ca.ChannelType.CHAR, 3, b'abc', None),
]

try:
    import numpy
except ImportError:
    pass
else:
    payloads += [
        (ca.ChannelType.INT, 5, numpy.array([7, 21, 2, 4, 5], dtype='i2'), None),
        (ca.ChannelType.FLOAT, 3, numpy.array([7, 21.1, 3.1], dtype='f4'), None),
        (ca.ChannelType.LONG, 5, numpy.array([7, 21, 2, 4, 5], dtype='i4'), None),
        (ca.ChannelType.DOUBLE, 3, numpy.array([7, 21.1, 3.1], dtype='f8'), None),
        (ca.ChannelType.STRING, 2, numpy.array(['abc', 'def'], '>S40'), None),
        (ca.ChannelType.STRING, 2, numpy.array(['abc', 'def'], 'S40'), None),
    ]


@pytest.mark.parametrize('data_type, data_count, data, metadata', payloads)
def test_reads(backends, circuit_pair, data_type, data_count, data, metadata):
    print('-------------------------------')
    print(data_type, data_count, data)

    cli_circuit, srv_circuit = circuit_pair
    cli_channel, srv_channel = make_channels(*circuit_pair, data_type,
                                             data_count)

    req = ca.ReadNotifyRequest(data_count=data_count, data_type=data_type,
                               ioid=0, sid=0)
    buffers_to_send = cli_circuit.send(req)
    # Socket transport would happen here. Calling bytes() simulates
    # serialization over the socket.
    commands, _ = srv_circuit.recv(*(_np_hack(buf) for buf in buffers_to_send))
    for command in commands:
        srv_circuit.process_command(command)
    res = ca.ReadNotifyResponse(data=data, metadata=metadata,
                                data_count=data_count, data_type=data_type,
                                ioid=0, status=1)
    buffers_to_send = srv_circuit.send(res)
    # Socket transport would happen here. Calling bytes() simulates
    # serialization over the socket.
    commands, _ = cli_circuit.recv(*(_np_hack(buf) for buf in buffers_to_send))
    res_received, = commands
    cli_circuit.process_command(res_received)

    if isinstance(data, array.ArrayType):
        expected = copy.deepcopy(data)
        if (data.endian == '>' and isinstance(res_received.data,
                                              array.ArrayType)):
            # Before comparing array.array (which exposes the byteorder
            # naively) with a numpy.ndarray (which buries the byteorder in
            # dtype), flip the byte order to little-endian.
            expected.byteswap()

        # NOTE: arrays are automatically byteswapped now...
        print(res_received.data, expected)
        assert_array_almost_equal(res_received.data, expected)
    elif isinstance(data, bytes):
        received_data = res_received.data
        if hasattr(received_data, 'endian'):
            # tests store data in big endian. swap received data endian for
            # comparison.
            received_data.byteswap()

        assert data == _np_hack(received_data)
    else:
        try:
            assert_array_equal(res_received.data, data)  # for strings
        except AssertionError:
            assert_array_almost_equal(res_received.data, data)  # for floats


@pytest.mark.parametrize('data_type, data_count, data, metadata', payloads)
def test_writes(backends, circuit_pair, data_type, data_count, data, metadata):

    cli_circuit, srv_circuit = circuit_pair
    cli_channel, srv_channel = make_channels(*circuit_pair, 5, 1)

    req = ca.WriteNotifyRequest(data=data, metadata=metadata,
                                data_count=data_count,
                                data_type=data_type, ioid=0, sid=0)
    buffers_to_send = cli_circuit.send(req)
    # Socket transport would happen here. Calling bytes() simulates
    # serialization over the socket.
    commands, _ = srv_circuit.recv(*(_np_hack(buf) for buf in buffers_to_send))
    for command in commands:
        srv_circuit.process_command(command)
    req_received, = commands
    res = ca.WriteNotifyResponse(data_count=data_count, data_type=data_type,
                                 ioid=0, status=1)
    buffers_to_send = srv_circuit.send(res)

    # Socket transport would happen here. Calling bytes() simulates
    # serialization over the socket.
    commands, _ = cli_circuit.recv(*(_np_hack(buf) for buf in buffers_to_send))
    for command in commands:
        cli_circuit.process_command(command)

    if isinstance(data, array.ArrayType):
        expected = copy.deepcopy(data)
        if (data.endian == '>' and isinstance(req_received.data,
                                              array.ArrayType)):
            # Before comparing array.array (which exposes the byteorder
            # naively) with a numpy.ndarray (which buries the byteorder in
            # dtype), flip the byte order to little-endian.
            expected.byteswap()
        assert_array_almost_equal(req_received.data, expected)
    elif isinstance(data, bytes):
        received_data = req_received.data
        if hasattr(received_data, 'endian'):
            # tests store data in big endian. swap received data endian for
            # comparison>
            received_data.byteswap()

        assert data == _np_hack(received_data)
    else:
        try:
            assert_array_equal(req_received.data, data)  # for strings
        except AssertionError:
            assert_array_almost_equal(req_received.data, data)  # for floats


def test_extended():
    req = ca.ReadNotifyRequest(data_type=5, data_count=1000000, sid=0, ioid=0)
    assert req.header.data_count == 1000000
    assert req.data_count == 1000000
    assert isinstance(req.header, ExtendedMessageHeader)


def test_bytelen():
    with pytest.raises(ca.CaprotoNotImplementedError):
        bytelen([1, 2, 3])
    assert bytelen(b'abc') == 3
    assert bytelen(bytearray(b'abc')) == 3
    assert bytelen(array.array('d', [1, 2, 3])) == 3 * 8
    assert bytelen(memoryview(b'abc')) == 3
    assert bytelen(ctypes.c_uint(1)) == 4

    try:
        import numpy
    except ImportError:
        pass
        # skip this one assert
    else:
        assert bytelen(numpy.array([1, 2, 3], 'f8')) == 3 * 8


def test_overlong_strings():
    with pytest.raises(ca.CaprotoValueError):
        ca.SearchRequest(name='a' * (ca.MAX_RECORD_LENGTH + 1), cid=0,
                         version=ca.DEFAULT_PROTOCOL_VERSION)


skip_ext_headers = [
    'MessageHeader',
    'ExtendedMessageHeader',

    # TODO: these have no args, and cannot get an extended header
    'EchoRequestHeader',
    'EchoResponseHeader',
    'EventsOffRequestHeader',
    'EventsOnRequestHeader',
    'ReadSyncRequestHeader',
]


all_headers = [header_name
               for header_name in dir(ca._headers)
               if header_name.endswith('Header') and
               not header_name.startswith('_') and
               header_name not in skip_ext_headers]


@pytest.mark.parametrize('header_name', all_headers)
def test_extended_headers_smoke(header_name):
    header = getattr(ca._headers, header_name)
    sig = inspect.signature(header)

    regular_bind_args = {}
    extended_bind_args = {}
    for param in sig.parameters.keys():
        regular_bind_args[param] = 0
        extended_bind_args[param] = 2 ** 32

    reg_args = sig.bind(**regular_bind_args)
    reg_hdr = header(*reg_args.args, **reg_args.kwargs)

    ext_args = sig.bind(**extended_bind_args)
    ext_hdr = header(*ext_args.args, **ext_args.kwargs)

    print(reg_hdr)
    assert isinstance(reg_hdr, MessageHeader)
    print(ext_hdr)
    assert isinstance(ext_hdr, (MessageHeader, ExtendedMessageHeader))
