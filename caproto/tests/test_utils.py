import os

import pytest

import caproto as ca
from caproto._headers import MessageHeader


def test_broadcast_auto_address_list():
    pytest.importorskip('netifaces')
    env = os.environ.copy()
    try:
        os.environ['EPICS_CA_ADDR_LIST'] = ''
        os.environ['EPICS_CA_AUTO_ADDR_LIST'] = 'YES'
        expected = set(bcast for addr, bcast in ca.get_netifaces_addresses())
        assert set(ca.get_address_list()) == expected
    finally:
        os.environ.clear()
        os.environ.update(env)


def test_ensure_bytes():
    assert ca.ensure_bytes('abc') == b'abc\0'
    assert ca.ensure_bytes(b'abc\0') == b'abc\0'
    with pytest.raises(ca.CaprotoTypeError):
        ca.ensure_bytes(1)


_incr_sends = [
    [(b'abc', b'def', b'ghi'),
     0,
     (b'abc', b'def', b'ghi')
     ],

    [(b'abc', b'def', b'ghi'),
     1,
     (b'bc', b'def', b'ghi')
     ],

    [(b'abc', b'def', b'ghi'),
     3,
     (b'def', b'ghi')
     ],

    [(MessageHeader(0, 1, 2, 3, 4, 5), b'def'),
     0,
     (bytes(MessageHeader(0, 1, 2, 3, 4, 5)), b'def'),
     ],

    [(MessageHeader(0, 1, 2, 3, 4, 5), b'def'),
     5,
     (bytes(MessageHeader(0, 1, 2, 3, 4, 5))[5:], b'def'),
     ],
]


@pytest.mark.parametrize('buffers, offset, expected', _incr_sends)
def test_buffer_list_slice(buffers, offset, expected):
    assert ca.buffer_list_slice(*buffers, offset=offset) == expected


@pytest.mark.parametrize('buffers, offset, expected', _incr_sends)
def test_incremental_send(buffers, offset, expected):
    full_bytes = b''.join(bytes(b) for b in buffers)

    gen = ca.incremental_buffer_list_slice(*buffers)
    gen.send(None)

    for i in range(len(full_bytes)):
        try:
            buffers = gen.send(1)
        except StopIteration:
            assert i == (len(full_bytes) - 1), 'StopIteration unexpected'
            break
        assert full_bytes[i + 1:] == b''.join(bytes(b) for b in buffers)


records_to_check = [
    ['x.NAME', ('x.NAME', 'x', 'NAME', None)],
    ['x.', ('x', 'x', None, None)],
    ['x', ('x', 'x', None, None)],

    ['x.NAME$',
     ('x.NAME', 'x', 'NAME',
      ca.RecordModifier(ca.RecordModifiers.long_string, None),
      )],
    ['x.VAL{"ts":true}',
     ('x.VAL', 'x', 'VAL',
      ca.RecordModifier(ca.RecordModifiers.filtered, '{"ts":true}')
      )],
    ['x.{}',
     ('x', 'x', None,
      ca.RecordModifier(ca.RecordModifiers.filtered, '{}'),
      )],
    ['x.VAL{}',
     ('x.VAL', 'x', 'VAL',
      ca.RecordModifier(ca.RecordModifiers.filtered, '{}'),
      )],
    ['x.NAME${}',
     ('x.NAME', 'x', 'NAME',
      ca.RecordModifier(ca.RecordModifiers.filtered |
                        ca.RecordModifiers.long_string, '{}'),
      )],
]


@pytest.mark.parametrize('pvname, expected_tuple', records_to_check)
def test_parse_record(pvname, expected_tuple):
    parsed = ca.parse_record_field(pvname)
    print('parsed:  ', tuple(parsed))
    print('expected:', expected_tuple)
    assert tuple(parsed) == expected_tuple

    if parsed.modifiers:
        modifiers, filter_text = parsed.modifiers
        if filter_text:
            # smoke test these
            ca.parse_channel_filter(filter_text)


bad_filters = [
    ["x.{not-json}",
     ('x', 'x', None,
      ca.RecordModifier(ca.RecordModifiers.filtered, '{not-json}'),
      )],
    ['x.{"none":null}',
     ('x', 'x', None,
      ca.RecordModifier(ca.RecordModifiers.filtered, '{"none":null}'),
      )],
]


@pytest.mark.parametrize('pvname, expected_tuple', bad_filters)
def test_parse_record_bad_filters(pvname, expected_tuple):
    parsed = ca.parse_record_field(pvname)
    print('parsed:  ', tuple(parsed))
    print('expected:', expected_tuple)
    assert tuple(parsed) == expected_tuple

    modifiers, filter_text = parsed.modifiers
    try:
        filter_ = ca.parse_channel_filter(filter_text)
    except ValueError:
        # expected failure
        ...
    else:
        raise ValueError(f'Expected failure, instead returned {filter_}')


