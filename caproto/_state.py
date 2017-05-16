from ._commands import (AccessRightsResponse, ClearChannelRequest,
                        ClearChannelResponse, ClientNameRequest,
                        CreateChanRequest, CreateChanResponse, EchoRequest,
                        EchoResponse, ErrorResponse, EventAddRequest,
                        EventAddResponse, EventCancelRequest,
                        EventCancelResponse, HostNameRequest,
                        ReadNotifyRequest, ReadNotifyResponse,
                        ServerDisconnResponse, VersionRequest, VersionResponse,
                        WriteNotifyRequest, WriteNotifyResponse, WriteRequest,
                        EventsOnRequest, EventsOffRequest, CreateChFailResponse
                       )
from ._utils import (AWAIT_CREATE_CHAN_RESPONSE, AWAIT_VERSION_RESPONSE,
                     CLIENT, CLOSED, CONNECTED, DISCONNECTED, FAILED, IDLE,
                     MUST_CLOSE, REQUEST, RESPONSE, SEND_CREATE_CHAN_REQUEST,
                     SEND_CREATE_CHAN_RESPONSE, SEND_VERSION_REQUEST,
                     SEND_VERSION_RESPONSE, SERVER,

                     LocalProtocolError, RemoteProtocolError,
                     )


COMMAND_TRIGGERED_CIRCUIT_TRANSITIONS = {
    CLIENT: {
        SEND_VERSION_REQUEST: {
            VersionRequest: AWAIT_VERSION_RESPONSE,

            # C channel access server (rsrv) sends VersionResponse upon TCP
            # connection, unprompted by a VersionRequest, so we must accept
            # that here.
            VersionResponse: SEND_VERSION_REQUEST,
        },
        AWAIT_VERSION_RESPONSE: {
            VersionResponse: CONNECTED,

            # Host and Client requests may come before or after we connect.
            HostNameRequest: AWAIT_VERSION_RESPONSE,
            ClientNameRequest: AWAIT_VERSION_RESPONSE,

            EchoRequest: AWAIT_VERSION_RESPONSE,
            EchoResponse: AWAIT_VERSION_RESPONSE,
            ErrorResponse: AWAIT_VERSION_RESPONSE,
        },
        CONNECTED: {
            # Host and Client requests may come before or after we connect.
            HostNameRequest: CONNECTED,
            ClientNameRequest: CONNECTED,

            EventsOffRequest: CONNECTED,
            EventsOnRequest: CONNECTED,

            EchoRequest: CONNECTED,
            EchoResponse: CONNECTED,

            ErrorResponse: CONNECTED,
        },
        DISCONNECTED: {
            # a terminal state that may only be reached by a special method
        },
    },
    SERVER: {
        IDLE: {
            VersionRequest: SEND_VERSION_RESPONSE,

            # C channel access server (rsrv) sends VersionResponse upon TCP
            # connection, unprompted by a VersionRequest, so we must accept
            # that here.
            VersionResponse: IDLE,
        },
        SEND_VERSION_RESPONSE: {
            VersionResponse: CONNECTED,

            # Host and Client requests may come before or after we connect.
            HostNameRequest: SEND_VERSION_RESPONSE,
            ClientNameRequest: SEND_VERSION_RESPONSE,

            ErrorResponse: SEND_VERSION_RESPONSE,
        },
        CONNECTED: {
            # Host and Client requests may come before or after we connect.
            HostNameRequest: CONNECTED,
            ClientNameRequest: CONNECTED,

            EventsOffRequest: CONNECTED,
            EventsOnRequest: CONNECTED,

            EchoRequest: CONNECTED,
            EchoResponse: CONNECTED,

            ErrorResponse: CONNECTED,
        },
        DISCONNECTED: {
            # a terminal state that may only be reached by a special method
        },
    },
}


COMMAND_TRIGGERED_CHANNEL_TRANSITIONS = {
    CLIENT: {
        SEND_CREATE_CHAN_REQUEST: {
            CreateChanRequest: AWAIT_CREATE_CHAN_RESPONSE,
            ErrorResponse: SEND_CREATE_CHAN_REQUEST,
        },
        AWAIT_CREATE_CHAN_RESPONSE: {
            CreateChanResponse: CONNECTED,
            AccessRightsResponse: AWAIT_CREATE_CHAN_RESPONSE,
            CreateChFailResponse: FAILED,
            ErrorResponse: AWAIT_CREATE_CHAN_RESPONSE,
        },
        CONNECTED: {
            AccessRightsResponse: CONNECTED,

            ReadNotifyRequest: CONNECTED,
            ReadNotifyResponse: CONNECTED,
            WriteNotifyRequest: CONNECTED,
            WriteNotifyResponse: CONNECTED,
            WriteRequest: CONNECTED,

            EventAddRequest: CONNECTED,
            EventAddResponse: CONNECTED,
            EventCancelRequest: CONNECTED,
            EventCancelResponse: CONNECTED,

            ClearChannelRequest: MUST_CLOSE,
            ServerDisconnResponse: CLOSED,
            ErrorResponse: CONNECTED,

            # The commands ReadRequest, WriteResponse, and
            # ReadSync (deprecated in 3.13) will need to be added here if we
            # want to support them.
        },
        MUST_CLOSE: {
            ClearChannelResponse: CLOSED,
            ServerDisconnResponse: CLOSED,
            ErrorResponse: MUST_CLOSE,
        },
        CLOSED: {
            # a terminal state
        },
        FAILED: {
            # a terminal state
            ClearChannelResponse: FAILED,
            ServerDisconnResponse: FAILED,
            ErrorResponse: FAILED
        },
    },
    SERVER: {
        IDLE: {
            CreateChanRequest: SEND_CREATE_CHAN_RESPONSE,
            # No ErrorResponse possible here because we don't have a cid yet.
        },
        SEND_CREATE_CHAN_RESPONSE: {
            AccessRightsResponse: SEND_CREATE_CHAN_RESPONSE,
            CreateChanResponse: CONNECTED,
            CreateChFailResponse: FAILED,
            ErrorResponse: SEND_CREATE_CHAN_RESPONSE,
        },
        CONNECTED: {
            AccessRightsResponse: CONNECTED,

            ReadNotifyRequest: CONNECTED,
            ReadNotifyResponse: CONNECTED,
            WriteNotifyRequest: CONNECTED,
            WriteNotifyResponse: CONNECTED,
            WriteRequest: CONNECTED,

            EventAddRequest: CONNECTED,
            EventAddResponse: CONNECTED,
            EventCancelRequest: CONNECTED,
            EventCancelResponse: CONNECTED,

            ClearChannelRequest: MUST_CLOSE,
            ServerDisconnResponse: CLOSED,
            ErrorResponse: CONNECTED,
            # The commands ReadRequest, WriteResponse, and
            # ReadSync (deprecated in 3.13) will need to be added here if we
            # want to support them.
        },
        MUST_CLOSE: {
            ClearChannelResponse: CLOSED,
            ServerDisconnResponse: CLOSED,
            ErrorResponse: MUST_CLOSE,
        },
        CLOSED: {
            # a terminal state
        },
        FAILED: {
            # a terminal state
            ClearChannelResponse: FAILED,
            ServerDisconnResponse: FAILED,
            ErrorResponse: FAILED
        },
    },
}

