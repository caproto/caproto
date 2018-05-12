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
from .messages import (ApplicationCommands,
                       DirectionFlag,
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
            # ConnectionValidationRequest: INIT,
            SetByteOrder: CONNECTED,
        },
        CONNECTED: {
            ConnectionValidationRequest: CONNECTED,
            ConnectionValidationResponse: CONNECTED,
            ConnectionValidatedResponse: CONNECTED,
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
            ConnectionValidationRequest: CONNECTED,
            ConnectionValidationResponse: CONNECTED,
            ConnectionValidatedResponse: CONNECTED,
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

    # MERGE
    def _fire_command_triggered_transitions(self, role, command):
        command_type = type(command)
        current_state = self.states[role]
        allowed_transitions = self.TRANSITIONS[role][current_state]
        try:
            new_state = allowed_transitions[command_type]
        except KeyError:
            err_cls = get_exception(role, command)
            err = err_cls(f"{self} cannot handle command type "
                          f"{command_type.__name__} when role={role} and "
                          f"state={self.states[role]}")
            raise err from None
        self.states[role] = new_state


class CircuitState(_CircuitState):
    TRANSITIONS = COMMAND_TRIGGERED_CIRCUIT_TRANSITIONS

    def __init__(self, channels):
        self.states = {CLIENT: INIT, SERVER: INIT}
        self.channels = channels

    # MERGE
    def _fire_command_triggered_transitions(self, role, command):
        command_type = type(command)
        if command_type._ENDIAN is not None:
            if command_type.ID in ApplicationCommands:
                command_type = command_type.__bases__[0]
                # TODO: HACK! Horrible, horrible hack...
                # This side-steps putting big- and little-endian messages in
                # the state transition dictionary. This should be redone.

        current_state = self.states[role]
        allowed_transitions = self.TRANSITIONS[role][current_state]
        try:
            new_state = allowed_transitions[command_type]
        except KeyError:
            err_cls = get_exception(role, command)
            err = err_cls(f"{self} cannot handle command type "
                          f"{command_type.__name__} when role={role} and "
                          f"state={self.states[role]}")
            raise err from None
        self.states[role] = new_state


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
    if not hasattr(command, 'direction') and hasattr(command, 'header'):
        # TODO
        direction = command.header.direction
    else:
        direction = command.direction

    if direction == DirectionFlag.FROM_CLIENT:
        party_at_fault = CLIENT
    elif direction == DirectionFlag.FROM_SERVER:
        party_at_fault = SERVER

    if our_role is party_at_fault:
        _class = LocalProtocolError
    else:
        _class = RemoteProtocolError
    return _class
