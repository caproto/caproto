# This module defines classes that encapsulate key abstractions in
# Channel Access: Channels and VirtualCircuits. Each VirtualCircuit is a
# companion to a TCP socket managed by a higher-level client or server
# implementation, updating its state in response to incoming and outgoing TCP
# bytestreams. Each Channel belongs to a circuit, and tracks state particular
# to that Channel. A ClientChannel provides convenience methods for composing
# Requests; a ServerChannel provides convenience methods for composing
# Responses.
import logging
from collections import deque
from collections.abc import Iterable
import os

from ._commands import (AccessRightsResponse, CreateChFailResponse,
                        ClearChannelRequest, ClearChannelResponse,
                        ClientNameRequest, CreateChanRequest,
                        CreateChanResponse, EventAddRequest, EventAddResponse,
                        EventCancelRequest, EventCancelResponse,
                        HostNameRequest, ReadNotifyRequest,
                        ReadRequest, ReadNotifyResponse, ReadResponse,
                        SearchResponse, ServerDisconnResponse,
                        VersionRequest, VersionResponse, WriteNotifyRequest,
                        WriteNotifyResponse, WriteRequest,
                        read_from_bytestream,)
from ._state import (ChannelState, CircuitState, get_exception)
from ._utils import (CLIENT, SERVER, NEED_DATA, DISCONNECTED, CaprotoKeyError,
                     CaprotoValueError, CaprotoRuntimeError, CaprotoError,
                     CaprotoTypeError,
                     parse_channel_filter, parse_record_field,
                     ChannelFilter, ThreadsafeCounter)
from ._dbr import (ChannelType, SubscriptionType, field_types, native_type)
from ._constants import DEFAULT_PROTOCOL_VERSION
from ._status import CAStatus


__all__ = ('VirtualCircuit', 'ClientChannel', 'ServerChannel',
           'extract_address')

STRING_ENCODING = os.environ.get('CAPROTO_STRING_ENCODING', 'latin-1')


