# This module includes all exceptions raised by caproto, sentinel objects used
# throughout the package (see detailed comment below), various network-related
# helper functions, and other miscellaneous utilities.
import argparse
import array
import collections
import enum
import functools
import inspect
import ipaddress
import json
import logging
import os
import random
import socket
import struct
import sys
import threading
import typing
import weakref
from collections import namedtuple
from contextlib import contextmanager
from warnings import warn

from ._version import get_versions

__version__ = get_versions()['version']

try:
    import fcntl
    import termios
except ImportError:
    fcntl = None
    termios = None
    # fcntl is unavailale on windows


try:
    import netifaces
except ImportError:
    netifaces = None


__all__ = (  # noqa F822
    'adapt_old_callback_signature',
    'apply_arr_filter',
    'ChannelFilter',
    'get_environment_variables',
    'get_address_list',
    'get_local_address',
    'get_beacon_address_list',
    'get_client_address_list',
    'get_server_address_list',
    'get_netifaces_addresses',
    'ensure_bytes',
    'random_ports',
    'bcast_socket',
    'buffer_list_slice',
    'incremental_buffer_list_slice',
    'send_all',
    'async_send_all',
    'parse_record_field',
    'parse_channel_filter',
    'batch_requests',
    'CaprotoError',
    'Protocol',
    'ProtocolError',
    'LocalProtocolError',
    'RemoteProtocolError',
    'CaprotoTimeoutError',
    'CaprotoKeyError',
    'CaprotoAttributeError',
    'CaprotoNotImplementedError',
    'CaprotoValueError',
    'CaprotoTypeError',
    'CaprotoConversionError',
    'CaprotoRuntimeError',
    'CaprotoNetworkError',
    'ErrorResponseReceived',
    'SendAllRetry',
    'RecordModifiers',
    'RecordModifier',
    'RecordAndField',
    'ThreadsafeCounter',
    '__version__',
    # sentinels dynamically defined and added to globals() below
    'CLIENT', 'SERVER', 'RESPONSE', 'REQUEST', 'NEED_DATA',
    'SEND_SEARCH_REQUEST', 'AWAIT_SEARCH_RESPONSE',
    'SEND_SEARCH_RESPONSE', 'SEND_VERSION_REQUEST',
    'AWAIT_VERSION_RESPONSE', 'SEND_VERSION_RESPONSE',
    'SEND_CREATE_CHAN_REQUEST', 'AWAIT_CREATE_CHAN_RESPONSE',
    'SEND_CREATE_CHAN_RESPONSE', 'CONNECTED', 'MUST_CLOSE',
    'CLOSED', 'IDLE', 'FAILED', 'DISCONNECTED')


logger = logging.getLogger(__name__)


# This module defines sentinels used in the state machine and elsewhere, such
# as NEED_DATA, CLIENT, SERVER, AWAITING_SEARCH_RESPONSE, etc.
# It also defines some custom Exceptions.

class _SimpleReprEnum(enum.Enum):
    def __repr__(self):
        return self.name


class Role(_SimpleReprEnum):
    CLIENT = enum.auto()
    SERVER = enum.auto()


class Direction(_SimpleReprEnum):
    RESPONSE = enum.auto()
    REQUEST = enum.auto()


class States(_SimpleReprEnum):
    SEND_SEARCH_REQUEST = enum.auto()
    AWAIT_SEARCH_RESPONSE = enum.auto()
    SEND_SEARCH_RESPONSE = enum.auto()
    SEND_VERSION_REQUEST = enum.auto()
    AWAIT_VERSION_RESPONSE = enum.auto()
    SEND_VERSION_RESPONSE = enum.auto()
    SEND_CREATE_CHAN_REQUEST = enum.auto()
    AWAIT_CREATE_CHAN_RESPONSE = enum.auto()
    SEND_CREATE_CHAN_RESPONSE = enum.auto()
    CONNECTED = enum.auto()
    MUST_CLOSE = enum.auto()
    CLOSED = enum.auto()
    IDLE = enum.auto()
    FAILED = enum.auto()
    DISCONNECTED = enum.auto()

    # Special old 'sentinel' for needing more data
    NEED_DATA = enum.auto()


class ConversionDirection(_SimpleReprEnum):
    FROM_WIRE = enum.auto()
    TO_WIRE = enum.auto()


