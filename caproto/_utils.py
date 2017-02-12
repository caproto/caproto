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

sentinels = ("CLIENT SERVER "
             "NEED_DATA "
             # states
             "SEND_SEARCH_REQUEST AWAIT_SEARCH_RESPONSE "
             "SEND_SEARCH_RESPONSE NEED_CIRCUIT "
             "SEND_VERSION_REQUEST AWAIT_VERSION_RESPONSE "
             "SEND_VERSION_RESPONSE "
             "SEND_CREATE_CHAN_REQUEST AWAIT_CREATE_CHAN_RESPONSE "
             "SEND_CREATE_CHAN_RESPONSE "
             "CONNECTED MUST_CLOSE DISCONNECTED IDLE ERROR".split())
for token in sentinels:
    globals()[token] = make_sentinel(token)


class CaprotoError(Exception):
    # All exceptions raised by this codebase inherit from this.
    ...


class ChannelAccessProtocolError(CaprotoError):
    # Any error resulting from sending or receiving a command will raise (a
    # subclass of) this error and never any other error.
    ...


class LocalProtocolError(ChannelAccessProtocolError):
    ...


class RemoteProtocolError(ChannelAccessProtocolError):
    ...


class UninitializedVirtualCircuit(CaprotoError):
    ...


class CaprotoKeyError(KeyError, CaprotoError):
    ...


class CaprotoValueError(ValueError, CaprotoError):
    ...


class CaprotoTypeError(TypeError, CaprotoError):
    ...