class VirtualCircuit:
    """
    An object encapulating the state of one CA client--server connection.

    It is a companion to a TCP socket managed by the user. All data
    received over the socket should be passed to :meth:`recv`. Any data sent
    over the socket should first be passed through :meth:`send`.

    Parameters
    ----------
    our_role : CLIENT or SERVER
    address : tuple
        ``(host, port)`` as a string and an integer respectively
    priority : integer or None
        May be used by the server to prioritize requests when under high
        load. Lowest priority is 0; highest is 99.
    """
    def __init__(self, our_role, address, priority,
                 protocol_version=DEFAULT_PROTOCOL_VERSION):
        self.our_role = our_role
        if our_role is CLIENT:
            self.their_role = SERVER
        else:
            self.their_role = CLIENT
        self.address = address
        self.our_address = None
        self.priority = priority
        self.channels = {}  # map cid to Channel
        self.channels_sid = {}  # map sid to Channel
        self.states = CircuitState(self.channels)
        self._data = bytearray()
        self._ioids = {}  # map ioid to Channel
        self.event_add_commands = {}  # map subscriptionid to EventAdd command
        # map subscriptionid to EventAdd command as we wait for them to die
        self.event_cancel_commands = {}
        # There are only used by the convenience methods, to auto-generate ids.
        if our_role is CLIENT:
            self._channel_id_counter = ThreadsafeCounter(
                dont_clash_with=self.channels
            )
        else:
            self._channel_id_counter = ThreadsafeCounter(
                dont_clash_with=self.channels_sid
            )
        self._ioid_counter = ThreadsafeCounter(dont_clash_with=self._ioids)
        self._sub_counter = ThreadsafeCounter(
            dont_clash_with=self.event_add_commands)
        if priority is None and self.our_role is CLIENT:
            raise CaprotoRuntimeError("Client-side VirtualCircuit requires a "
                                      "non-None priority at initialization "
                                      "time.")
        self.protocol_version = protocol_version

    @property
    def priority(self):
        return self._priority

    @priority.setter
    def priority(self, priority):
        # A server-side circuit does not get to know its priority until after
        # instantiation, so we need a setter.
        self._priority = priority
        # The logger_name includes the priority so we have to set it.
        self.log = logging.getLogger('caproto.circ')

    @property
    def host(self):
        '''Peer host name'''
        return self.address[0]

    @property
    def port(self):
        '''Port number'''
        return self.address[1]

    def __repr__(self):
        return (f"<VirtualCircuit host={self.host!r} port={self.port} "
                f"our_role={self.our_role}> logger_name={self.log.name!r}>")

    @property
    def key(self):
        if self.priority is None:
            raise CaprotoRuntimeError("This VirtualCircuit has not received a "
                                      "VersionRequest and does not know its "
                                      "priority. Therefore, it does not yet "
                                      "have a key.")
        return self.address, self.priority  # a unique identifier

    def __eq__(self, other):
        return hash(self) == hash(other)

    def __hash__(self):
        return hash((self.address, self.priority, self.our_role))

    def send(self, *commands):
        """
        Convert one or more high-level Commands into buffers of bytes that may
        be broadcast together in one TCP packet. Update our internal
        state machine.

        Parameters
        ----------
        *commands :
            any number of :class:`Message` objects

        Returns
        -------
        buffers_to_send : list
            list of buffers to send over a socket
        """
        buffers_to_send = []
        tags = {'their_address': self.address,
                'our_address': self.our_address,
                'direction': '--->>>',
                'role': repr(self.our_role)}
        for command in commands:
            self._process_command(self.our_role, command)
            if hasattr(command, 'name') and not isinstance(command, (ClientNameRequest, HostNameRequest)):
                tags['pv'] = command.name
            self.log.debug("(%dB) %r", len(command), command, extra=tags)
            buffers_to_send.append(memoryview(command.header))
            buffers_to_send.extend(command.buffers)
        return buffers_to_send

    def recv(self, *buffers):
        """
        Parse commands from buffers received over TCP.

        When the caller is ready to process the commands, each command should
        first be passed to :meth:`VirtualCircuit.process_command` to validate
        it against the protocol and update the VirtualCircuit's state.

        Parameters
        ----------
        *buffers :
            any number of bytes-like buffers

        Returns
        -------
        ``(commands, num_bytes_needed)``
        """
        total_received = sum(len(byteslike) for byteslike in buffers)
        commands = deque()
        if total_received == 0:
            self.log.debug('Zero-length recv; sending disconnect notification')
            commands.append(DISCONNECTED)
            return commands, 0

        self._data += b''.join(buffers)

        tags = {'their_address': self.address,
                'our_address': self.our_address,
                'direction': '<<<---',
                'role': repr(self.our_role)}
        while True:
            (self._data,
             command,
             num_bytes_needed) = read_from_bytestream(self._data,
                                                      self.their_role)
            if command is not NEED_DATA:
                self.log.debug("(%dB) %r", len(command), command, extra=tags)
                commands.append(command)
            else:
                # Less than a full command's worth of bytes are cached. Wait
                # for more bytes to come in before continuing parsing.
                break
        return commands, num_bytes_needed

    def process_command(self, command):
        """
        Update internal state machine and raise if protocol is violated.

        Received commands should be passed through here before any additional
        processing by a server or client layer.
        """
        self._process_command(self.their_role, command)

    def _process_command(self, role, command):
        """
        All commands go through here.

        Parameters
        ----------
        role : ``CLIENT`` or ``SERVER``
        command : Message
        """
        if command is DISCONNECTED:
            self.states.disconnect()
            return

        if isinstance(command, EventAddResponse):
            # well, this is dirty...
            if (command.subscriptionid in self.event_cancel_commands and
                    command.payload_size == 0):
                try:
                    ev_add = self.event_cancel_commands[command.subscriptionid]
                except KeyError:
                    # EventCancelResponse messages never get sent,
                    # instead we get sent EventAddResponse with 0
                    # payload.  This means we can have the following
                    # race condition:

                    #  -> cancel request
                    #  <- an update that really is an 0 length array
                    #  <- the cancel response

                    # where the real update is treated as the
                    # EventCancelResponse.  Thus, if get
                    # EventCancelResponse or EventAddResponse which is
                    # not associated with an active subscription but
                    # has 0 payload, just drop it on the floor and
                    # move on.
                    return
                # Otherwise, transmute the Command to a EventCancelResponse.
                command = EventCancelResponse(command.data_type,
                                              ev_add.sid,
                                              command.subscriptionid,
                                              command.data_count)

        # Filter for Commands that are pertinent to a specific Channel, as
        # opposed to the Circuit as a whole:
        if isinstance(command, (ClearChannelRequest, ClearChannelResponse,
                                CreateChanRequest, CreateChanResponse,
                                CreateChFailResponse, AccessRightsResponse,
                                ReadNotifyRequest, ReadNotifyResponse,
                                ReadRequest, ReadResponse,
                                WriteNotifyRequest, WriteNotifyResponse,
                                WriteRequest,
                                EventAddRequest, EventAddResponse,
                                EventCancelRequest, EventCancelResponse,
                                ServerDisconnResponse,)):
            # Identify which Channel this Command is referring to. We have to
            # do this in one of a couple different ways depenending on the
            # Command.
            if isinstance(command, (ReadNotifyRequest, WriteNotifyRequest,
                                    WriteRequest, ReadRequest,
                                    EventAddRequest)):
                # Identify the Channel based on its sid.
                sid = command.sid
                try:
                    chan = self.channels_sid[sid]
                except KeyError:
                    err = get_exception(self.our_role, command)
                    raise err("Unknown Channel sid {!r}".format(command.sid))
            elif isinstance(command, (ReadNotifyResponse, ReadResponse,
                                      WriteNotifyResponse)):
                # Identify the Channel based on its ioid.
                try:
                    chan = self._ioids.pop(command.ioid)
                except KeyError:
                    err = get_exception(self.our_role, command)
                    raise err("Unknown Channel ioid {!r}".format(command.ioid))
            elif isinstance(command, (EventCancelRequest,)):
                # Identify the Channel based on its subscriptionid
                try:
                    event_add = self.event_add_commands[command.subscriptionid]
                except KeyError:
                    err = get_exception(self.our_role, command)
                    raise err("Unrecognized subscriptionid {!r}"
                              "".format(command.subscriptionid))
                chan = self.channels_sid[event_add.sid]
            elif isinstance(command, (EventAddResponse, EventCancelResponse)):
                # Identify the Channel based on its subscriptionid
                try:
                    event_add = self.event_add_commands[command.subscriptionid]
                except KeyError:
                    if command.payload_size == 0:

                        return

                    err = get_exception(self.our_role, command)
                    raise err("Unrecognized subscriptionid {!r}"
                              "".format(command.subscriptionid))
                chan = self.channels_sid[event_add.sid]
            elif isinstance(command, CreateChanRequest):
                # A Channel instance for this cid may already exist.
                try:
                    chan = self.channels[command.cid]
                except KeyError:
                    _class = {CLIENT: ClientChannel,
                              SERVER: ServerChannel}[self.our_role]
                    chan = _class(command.name, self, command.cid)
            else:
                # In all other cases, the Command gives us a cid.
                cid = command.cid
                chan = self.channels[cid]

            # Do some additional validation on commands related to an existing
            # subscription.
            if isinstance(command, (EventAddResponse, EventCancelRequest,
                                    EventCancelResponse)):
                # Verify data_type matches the one in the original request.
                event_add = self.event_add_commands[command.subscriptionid]
                if event_add.data_type != command.data_type:
                    err = get_exception(self.our_role, command)
                    raise err("The data_type in {!r} does not match the "
                              "data_type in the original EventAddRequest "
                              "for this subscriptionid, {!r}."
                              "".format(command, event_add.data_type))
            if isinstance(command, (EventAddResponse,)):
                # Verify data_count matches the one in the original request.
                # NOTE The docs say that EventCancelRequest should echo the
                # original data_count too, but in fact it seems to be 0.
                event_add = self.event_add_commands[command.subscriptionid]
                if (event_add.data_count > 0 and
                        event_add.data_count != command.data_count):
                    err = get_exception(self.our_role, command)
                    raise err("The data_count in {!r} does not match the "
                              "data_count in the original EventAddRequest "
                              "for this subscriptionid, {!r}."
                              "".format(command, event_add.data_count))
            if isinstance(command, (EventCancelRequest, EventCancelResponse)):
                # Verify sid matches the one in the original request.
                event_add = self.event_add_commands[command.subscriptionid]
                if event_add.sid != command.sid:
                    err = get_exception(self.our_role, command)
                    raise err("The sid in {!r} does not match the sid in "
                              "in the original EventAddRequest for this "
                              "subscriptionid, {!r}."
                              "".format(command, event_add.sid))

            # Update the state machine of the pertinent Channel.
            # If this is not a valid command, the state machine will raise
            # here. Stash the state transitions in a local var and run the
            # callbacks at the end.
            transitions = chan.process_command(command)

            # If we got this far, the state machine has validated this Command.
            # Update other Channel and Circuit state.
            if isinstance(command, AccessRightsResponse):
                chan.access_rights = command.access_rights
            elif isinstance(command, CreateChanResponse):
                chan.sid = command.sid
                chan.protocol_version = self.protocol_version
                self.channels_sid[chan.sid] = chan
            elif isinstance(command, (ServerDisconnResponse,
                                      ClearChannelResponse)):
                self.channels_sid.pop(chan.sid)
                self.channels.pop(chan.cid)
                # put in list comprehension (not generator) to not change
                # the size while iterating
                for k in [k for k, v in self._ioids.items() if v is chan]:
                    self._ioids.pop(k)

            elif isinstance(command, (ReadNotifyRequest, ReadRequest,
                                      WriteNotifyRequest)):
                # Stash the ioid for later reference.
                self._ioids[command.ioid] = chan
            elif isinstance(command, EventAddRequest):
                # We will use the info in this command later to validate that
                # {EventAddResponse, EventCancelRequest, EventCancelResponse}
                # send or received in the future are valid.
                self.event_add_commands[command.subscriptionid] = command
            elif isinstance(command, EventCancelRequest):
                # If we see a cancel request, note that so we know to interpret
                # the next EventAddResponse with an empty payload as an
                # EventCancelResponse.
                self.event_cancel_commands[command.subscriptionid] = \
                    self.event_add_commands[command.subscriptionid]
            elif isinstance(command, EventCancelResponse):
                self.event_add_commands.pop(command.subscriptionid)
                self.event_cancel_commands.pop(command.subscriptionid)
            # We are done. Run the Channel state change callbacks.
            for transition in transitions:
                chan.state_changed(*transition)

        # Otherwise, this Command affects the state of this circuit, not a
        # specific Channel. Run the circuit's state machine.
        else:
            self.states.process_command_type(self.our_role, type(command))
            self.states.process_command_type(self.their_role, type(command))

        if isinstance(command, VersionRequest):
            if self.priority is None:
                self.priority = command.priority
            elif self.priority != command.priority:
                err = get_exception(self.our_role, command)
                raise err("priority {} does not match previously set priority "
                          "of {} for this circuit".format(command.priority,
                                                          self.priority))
            protocol_version = min(self.protocol_version, command.version)
            self.protocol_version = protocol_version
            for cid, chan in self.channels.items():
                chan.protocol_version = protocol_version

        if isinstance(command, VersionResponse):
            if command.version == 0:
                # Per the specification:
                # "In CA < 4.11, Message does not include minor version number
                # (it is always 0) and is interpreted as an echo command that
                # carries no data. Version exchange is performed immediately
                # after [channel creation]."
                return
            protocol_version = min(self.protocol_version, command.version)
            self.protocol_version = protocol_version
            for cid, chan in self.channels.items():
                chan.protocol_version = protocol_version

    def disconnect(self):
        """
        Notify all channels on this circuit that they are disconnected.

        Clients should call this method when a TCP connection is lost.
        """
        return DISCONNECTED

    def new_channel_id(self):
        "Return a valid value for a cid or sid."
        # Return the next sequential unused id. Wrap back to 0 on overflow.
        return self._channel_id_counter()

    def new_subscriptionid(self):
        """
        This is used by the convenience methods to obtain an unused integer ID.
        It does not update any important state.
        """
        return self._sub_counter()

    def new_ioid(self):
        """
        This is used by the convenience methods to obtain an unused integer ID.
        It does not update any important state.
        """
        return self._ioid_counter()