class Protocol(str, _SimpleReprEnum):
    PVAccess = 'PVA'
    ChannelAccess = 'CA'

    @property
    def server_env_key(self) -> str:
        """The environment variable key used for server settings."""
        return {
            Protocol.ChannelAccess: 'CAS',
            Protocol.PVAccess: 'PVAS',
        }[self]


CLIENT = Role.CLIENT
SERVER = Role.SERVER
RESPONSE = Direction.RESPONSE
REQUEST = Direction.REQUEST

SEND_SEARCH_REQUEST = States.SEND_SEARCH_REQUEST
AWAIT_SEARCH_RESPONSE = States.AWAIT_SEARCH_RESPONSE
SEND_SEARCH_RESPONSE = States.SEND_SEARCH_RESPONSE
SEND_VERSION_REQUEST = States.SEND_VERSION_REQUEST
AWAIT_VERSION_RESPONSE = States.AWAIT_VERSION_RESPONSE
SEND_VERSION_RESPONSE = States.SEND_VERSION_RESPONSE
SEND_CREATE_CHAN_REQUEST = States.SEND_CREATE_CHAN_REQUEST
AWAIT_CREATE_CHAN_RESPONSE = States.AWAIT_CREATE_CHAN_RESPONSE
SEND_CREATE_CHAN_RESPONSE = States.SEND_CREATE_CHAN_RESPONSE
CONNECTED = States.CONNECTED
MUST_CLOSE = States.MUST_CLOSE
CLOSED = States.CLOSED
IDLE = States.IDLE
FAILED = States.FAILED
DISCONNECTED = States.DISCONNECTED
NEED_DATA = States.NEED_DATA

FROM_WIRE = ConversionDirection.FROM_WIRE
TO_WIRE = ConversionDirection.TO_WIRE

PVAccess = Protocol.PVAccess
ChannelAccess = Protocol.ChannelAccess


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


class ValidationError(CaprotoError):
    """
    Could not parse into valid command.
    """
    ...


class CaprotoTimeoutError(TimeoutError, CaprotoError):
    ...


class CaprotoAttributeError(AttributeError, CaprotoError):
    ...


class CaprotoKeyError(KeyError, CaprotoError):
    ...


class CaprotoNotImplementedError(NotImplementedError, CaprotoError):
    ...


class CaprotoValueError(ValueError, CaprotoError):
    ...


class CaprotoConversionError(CaprotoValueError):
    ...


class CaprotoEnvironmentSetupError(ValueError, CaprotoError):
    ...


class FilterValidationError(CaprotoValueError):
    ...


class CaprotoTypeError(TypeError, CaprotoError):
    ...


class CaprotoRuntimeError(RuntimeError, CaprotoError):
    ...


class CaprotoNetworkError(OSError, CaprotoError):
    ...


class ErrorResponseReceived(CaprotoError):
    ...


_ENVIRONMENT_DEFAULTS = dict(
    EPICS_CA_ADDR_LIST='',
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

    # pvAccess
    EPICS_PVA_DEBUG=0,
    EPICS_PVA_ADDR_LIST='',
    EPICS_PVA_AUTO_ADDR_LIST='YES',
    EPICS_PVA_CONN_TMO=30.0,
    EPICS_PVA_BEACON_PERIOD=15.0,
    EPICS_PVA_BROADCAST_PORT=5076,
    EPICS_PVA_MAX_ARRAY_BYTES=16384,
    EPICS_PVA_SERVER_PORT=5075,

    # pvAccess server
    EPICS_PVAS_BEACON_ADDR_LIST='',
    EPICS_PVAS_AUTO_BEACON_ADDR_LIST='YES',
    EPICS_PVAS_BEACON_PERIOD=15.0,
    EPICS_PVAS_SERVER_PORT=5075,
    EPICS_PVAS_BROADCAST_PORT=5076,
    EPICS_PVAS_MAX_ARRAY_BYTES=16384,
    EPICS_PVAS_PROVIDER_NAMES='local',
    EPICS_PVAS_INTF_ADDR_LIST='',
    EPICS_PVA_PROVIDER_NAMES='local',
)


