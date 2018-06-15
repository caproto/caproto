import enum
import ctypes
import ipaddress
from .._utils import (CaprotoKeyError, CaprotoValueError, CaprotoRuntimeError,
                      CaprotoError, ErrorResponseReceived,
                      CLIENT, SERVER, _SimpleReprEnum,
                      LocalProtocolError, RemoteProtocolError,
                      ThreadsafeCounter)


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
    # also: DISCONNECTED, DESTROYED


globals().update(
    {token: getattr(_enum, token)
     for _enum in [ConnectionState, ChannelLifeCycle, ChannelRequest]
     for token in dir(_enum)
     if not token.startswith('_')
     })


def ubyte_array_to_ip(arr):
    'Convert an address encoded as a c_ubyte array to a string'
    addr = ipaddress.ip_address(bytes(arr))
    ipv4 = addr.ipv4_mapped
    if ipv4:
        return str(ipv4)
    else:
        return str(addr)


def ip_to_ubyte_array(ip):
    'Convert an IPv4 or IPv6 to a c_ubyte*16 array'
    addr = ipaddress.ip_address(ip)
    packed = addr.packed
    if len(packed) == 4:
        # case of IPv4
        packed = [0] * 10 + [0xff, 0xff] + list(packed)

    return (ctypes.c_ubyte * 16)(*packed)
