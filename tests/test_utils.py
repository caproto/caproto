import os
import pytest
import caproto as ca


def test_broadcast_address_list_from_interfaces():
    # Smoke test broadcast_address_list_from_interfaces by setting the right
    # env vars and calling get_address_list.
    env = os.environ.copy()
    try:
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

    [(ca.MessageHeader(0, 1, 2, 3, 4, 5), b'def'),
     0,
     (bytes(ca.MessageHeader(0, 1, 2, 3, 4, 5)), b'def'),
     ],

    [(ca.MessageHeader(0, 1, 2, 3, 4, 5), b'def'),
     5,
     (bytes(ca.MessageHeader(0, 1, 2, 3, 4, 5))[5:], b'def'),
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