def get_environment_variables():
    '''Get a dictionary of known EPICS environment variables'''
    result = dict(os.environ)
    for key, default_value in _ENVIRONMENT_DEFAULTS.items():
        type_of_env_var = type(default_value)
        try:
            result[key] = type_of_env_var(result[key])
        except KeyError:
            result[key] = default_value
        except Exception as ex:
            raise CaprotoEnvironmentSetupError(f'Environment variable {key} misconfigured: '
                                               f'{ex.__class__.__name__} {ex}') from ex

    return result


def _split_address_list(addr_list):
    '''Split an address list string into individual items'''
    return list(set(addr for addr in addr_list.split(' ') if addr.strip()))


def get_manually_specified_beacon_addresses(
        *, protocol=Protocol.ChannelAccess):
    '''Get a list of addresses, as configured by EPICS_CA_ADDR_LIST'''
    protocol_key = Protocol(protocol).server_env_key
    return _split_address_list(
        get_environment_variables()[f'EPICS_{protocol_key}_BEACON_ADDR_LIST'])


def get_manually_specified_client_addresses(
        *, protocol=Protocol.ChannelAccess):
    '''Get a list of addresses, as configured by EPICS_CA_ADDR_LIST'''
    return _split_address_list(
        get_environment_variables()[f'EPICS_{protocol}_ADDR_LIST'])


def get_address_list(*, protocol=Protocol.ChannelAccess):
    '''
    Get channel access client address list based on environment variables

    If the address list is set to be automatic, the network interfaces will be
    scanned and used to determine the broadcast addresses available.
    '''
    protocol = Protocol(protocol)

    env = get_environment_variables()
    addresses = get_manually_specified_client_addresses(protocol=protocol)
    auto_addr_list = env[f'EPICS_{protocol}_AUTO_ADDR_LIST']

    if addresses and auto_addr_list.lower() != 'yes':
        # Custom address list specified, and EPICS_CA_AUTO_ADDR_LIST=NO
        auto_addr_list = []
    else:
        # No addresses configured or EPICS_CA_AUTO_ADDR_LIST=YES
        if netifaces is not None:
            auto_addr_list = [bcast for _, bcast in get_netifaces_addresses()]
        else:
            auto_addr_list = ['255.255.255.255']

    return list(set(addresses + auto_addr_list))


def get_client_address_list(*, protocol=Protocol.ChannelAccess):
    '''
    Get channel access client address list in the form of (host, port) based on
    environment variables.

    For CA, the default port is ``EPICS_CA_SERVER_PORT``.
    For PVA, the default port is ``EPICS_PVA_BROADCAST_PORT``.

    See Also
    --------
    :func:`get_address_list`
    '''
    protocol = Protocol(protocol)
    env = get_environment_variables()
    if protocol == Protocol.ChannelAccess:
        default_port = env['EPICS_CA_SERVER_PORT']
    else:
        default_port = env['EPICS_PVA_BROADCAST_PORT']

    return list(set(
        get_address_and_port_from_string(addr, default_port)
        for addr in get_address_list(protocol=protocol)
    ))


def get_address_and_port_from_string(
        address: str, default_port: int) -> typing.Tuple[str, int]:
    '''
    Return (address, port) tuple given an IP address of the form ``ip:port``
    or ``ip``.

    If no port is specified, the default port is used.

    Parameters
    ----------
    address : str
        The address.

    default_port : int
        The port to return if none is specified.

    Returns
    -------
    host : str
        The host IP address.

    port : int
        The specified or default port.
    '''
    if address.count(':') > 1:
        # May support [IPv6]:[port] in the future?
        raise ValueError(f'IPv6 or invalid address specified: {address}')

    if ':' in address:
        address, specified_port = address.split(':')
        return (address, int(specified_port))

    return (address, default_port)


def get_server_address_list(*, protocol=Protocol.ChannelAccess):
    '''Get the server interface addresses based on environment variables

    Returns
    -------
    list of interfaces
    '''
    protocol_key = Protocol(protocol).server_env_key

    key = f'EPICS_{protocol_key}_INTF_ADDR_LIST'
    intf_addrs = get_environment_variables()[key]

    if not intf_addrs:
        return ['0.0.0.0']

    def strip_port(addr):
        if ':' in addr:
            addr, _, specified_port = addr.partition(':')
            warn("Port specified in EPICS_CAS_INTF_ADDR_LIST was ignored.")
        return addr

    return list(set(strip_port(addr)
                    for addr in _split_address_list(intf_addrs)))


