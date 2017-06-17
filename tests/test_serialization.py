import array
import copy
import ctypes
from numpy.testing import assert_array_equal, assert_array_almost_equal
import numpy

import caproto as ca
import inspect
import pytest


ip = '255.255.255.255'
int_encoded_ip = ca.ipv4_to_int32(ip)


parameter_values = {
    'address': [int_encoded_ip],
    'client_address': [ip],
    'ip': [ip],
    'repeater_address': [ip],

    'access_rights': [3],
    'beacon_id': [3],
    'cid': [2],
    'data_count': [1],
    'data_type': [ca.DBR_LONG.DBR_ID],
    'error_message': ['error msg'],
    'header': [9],
    'high': [27],
    'ioid': [3],
    'low': [8],
    'mask': [3],
    'metadata': [None],
    'name': ['name'],
    'original_request': [ca.CreateChanRequest('test', 0, 1)],
    'payload': [ca.DBR_LONG(5)],
    'port': [4321],
    'priority': [0],
    'server_port': [1234],
    'sid': [2],
    'status': [99],
    'status_code': [999],
    'subscriptionid': [5],
    'to': [7],
    'validate': [1],
    'data': [[1], ],
    'version': [13],
}

all_commands = set(ca._commands._commands) - set([ca.Message])


def _np_hack(buf):
    try:
        return bytes(buf)
    except TypeError:
        return buf.tobytes()


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

    wire_inst = ca.read_datagram(bytes(inst), ('addr', 0), role)[0]
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


# Define big-endian arrays for use below in test_reads and test_writes.
int_arr = array.array('h', [7, 21, 2, 4, 5])
int_arr.byteswap()
float_arr = array.array('f', [7, 21.1, 3.1])
float_arr.byteswap()
long_arr = array.array('i', [7, 21, 2, 4, 5])
long_arr.byteswap()
double_arr = array.array('d', [7, 21.1, 3.1])
double_arr.byteswap()

payloads = [
    # data_type, data_count, data, metadata
    (ca.ChType.INT, 1, (7,), None),
    (ca.ChType.INT, 5, (7, 21, 2, 4, 5), None),
    (ca.ChType.INT, 5, int_arr, None),
    (ca.ChType.INT, 5, bytes(int_arr), None),
    (ca.ChType.INT, 5, numpy.array([7, 21, 2, 4, 5], dtype='i2'), None),

    (ca.ChType.FLOAT, 1, (7,), None),
    (ca.ChType.FLOAT, 3, (7, 21.1, 3.1), None),
    (ca.ChType.FLOAT, 3, float_arr, None),
    (ca.ChType.FLOAT, 3, bytes(float_arr), None),
    (ca.ChType.FLOAT, 3, numpy.array([7, 21.1, 3.1], dtype='f4'), None),

    (ca.ChType.LONG, 1, (7,), None),
    (ca.ChType.LONG, 2, (7, 21), None),
    (ca.ChType.LONG, 5, numpy.array([7, 21, 2, 4, 5], dtype='i4'), None),
    (ca.ChType.LONG, 5, long_arr, None),
    (ca.ChType.LONG, 5, bytes(long_arr), None),

    (ca.ChType.DOUBLE, 1, (7,), None),
    (ca.ChType.DOUBLE, 6, (7, 21.1, 7, 7, 2.1, 1.1), None),
    (ca.ChType.DOUBLE, 3, numpy.array([7, 21.1, 3.1], dtype='f8'), None),
    (ca.ChType.DOUBLE, 3, double_arr, None),
    (ca.ChType.DOUBLE, 3, bytes(double_arr), None),

    (ca.ChType.TIME_DOUBLE, 1, (7,), ca.DBR_TIME_DOUBLE(1, 0, 3, 5)),
    (ca.ChType.TIME_DOUBLE, 1, (7,), (1, 0, 3, 5)),
    (ca.ChType.TIME_DOUBLE, 2, (7, 3.4), (1, 0, 3, 5)),

    (ca.ChType.STRING, 1, b'abc'.ljust(40, b'\x00'), None),
    (ca.ChType.STRING, 3, 3 * b'abc'.ljust(40, b'\x00'), None),
    (ca.ChType.STRING, 3, numpy.array(['abc', 'def'], '>S40'), None),
    (ca.ChType.STRING, 3, numpy.array(['abc', 'def'], 'S40'), None),
    (ca.ChType.CHAR, 1, b'z', None),
    (ca.ChType.CHAR, 3, b'abc', None),
]


