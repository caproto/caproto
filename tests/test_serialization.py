import struct
import socket

import caproto as ca
import inspect
import pytest

# TODO this is used in several places in _commands.py
ip = '255.255.255.255'
encoded_ip = socket.inet_pton(socket.AF_INET, ip)
int_encoded_ip, = struct.unpack('!I', encoded_ip)  # bytes -> int

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
    # TODO this is important to check:
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
    (5, 1, (1,), None)
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
    print(com.data)


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
    assert com.data == data
