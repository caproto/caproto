# This module includes all exceptions raised by caproto, sentinel objects used
# throughout the package (see detailed comment below), various network-related
# helper functions, and other miscellaneous utilities.
import itertools
import logging
import os
import socket
import sys
import enum
import json
from collections import namedtuple

try:
    import netifaces
except ImportError:
    netifaces = None


# This module defines sentinels used in the state machine and elsewhere, such
# as NEED_DATA, CLIENT, SERVER, AWAITING_SEARCH_RESPONSE, etc.
# It also defines some custom Exceptions. That is all.

# This sentinel code is copied, with thanks and admiration, from h11,
# which is released under an MIT license.
#
# Sentinel values
#
# - Inherit identity-based comparison and hashing from object
# - Have a nice repr
# - Have a *bonus property*: type(sentinel) is sentinel
#
# The bonus property is useful if you want to take the return value from
# next_event() and do some sort of dispatch based on type(event).
class _SentinelBase(type):
    def __repr__(self):
        return self.__name__


def make_sentinel(name):
    cls = _SentinelBase(name, (_SentinelBase,), {})
    cls.__class__ = cls
    return cls


globals().update(
    {token: make_sentinel(token) for token in
     ('CLIENT', 'SERVER',  # roles
      'RESPONSE', 'REQUEST',  # directions
      'NEED_DATA',  # special sentinel for read_* functions
      # and states
      'SEND_SEARCH_REQUEST', 'AWAIT_SEARCH_RESPONSE',
      'SEND_SEARCH_RESPONSE', 'SEND_VERSION_REQUEST',
      'AWAIT_VERSION_RESPONSE', 'SEND_VERSION_RESPONSE',
      'SEND_CREATE_CHAN_REQUEST', 'AWAIT_CREATE_CHAN_RESPONSE',
      'SEND_CREATE_CHAN_RESPONSE', 'CONNECTED', 'MUST_CLOSE', 'CLOSED',
      'IDLE', 'FAILED', 'DISCONNECTED')
     })


class CaprotoError(Exception):
    # All exceptions raised by this codebase inherit from this.
    ...


class ProtocolError(CaprotoError):
    # Any error resulting from sending or receiving a command will raise (a
    # subclass of) this error and never any other error.
    ...


class LocalProtocolError(ProtocolError):
    """
    You tried to do something that caproto thinks is illegal.
    """
    ...


class RemoteProtocolError(ProtocolError):
    """
    Your remote peer tried to do something that caproto thinks is illegal.
    """
    ...


class CaprotoKeyError(KeyError, CaprotoError):
    ...


class CaprotoNotImplementedError(NotImplementedError, CaprotoError):
    ...


class CaprotoValueError(ValueError, CaprotoError):
    ...


class CaprotoTypeError(TypeError, CaprotoError):
    ...


class CaprotoRuntimeError(RuntimeError, CaprotoError):
    ...


class ErrorResponseReceived(CaprotoError):
    ...


def get_environment_variables():
    '''Get a dictionary of known EPICS environment variables'''
    defaults = dict(EPICS_CA_ADDR_LIST='',
                    EPICS_CA_AUTO_ADDR_LIST='YES',
                    EPICS_CA_CONN_TMO=30.0,
                    EPICS_CA_BEACON_PERIOD=15.0,
                    EPICS_CA_REPEATER_PORT=5065,
                    EPICS_CA_SERVER_PORT=5064,
                    EPICS_CA_MAX_ARRAY_BYTES=16384,
                    EPICS_CA_MAX_SEARCH_PERIOD=300,
                    EPICS_TS_MIN_WEST=360,
                    EPICS_CAS_SERVER_PORT=5064,
                    EPICS_CAS_AUTO_BEACON_ADDR_LIST='YES',
                    EPICS_CAS_BEACON_ADDR_LIST='',
                    EPICS_CAS_BEACON_PERIOD=15.0,
                    EPICS_CAS_BEACON_PORT=5065,
                    EPICS_CAS_INTF_ADDR_LIST='',
                    EPICS_CAS_IGNORE_ADDR_LIST='',
                    )

    def get_value(env_var):
        default = defaults[env_var]
        value = os.environ.get(env_var, default)
        return type(default)(value)

    return dict((env_var, get_value(env_var)) for env_var in defaults.keys())


