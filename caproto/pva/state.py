from .._utils import (CLIENT, SERVER, make_sentinel,
                      LocalProtocolError, RemoteProtocolError)
from .._state import (CircuitState as _CircuitState,
                      ChannelState as _ChannelState)
from .messages import (DirectionFlag,
                       _Status,  # ExtendedMessageBase
                       _BeaconMessage,  # ExtendedMessageBase
                       SetMarker,  # MessageHeaderLE
                       AcknowledgeMarker,  # MessageHeaderLE
                       SetByteOrder,  # MessageHeaderLE
                       _ConnectionValidationRequest,  # ExtendedMessageBase
                       _ConnectionValidationResponse,  # ExtendedMessageBase
                       _Echo,  # ExtendedMessageBase
                       _ConnectionValidatedResponse,  # _Status
                       _SearchRequest,  # ExtendedMessageBase
                       _SearchResponse,  # ExtendedMessageBase
                       _CreateChannelRequest,  # ExtendedMessageBase
                       _CreateChannelResponse,  # ExtendedMessageBase
                       _ChannelGetRequest,  # ExtendedMessageBase
                       _ChannelGetResponse,  # ExtendedMessageBase
                       _ChannelFieldInfoRequest,  # ExtendedMessageBase
                       _ChannelFieldInfoResponse,  # ExtendedMessageBase
                       )


# Connection state
CONNECTED = make_sentinel('CONNECTED')
RESPONSIVE = make_sentinel('RESPONSIVE')
UNRESPONSIVE = make_sentinel('UNRESPONSIVE')
DISCONNECTED = make_sentinel('DISCONNECTED')

# Channel life-cycle
NEVER_CONNECTED = make_sentinel('NEVER_CONNECTED')
# also: CONNECTED, DISCONNECTED
DESTROYED = make_sentinel('DESTROYED')

# Channel request
INIT = make_sentinel('INIT')
READY = make_sentinel('READY')
IN_PROGRESS = make_sentinel('IN_PROGRESS')
# also: DISCONNECTED, DESTROYED


COMMAND_TRIGGERED_CIRCUIT_TRANSITIONS = {
    CLIENT: {
        CONNECTED: {
        },
        RESPONSIVE: {
        },
        UNRESPONSIVE: {
        },
        DISCONNECTED: {
            # a terminal state that may only be reached by a special method
        },
    },
    SERVER: {
        CONNECTED: {
        },
        RESPONSIVE: {
        },
        UNRESPONSIVE: {
        },
        DISCONNECTED: {
            # a terminal state that may only be reached by a special method
        },
    },
}


COMMAND_TRIGGERED_CHANNEL_TRANSITIONS = {
    CLIENT: {
    },
    SERVER: {
    },
}

STATE_TRIGGERED_TRANSITIONS = {
    # (CHANNEL_STATE, CIRCUIT_STATE)
    CLIENT: {
        # (SEND_CREATE_CHAN_REQUEST, DISCONNECTED): (CLOSED, DISCONNECTED),
    },
    SERVER: {
        # (SEND_CREATE_CHAN_RESPONSE, DISCONNECTED): (CLOSED, DISCONNECTED),
    }
}


class ChannelState(_ChannelState):
    TRANSITIONS = COMMAND_TRIGGERED_CHANNEL_TRANSITIONS
    STT = STATE_TRIGGERED_TRANSITIONS

    def __init__(self, circuit_state):
        self.states = {CLIENT: NEVER_CONNECTED,
                       SERVER: NEVER_CONNECTED}
        self.circuit_state = circuit_state


class CircuitState(_CircuitState):
    TRANSITIONS = COMMAND_TRIGGERED_CIRCUIT_TRANSITIONS

    def __init__(self, channels):
        self.states = {CLIENT: CONNECTED, SERVER: CONNECTED}
        self.channels = channels


# MERGE
def get_exception(our_role, command):
    """
    Return a (Local|Remote)ProtocolError depending on which command this is and
    which role we are playing.

    Note that this method does not raise; it is up to the caller to raise.

    Parameters
    ----------
    our_role: ``CLIENT`` or ``SERVER``
    command : Message instance or class
        We will test whether it is a ``REQUEST`` or ``RESPONSE``.
    """
    # TO DO Give commands an attribute so we can easily check whether one
    # is a Request or a Response
    if command.direction == DirectionFlag.FROM_CLIENT:
        party_at_fault = CLIENT
    elif command.direction == DirectionFlag.FROM_SERVER:
        party_at_fault = SERVER

    if our_role is party_at_fault:
        _class = LocalProtocolError
    else:
        _class = RemoteProtocolError
    return _class
