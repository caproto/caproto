import os
import socket

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


def broadcast_address_list_from_interfaces():
    '''Get a list of broadcast addresses using netifaces

    If netifaces is unavailable, the standard IPv4 255.255.255.255 broadcast
    address is returned.
    '''
    if netifaces is None:
        return ['255.255.255.255']

    interfaces = [netifaces.ifaddresses(interface)
                  for interface in netifaces.interfaces()
                  ]

    bcast = [af_inet_info['broadcast']
             if 'broadcast' in af_inet_info
             else af_inet_info['peer']

             for interface in interfaces
             if netifaces.AF_INET in interface
             for af_inet_info in interface[netifaces.AF_INET]
             ]

    return bcast


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