def get_address_list():
    '''Get channel access client address list based on environment variables

    If the address list is set to be automatic, the network interfaces will be
    scanned and used to determine the broadcast addresses available.
    '''
    env = get_environment_variables()
    auto_addr_list = env['EPICS_CA_AUTO_ADDR_LIST']
    addr_list = env['EPICS_CA_ADDR_LIST']

    if not addr_list or auto_addr_list.lower() == 'yes':
        return broadcast_address_list_from_interfaces()

    return addr_list.split(' ')


def get_beacon_address_list():
    '''Get channel access beacon address list based on environment variables

    If the address list is set to be automatic, the network interfaces will be
    scanned and used to determine the broadcast addresses available.

    Returns
    -------
    addr_list : list of (addr, beacon_port)
    '''
    env = get_environment_variables()
    auto_addr_list = env['EPICS_CAS_AUTO_BEACON_ADDR_LIST']
    addr_list = env['EPICS_CAS_BEACON_ADDR_LIST']
    beacon_port = env['EPICS_CAS_BEACON_PORT']

    def get_addr_port(addr):
        if ':' in addr:
            addr, _, specified_port = addr.partition(':')
            return (addr, int(specified_port))
        return (addr, beacon_port)

    if not addr_list or auto_addr_list.lower() == 'yes':
        return [get_addr_port(addr) for addr in
                broadcast_address_list_from_interfaces()]

    return [get_addr_port(addr) for addr in addr_list.split(' ')]


def get_netifaces_addresses():
    '''Get a list of addresses + broadcast using netifaces

    Yields (address, broadcast_address)
    '''
    if netifaces is None:
        raise RuntimeError('netifaces unavailable')

    for iface in netifaces.interfaces():
        interface = netifaces.ifaddresses(iface)
        if netifaces.AF_INET in interface:
            for af_inet_info in interface[netifaces.AF_INET]:
                addr = af_inet_info.get('addr', None)
                peer = af_inet_info.get('peer', None)
                broadcast = af_inet_info.get('broadcast', None)

                if addr is not None and broadcast is not None:
                    yield (addr, broadcast)
                elif peer is not None and broadcast is not None:
                    yield (peer, broadcast)
                elif addr is not None:
                    yield (addr, addr)
                elif peer is not None:
                    yield (peer, peer)


def broadcast_address_list_from_interfaces():
    '''Get a list of broadcast addresses using netifaces

    If netifaces is unavailable, the standard IPv4 255.255.255.255 broadcast
    address is returned.
    '''
    if netifaces is None:
        return ['255.255.255.255']

    return [bcast for addr, bcast in get_netifaces_addresses()]


def ensure_bytes(s):
    """Encode string as bytes with null terminator. Bytes pass through."""
    if isinstance(s, bytes):
        return s
    elif isinstance(s, str):
        # be sure to include a null terminator
        return s.encode() + b'\0'
    else:
        raise CaprotoTypeError("expected str or bytes")


def bcast_socket(socket_module=socket):
    """
    Make a socket and configure it for UDP broadcast.

    Parameters
    ----------
    socket_module: module, optional
        Default is the built-in :mod:`socket` module, but anything with the
        same interface may be used, such as :mod:`curio.socket`.
    """
    socket = socket_module
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    # for BSD/Darwin only
    try:
        socket.SO_REUSEPORT
    except AttributeError:
        ...
    else:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    return sock


def buffer_list_slice(*buffers, offset):
    'Helper function for slicing a list of buffers'
    if offset < 0:
        raise ValueError('Negative offset')

    buffers = tuple(memoryview(b).cast('b') for b in buffers)

    start = 0
    for bufidx, buf in enumerate(buffers):
        end = start + len(buf)
        if offset < end:
            offset -= start
            return (buf[offset:], ) + buffers[bufidx + 1:]

        start = end

    raise ValueError('Offset beyond end of buffers (total length={} offset={})'
                     ''.format(end, offset))


def incremental_buffer_list_slice(*buffers):
    'Incrementally slice a list of buffers'
    buffers = tuple(memoryview(b).cast('b') for b in buffers)
    total_size = sum(len(b) for b in buffers)
    total_sent = 0

    while total_sent < total_size:
        sent = yield buffers
        total_sent += sent
        if total_sent == total_size:
            break
        buffers = buffer_list_slice(*buffers, offset=sent)


