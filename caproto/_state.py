from ._commands import *
from ._utils import *


COMMAND_TRIGGERED_CIRCUIT_TRANSITIONS = {
    CLIENT: {
        SEND_VERSION_REQUEST: {
            VersionRequest: AWAIT_VERSION_RESPONSE,
            ErrorResponse: ERROR,
        },
        AWAIT_VERSION_RESPONSE: {
            VersionResponse: CONNECTED,
            ErrorResponse: ERROR,
        },
        CONNECTED: {
            ErrorResponse: ERROR,
            HostNameRequest: CONNECTED,
            ClientNameRequest: CONNECTED,
            AccessRightsResponse: CONNECTED,
            # VirtualCircuits can only be closed by timeout.
        },
        ERROR: {},
    },
    SERVER: {
        IDLE: {
            VersionRequest: SEND_VERSION_RESPONSE,
        },
        SEND_VERSION_RESPONSE: {
            VersionResponse: CONNECTED,
        },
        CONNECTED: {
            HostNameRequest: CONNECTED,
            ClientNameRequest: CONNECTED,
            AccessRightsResponse: CONNECTED,
            # VirtualCircuits can only be closed by timeout.
        },
    },
}


COMMAND_TRIGGERED_CHANNEL_TRANSITIONS = {
    CLIENT: {
        # Remove SEARCH from the state machine entirely?
        SEND_SEARCH_REQUEST: {
            SearchRequest: AWAIT_SEARCH_RESPONSE,
            ErrorResponse: ERROR,
        },
        AWAIT_SEARCH_RESPONSE: {
            SearchResponse: NEED_CIRCUIT,  # escape via state-based transition
            ErrorResponse: ERROR,
        },
        SEND_CREATE_CHAN_REQUEST: {
            CreateChanRequest: AWAIT_CREATE_CHAN_RESPONSE,
            ErrorResponse: ERROR,
        },
        AWAIT_CREATE_CHAN_RESPONSE: {
            CreateChanResponse: CONNECTED,
            ErrorResponse: ERROR,
        },
        CONNECTED: {
            ClearChannelRequest: MUST_CLOSE,
            ServerDisconnResponse: DISCONNECTED,
            ErrorResponse: ERROR,
            ReadNotifyRequest: CONNECTED,
            WriteNotifyRequest: CONNECTED,
            EventAddRequest: CONNECTED,
            ReadNotifyResponse: CONNECTED,
            WriteNotifyResponse: CONNECTED,
            EventAddResponse: CONNECTED,
        },
        MUST_CLOSE: {
            ClearChannelResponse: DISCONNECTED,
        },
        ERROR: {}, 
    },
    SERVER: {
        IDLE: {
            SearchRequest: SEND_SEARCH_RESPONSE,
            CreateChanRequest: SEND_CREATE_CHAN_RESPONSE,
            ClearChannelResponse: IDLE,
        },
        SEND_SEARCH_RESPONSE: {
            SearchResponse: IDLE,
        },
        SEND_CREATE_CHAN_RESPONSE: {
            CreateChanResponse: CONNECTED,
            # HostNameRequest and ClientNameRequest may arrive before or
            # after response to connection is sent.
            HostNameRequest: SEND_CREATE_CHAN_RESPONSE,
            ClientNameRequest: SEND_CREATE_CHAN_RESPONSE,
        },
        CONNECTED: {
            ClearChannelRequest: IDLE,
            ReadNotifyRequest: CONNECTED,
            WriteNotifyRequest: CONNECTED,
            EventAddRequest: CONNECTED,  # TODO a subscription state machine?
            ReadNotifyResponse: CONNECTED,
            WriteNotifyResponse: CONNECTED,
            EventAddResponse: CONNECTED,
        },
    },
}

STATE_TRIGGERED_TRANSITIONS = {
    # (CHANNEL_STATE, CIRCUIT_STATE)
    CLIENT: {
        (NEED_CIRCUIT, CONNECTED): (SEND_CREATE_CHAN_REQUEST, CONNECTED),
    },
    SERVER: {
    }
}


class _BaseState:
    def _fire_command_triggered_transitions(self, role, command_type):
        state = self.states[role]
        try:
            new_state = self.TRANSITIONS[role][state][command_type]
        except KeyError:
            raise LocalProtocolError(
                "can't handle command type {} when role={} and state={}"
                .format(command_type.__name__, role, self.states[role]))
        self.states[role] = new_state


class ChannelState(_BaseState):
    TRANSITIONS = COMMAND_TRIGGERED_CHANNEL_TRANSITIONS
    STT = STATE_TRIGGERED_TRANSITIONS

    def __init__(self):
        self.states = {CLIENT: SEND_SEARCH_REQUEST, SERVER: IDLE}
        # At __init__ time we do not know whether there is already a circuit
        # we can use for this channel or if we will need to create a new one.
        self.circuit_state = None

    def couple_circuit(self, circuit):
        self.circuit_state = circuit._state

    def _fire_state_triggered_transitions(self):
        new = self.STT[CLIENT].get((self.states[CLIENT],
                                    self.circuit_state.states[CLIENT]))
        if new is not None:
            self.states[CLIENT], self.circuit_state.states[CLIENT] = new

    def process_command(self, role, command_type):
        if self.circuit_state is not None:
            self._fire_state_triggered_transitions()
        self._fire_command_triggered_transitions(role, command_type)
        if self.circuit_state is not None:
            self._fire_state_triggered_transitions()
    

class CircuitState(_BaseState):
    TRANSITIONS = COMMAND_TRIGGERED_CIRCUIT_TRANSITIONS

    def __init__(self):
        self.states = {CLIENT: SEND_VERSION_REQUEST, SERVER: IDLE}

    def process_command(self, role, command_type):
        self._fire_command_triggered_transitions(role, command_type)
