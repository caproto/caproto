# This module contains only the Broadcaster object, encapsulating the state of
# one Channel Access UDP connection, intended to be used as a companion to a
# UDP socket provided by a client or server implementation.
import logging

from ._commands import (Beacon, RepeaterConfirmResponse,
                        RepeaterRegisterRequest, SearchRequest, SearchResponse,
                        read_datagram)
from ._constants import DEFAULT_PROTOCOL_VERSION
from ._utils import CLIENT, SERVER, CaprotoValueError, RemoteProtocolError

__all__ = ('Broadcaster',)


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
        else:
            self.their_role = CLIENT
        # Whereas VirtualCircuit has one client address and one server address,
        # the Broadcaster has multiple addresses on the server side (one per
        # interface that it listens on) and one on the client side.
        # We also provide the properties `our_addresses` and `their_addresses`,
        # whose meaning depends on our_role. Whichever one corresponds to the
        # client role will have a length of one.
        self.server_addresses = []
        self.client_address = None
        self.protocol_version = protocol_version
        # Unlike VirtualCircuit and Channel, there is very little state to
        # track for the Broadcaster. We don't need a full state machine, just
        # one flag to check whether we have yet registered with a repeater.
        self._registered = False
        self.log = logging.getLogger("caproto.bcast")
        self.beacon_log = logging.getLogger('caproto.bcast.beacon')
        self.search_log = logging.getLogger('caproto.bcast.search')

    @property
    def our_addresses(self):
        if self.our_role is CLIENT:
            return [self.client_address]  # always return a list
        else:
            return self.server_addresses

    @property
    def their_addresses(self):
        if self.their_role is CLIENT:
            return [self.client_address]  # always return a list
        else:
            return self.server_addresses

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
        total_commands = len(commands)
        tags = {'role': repr(self.our_role)}
        for i, command in enumerate(commands):
            tags['counter'] = (1 + i, total_commands)
            if isinstance(command, (SearchRequest, SearchResponse)):
                self.search_log.debug("%r", command, extra=tags)
            else:
                self.log.debug("%r", command, extra=tags)
            self._process_command(self.our_role, command)
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
        try:
            commands = read_datagram(byteslike, address, self.their_role)
        except RemoteProtocolError:
            raise
        except Exception as ex:
            raise RemoteProtocolError(f'Broadcaster malformed packet received:'
                                      f' {ex.__class__.__name__} {ex}') from ex

        tags = {'their_address': address,
                'direction': '<<<---',
                'role': repr(self.our_role)}
        for command in commands:
            tags['bytesize'] = len(command)
            for address in self.our_addresses:
                tags['our_address'] = address
                if isinstance(command, Beacon):
                    log = self.beacon_log
                else:
                    log = self.log
                log.debug("%r", command, extra=tags)
        return commands

    def process_commands(self, commands):
        """
        Update internal state machine and raise if protocol is violated.

        Received commands should be passed through here before any additional
        processing by a server or client layer.
        """
        for command in commands:
            self._process_command(self.their_role, command)

    def _process_command(self, role, command):
        """
        All comands go through here.

        Parameters
        ----------
        role : ``CLIENT`` or ``SERVER``
        command : Message
        history : list
            This input will be mutated: command will be appended at the end.
        """
        if isinstance(command, RepeaterConfirmResponse):
            self._registered = True

    # CONVENIENCE METHODS

    def register(self, ip='0.0.0.0'):
        """
        Generate a valid :class:`RepeaterRegisterRequest`.

        Parameters
        ----------
        ip : string, optional
            Our IP address. Defaults is '0.0.0.0', which ends up being
            converted by the repeater to the IP from which it receives the
            packet.

        Returns
        -------
        RepeaterRegisterRequest
        """
        if ip is None:
            ip = '0.0.0.0'
        command = RepeaterRegisterRequest(ip)
        return command

    def disconnect(self):
        self._registered = False

    @property
    def registered(self):
        return self._registered
