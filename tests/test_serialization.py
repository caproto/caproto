import struct
import socket
from numpy.testing import assert_array_almost_equal

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


payloads = [
    # data_type, data_count, data, metadata
    (ca.ChType.INT, 1, (7,), None),
    (ca.ChType.INT, 5, (7, 21, 2, 4, 5), None),
    (ca.ChType.FLOAT, 1, (7,), None),
    (ca.ChType.FLOAT, 3, (7, 21.1, 3.1), None),
    (ca.ChType.LONG, 1, (7,), None),
    (ca.ChType.LONG, 2, (7, 21), None),
    (ca.ChType.DOUBLE, 1, (7,), None),
    (ca.ChType.DOUBLE, 6, (7, 21.1, 7, 7, 2.1, 1.1), None),
]

@pytest.mark.parametrize('data_type, data_count, data, metadata', payloads)
def test_reads(circuit_pair, data_type, data_count, data, metadata):

    cli_circuit, srv_circuit = circuit_pair
    cli_channel, srv_channel = make_channels(*circuit_pair, 5, 1)

    req = ca.ReadNotifyRequest(data_count=data_count, data_type=data_type,
                               ioid=0, sid=0)
    buffers_to_send = cli_circuit.send(req)
    srv_circuit.recv(*buffers_to_send)
    srv_circuit.next_command()
    res = ca.ReadNotifyResponse(data=data, metadata=metadata,
                                data_count=data_count, data_type=data_type,
                                ioid=0, status=1)
    buffers_to_send = srv_circuit.send(res)
    cli_circuit.recv(*buffers_to_send)
    com = cli_circuit.next_command()
    assert_array_almost_equal(com.data, data, )


@pytest.mark.parametrize('data_type, data_count, data, metadata', payloads)
def test_writes(circuit_pair, data_type, data_count, data, metadata):

    cli_circuit, srv_circuit = circuit_pair
    cli_channel, srv_channel = make_channels(*circuit_pair, 5, 1)

    req = ca.WriteNotifyRequest(data=data, data_count=data_count,
                                data_type=data_type, ioid=0, sid=0)
    buffers_to_send = cli_circuit.send(req)
    srv_circuit.recv(*buffers_to_send)
    srv_circuit.next_command()
    res = ca.ReadNotifyResponse(data=data, metadata=metadata,
                                data_count=data_count, data_type=data_type,
                                ioid=0, status=1)
    buffers_to_send = srv_circuit.send(res)
    cli_circuit.recv(*buffers_to_send)
    com = cli_circuit.next_command()
    assert_array_almost_equal(com.data, data)
