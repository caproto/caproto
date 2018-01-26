# This module contains only the Broadcaster object, encapsulating the state of
# one Channel Access UDP connection, intended to be used as a companion to a
# UDP socket provided by a client or server implementation.
import itertools
import logging
import socket

from ._constants import (DEFAULT_PROTOCOL_VERSION, MAX_ID)
from ._utils import (CLIENT, SERVER, CaprotoValueError, LocalProtocolError)
from ._state import get_exception
from ._commands import (RepeaterConfirmResponse, RepeaterRegisterRequest,
                        SearchRequest, SearchResponse, VersionRequest,
                        VersionResponse, read_datagram,
                        )


class Broadcaster:
    """
    An object encapsulating the state of one CA UDP connection.

    It is a companion to a UDP socket managed by a client or server
    implementation. All data received over the socket should be passed to
    :meth:`recv`. Any data sent over the socket should first be passed through
    :meth:`send`.

    Parameters
    ----------
    our_role : CLIENT or SERVER
    protocol_version : integer
        Default is ``DEFAULT_PROTOCOL_VERSION``.
    """
    def __init__(self, our_role, protocol_version=DEFAULT_PROTOCOL_VERSION):
        if our_role not in (SERVER, CLIENT):
            raise CaprotoValueError("role must be caproto.SERVER or "
                                    "caproto.CLIENT")
        self.our_role = our_role
        if our_role is CLIENT:
            self.their_role = SERVER
            abbrev = 'cli'  # just for logger
        else:
            self.their_role = CLIENT
            abbrev = 'srv'
        self.protocol_version = protocol_version
        self.unanswered_searches = {}  # map search id (cid) to name
        # Unlike VirtualCircuit and Channel, there is very little state to
        # track for the Broadcaster. We don't need a full state machine, just
        # one flag to check whether we have yet registered with a repeater.
        self._registered = False
        self._search_id_counter = itertools.count(0)
        logger_name = f"{abbrev}.bcast"
        self.log = logging.getLogger(logger_name)

    def send(self, *commands):
        """
        Convert one or more high-level Commands into bytes that may be
        broadcast together in one UDP datagram. Update our internal
        state machine.

        Parameters
        ----------
        *commands :
            any number of :class:`Message` objects

        Returns
        -------
        bytes_to_send : bytes
            bytes to send over a socket
        """
        bytes_to_send = b''
        self.log.debug("Serializing %d commands into one datagram",
                       len(commands))
        history = []
        for i, command in enumerate(commands):
            self.log.debug("%d of %d %r", 1 + i, len(commands), command)
            self._process_command(self.our_role, command, history=history)
            bytes_to_send += bytes(command)
        return bytes_to_send

    def recv(self, byteslike, address):
        """
        Parse commands from a UDP datagram.

        When the caller is ready to process the commands, each command should
        first be passed to :meth:`Broadcaster.process_command` to validate it
        against the protocol and update the Broadcaster's state.

        Parameters
        ----------
        byteslike : bytes-like
        address : tuple
            ``(host, port)`` as a string and an integer respectively

        Returns
        -------
        commands : list
        """
        self.log.debug("Received datagram from %r with %d bytes.",
                       address, len(byteslike))
        commands = read_datagram(byteslike, address, self.their_role)
        return commands

    def process_commands(self, commands):
        """
        Update internal state machine and raise if protocol is violated.

        Received commands should be passed through here before any additional
        processing by a server or client layer.
        """
        history = []
        for command in commands:
            self._process_command(self.their_role, command, history)

    def _process_command(self, role, command, history):
        """
        All comands go through here.

        Parameters
        ----------
        role : ``CLIENT`` or ``SERVER``
        command : Message
        history : list
            This input will be mutated: command will be appended at the end.
        """
        # All commands go through here.
        if isinstance(command, RepeaterRegisterRequest):
            pass
        elif isinstance(command, RepeaterConfirmResponse):
            self._registered = True
        elif (role is CLIENT and
              self.our_role is CLIENT and
              not self._registered):
            raise LocalProtocolError("Client must send a "
                                     "RegisterRepeaterRequest before any "
                                     "other commands")
        elif isinstance(command, SearchRequest):
            if VersionRequest not in map(type, history):
                err = get_exception(self.our_role, command)
                raise err("A broadcasted SearchResponse must be preceded by a "
                          "VersionResponse in the same datagram.")
            self.unanswered_searches[command.cid] = command.name
        elif isinstance(command, SearchResponse):
            if VersionResponse not in map(type, history):
                err = get_exception(self.our_role, command)
                raise err("A broadcasted SearchResponse must be preceded by a "
                          "VersionResponse in the same datagram.")
            self.unanswered_searches.pop(command.cid, None)

        history.append(command)

    ### CONVENIENCE METHODS ###

    def new_search_id(self):
        # Return the next sequential unused id. Wrap back to 0 on overflow.
        while True:
            i = next(self._search_id_counter)
            if i in self.unanswered_searches:
                continue
            if i == MAX_ID:
                self._search_id_counter = itertools.count(0)
                continue
            return i

    def search(self, name):
        """
        Generate a valid :class:`VersionRequest` and :class:`SearchRequest`.

        The protocol requires that these be transmitted together as part of one
        datagram.

        Parameters
        ----------
        name : string
            Channnel name (PV)

        Returns
        -------
        (VersionRequest, SearchRequest)
        """
        cid = self.new_search_id()
        commands = (VersionRequest(0, self.protocol_version),
                    SearchRequest(name, cid, self.protocol_version))
        return commands

    def register(self, ip=None):
        """
        Generate a valid :class:`RepeaterRegisterRequest`.

        Parameters
        ----------
        ip : string, optional
            Our IP address. Defaults is output of ``socket.gethostbyname``.

        Returns
        -------
        RepeaterRegisterRequest
        """
        if ip is None:
            hostname = socket.gethostname()
            ip = socket.gethostbyname(hostname)
        command = RepeaterRegisterRequest(ip)
        return command

    def disconnect(self):
        self._registered = False

    @property
    def registered(self):
        return self._registered
