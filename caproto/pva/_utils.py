import ctypes
import datetime
import enum
import ipaddress
import uuid

from .._utils import (CLIENT, SERVER, CaprotoError, CaprotoKeyError,
                      CaprotoRuntimeError, CaprotoValueError,
                      ErrorResponseReceived, LocalProtocolError,
                      RemoteProtocolError, Role, ThreadsafeCounter,
                      _SimpleReprEnum)

# Borrow some items from top-level utils:
__all__ = [
    'CLIENT', 'SERVER', 'CaprotoError', 'CaprotoKeyError',
    'CaprotoRuntimeError', 'CaprotoValueError',
    'ErrorResponseReceived', 'LocalProtocolError',
    'RemoteProtocolError', 'Role', 'ThreadsafeCounter',

    # And add on our own:
    'ConnectionState', 'ChannelLifeCycle', 'ChannelRequest',

    'CONNECTED', 'RESPONSIVE', 'UNRESPONSIVE', 'DISCONNECTED',
    'NEVER_CONNECTED', 'DESTROYED', 'NEED_DATA', 'CLEAR_SEGMENTS',
    'INIT', 'READY', 'IN_PROGRESS',

    'ubyte_array_to_ip', 'ip_to_ubyte_array', 'timestamp_to_datetime',
    'new_guid',
]


class ConnectionState(_SimpleReprEnum):
    # Connection state
    CONNECTED = enum.auto()
    RESPONSIVE = enum.auto()
    UNRESPONSIVE = enum.auto()
    DISCONNECTED = enum.auto()


class ChannelLifeCycle(_SimpleReprEnum):
    # Channel life-cycle
    NEVER_CONNECTED = enum.auto()
    # also: CONNECTED, DISCONNECTED
    DESTROYED = enum.auto()
    NEED_DATA = enum.auto()
    CLEAR_SEGMENTS = enum.auto()


class ChannelRequest(_SimpleReprEnum):
    # Channel request
    INIT = enum.auto()
    READY = enum.auto()
    IN_PROGRESS = enum.auto()
    DESTROY_AFTER = enum.auto()
    DISCONNECTED = enum.auto()
    DESTROYED = enum.auto()


CONNECTED = ConnectionState.CONNECTED
RESPONSIVE = ConnectionState.RESPONSIVE
UNRESPONSIVE = ConnectionState.UNRESPONSIVE
DISCONNECTED = ConnectionState.DISCONNECTED

NEVER_CONNECTED = ChannelLifeCycle.NEVER_CONNECTED
DESTROYED = ChannelLifeCycle.DESTROYED
NEED_DATA = ChannelLifeCycle.NEED_DATA
CLEAR_SEGMENTS = ChannelLifeCycle.CLEAR_SEGMENTS

INIT = ChannelRequest.INIT
READY = ChannelRequest.READY
IN_PROGRESS = ChannelRequest.IN_PROGRESS


def ubyte_array_to_ip(arr):
    'Convert an address encoded as a c_ubyte array to a string'
    addr = ipaddress.ip_address(bytes(arr))
    ipv4 = addr.ipv4_mapped
    if ipv4:
        return str(ipv4)
    return str(addr)


def ip_to_ubyte_array(ip):
    'Convert an IPv4 or IPv6 to a c_ubyte*16 array'
    addr = ipaddress.ip_address(ip)
    packed = addr.packed
    if len(packed) == 4:
        # case of IPv4
        packed = [0] * 10 + [0xff, 0xff] + list(packed)

    return (ctypes.c_ubyte * 16)(*packed)


def timestamp_to_datetime(seconds: int,
                          nanoseconds: int) -> datetime.datetime:
    """
    Given seconds and nanoseconds that make up a posix timestamp, return a
    datetime.datetime.
    """
    posix_timestamp = seconds + nanoseconds * 1e-9
    return datetime.datetime.fromtimestamp(posix_timestamp)


def new_guid() -> str:
    """A pva-compatible UUID (of length 12)."""
    return str(uuid.uuid4()).replace('-', '')[:12]
