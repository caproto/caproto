# This module includes all exceptions raised by caproto, sentinel objects used
# throughout the package (see detailed comment below), various network-related
# helper functions, and other miscellaneous utilities.
import collections
import os
import socket
import sys
import enum
import json
import threading
from collections import namedtuple
from warnings import warn

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

    result = dict(os.environ)
    # Handled coupled items.
    if (result.get('EPICS_CA_ADDR_LIST') and
            result.get('EPICS_CA_AUTO_ADDR_LIST', '').upper() != 'NO'):
        warn("EPICS_CA_ADDR_LIST is set but will be ignored because "
             "EPICS_CA_AUTO_AUTO_ADDR_LIST is not set to 'no'.")
    if (result.get('EPICS_CAS_BEACON_ADDR_LIST') and
            result.get('EPICS_CAS_AUTO_BEACON_ADDR_LIST', '').upper() != 'NO'):
        warn("EPICS_CAS_BEACON_ADDR_LIST is set but will be ignored because "
             "EPICS_CAS_AUTO_BEACON_ADDR_LIST is not set to 'no'.")
    for k, v in defaults.items():
        result.setdefault(k, v)
    return result


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


def get_server_address_list(default_port):
    '''Get the server interface addresses based on environment variables

    Returns
    -------
    list of (addr, port)
    '''
    intf_addrs = get_environment_variables()['EPICS_CAS_INTF_ADDR_LIST']

    if not intf_addrs:
        return [('0.0.0.0', default_port)]

    def get_addr_port(addr):
        if ':' in addr:
            addr, _, specified_port = addr.partition(':')
            return (addr, int(specified_port))
        return (addr, default_port)

    return [get_addr_port(addr) for addr in intf_addrs.split(' ')]


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
        raise CaprotoTypeError(f"expected str or bytes, got {s!r} of type "
                               f"{type(s)}")


def find_available_tcp_port(host='0.0.0.0', starting_port=None):
    '''Find the next available TCP server port

    Parameters
    ----------
    host : str, optional
        Host/interface to bind on; defaults to 0.0.0.0
    starting_port : int, optional
        Port to try first
    '''
    import random
    if starting_port is None:
        from ._constants import EPICS_CA2_PORT
        starting_port = EPICS_CA2_PORT + 1

    port = starting_port
    stashed_ex = None

    for attempt in range(100):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind((host, port))
        except IOError as ex:
            stashed_ex = ex
        else:
            s.close()
            return port

        port = random.randint(49152, 65535)

    raise RuntimeError('No available ports and/or bind failed') from stashed_ex


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


class SendAllRetry(CaprotoError):
    ...


def send_all(buffers_to_send, send_func):
    '''Incrementally slice a list of buffers, and send it using `send_func`

    Parameters
    ----------
    buffers_to_send : (buffer1, buffer2, ...)
        Buffers are expected to be memoryviews or similar
    send_func : callable
        Function to call with list of buffers to send
        Expected to return number of bytes sent or raise SendAllRetry otherwise
    '''

    if not buffers_to_send:
        return

    gen = incremental_buffer_list_slice(*buffers_to_send)

    # prime the generator
    gen.send(None)

    while buffers_to_send:
        try:
            while True:
                try:
                    sent = send_func(buffers_to_send)
                    break
                except OSError:
                    buffers_to_send = buffers_to_send[:len(buffers_to_send)//2]

        except SendAllRetry:
            continue

        try:
            buffers_to_send = gen.send(sent)
        except StopIteration:
            # finished sending
            break


async def async_send_all(buffers_to_send, async_send_func):
    '''Incrementally slice a list of buffers, and send it using `send_func`

    Parameters
    ----------
    buffers_to_send : (buffer1, buffer2, ...)
        Buffers are expected to be memoryviews or similar
    async_send_func : callable
        Async function to call with list of buffers to send
        Expected to return number of bytes sent or raise SendAllRetry otherwise
    '''

    if not buffers_to_send:
        return

    gen = incremental_buffer_list_slice(*buffers_to_send)
    # prime the generator
    gen.send(None)

    while buffers_to_send:
        try:
            while True:
                try:
                    sent = await async_send_func(buffers_to_send)
                    break
                except OSError:
                    buffers_to_send = buffers_to_send[:len(buffers_to_send)//2]
        except SendAllRetry:
            continue

        try:
            buffers_to_send = gen.send(sent)
        except StopIteration:
            # finished sending
            break


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


def batch_requests(request_iter, max_length):
    '''Batch a set of items with length, thresholded on sum of item length

    Yields
    ------
    batch : collections.deque
        Batch of items from request_iter, where:
            sum(len(b) for b in batch) < max_length
        NOTE: instance of deque is reused, cleared at each iteration
    '''
    size = 0
    batch = collections.deque()
    for command in request_iter:
        _len = len(command)
        if size + _len > max_length:
            yield batch
            batch.clear()
            size = 0
        batch.append(command)
        size += _len
    if batch:
        yield batch


class ThreadsafeCounter:
    '''A thread-safe counter with a couple features:

    1. Loops around at 2 ** 16
    2. Optionally ensures no clashing with existing IDs

    Note: if necessary, use the counter lock to keep the dont_clash_with object
    in sync.
    '''
    MAX_ID = 2 ** 16

    def __init__(self, *, initial_value=0, dont_clash_with=None):
        self.value = initial_value
        self.lock = threading.RLock()
        self.dont_clash_with = dont_clash_with

    def __call__(self):
        'Get next ID, wrapping around at 2**16, ensuring no clashes'
        if not self.dont_clash_with:
            with self.lock:
                self.value += 1
                if self.value >= self.MAX_ID:
                    self.value = 0
                return self.value
        else:
            with self.lock:
                value = self.value

                while value in self.dont_clash_with or value >= self.MAX_ID:
                    value += 1
                    if value >= self.MAX_ID:
                        value = 0

                self.value = value
                return value