@pytest.mark.parametrize('data_type, data_count, data, metadata', payloads)
def test_reads(circuit_pair, data_type, data_count, data, metadata):

    cli_circuit, srv_circuit = circuit_pair
    cli_channel, srv_channel = make_channels(*circuit_pair, data_type,
                                             data_count)

    req = ca.ReadNotifyRequest(data_count=data_count, data_type=data_type,
                               ioid=0, sid=0)
    buffers_to_send = cli_circuit.send(req)
    # Socket transport would happen here. Calling bytes() simulates
    # serialization over the socket.
    srv_circuit.recv(*(_np_hack(buf) for buf in buffers_to_send))
    srv_circuit.next_command()
    res = ca.ReadNotifyResponse(data=data, metadata=metadata,
                                data_count=data_count, data_type=data_type,
                                ioid=0, status=1)
    buffers_to_send = srv_circuit.send(res)
    # Socket transport would happen here. Calling bytes() simulates
    # serialization over the socket.
    cli_circuit.recv(*(_np_hack(buf) for buf in buffers_to_send))
    res_received = cli_circuit.next_command()

    if isinstance(data, array.ArrayType):
        # Before comparing array.array (which exposes the byteorder naively)
        # with a numpy.ndarray (which buries the byteorder in dtype), flip
        # the byte order to little-endian.
        expected = copy.deepcopy(data)
        expected.byteswap()
        assert_array_almost_equal(res_received.data, expected)
    elif isinstance(data, bytes):
        assert data == _np_hack(res_received.data)
    else:
        try:
            assert_array_equal(res_received.data, data)  # for strings
        except AssertionError:
            assert_array_almost_equal(res_received.data, data)  # for floats


@pytest.mark.parametrize('data_type, data_count, data, metadata', payloads)
def test_writes(circuit_pair, data_type, data_count, data, metadata):

    cli_circuit, srv_circuit = circuit_pair
    cli_channel, srv_channel = make_channels(*circuit_pair, 5, 1)

    req = ca.WriteNotifyRequest(data=data, metadata=metadata,
                                data_count=data_count,
                                data_type=data_type, ioid=0, sid=0)
    buffers_to_send = cli_circuit.send(req)
    # Socket transport would happen here. Calling bytes() simulates
    # serialization over the socket.
    srv_circuit.recv(*(_np_hack(buf) for buf in buffers_to_send))
    req_received = srv_circuit.next_command()
    res = ca.WriteNotifyResponse(data_count=data_count, data_type=data_type,
                                 ioid=0, status=1)
    buffers_to_send = srv_circuit.send(res)

    # Socket transport would happen here. Calling bytes() simulates
    # serialization over the socket.
    cli_circuit.recv(*(_np_hack(buf) for buf in buffers_to_send))
    cli_circuit.next_command()

    if isinstance(data, array.ArrayType):
        # Before comparing array.array (which exposes the byteorder naively)
        # with a numpy.ndarray (which buries the byteorder in dtype), flip
        # the byte order to little-endian.
        expected = copy.deepcopy(data)
        expected.byteswap()
        assert_array_almost_equal(req_received.data, expected)
    elif isinstance(data, bytes):
        assert data == _np_hack(req_received.data)
    else:
        try:
            assert_array_equal(req_received.data, data)  # for strings
        except AssertionError:
            assert_array_almost_equal(req_received.data, data)  # for floats


def test_extended():
    req = ca.ReadNotifyRequest(data_type=5, data_count=1000000, sid=0, ioid=0)
    assert req.header.data_count == 1000000
    assert req.data_count == 1000000
    assert isinstance(req.header, ca.ExtendedMessageHeader)


def test_bytelen():
    with pytest.raises(ca.CaprotoNotImplementedError):
        ca.bytelen([1, 2, 3])
    assert ca.bytelen(b'abc') == 3
    assert ca.bytelen(bytearray(b'abc')) == 3
    assert ca.bytelen(array.array('d', [1, 2, 3])) == 3 * 8
    assert ca.bytelen(numpy.array([1, 2, 3], 'f8')) == 3 * 8
    assert ca.bytelen(memoryview(b'abc')) == 3
    assert ca.bytelen(ctypes.c_uint(1)) == 4


def test_overlong_strings():
    with pytest.raises(ca.CaprotoValueError):
        ca.SearchRequest(name='a' * 41, cid=0, version=13)


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
               if header_name.endswith('Header')
               and not header_name.startswith('_')
               and header_name not in skip_ext_headers]


@pytest.mark.parametrize('header_name', all_headers)
def test_extended_headers_smoke(header_name):
    header = getattr(ca, header_name)
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
    assert isinstance(reg_hdr, ca.MessageHeader)
    print(ext_hdr)
    assert isinstance(ext_hdr, ca.ExtendedMessageHeader)