def get_beacon_address_list(*, protocol=Protocol.ChannelAccess):
    '''Get channel access beacon address list based on environment variables

    If the address list is set to be automatic, the network interfaces will be
    scanned and used to determine the broadcast addresses available.

    Returns
    -------
    addr_list : list of (addr, beacon_port)
    '''
    protocol_key = Protocol(protocol).server_env_key

    env = get_environment_variables()
    auto_addr_list = env[f'EPICS_{protocol_key}_AUTO_BEACON_ADDR_LIST']
    addr_list = get_manually_specified_beacon_addresses(protocol=protocol)
    if protocol == Protocol.ChannelAccess:
        beacon_port = env['EPICS_CAS_BEACON_PORT']
    else:
        beacon_port = env['EPICS_PVAS_BROADCAST_PORT']

    if addr_list and auto_addr_list.lower() != 'yes':
        # Custom address list and EPICS_CAS_AUTO_BEACON_ADDR_LIST=NO
        auto_list = []
    else:
        auto_list = ['255.255.255.255']

    return [
        get_address_and_port_from_string(addr, beacon_port)
        for addr in addr_list + auto_list
    ]


def get_netifaces_addresses():
    '''Get a list of addresses + broadcast using netifaces

    Yields (address, broadcast_address)
    '''
    if netifaces is None:
        raise CaprotoRuntimeError('netifaces unavailable')

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


@functools.lru_cache(maxsize=1)
def get_local_address() -> str:
    """
    Get the local IPv4 address.

    Falls back to 127.0.0.1 if netifaces is unavailable.

    Returns
    -------
    local_addr : str
        The local address.

    Notes
    -----
    The result from this function is cached by way of ``functools.lru_cache``
    such that it is only checked once.  Changes to network topology will not be
    accounted for after the first call.
    """
    fallback_address = socket.inet_ntoa(
        struct.pack("!I", socket.INADDR_LOOPBACK)
    )

    if netifaces is None:
        logger.debug('Netifaces unavailable; using %s as local address',
                     fallback_address)
        return fallback_address

    loopback_address = None

    for interface in netifaces.interfaces():
        for addr in netifaces.ifaddresses(interface).get(netifaces.AF_INET, []):
            try:
                ipv4 = ipaddress.IPv4Address(addr['addr'])
            except KeyError:
                continue

            if not ipv4.is_loopback:
                logger.debug('Found the first local address %s', ipv4)
                return str(ipv4)

            if loopback_address is None:
                loopback_address = str(ipv4)

    if loopback_address is not None:
        logger.debug(
            'Netifaces failed to find any local address, falling back to '
            'the loopback address %s', loopback_address
        )
        return loopback_address

    logger.warning(
        'Netifaces failed to find any local address, including a loopback '
        'address.  This is probably a caproto bug.  Falling back to: %s',
        fallback_address
    )
    return fallback_address


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


def random_ports(num, *, try_first=None):
    """Yield `num` random port numbers, optionally `try_first`."""
    if try_first is not None:
        yield try_first
    for _ in range(num):
        yield random.randint(49152, 65535)


def bcast_socket(socket_module=socket):
    """
    Make a socket and configure it for UDP broadcast.

    Parameters
    ----------
    socket_module: module, optional
        Default is the built-in :mod:`socket` module, but anything with the
        same interface may be used, such as :mod:`curio.socket`.
    """
    sock = socket_module.socket(socket_module.AF_INET, socket_module.SOCK_DGRAM)
    try:
        sock.setsockopt(socket_module.SOL_SOCKET, socket_module.SO_REUSEADDR, 1)
    except AttributeError:
        if sys.platform != 'win32':
            raise
        # WIN32_TODO: trio compatibility
        import socket as system_socket
        sock.setsockopt(socket_module.SOL_SOCKET,
                        system_socket.SO_REUSEADDR, 1)
        # sock.setsockopt(socket_module.SOL_SOCKET,
        #                 system_socket.SO_EXCLUSIVEADDRUSE, 1)

    sock.setsockopt(socket_module.SOL_SOCKET, socket_module.SO_BROADCAST, 1)

    # for BSD/Darwin only
    try:
        socket_module.SO_REUSEPORT
    except AttributeError:
        ...
    else:
        sock.setsockopt(socket_module.SOL_SOCKET, socket_module.SO_REUSEPORT, 1)
    return sock


