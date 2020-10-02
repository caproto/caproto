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
from ._utils import (CLIENT, CONNECTED, DISCONNECTED, INIT, NEVER_CONNECTED,
                     RESPONSIVE, SERVER, UNRESPONSIVE, LocalProtocolError,
                     RemoteProtocolError)

# TODO: SetMarker, AcknowledgeMarker, BeaconMessage, Echo, SearchRequest, SearchResponse,
# TODO: DESTROYED, IN_PROGRESS, NEED_DATA, READY

# Connection state; Channel life-cycle;
# also: CONNECTED, DISCONNECTED; Channel
# request; also: DISCONNECTED, DESTROYED


COMMAND_TRIGGERED_CIRCUIT_TRANSITIONS = {
    CLIENT: {
        INIT: {
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
        INIT: {
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
        NEVER_CONNECTED: {
            Subcommand.INIT: CONNECTED,
        },
        CONNECTED: {
            Subcommand.INIT: CONNECTED,
            Subcommand.DEFAULT: CONNECTED,
            Subcommand.GET: CONNECTED,
            Subcommand.GET_PUT: CONNECTED,
            Subcommand.PROCESS: CONNECTED,
            Subcommand.DESTROY: DISCONNECTED,
        },
        DISCONNECTED: {
        },
    }
}

SUBCOMMAND_TRANSITIONS[SERVER] = SUBCOMMAND_TRANSITIONS[CLIENT]

MONITOR_TRANSITIONS = {
    CLIENT: {
        NEVER_CONNECTED: {
            MonitorSubcommand.INIT: CONNECTED,
        },
        CONNECTED: {
            MonitorSubcommand.INIT: CONNECTED,
            MonitorSubcommand.DEFAULT: CONNECTED,
            MonitorSubcommand.PIPELINE: CONNECTED,
            MonitorSubcommand.START: CONNECTED,
            MonitorSubcommand.STOP: CONNECTED,
            MonitorSubcommand.DESTROY: DISCONNECTED,
        },
        DISCONNECTED: {
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
        self.states = {CLIENT: NEVER_CONNECTED,
                       SERVER: NEVER_CONNECTED}
        self.circuit_state = circuit_state

    # MERGE
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
            err = err_cls(f"{self} cannot handle command type "
                          f"{command_type.__name__} when role={role} and "
                          f"state={self.states[role]}")
            raise err from None
        self.states[role] = new_state


class RequestState(_BaseState):
    def __init__(self, is_monitor):
        self.monitor = is_monitor
        self.TRANSITIONS = (MONITOR_TRANSITIONS if is_monitor
                            else SUBCOMMAND_TRANSITIONS)
        self.states = {CLIENT: NEVER_CONNECTED, SERVER: NEVER_CONNECTED}

    def process_subcommand(self, subcommand):
        self._fire_command_triggered_transitions(CLIENT, subcommand)
        self._fire_command_triggered_transitions(SERVER, subcommand)

    # MERGE
    def _fire_command_triggered_transitions(self, role, subcommand):
        current_state = self.states[role]
        allowed_transitions = self.TRANSITIONS[role][current_state]
        if self.monitor:
            subcommand = MonitorSubcommand(subcommand)
        else:
            subcommand = Subcommand(subcommand)

        try:
            new_state = allowed_transitions[subcommand]
        except KeyError:
            err_cls = get_exception(role, subcommand)
            err = err_cls(f"{self} cannot handle subcommand type "
                          f"{subcommand!r} when role={role} and "
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