STATE_TRIGGERED_TRANSITIONS = {
    # (CHANNEL_STATE, CIRCUIT_STATE)
    CLIENT: {
        (SEND_CREATE_CHAN_REQUEST, DISCONNECTED): (CLOSED, DISCONNECTED),
        (AWAIT_CREATE_CHAN_RESPONSE, DISCONNECTED): (CLOSED, DISCONNECTED),
        (CONNECTED, DISCONNECTED): (CLOSED, DISCONNECTED),
        (MUST_CLOSE, DISCONNECTED): (CLOSED, DISCONNECTED),
        (FAILED, DISCONNECTED): (CLOSED, DISCONNECTED),
        (CLOSED, DISCONNECTED): (CLOSED, DISCONNECTED),
    },
    SERVER: {
        (SEND_CREATE_CHAN_RESPONSE, DISCONNECTED): (CLOSED, DISCONNECTED),
        (CONNECTED, DISCONNECTED): (CLOSED, DISCONNECTED),
        (MUST_CLOSE, DISCONNECTED): (CLOSED, DISCONNECTED),
        (FAILED, DISCONNECTED): (CLOSED, DISCONNECTED),
        (CLOSED, DISCONNECTED): (CLOSED, DISCONNECTED),
    }
}


class _BaseState:
    TRANSITIONS = {}  # Subclasses should override this with non-empty dict.

    def __repr__(self):
        return "<{!s} states={!r}>".format(type(self).__name__, self.states)

    def __getitem__(self, role):
        return self.states[role]

    def _fire_command_triggered_transitions(self, role, command_type):
        current_state = self.states[role]
        allowed_transitions = self.TRANSITIONS[role][current_state]
        try:
            new_state = allowed_transitions[command_type]
        except KeyError:
            err = get_exception(role, command_type)
            raise err(
                "{} cannot handle command type {} when role={} and state={}"
                .format(self, command_type.__name__, role, self.states[role]))
        self.states[role] = new_state

    def process_command_type(self, role, command_type):
        raise NotImplementedError("Subclass must define this.")


class ChannelState(_BaseState):
    TRANSITIONS = COMMAND_TRIGGERED_CHANNEL_TRANSITIONS
    STT = STATE_TRIGGERED_TRANSITIONS

    def __init__(self, circuit_state):
        self.states = {CLIENT: SEND_CREATE_CHAN_REQUEST, SERVER: IDLE}
        self.circuit_state = circuit_state

    def _fire_state_triggered_transitions(self, role):
        new = self.STT[role].get((self.states[role],
                                  self.circuit_state.states[role]))
        if new is not None:
            self.states[role], self.circuit_state.states[role] = new

    def process_command_type(self, role, command_type):
        self._fire_command_triggered_transitions(role, command_type)
        self.update()

    def update(self):
        self._fire_state_triggered_transitions(CLIENT)
        self._fire_state_triggered_transitions(SERVER)


class CircuitState(_BaseState):
    TRANSITIONS = COMMAND_TRIGGERED_CIRCUIT_TRANSITIONS

    def __init__(self, channels):
        self.states = {CLIENT: SEND_VERSION_REQUEST, SERVER: IDLE}
        self.channels = channels

    def process_command_type(self, role, command_type):
        self._fire_command_triggered_transitions(role, command_type)
        for chan in self.channels.values():
            chan.states.update()

    def disconnect(self):
        self.states = {CLIENT: DISCONNECTED, SERVER: DISCONNECTED}
        # Notify channels on this circuit.
        for chan in self.channels.values():
            chan.states.update()


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
    if command.DIRECTION is REQUEST:
        party_at_fault = CLIENT
    elif command.DIRECTION is RESPONSE:
        party_at_fault = SERVER
    if our_role is party_at_fault:
        _class = LocalProtocolError
    else:
        _class = RemoteProtocolError
    return _class
