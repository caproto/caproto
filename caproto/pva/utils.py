import ctypes
import ipaddress
import itertools
from .._utils import (CaprotoKeyError, CaprotoValueError, CaprotoRuntimeError,
                      CaprotoError, ErrorResponseReceived,
                      CLIENT, SERVER, make_sentinel,
                      LocalProtocolError, RemoteProtocolError,
                      ThreadsafeCounter)


# Connection state
CONNECTED = make_sentinel('CONNECTED')
RESPONSIVE = make_sentinel('RESPONSIVE')
UNRESPONSIVE = make_sentinel('UNRESPONSIVE')
DISCONNECTED = make_sentinel('DISCONNECTED')

# Channel life-cycle
NEVER_CONNECTED = make_sentinel('NEVER_CONNECTED')
# also: CONNECTED, DISCONNECTED
DESTROYED = make_sentinel('DESTROYED')
NEED_DATA = make_sentinel('NEED_DATA')

# Channel request
INIT = make_sentinel('INIT')
READY = make_sentinel('READY')
IN_PROGRESS = make_sentinel('IN_PROGRESS')
# also: DISCONNECTED, DESTROYED


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
