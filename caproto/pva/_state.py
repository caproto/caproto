from .._state import ChannelState as _ChannelState
from .._state import CircuitState as _CircuitState
from .._state import _BaseState
from ._messages import (ApplicationCommand, ChannelDestroyRequest,
                        ChannelDestroyResponse, ChannelFieldInfoRequest,
                        ChannelFieldInfoResponse, ChannelGetRequest,
                        ChannelGetResponse, ChannelMonitorRequest,
                        ChannelMonitorResponse, ChannelProcessRequest,
                        ChannelProcessResponse, ChannelPutGetRequest,
                        ChannelPutGetResponse, ChannelPutRequest,
                        ChannelPutResponse, ChannelRequestCancel,
                        ChannelRequestDestroy, ChannelRpcRequest,
                        ChannelRpcResponse, ConnectionValidatedResponse,
                        ConnectionValidationRequest,
                        ConnectionValidationResponse, ControlCommand,
                        CreateChannelRequest, CreateChannelResponse,
                        MessageFlags, MonitorSubcommand, SetByteOrder,
                        Subcommand)
from ._utils import (CLIENT, CONNECTED, DISCONNECTED, NEVER_CONNECTED,
                     RESPONSIVE, SERVER, UNRESPONSIVE, ChannelRequest,
                     LocalProtocolError, RemoteProtocolError)

# TODO: SetMarker, AcknowledgeMarker, BeaconMessage, Echo, SearchRequest, SearchResponse,
# TODO: DESTROYED, IN_PROGRESS, NEED_DATA, READY