class _BaseChannel:
    # Base class for ClientChannel and ServerChannel, which add convenience
    # methods for composing requests and repsponses, respectively. All of the
    # important code is here in the base class.
    def __init__(self, name, circuit, cid=None, string_encoding=STRING_ENCODING):
        self.log = logging.LoggerAdapter(logging.getLogger('caproto.ch'), {'pv': name})
        self.protocol_version = circuit.protocol_version
        self.name = name
        self.string_encoding = string_encoding
        modifiers = parse_record_field(name).modifiers
        if modifiers is not None:
            self.channel_filter = parse_channel_filter(modifiers.filter_)
        else:
            self.channel_filter = ChannelFilter(
                ts=None, dbnd=None, arr=None, sync=None)
        self.circuit = circuit
        if cid is None:
            cid = self.circuit.new_channel_id()
        self.cid = cid
        self.circuit.channels[self.cid] = self
        self.states = ChannelState(self.circuit.states)
        # These will be set when the circuit processes CreateChanResponse.
        self.native_data_type = None
        self.native_data_count = None
        self.sid = None
        self.access_rights = None

    def __repr__(self):
        return (f"<{type(self).__name__} name={self.name!r} cid={self.cid} "
                f"sid={self.sid} data_type={self.native_data_type} "
                f"logger_name={self.log.name!r}>")

    @property
    def subscriptions(self):
        """
        Get cached EventAdd commands for this channel's active subscriptions.
        """
        return {k: v for k, v in self.circuit.event_add_commands.items()
                if v.sid == self.sid}

    def _fill_defaults(self, data_type, data_count):
        # Boilerplate used in many convenience methods
        if data_type is None:
            # Replace `None` default arg with actual default value.
            data_type = self.native_data_type
        elif isinstance(data_type, str):
            # For example, if data_type is 'time', look up the 'time' type
            # corresponding to this channel's native data type.
            data_type = field_types[data_type.lower()][self.native_data_type]
        if data_count is None:
            if self.protocol_version >= 13:
                data_count = 0
            else:
                data_count = self.native_data_count
        return data_type, data_count

    def state_changed(self, role, old_state, new_state, command):
        '''State changed callback for subclass usage'''
        pass

    def process_command(self, command):
        if isinstance(command, CreateChanResponse):
            self.native_data_type = command.data_type
            self.native_data_count = command.data_count

        transitions = []
        for role in (self.circuit.our_role, self.circuit.their_role):
            initial_state = self.states[role]
            try:
                self.states.process_command_type(role, type(command))
            except CaprotoError as ex:
                ex.channel = self
                raise

            new_state = self.states[role]
            # Assemble arguments needed by state_changed, to be called later.
            if initial_state is not new_state:
                transition = (role, initial_state, new_state, command)
                transitions.append(transition)
        return transitions