if 'pypy' in sys.implementation.name:
    def _cast_buffers_to_byte(buffers):
        def inner(b):
            try:
                return memoryview(b).cast('b')
            except TypeError:
                target_type = b.dtype.str.replace('>', '<')
                return memoryview(b.astype(target_type)).cast('b')
        return tuple(inner(b) for b in buffers)

else:
    def _cast_buffers_to_byte(buffers):
        return tuple(memoryview(b).cast('b') for b in buffers)


def buffer_list_slice(*buffers, offset):
    'Helper function for slicing a list of buffers'
    if offset < 0:
        raise CaprotoValueError('Negative offset')

    buffers = _cast_buffers_to_byte(buffers)

    start = 0
    for bufidx, buf in enumerate(buffers):
        end = start + len(buf)
        if offset < end:
            offset -= start
            return (buf[offset:], ) + buffers[bufidx + 1:]

        start = end

    raise CaprotoValueError('Offset beyond end of buffers '
                            '(total length={} offset={})'.format(end, offset))


def incremental_buffer_list_slice(*buffers):
    'Incrementally slice a list of buffers'
    buffers = _cast_buffers_to_byte(buffers)
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
                    buffers_to_send = buffers_to_send[:len(buffers_to_send) // 2]

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
                    buffers_to_send = buffers_to_send[:len(buffers_to_send) // 2]
        except SendAllRetry:
            continue

        try:
            buffers_to_send = gen.send(sent)
        except StopIteration:
            # finished sending
            break


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
        elif '[' in field and field.endswith(']'):
            field, filter_ = field.split('[', 1)
            filter_ = '[' + filter_
            modifiers = RecordModifiers.filtered
        else:
            filter_ = None
            modifiers = None

        if field.endswith('$'):
            if modifiers is not None:
                modifiers |= RecordModifiers.long_string
            else:
                modifiers = RecordModifiers.long_string
            field = field[:-1]

    # NOTE: VAL is equated to 'record' at a higher level than this.
    if field:
        record_field = f'{record}.{field}'
    else:
        record_field = record

    if modifiers:
        modifiers = RecordModifier(modifiers, filter_=filter_)
    return RecordAndField(record_field, record, field, modifiers)


ChannelFilter = namedtuple('ChannelFilter', 'ts dbnd arr sync')
# TimestampFilter is just True or None, no need for namedtuple.
DeadbandFilter = namedtuple('DeadbandFilter', 'm d')
ArrayFilter = namedtuple('ArrayFilter', 's i e')
SyncFilter = namedtuple('SyncFilter', 'm s')

sync_modes = set(['before', 'first', 'while', 'last', 'after', 'unless'])


def parse_channel_filter(filter_text):
    "Parse and validate filter_text into a ChannelFilter."
    # https://epics.anl.gov/base/R3-15/5-docs/filters.html

    if not filter_text:
        return ChannelFilter(ts=False, dbnd=None, sync=None, arr=None)

    # If there is a shorthand array filter, that is the only filter allowed, so
    # we parse that and return, shortcircuiting the rest.
    if filter_text.startswith('[') and filter_text.endswith(']'):
        arr = parse_arr_shorthand_filter(filter_text)
        return ChannelFilter(ts=False, dbnd=None, sync=None, arr=arr)

    try:
        filter_ = json.loads(filter_text)
    except Exception as exc:
        raise FilterValidationError(
            f"Unable to parse channel filter text as JSON: "
            f"{filter_text}") from exc

    # If there is a shorthand sync filter, that is the only filter allowed.
    # Rewrite the filter to expand the shorthand and go through the normal
    # codepath.
    intersection = sync_modes & set(filter_)
    if intersection:
        if len(filter_) > 1:
            raise FilterValidationError(
                f"Found shorthand sync filter key {next(iter(intersection))} "
                f"This must be the only key if present but additional keys "
                f"were found: {filter_}")
        (mode, state), = filter_.items()
        filter_ = {"sync": {"m": mode, "s": state}}
    valid_filters = {'ts', 'arr', 'sync', 'dbnd'}
    filter_keys = set(filter_)
    invalid_keys = filter_keys - valid_filters
    if invalid_keys:
        raise FilterValidationError(f'Unsupported filters: {invalid_keys}')
    # Validate and normalize the filter, expanding "shorthand" notation and
    # applying defaults.
    return ChannelFilter(arr=parse_arr_filter(filter_.get('arr')),
                         dbnd=parse_dbnd_filter(filter_.get('dbnd')),
                         ts=parse_ts_filter(filter_.get('ts')),
                         sync=parse_sync_filter(filter_.get('sync')))


def parse_arr_shorthand_filter(filter_text):
    elements = []
    for elem in filter_text[1:-1].split(':'):
        if not elem:
            elements.append(None)
        else:
            elements.append(int(elem))
    if len(elements) == 1:
        arr = ArrayFilter(s=elements[0], i=1, e=elements[0])
    elif len(elements) == 2:
        arr = ArrayFilter(s=elements[0], i=1, e=elements[1])
    elif len(elements) == 3:
        arr = ArrayFilter(s=elements[0], i=elements[1], e=elements[2])
    return arr


def parse_ts_filter(val):
    if val is None:
        return None
    # Empty object means 'true' according to the spec:
    # https://epics.anl.gov/base/R3-15/3-docs/filters.html
    if val == {}:
        return True
    # We'll accept `true` and any other truth-y value also....
    return bool(val)


def parse_dbnd_filter(val):
    if val is None:
        return None
    if 'rel' in val:
        invalid_keys = set(val.keys()) - set(['rel'])
        if invalid_keys:
            raise FilterValidationError(
                f"Unsupported keys in 'dbnd': {invalid_keys}. When 'rel' "
                f"shorthand is used, no other keys may be used.")
        return DeadbandFilter(m='rel', d=float(val['rel']))
    if 'abs' in val:
        invalid_keys = set(val.keys()) - set(['abs'])
        if invalid_keys:
            raise FilterValidationError(
                f"Unsupported keys in 'dbnd': {invalid_keys}. When 'abs' "
                f"shorthand is used, no other keys may be used.")
        return DeadbandFilter(m='abs', d=float(val['abs']))
    else:
        invalid_keys = set(val.keys()) - set('dm')
        if invalid_keys:
            raise FilterValidationError(
                f"Unsupported keys in 'dbnd': {invalid_keys}")
        if set('md') != set(val.keys()):
            raise FilterValidationError(
                f"'dbnd' must include 'rel' or 'abs' or both 'd' and 'm'. "
                f"Found keys {set(val.keys())}.")
        return DeadbandFilter(m=float(val['m']), d=float(val['d']))


def parse_arr_filter(val):
    if val is None:
        return None
    invalid_keys = set(val.keys()) - set('sie')
    if invalid_keys:
        raise FilterValidationError(f"Unsupported keys in 'arr': "
                                    f"{invalid_keys}")
    return ArrayFilter(s=int(val.get('s', 0)),
                       i=int(val.get('i', 1)),
                       e=int(val.get('e', -1)))


def parse_sync_filter(val):
    if val is None:
        return None
    if set('ms') != set(val.keys()):
        raise FilterValidationError(
            f"'sync' must include both 'm' and 's'. "
            f"Found keys {set(val.keys())}.")
    if val['m'] not in sync_modes:
        raise FilterValidationError(f"Unsupported mode in 'sync': "
                                    f"{val['m']}")
    if not isinstance(val['s'], str):
        raise FilterValidationError(f"Unsupported type in 'sync': "
                                    f"value 's' must be a string. "
                                    f"Found {repr(val['s'])}.")
    return SyncFilter(m=val['m'], s=val['s'])


def apply_arr_filter(arr_filter, values):
    # Apply array Channel Filter.
    if arr_filter is None:
        return values
    start, stop, step = arr_filter.s, arr_filter.e, arr_filter.i
    # Cope with CA slice conventions being different from
    # Python's. It specifies an interval closed on both ends,
    # whereas Python's open open on the right end.
    if stop is not None:
        if stop == -1:
            stop = None
        else:
            stop += 1
    return values[start:stop:step]


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

    def __init__(self, *, initial_value=-1, dont_clash_with=None):
        if dont_clash_with is None:
            dont_clash_with = set()

        self.value = initial_value
        self.lock = threading.RLock()
        self.dont_clash_with = dont_clash_with

    def __call__(self):
        'Get next ID, wrapping around at 2**16, ensuring no clashes'
        with self.lock:
            value = self.value + 1

            while value in self.dont_clash_with or value >= self.MAX_ID:
                value = 0 if value >= self.MAX_ID else value + 1

            self.value = value
            return self.value


if sys.platform == 'win32' or fcntl is None:
    def socket_bytes_available(sock, *, default_buffer_size=4096,  # noqa
                               available_buffer=None):
        # No support for fcntl/termios on win32
        return default_buffer_size
else:
    def socket_bytes_available(sock, *, default_buffer_size=4096,
                               available_buffer=None):
        '''Return bytes available to receive on socket

        Parameters
        ----------
        sock : socket.socket
        default_buffer_size : int, optional
            Default recv buffer size, should the platform not support the call or
            the call fails for unknown reasons
        available_buffer : array.array, optional
            Array used for call to fcntl; can be specified to avoid reallocating
            many times
        '''
        if available_buffer is None:
            available_buffer = array.array('i', [0])

        ok = fcntl.ioctl(sock, termios.FIONREAD, available_buffer) >= 0
        return (max((available_buffer[0], default_buffer_size))
                if ok else default_buffer_size)


@contextmanager
def named_temporary_file(*args, delete=True, **kwargs):
    '''NamedTemporaryFile wrapper that works around issues in windows'''
    # See: https://bugs.python.org/issue14243

    from tempfile import NamedTemporaryFile
    with NamedTemporaryFile(*args, delete=False, **kwargs) as f:
        try:
            yield f
        finally:
            if delete:
                os.unlink(f.name)


class ShowVersionAction(argparse.Action):
    # a special action that allows the usage --version to override
    # any 'required args' requirements, the same way that --help does

    def __init__(self,
                 option_strings,
                 dest=argparse.SUPPRESS,
                 default=argparse.SUPPRESS,
                 help=None):
        super().__init__(
            option_strings=option_strings,
            dest=dest,
            default=default,
            nargs=0,
            help=help)

    def __call__(self, parser, namespace, values, option_string=None):
        print(__version__)
        parser.exit()


@functools.lru_cache(maxsize=128)
def safe_getsockname(sock):
    """
    Call sock.getsockname() and, on Windows, return ('0.0.0.0', 0) if an error is raised.

    This is a workaround to a critical issue affecting Windows. A better
    solution should be found but requires more discussion. See
    https://github.com/caproto/caproto/issues/514
    and issues/PRs linked from there.
    """
    try:
        return sock.getsockname()
    except Exception:
        if sys.platform != 'win32':
            raise
        # This is what the Linux OS returns for a unconnected socket that has
        # not yet been sent from.
        return ('0.0.0.0', 0)


def adapt_old_callback_signature(func, weakref_set):
    """
    If func has signature func(response), wrap in signature func(sub, response)

    Parameters
    ----------
    func: callable
        Expected signature ``f(response)`` or ``f(sub, response)``
    weakref_set: set
        Will be used to store state.

    Returns
    -------
    func: callable
        Signature ``f(sub, response)``
    """
    # Handle func with signature func(respons) for back-compat.
    sig = inspect.signature(func)
    try:
        # Does this function accept two positional arguments?
        sig.bind(None, None)
    except TypeError:
        warn(
            "The signature of a subscription callback is now expected to "
            "be func(sub, response). The signature func(response) is "
            "supported, but support will be removed in a future release "
            "of caproto.")
        raw_func = func
        raw_func_weakref = weakref.ref(raw_func)

        def func(sub, response):
            # Avoid closing over raw_func itself here or it will never be
            # garbage collected.
            raw_func = raw_func_weakref()
            if raw_func is not None:
                # Do nothing with sub because the user-provided func cannot
                # accept it.
                raw_func(response)

        # Ensure func does not get garbage collected until raw_func does.
        def called_when_raw_func_is_released(w):
            # The point of this function is to hold one hard ref to func
            # until raw_func is garbage collected.
            func
            # Clean up after ourselves.
            weakref_set.remove(w)

        w = weakref.ref(raw_func, called_when_raw_func_is_released)
        # Hold a hard reference to w. Its callback removes it from this set.
        weakref_set.add(w)
    return func