def spawn_daemon(func, *args, **kwargs):
    # adapted from https://stackoverflow.com/a/6011298/1221924

    # Do the UNIX double-fork magic to avoid receiving signals from the parent
    # See Stevens' "Advanced # Programming in the UNIX Environment"
    # (ISBN 0201563177)
    try:
        pid = os.fork()
        if pid > 0:
            # parent process, return and keep running
            return
    except OSError as e:
        print("fork #1 failed: %d (%s)" % (e.errno, e.strerror),
              out=sys.stderr)
        sys.exit(1)

    os.setsid()
    sys.stdout = open('/dev/null', 'w')
    sys.stderr = open('/dev/null', 'w')

    # do second fork
    try:
        pid = os.fork()
        if pid > 0:
            # exit from second parent
            sys.exit(0)
    except OSError as e:
        print("fork #2 failed: %d (%s)" % (e.errno, e.strerror),
              out=sys.stderr)
        sys.exit(1)

    # do stuff
    func(*args, **kwargs)

    # all done
    os._exit(os.EX_OK)


RecordAndField = namedtuple('RecordAndField',
                            ['record_dot_field', 'record',
                             'field', 'modifiers'])


class RecordModifiers(enum.Flag):
    long_string = enum.auto()
    filtered = enum.auto()
    filter_timestamp = enum.auto()
    filter_deadband = enum.auto()
    filter_array = enum.auto()
    filter_synchronize = enum.auto()


RecordModifier = namedtuple('RecordModifier',
                            ['modifiers', 'filter_'])


def parse_record_field(pvname):
    '''Parse a record[.FIELD][{FILTER}]

    Returns
    -------
    RecordAndField(record_dot_field, record, field, modifiers)
    '''
    if '.' not in pvname:
        return RecordAndField(pvname, pvname, None, None)

    record, field = pvname.split('.', 1)
    if field.startswith('{'):
        field, filter_ = None, field
        modifiers = RecordModifiers.filtered
    elif not field:
        # valid case of "{record}."
        return RecordAndField(record, record, None, None)
    else:
        if '{' in field:
            field, filter_ = field.split('{', 1)
            filter_ = '{' + filter_
            modifiers = RecordModifiers.filtered
        else:
            filter_ = None
            modifiers = None

        if field.endswith('$'):
            if modifiers is not None:
                modifiers |= RecordModifiers.long_string
            else:
                modifiers = RecordModifiers.long_string
            field = field.rstrip('$')

    # NOTE: VAL is equated to 'record' at a higher level than this.
    if field:
        record_field = f'{record}.{field}'
    else:
        record_field = record

    if modifiers:
        modifiers = RecordModifier(modifiers, filter_=filter_)
    return RecordAndField(record_field, record, field, modifiers)


def evaluate_channel_filter(filter_text):
    'Evaluate JSON-based channel filter into easy Python type'

    filter_ = json.loads(filter_text)

    valid_filters = {'ts', 'arr', 'sync', 'dbnd'}
    filter_keys = set(filter_.keys())
    invalid_keys = filter_keys - valid_filters
    if invalid_keys:
        raise ValueError(f'Unsupported filters: {invalid_keys}')
    # TODO: parse/validate filters into python types?
    return filter_


no_pad = '__no__pad__'


def partition_all(n, seq):
    """ Partition all elements of sequence into tuples of length at most n

    The final tuple may be shorter to accommodate extra elements.

    >>> list(partition_all(2, [1, 2, 3, 4]))
    [(1, 2), (3, 4)]

    >>> list(partition_all(2, [1, 2, 3, 4, 5]))
    [(1, 2), (3, 4), (5,)]

    See Also:
        partition

    Vendored from toolz.itertoolz
    """
    args = [iter(seq)] * n
    it = itertools.zip_longest(*args, fillvalue=no_pad)
    try:
        prev = next(it)
    except StopIteration:
        return
    for item in it:
        yield prev
        prev = item
    if prev[-1] is no_pad:
        yield prev[:prev.index(no_pad)]
    else:
        yield prev