class ClientChannel(_BaseChannel):
    """An object encapsulating the state of the EPICS Channel on a Client.

    A ClientChannel may be created in one of two ways:
    (1) The user instantiates a ClientChannel with a name, server address,
    priority, and optional cid. The server address and priority are used to
    assign the ClientChannel to a VirtualCircuit. If no cid is given, a unique
    one is allocated by the VirtualCircuit.
    (2) A VirtualCircuit processes a CreateChanRequest that refers to a cid
    that it has not yet seen. A ClientChannel will be automatically
    instantiated with the name and cid indicated that command and the address
    and priority of that VirtualCircuit. It can be accessed in the circuit's
    ``channels`` attribute.

    Parameters
    ----------
    name : string
        Channnel name (PV)
    circuit : VirtualCircuit
    cid : integer, optional
    string_encoding : string
        Default is 'latin-1' or value of ``CAPROTO_STRING_ENCODING``
        environment variable.
    """
    def version(self):
        """
        Generate a valid :class:`VersionRequest`.

        Parameters
        ----------
        priority : integer, optional
            May be used by the server to prioritize requests when under high
            load. Lowest priority is 0; highest is 99. Default is 0.

        Returns
        -------
        VersionRequest
        """
        command = VersionRequest(version=self.protocol_version,
                                 priority=self.circuit.priority)
        return command

    def host_name(self, host_name):
        """
        Generate a valid :class:`HostNameRequest`.

        Parameters
        ----------
        host_name : string

        Returns
        -------
        HostNameRequest
        """
        command = HostNameRequest(host_name)
        return command

    def client_name(self, client_name):
        """
        Generate a valid :class:`ClientNameRequest`.

        Parameters
        ----------
        client_name : string, optional
            defaults to output of ``getpass.getuser()``

        Returns
        -------
        ClientNameRequest
        """
        command = ClientNameRequest(client_name)
        return command

    def create(self):
        """
        Generate a valid :class:`CreateChanRequest`.

        Returns
        -------
        CreateChanRequest
        """
        command = CreateChanRequest(self.name, self.cid,
                                    self.protocol_version)
        return command

    def clear(self):
        """
        Generate a valid :class:`ClearChannelRequest`.

        Returns
        -------
        ClearChannelRequest
        """
        command = ClearChannelRequest(self.sid, self.cid)
        return command

    def read(self, data_type=None, data_count=None, ioid=None,
             notify=True):
        """
        Generate a valid :class:`ReadRequest` or :class:`ReadNotifyRequest`.

        Parameters
        ----------
        data_type : {'native', 'status', 'time', 'graphic', 'control'} or ChannelType or int ID, optional
            Requested Channel Access data type. Default is the channel's
            native data type, which can be checked in the Channel's attribute
            :attr:`native_data_type`.
        data_count : integer, optional
            Requested number of values. Default is the channel's native data
            count, which can be checked in the Channel's attribute
            :attr:`native_data_count`.
        ioid : integer, optional
            Input/output ID. If None, one is generated.
        notify : boolean, optional
            True by default. If True, send a ``ReadNotifyRequest`` instead of
            a ``ReadRequest``. Note that ``ReadRequest`` has been deprecated by
            Channel Access in 3.13 and is not well-supported by caproto.

        Returns
        -------
        ReadNotifyRequest
        """
        data_type, data_count = self._fill_defaults(data_type, data_count)
        if ioid is None:
            ioid = self.circuit.new_ioid()
        cls = ReadNotifyRequest if notify else ReadRequest
        command = cls(data_type, data_count, self.sid, ioid)
        return command

    def write(self, data, data_type=None, data_count=None, metadata=None,
              ioid=None, notify=False):
        """
        Generate a valid :class:`WriteRequest or `:class:`WriteNotifyRequest`.

        Parameters
        ----------
        data : tuple, ``numpy.ndarray``, ``array.array``, or bytes
        data_type : {'native', 'status', 'time', 'graphic', 'control'} or ChannelType or int ID, optional
            Requested Channel Access data type. Default is the channel's
            native data type, which can be checked in the Channel's attribute
            :attr:`native_data_type`.
        data_count : integer, optional
            Requested number of values. Default is the channel's native data
            count, which can be checked in the Channel's attribute
            :attr:`native_data_count`.
        metadata : ``ctypes.BigEndianStructure`` or tuple
            Status and control metadata for the values
        ioid : integer, optional
            Input/output ID. If None, one is generated.
        notify : boolean, optional
            False by default. If True, send a ``WriteNotifyRequest`` instead of
            a ``WriteRequest``.

        Returns
        -------
        WriteNotifyRequest
        """
        data_type, data_count = self._fill_defaults(data_type, data_count)
        if native_type(data_type) != ChannelType.CHAR:
            if not isinstance(data, Iterable) or isinstance(data, (str, bytes)):
                data = [data]
            if len(data) and isinstance(data[0], str):
                data = [val.encode(self.string_encoding) for val in data]
        elif len(data) and isinstance(data[0], str):
            if isinstance(data, (list, tuple)):
                data = [d.encode(self.string_encoding) for d in data]
            else:
                data = data.encode(self.string_encoding)
        if data_count == 0:
            data_count = len(data)
        if ioid is None:
            ioid = self.circuit.new_ioid()

        cls = WriteNotifyRequest if notify else WriteRequest
        command = cls(data, data_type, data_count, self.sid, ioid,
                      metadata=metadata)
        return command

    def subscribe(self, data_type=None, data_count=None,
                  subscriptionid=None,
                  low=0.0, high=0.0, to=0.0, mask=None):
        """
        Generate a valid :class:`EventAddRequest`.

        Parameters
        ----------
        data_type : {'native', 'status', 'time', 'graphic', 'control'} or ChannelType or int ID, optional
            Requested Channel Access data type. Default is the channel's
            native data type, which can be checked in the Channel's attribute
            :attr:`native_data_type`.
        data_count : integer, optional
            Requested number of values. Default is the channel's native data
            count, which can be checked in the Channel's attribute
            :attr:`native_data_count`.
        subscriptionid : integer, optional
        low : number
            Default is 0.
        high : number
            Default is 0.
        to : number
            Default is 0.
        mask :
            Default is None, which resolves to:
            ``(SubscriptionType.DBE_VALUE | ``
            `` SubscriptionType.DBE_ALARM | ``
            `` SubscriptionType.DBE_PROPERTY)``

        Returns
        -------
        EventAddRequest
        """
        data_type, data_count = self._fill_defaults(data_type, data_count)
        if mask is None:
            mask = (SubscriptionType.DBE_VALUE |
                    SubscriptionType.DBE_ALARM |
                    SubscriptionType.DBE_PROPERTY)
        if subscriptionid is None:
            subscriptionid = self.circuit.new_subscriptionid()
        command = EventAddRequest(data_type, data_count, self.sid,
                                  subscriptionid, low, high, to, mask)
        return command

    def unsubscribe(self, subscriptionid):
        """
        Generate a valid :class:`EventAddRequest`.

        Parameters
        ----------
        subscriptionid : integer
            The ``subscriptionid`` that was originally sent in the
            corresponding :class:`EventAddRequest`.

        Returns
        -------
        EventAddRequest
        """
        try:
            event_add = self.circuit.event_add_commands[subscriptionid]
        except KeyError:
            raise CaprotoKeyError("No current subscription has id {!r}"
                                  "".format(subscriptionid))
        if event_add.sid != self.sid:
            raise CaprotoValueError("This subscription is for a different "
                                    "Channel.")
        command = EventCancelRequest(event_add.data_type, self.sid,
                                     subscriptionid)
        return command


