from .utils import (CLIENT, SERVER,
                    LocalProtocolError, RemoteProtocolError,

                    # Connection state
                    CONNECTED, RESPONSIVE, UNRESPONSIVE, DISCONNECTED,

                    # Channel life-cycle
                    NEVER_CONNECTED, DESTROYED, NEED_DATA,
                    # also: CONNECTED, DISCONNECTED

                    # Channel request
                    INIT, READY, IN_PROGRESS,
                    # also: DISCONNECTED, DESTROYED
                    )

from .._state import (CircuitState as _CircuitState,
                      ChannelState as _ChannelState)
from .messages import (DirectionFlag,
                       Status,  # ExtendedMessageBase
                       BeaconMessage,  # ExtendedMessageBase
                       SetMarker,  # MessageHeaderLE
                       AcknowledgeMarker,  # MessageHeaderLE
                       SetByteOrder,  # MessageHeaderLE
                       ConnectionValidationRequest,  # ExtendedMessageBase
                       ConnectionValidationResponse,  # ExtendedMessageBase
                       Echo,  # ExtendedMessageBase
                       ConnectionValidatedResponse,  # _Status
                       SearchRequest,  # ExtendedMessageBase
                       SearchResponse,  # ExtendedMessageBase
                       CreateChannelRequest,  # ExtendedMessageBase
                       CreateChannelResponse,  # ExtendedMessageBase
                       ChannelGetRequest,  # ExtendedMessageBase
                       ChannelGetResponse,  # ExtendedMessageBase
                       ChannelFieldInfoRequest,  # ExtendedMessageBase
                       ChannelFieldInfoResponse,  # ExtendedMessageBase
                       )



COMMAND_TRIGGERED_CIRCUIT_TRANSITIONS = {
    CLIENT: {
        INIT: {
            SetByteOrder: CONNECTED,
        },
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
        INIT: {
            SetByteOrder: CONNECTED,
        },
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