COMMAND_TRIGGERED_CIRCUIT_TRANSITIONS = {
    CLIENT: {
        NEVER_CONNECTED: {
            SetByteOrder: CONNECTED,
        },
        CONNECTED: {
            ConnectionValidationRequest: CONNECTED,
            ConnectionValidationResponse: CONNECTED,
            ConnectionValidatedResponse: RESPONSIVE,
        },
        RESPONSIVE: {
            CreateChannelRequest: RESPONSIVE,
            CreateChannelResponse: RESPONSIVE,
            ChannelFieldInfoRequest: RESPONSIVE,
            ChannelFieldInfoResponse: RESPONSIVE,
            ChannelGetRequest: RESPONSIVE,
            ChannelGetResponse: RESPONSIVE,
            ChannelPutRequest: RESPONSIVE,
            ChannelPutResponse: RESPONSIVE,
            ChannelMonitorRequest: RESPONSIVE,
            ChannelMonitorResponse: RESPONSIVE,
            ChannelPutGetRequest: RESPONSIVE,
            ChannelPutGetResponse: RESPONSIVE,
            ChannelRequestCancel: RESPONSIVE,
            ChannelRequestDestroy: RESPONSIVE,
            ChannelRpcRequest: RESPONSIVE,
            ChannelRpcResponse: RESPONSIVE,
            ChannelProcessRequest: RESPONSIVE,
            ChannelProcessResponse: RESPONSIVE,
            ChannelDestroyRequest: RESPONSIVE,
            ChannelDestroyResponse: RESPONSIVE,
        },
        UNRESPONSIVE: {
        },
        DISCONNECTED: {
            # a terminal state that may only be reached by a special method
        },
    },
    SERVER: {
        NEVER_CONNECTED: {
            SetByteOrder: CONNECTED,
        },
        CONNECTED: {
            ConnectionValidationRequest: CONNECTED,
            ConnectionValidationResponse: CONNECTED,
            ConnectionValidatedResponse: RESPONSIVE,
        },
        RESPONSIVE: {
            CreateChannelRequest: RESPONSIVE,
            CreateChannelResponse: RESPONSIVE,
            ChannelFieldInfoRequest: RESPONSIVE,
            ChannelFieldInfoResponse: RESPONSIVE,
            ChannelGetRequest: RESPONSIVE,
            ChannelGetResponse: RESPONSIVE,
            ChannelMonitorRequest: RESPONSIVE,
            ChannelMonitorResponse: RESPONSIVE,
            ChannelPutRequest: RESPONSIVE,
            ChannelPutResponse: RESPONSIVE,
            ChannelPutGetRequest: RESPONSIVE,
            ChannelPutGetResponse: RESPONSIVE,
            ChannelRequestCancel: RESPONSIVE,
            ChannelRequestDestroy: RESPONSIVE,
            ChannelRpcRequest: RESPONSIVE,
            ChannelRpcResponse: RESPONSIVE,
            ChannelProcessRequest: RESPONSIVE,
            ChannelProcessResponse: RESPONSIVE,
            ChannelDestroyRequest: RESPONSIVE,
            ChannelDestroyResponse: RESPONSIVE,
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
        NEVER_CONNECTED: {
            CreateChannelRequest: NEVER_CONNECTED,
            CreateChannelResponse: CONNECTED,
        },
        CONNECTED: {
            ChannelFieldInfoRequest: CONNECTED,
            ChannelFieldInfoResponse: CONNECTED,
            ChannelGetRequest: CONNECTED,
            ChannelGetResponse: CONNECTED,
            ChannelPutRequest: CONNECTED,
            ChannelPutResponse: CONNECTED,
            ChannelDestroyRequest: CONNECTED,
            ChannelDestroyResponse: DISCONNECTED,
            ChannelMonitorRequest: CONNECTED,
            ChannelMonitorResponse: CONNECTED,
            ChannelPutGetRequest: CONNECTED,
            ChannelPutGetResponse: CONNECTED,
            ChannelRequestCancel: CONNECTED,
            ChannelRequestDestroy: CONNECTED,
            ChannelRpcRequest: CONNECTED,
            ChannelRpcResponse: CONNECTED,
            ChannelProcessRequest: CONNECTED,
            ChannelProcessResponse: CONNECTED,
        },
        DISCONNECTED: {
        },
    },
    SERVER: {
        NEVER_CONNECTED: {
            CreateChannelRequest: NEVER_CONNECTED,
            CreateChannelResponse: CONNECTED,
        },
        CONNECTED: {
            ChannelFieldInfoRequest: CONNECTED,
            ChannelFieldInfoResponse: CONNECTED,
            ChannelGetRequest: CONNECTED,
            ChannelGetResponse: CONNECTED,
            ChannelPutRequest: CONNECTED,
            ChannelPutResponse: CONNECTED,
            ChannelDestroyRequest: CONNECTED,
            ChannelDestroyResponse: DISCONNECTED,
            ChannelMonitorRequest: CONNECTED,
            ChannelMonitorResponse: CONNECTED,
            ChannelRequestCancel: CONNECTED,
            ChannelRequestDestroy: CONNECTED,
            ChannelPutGetRequest: CONNECTED,
            ChannelPutGetResponse: CONNECTED,
            ChannelRpcRequest: CONNECTED,
            ChannelRpcResponse: CONNECTED,
            ChannelProcessRequest: CONNECTED,
            ChannelProcessResponse: CONNECTED,
        },
        DISCONNECTED: {
        },
    },
}

SUBCOMMAND_TRANSITIONS = {
    CLIENT: {
        ChannelRequest.INIT: {
            Subcommand.INIT: ChannelRequest.READY,
        },
        ChannelRequest.READY: {
            # TODO: the transitions should be
            # READY -> IN_PROGRESS -> READY
            Subcommand.INIT: ChannelRequest.READY,
            Subcommand.DEFAULT: ChannelRequest.READY,
            Subcommand.GET: ChannelRequest.READY,
            Subcommand.GET_PUT: ChannelRequest.READY,
            Subcommand.PROCESS: ChannelRequest.READY,

            Subcommand.GET | Subcommand.DESTROY: ChannelRequest.DESTROY_AFTER,
            Subcommand.GET_PUT | Subcommand.DESTROY: ChannelRequest.DESTROY_AFTER,
            Subcommand.PROCESS | Subcommand.DESTROY: ChannelRequest.DESTROY_AFTER,

            # TODO: This doesn't really make sense to me:
            # * DEFAULT mask is 0x00, so DEFAULT|DESTROY = DESTROY
            # * `pvput` relies on this behavior: INIT -> DESTROY (means do the put)
            Subcommand.DEFAULT | Subcommand.DESTROY: ChannelRequest.DESTROY_AFTER,
        },
        ChannelRequest.DESTROY_AFTER: {
            Subcommand.DEFAULT: ChannelRequest.DESTROYED,
            Subcommand.GET: ChannelRequest.DESTROYED,
            Subcommand.GET_PUT: ChannelRequest.DESTROYED,
            Subcommand.PROCESS: ChannelRequest.DESTROYED,

            Subcommand.GET | Subcommand.DESTROY: ChannelRequest.DESTROYED,
            Subcommand.GET_PUT | Subcommand.DESTROY: ChannelRequest.DESTROYED,
            Subcommand.PROCESS | Subcommand.DESTROY: ChannelRequest.DESTROYED,
            Subcommand.DESTROY: ChannelRequest.DESTROYED,
        },
        ChannelRequest.DESTROYED: {
        },
    }
}

SUBCOMMAND_TRANSITIONS[SERVER] = SUBCOMMAND_TRANSITIONS[CLIENT]

MONITOR_TRANSITIONS = {
    CLIENT: {
        ChannelRequest.INIT: {
            MonitorSubcommand.INIT: ChannelRequest.READY,
        },
        ChannelRequest.READY: {
            MonitorSubcommand.INIT: ChannelRequest.READY,
            MonitorSubcommand.DEFAULT: ChannelRequest.READY,
            MonitorSubcommand.PIPELINE: ChannelRequest.READY,
            MonitorSubcommand.START: ChannelRequest.READY,
            MonitorSubcommand.STOP: ChannelRequest.READY,
            MonitorSubcommand.DESTROY: ChannelRequest.DESTROYED,
        },
        ChannelRequest.DESTROYED: {
        },
    }
}

MONITOR_TRANSITIONS[SERVER] = MONITOR_TRANSITIONS[CLIENT]

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
        self.states = {
            CLIENT: NEVER_CONNECTED,
            SERVER: NEVER_CONNECTED,
        }
        self.circuit_state = circuit_state

    def _fire_command_triggered_transitions(self, role, command):
        command_type = type(command)
        if command_type._ENDIAN is not None:
            if command_type.ID in ApplicationCommand:
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
            err = err_cls(
                f"{self} cannot handle command type {command_type.__name__} "
                f"when role={role} and state={self.states[role]}"
            )
            raise err from None
        self.states[role] = new_state


class CircuitState(_CircuitState):
    TRANSITIONS = COMMAND_TRIGGERED_CIRCUIT_TRANSITIONS

    def __init__(self, channels):
        self.states = {
            CLIENT: NEVER_CONNECTED,
            SERVER: NEVER_CONNECTED,
        }
        self.channels = channels

    def _fire_command_triggered_transitions(self, role, command):
        command_type = type(command)
        if command.ID in ControlCommand:
            ...
        elif command.ID in ApplicationCommand:
            if command._ENDIAN is not None:
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
            err = err_cls(
                f"{self} cannot handle command type {command_type.__name__} "
                f"when role={role} and state={self.states[role]}"
            )
            raise err from None
        self.states[role] = new_state


class RequestState(_BaseState):
    """
    Request state tracking for non-monitors.

    Parameters
    ----------
    reference : str
        A string reference for the request.
    """

    _subcommand_class = Subcommand
    TRANSITIONS = SUBCOMMAND_TRANSITIONS

    def __init__(self, reference: str):
        self.states = {
            CLIENT: ChannelRequest.INIT,
            SERVER: ChannelRequest.INIT,
        }
        self.reference = reference

    def __repr__(self):
        return (
            f"<{self.__class__.__name__} {self.reference} "
            "states={self.states!r}>"
        )

    def process_subcommand(self, subcommand):
        subcommand = self._subcommand_class(subcommand)
        self._fire_command_triggered_transitions(CLIENT, subcommand)
        self._fire_command_triggered_transitions(SERVER, subcommand)

    def _fire_command_triggered_transitions(self, role, subcommand):
        current_state = self.states[role]
        allowed_transitions = self.TRANSITIONS[role][current_state]

        try:
            new_state = allowed_transitions[subcommand]
        except KeyError:
            # err_cls = get_exception(role, subcommand)
            # TODO: direction isn't clear here
            err = RemoteProtocolError(
                f"{self} cannot handle subcommand type {subcommand!r} when "
                f"role={role} and state={self.states[role]}"
            )
            raise err from None
        self.states[role] = new_state


class MonitorRequestState(RequestState):
    """
    Request state tracking for monitors.

    Parameters
    ----------
    reference : str
        A string reference for the request.
    """

    _subcommand_class = MonitorSubcommand
    TRANSITIONS = MONITOR_TRANSITIONS


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
    header = getattr(command, 'header', command)

    if MessageFlags.FROM_SERVER in header.flags:
        party_at_fault = SERVER
    else:
        party_at_fault = CLIENT

    if our_role is party_at_fault:
        _class = LocalProtocolError
    else:
        _class = RemoteProtocolError
    return _class