class ServerChannel(_BaseChannel):
    """
    A server-side Channel.

    Parameters
    ----------
    name : string
        Channnel name (PV)
    circuit : VirtualCircuit
    cid : integer, optional
    string_encoding : string
        Default is 'latin-1' or value of ``CAPROTO_STRING_ENCODING``
        environment variable.
    """
    def version(self):
        """
        Generate a valid :class:`VersionResponse`.

        Returns
        -------
        VersionResponse
        """
        command = VersionResponse(self.protocol_version)
        return command

    def create(self, native_data_type, native_data_count, sid):
        """
        Generate a valid :class:`CreateChanResponse`.

        Parameters
        ----------
        native_data_type : a ChannelType or corresponding integer ID, optional
            Default Channel Access data type.
        native_data_count : integer
            Default number of values
        sid : integer
            server-allocated sid

        Returns
        -------
        CreateChanResponse
        """
        command = CreateChanResponse(native_data_type, native_data_count,
                                     self.cid, sid)
        return command

    def create_fail(self):
        """
        Generate a valid :class:`CreateChFailResponse`.

        Returns
        -------
        CreateChFailResponse
        """
        command = CreateChFailResponse(self.cid)
        return command

    def read(self, data, ioid, data_type=None, data_count=None, status=1, *,
             metadata=None, notify=True):
        """
        Generate a valid :class:`ReadResponse` or :class:`ReadNotifyResponse`.

        Parameters
        ----------
        data : tuple, ``numpy.ndarray``, ``array.array``, or bytes
        ioid : integer
        data_type : {'native', 'status', 'time', 'graphic', 'control'} or ChannelType or int ID, optional
            Requested Channel Access data type. Default is the channel's
            native data type, which can be checked in the Channel's attribute
            :attr:`native_data_type`.
        data_count : integer, optional
            Requested number of values. Default is the channel's native data
            count, which can be checked in the Channel's attribute
            :attr:`native_data_count`.
        status : integer, optional
            Default is 1 (success).
        metadata : ``ctypes.BigEndianStructure`` or tuple
            Status and control metadata for the values
        notify : boolean, optional
            True by default. If True, send a ``ReadNotifyRequest`` instead of
            a ``ReadRequest``. Note that ``ReadRequest`` has been deprecated by
            Channel Access in 3.13 and is not well-supported by caproto.

        Returns
        -------
        ReadResponse or ReadNotifyResponse
        """
        data_type, data_count = self._fill_defaults(data_type, data_count)
        # TODO: Un-comment this to make the server symmetric with the channel.
        # Some work is needed to integrate it with the server/ChannelData.
        # if native_type(data_type) != ChannelType.CHAR:
        #     if not isinstance(data, Iterable) or isinstance(data, (str, bytes)):
        #         data = [data]
        #     if len(data) and isinstance(data[0], str):
        #         data = [val.encode(self.string_encoding) for val in data]
        # elif len(data) and isinstance(data[0], str):
        #     data = data.encode(self.string_encoding)
        cls = ReadNotifyResponse if notify else ReadResponse
        command = cls(data, data_type, data_count, status, ioid,
                      metadata=metadata)
        return command

    def write(self, ioid, data_type=None, data_count=None, status=1):
        """
        Generate a valid :class:`WriteNotifyResponse`.

        Parameters
        ----------
        ioid : integer
        data_type : {'native', 'status', 'time', 'graphic', 'control'} or ChannelType or int ID, optional
            Requested Channel Access data type. Default is the channel's
            native data type, which can be checked in the Channel's attribute
            :attr:`native_data_type`.
        data_count : integer, optional
            Requested number of values. Default is the channel's native data
            count, which can be checked in the Channel's attribute
            :attr:`native_data_count`.
        status : integer, optional
            Default is 1 (success).

        Returns
        -------
        WriteNotifyResponse
        """
        data_type, data_count = self._fill_defaults(data_type, data_count)
        command = WriteNotifyResponse(data_type, data_count, status, ioid)
        return command

    def subscribe(self, data, subscriptionid, data_type=None,
                  data_count=None, status=CAStatus.ECA_NEWCONN,
                  metadata=None):
        """
        Generate a valid :class:`EventAddResponse`.

        Parameters
        ----------
        data : tuple, ``numpy.ndarray``, ``array.array``, or bytes
        subscriptionid : integer
        data_type : {'native', 'status', 'time', 'graphic', 'control'} or ChannelType or int ID, optional
            Requested Channel Access data type. Default is the channel's
            native data type, which can be checked in the Channel's attribute
            :attr:`native_data_type`.
        data_count : integer, optional
            Requested number of values. Default is the channel's native data
            count, which can be checked in the Channel's attribute
            :attr:`native_data_count`.
        status : CAStatus or corresponding integer code
            Default is ``CAStatus.ECA_NEWCONN``
        metadata : ``ctypes.BigEndianStructure`` or tuple
            Status and control metadata for the values

        Returns
        -------
        EventAddResponse
        """
        data_type, data_count = self._fill_defaults(data_type, data_count)
        command = EventAddResponse(data, data_type, data_count, status,
                                   subscriptionid, metadata=metadata)
        return command

    def unsubscribe(self, subscriptionid, data_type=None, data_count=None):
        """
        Generate a valid :class:`EventCancelResponse`.

        Parameters
        ----------
        subscriptionid : integer
        data_type : {'native', 'status', 'time', 'graphic', 'control'} or ChannelType or int ID, optional
            Requested Channel Access data type. Default is the channel's
            native data type, which can be checked in the Channel's attribute
            :attr:`native_data_type`.

        Returns
        -------
        EventCancelResponse
        """
        data_type, data_count = self._fill_defaults(data_type, data_count)
        command = EventCancelResponse(data_type, self.sid, subscriptionid,
                                      data_count)
        return command

    def clear(self):
        """
        Generate a valid :class:`ClearChannelResponse`

        Returns
        -------
        ClearChannelResposne
        """
        command = ClearChannelResponse(self.sid, self.cid)
        return command

    def disconnect(self):
        """
        Generate a valid :class:`ServerDisconnResponse`

        Returns
        -------
        ServerDisconnResponse
        """
        command = ServerDisconnResponse(self.cid)
        return command


def extract_address(search_response):
    """
    Extract the (host, port) from a SearchResponse.
    """
    if type(search_response) is not SearchResponse:
        raise CaprotoTypeError("expected SearchResponse, not {!r}"
                               "".format(type(search_response).__name__))
    if search_response.header.parameter1 == 0xffffffff:
        # The CA spec tells us that this sentinel value means we
        # should fall back to using the address of the sender of
        # the UDP datagram.
        address = search_response.sender_address[0]
    else:
        address = search_response.ip
    return (address, search_response.port)
