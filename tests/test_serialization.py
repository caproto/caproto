import struct
import socket

import caproto as ca
import inspect


def test_serialize():
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
        'beacon_id': [0],
        'cid': [0],
        'data': [[0], ],
        'data_count': [1],
        'data_type': [ca.DBR_LONG.DBR_ID],
        'error_message': ['error msg'],
        'header': [0],
        'high': [0],
        'ioid': [0],
        'low': [0],
        'mask': [0],
        'metadata': [None],
        'name': ['name'],
        'original_request': [ca.CreateChanRequest('test', 0, 1)],
        'payload': [ca.DBR_LONG(5)],
        'port': [4321],
        'priority': [0],
        'server_port': [1234],
        'sid': [0],
        'status': [0],
        'status_code': [0],
        'subscriptionid': [0],
        'to': [0],
        'validate': [0],
        'values': [[1], ],
        'version': [0],
    }

    for cmd in ca._commands._commands:
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

        if cmd in (ca.Message, ):
            continue

        role = (ca.CLIENT if cmd.__name__.endswith('Request')
                else ca.SERVER)

        print('inst', bytes(inst))
        print('    ', inst)

        wire_inst = ca.read_datagram(bytes(inst), ('addr', 0), role)[0]
        print('wire', bytes(wire_inst))
        print('    ', wire_inst)
        assert bytes(wire_inst.header) == bytes(inst.header)
        # TODO this is important to check:
        # assert wire_inst == inst