@pytest.mark.parametrize('protocol', list(ca.Protocol))
def test_env_util_smoke(protocol):
    ca.get_environment_variables()
    try:
        ca.get_netifaces_addresses()
    except RuntimeError:
        # Netifaces may be unavailable
        ...

    ca.get_address_list(protocol=protocol)
    ca.get_beacon_address_list(protocol=protocol)
    ca._utils.get_manually_specified_beacon_addresses(protocol=protocol)
    ca._utils.get_manually_specified_client_addresses(protocol=protocol)
    ca.get_server_address_list(protocol=protocol)


@pytest.mark.parametrize(
    'addr, default_port, expected',
    [pytest.param('1.2.3.4:56', 8, ('1.2.3.4', 56)),
     pytest.param('1.2.3.4', 8, ('1.2.3.4', 8)),
     pytest.param('[::]:34', 8, ValueError),
     ]
)
def test_split_address(addr, default_port, expected):
    if expected in {ValueError, }:
        with pytest.raises(expected):
            ca._utils.get_address_and_port_from_string(addr, default_port)
        return

    assert ca._utils.get_address_and_port_from_string(addr, default_port) == expected


def patch_env(monkeypatch, env_vars):
    """Patch `get_environment_variables` for testing below."""
    def get_env():
        return env_vars

    monkeypatch.setattr(ca._utils, 'get_environment_variables', get_env)


@pytest.mark.parametrize('protocol', list(ca.Protocol))
@pytest.mark.parametrize(
    'default_port, env_auto, env_addr, expected',
    [
        pytest.param(
            8088, 'YES', '1.2.3.4 1.2.3.4:556',
            [('1.2.3.4', 8088),
             ('1.2.3.4', 556),
             ('255.255.255.255', 8088),
             ]
        ),

        pytest.param(
            8088, 'NO', '1.2.3.4 1.2.3.4:556',
            [('1.2.3.4', 8088),
             ('1.2.3.4', 556),
             ]
        ),
    ],
)
def test_beacon_addresses(monkeypatch, protocol, default_port, env_auto,
                          env_addr, expected):
    env = ca.get_environment_variables()

    key = ca.Protocol(protocol).server_env_key
    env[f'EPICS_{key}_BEACON_ADDR_LIST'] = env_addr
    env[f'EPICS_{key}_AUTO_BEACON_ADDR_LIST'] = env_auto
    if protocol == ca.Protocol.ChannelAccess:
        env['EPICS_CAS_BEACON_PORT'] = int(default_port)
    else:
        env['EPICS_PVAS_BROADCAST_PORT'] = int(default_port)

    patch_env(monkeypatch, env)
    assert set(ca.get_beacon_address_list(protocol=protocol)) == set(expected)


@pytest.mark.parametrize('protocol', list(ca.Protocol))
@pytest.mark.parametrize(
    'default_port, env_auto, env_addr, expected',
    [
        pytest.param(
            8088, 'YES', '1.2.3.4 1.2.3.4:556',
            [('1.2.3.4', 8088),
             ('1.2.3.4', 556),
             ('255.255.255.255', 8088),
             ]
        ),

        pytest.param(
            8088, 'NO', '1.2.3.4 1.2.3.4:556',
            [('1.2.3.4', 8088),
             ('1.2.3.4', 556),
             ]
        ),
    ],
)
def test_client_addresses(monkeypatch, protocol, default_port, env_auto,
                          env_addr, expected):
    env = ca.get_environment_variables()

    # Easier to test without netifaces
    monkeypatch.setattr(ca._utils, 'netifaces', None)

    env[f'EPICS_{protocol}_ADDR_LIST'] = env_addr
    env[f'EPICS_{protocol}_AUTO_ADDR_LIST'] = env_auto
    if protocol == 'CA':
        env['EPICS_CA_SERVER_PORT'] = int(default_port)
    elif protocol == 'PVA':
        env['EPICS_PVA_BROADCAST_PORT'] = int(default_port)

    patch_env(monkeypatch, env)
    assert set(ca.get_client_address_list(protocol=protocol)) == set(expected)


@pytest.mark.parametrize('protocol', list(ca.Protocol))
@pytest.mark.parametrize(
    'env_addr, expected',
    [
        pytest.param('1.2.3.4', {'1.2.3.4'}, id='normal'),
        pytest.param('1.2.3.4 1.2.3.4:556', {'1.2.3.4'}, id='ignore-port',
                     marks=pytest.mark.filterwarnings("ignore:Port specified"),
                     ),
        pytest.param('1.2.3.4 5.6.7.8:556', {'1.2.3.4', '5.6.7.8'},
                     id='ignore-port-1',
                     marks=pytest.mark.filterwarnings("ignore:Port specified"),
                     ),
        pytest.param('', ['0.0.0.0'], id='empty-list'),
    ],
)
def test_server_addresses(monkeypatch, protocol, env_addr, expected):
    env = ca.get_environment_variables()
    key = ca.Protocol(protocol).server_env_key
    env[f'EPICS_{key}_INTF_ADDR_LIST'] = env_addr

    patch_env(monkeypatch, env)
    assert set(ca.get_server_address_list(protocol=protocol)) == set(expected)
