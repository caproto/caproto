import os
import pytest
import caproto as ca
from caproto._headers import MessageHeader


def test_broadcast_address_list_from_interfaces():
    # Smoke test broadcast_address_list_from_interfaces by setting the right
    # env vars and calling get_address_list.
    env = os.environ.copy()
    try:
        os.environ['EPICS_CA_ADDR_LIST'] = ''
        os.environ['EPICS_CA_AUTO_ADDR_LIST'] = 'YES'
        ca.get_address_list()
    finally:
        os.environ = env


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


def test_auto_addr_list_warnings():
    try:
        orig = dict(os.environ)
        os.environ.pop('EPICS_CA_AUTO_ADDR_LIST', None)
        os.environ.pop('EPICS_CA_ADDR_LIST', None)
        os.environ.pop('EPICS_CAS_AUTO_BEACON_ADDR_LIST', None)
        os.environ.pop('EPICS_CAS_BEACON_ADDR_LIST', None)

        with pytest.warns(None) as record:
            ca.get_environment_variables()  # no warning
            assert not record
        os.environ['EPICS_CA_ADDR_LIST'] = '127.0.0.1'
        with pytest.warns(UserWarning):
            ca.get_environment_variables()
        os.environ['EPICS_CA_AUTO_ADDR_LIST'] = 'no'
        with pytest.warns(None) as record:
            ca.get_environment_variables()  # no warning
            assert not record
        os.environ['EPICS_CAS_BEACON_ADDR_LIST'] = '127.0.0.1'
        with pytest.warns(UserWarning):
            ca.get_environment_variables()
        os.environ['EPICS_CAS_AUTO_BEACON_ADDR_LIST'] = 'no'
        with pytest.warns(None) as record:
            ca.get_environment_variables()  # no warning
            assert not record

    finally:
        # Restore env as it was.
        os.environ.pop('EPICS_CA_AUTO_ADDR_LIST', None)
        os.environ.pop('EPICS_CA_ADDR_LIST', None)
        os.environ.pop('EPICS_CAS_AUTO_BEACON_ADDR_LIST', None)
        os.environ.pop('EPICS_CAS_BEACON_ADDR_LIST', None)
        os.environ.update(orig)
