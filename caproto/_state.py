from ._messages import *
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

sentinels = ("CHANNEL VIRTUAL_CIRCUIT "
             # states
             "BROADCAST_SEARCH NEEDS_BROADCAST_SEARCH_RESPONSE "
             "CONNECT_CIRCUIT NEEDS_CONNECT_CIRCUIT_RESPONSE "
             "CREATE_CHANNEL NEEDS_CREATE_CHANNEL_RESPONSE "
             "READY SUBSCRIBED CONNECTED UNINITIALIZED DISCONNECTED "
             # responses
             "NEEDS_DATA SearchResponse VersionResponse "
             "CreateChanResponse".split())
for token in sentinels:
    globals()[token] = make_sentinel(token)


class ChannelAccessProtocolError(Exception):
    ...


class LocalProtocolError(ChannelAccessProtocolError):
    ...


EVENT_TRIGGERED_TRANSITIONS = {
    CHANNEL: {
        BROADCAST_SEARCH: {
            SearchRequest: NEEDS_BROADCAST_SEARCH_RESPONSE
        },
        NEEDS_BROADCAST_SEARCH_RESPONSE: {
            SearchResponse: CONNECT_CIRCUIT
        },
        CREATE_CHANNEL: {
            CreateChanRequest: NEEDS_CREATE_CHANNEL_RESPONSE
        },
        NEEDS_CREATE_CHANNEL_RESPONSE: {
            CreateChanResponse: READY
        },
        READY: {
            EventAddRequest: SUBSCRIBED
        },
        SUBSCRIBED: {
            EventCancelRequest: READY
        },
    },
    VIRTUAL_CIRCUIT: {
        UNINITIALIZED: {
            VersionRequest: NEEDS_CONNECT_CIRCUIT_RESPONSE
        },
        NEEDS_CONNECT_CIRCUIT_RESPONSE: {
            VersionResponse: CONNECTED
        },
        CONNECTED: {
            ClearChannelRequest: DISCONNECTED
        },
        DISCONNECTED: {
            VersionResponse: CONNECTED
        },
    }
}


class ClientState:
    def __init__(self):
        self.role = CHANNEL
        self.state = BROADCAST_SEARCH
    
    def process_event(self, event):
        self._fire_event_triggered_transitions(self.role, type(event))

    def _fire_event_triggered_transitions(self, role, event_type):
        state = self.state
        try:
            new_state = EVENT_TRIGGERED_TRANSITIONS[role][state][event_type]
        except KeyError:
            raise LocalProtocolError(
                "can't handle event type {} when role={} and state={}"
                .format(event_type.__name__, role, self.state))
        self.state = new_state
