"""
This module contains only the Broadcaster object, encapsulating the state of
one pvAccess UDP connection, intended to be used as a companion to a UDP
socket provided by a client or server implementation.
"""

import logging
import typing

from . import _utils as utils
from ._core import BIG_ENDIAN, LITTLE_ENDIAN, SYS_ENDIAN, UserFacingEndian
from ._messages import (SearchFlags, SearchRequest, SearchRequestBE,
                        SearchRequestLE, SearchResponse, SearchResponseBE,
                        SearchResponseLE, read_datagram)
# from ._state import get_exception
from ._utils import CLIENT, SERVER, CaprotoValueError, Role


class Broadcaster:
    """
    An object encapsulating the state of one PVA UDP connection.

    It is a companion to a UDP socket managed by a client or server
    implementation. All data received over the socket should be passed to
    :meth:`recv`. Any data sent over the socket should first be passed through
    :meth:`send`.

    Parameters
    ----------
    our_role : CLIENT or SERVER
        Our role.

    port : int
        UDP socket port for responses

    endian : LITTLE_ENDIAN or BIG_ENDIAN
        Default is SYS_ENDIAN
    """
    def __init__(self,
                 our_role: Role,
                 response_addr: typing.Tuple[str, int],
                 endian: UserFacingEndian = SYS_ENDIAN,
                 guid: str = None,
                 ):
        if our_role not in (SERVER, CLIENT):
            raise CaprotoValueError("role must be caproto.SERVER or "
                                    "caproto.CLIENT")
        self.our_role = our_role
        self.endian = endian
        if endian == LITTLE_ENDIAN:
            self.SearchRequest = SearchRequestLE
            self.SearchResponse = SearchResponseLE
        elif endian == BIG_ENDIAN:
            self.SearchRequest = SearchRequestBE
            self.SearchResponse = SearchResponseBE
        else:
            raise ValueError('Invalid endian setting')

        self.response_addr = response_addr
        self.guid = guid or utils.new_guid()

        if our_role is CLIENT:
            self.their_role = SERVER
            abbrev = 'cli'  # just for logger
        else:
            self.their_role = CLIENT
            abbrev = 'srv'
        self.unanswered_searches = {}  # map search id (cid) to name
        # Unlike VirtualCircuit and Channel, there is very little state to
        # track for the Broadcaster. We don't need a full state machine.
        self._sequence_id_counter = utils.ThreadsafeCounter(
        )
        self._search_id_counter = utils.ThreadsafeCounter(
            dont_clash_with=self.unanswered_searches
        )
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
        for i, command in enumerate(commands):
            self.log.debug("%d of %d %r", 1 + i, len(commands), command)
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
        self.log.debug("Received datagram from %r with %d bytes.",
                       address, len(byteslike))

        deserialized = read_datagram(
            byteslike, address, role=self.their_role,
            fixed_byte_order=LITTLE_ENDIAN)
        return deserialized.data

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
        """
        # All commands go through here.
        if isinstance(command, SearchRequest):
            for info in command.channels.items():
                id_ = info['id']
                channel_name = info['channel_name']
                self.unanswered_searches[id_] = channel_name
        elif isinstance(command, SearchResponse):
            for cid in command.search_instance_ids:
                self.unanswered_searches.pop(cid, None)

    # CONVENIENCE METHODS

    def search(self, pvs):
        """
        Generate a valid :class:`SearchRequest`

        Parameters
        ----------
        pvs : list
            PV name list.

        Returns
        -------
        pv_to_cid, SearchRequest
        """
        pv_to_cid = {pv: self._search_id_counter() for pv in pvs}

        seq_id = self._sequence_id_counter()

        req = self.SearchRequest(
            sequence_id=seq_id,
            flags=SearchFlags.broadcast,
            # (SearchFlags.reply_required | SearchFlags.broadcast),
            response_address=self.response_addr[0],
            response_port=self.response_addr[1],
            protocols=['tcp'],
            channels=[{'id': search_id, 'channel_name': pv}
                      for pv, search_id in pv_to_cid.items()]
        )

        return pv_to_cid, req

    def search_response(self,
                        pv_to_cid: typing.Dict[str, int],
                        *,
                        protocol: str = 'tcp',
                        guid: str = None
                        ) -> SearchResponse:
        """
        Generate a valid :class:`SearchResponse`

        Parameters
        ----------
        pv_to_cid : dict
            A mapping of {pv: cid}.

        protocol : str, optional
            Defaults to 'tcp'.

        guid : str, optional
            Override the Broadcaster guid.

        Returns
        -------
        SearchResponse
        """
        seq_id = self._sequence_id_counter()
        return self.SearchResponse(
            guid=[ord(c) for c in (guid or self.guid)],
            sequence_id=seq_id,
            server_address=self.response_addr[0],
            server_port=self.response_addr[1],
            protocol=protocol,
            search_count=len(pv_to_cid),
            search_instance_ids=list(pv_to_cid.values()),
            found=len(pv_to_cid),  # hmm
        )

    def disconnect(self):
        ...
