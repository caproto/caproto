# This module contains only the Broadcaster object, encapsulating the state of
# one pvAccess UDP connection, intended to be used as a companion to a UDP
# socket provided by a client or server implementation.
import itertools
import logging

from .const import SYS_ENDIAN, LITTLE_ENDIAN, BIG_ENDIAN
from .utils import (CLIENT, SERVER, CaprotoValueError, LocalProtocolError,
                    ThreadsafeCounter)
from .state import get_exception
from .messages import (SearchRequest, SearchRequestLE, SearchRequestBE,
                       SearchResponse, SearchResponseLE, SearchResponseBE,
                       MessageHeaderLE, MessageHeaderBE,
                       DirectionFlag, SearchFlags, EndianFlag,
                       read_datagram,
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
    port : int
        UDP socket port for responses
    endian : LITTLE_ENDIAN or BIG_ENDIAN
        Default is SYS_ENDIAN
    """
    def __init__(self, our_role, response_addr, endian=SYS_ENDIAN):
        if our_role not in (SERVER, CLIENT):
            raise CaprotoValueError("role must be caproto.SERVER or "
                                    "caproto.CLIENT")
        self.our_role = our_role
        self.endian = endian
        if endian == LITTLE_ENDIAN:
            self.SearchRequest = SearchRequestLE
        elif endian == BIG_ENDIAN:
            self.SearchRequest = SearchRequestBE
        else:
            raise ValueError('Invalid endian setting')

        self.response_addr = response_addr

        if our_role is CLIENT:
            self.their_role = SERVER
            abbrev = 'cli'  # just for logger
        else:
            self.their_role = CLIENT
            abbrev = 'srv'
        self.unanswered_searches = {}  # map search id (cid) to name
        # Unlike VirtualCircuit and Channel, there is very little state to
        # track for the Broadcaster. We don't need a full state machine.
        self._sequence_id_counter = ThreadsafeCounter()
        self._search_id_counter = ThreadsafeCounter()
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

        return read_datagram(byteslike, address, role=self.their_role,
                             fixed_byte_order=LITTLE_ENDIAN)

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

    def new_search_id(self):
        # Return the next sequential unused id. Wrap back to 0 on overflow.
        while True:
            i = self._search_id_counter()
            if i not in self.unanswered_searches:
                return i

    def search(self, pvs):
        """
        Generate a valid :class:`SearchRequest`

        Parameters
        ----------
        pvs : list or dict
            PV name list, where broadcaster generates IDs, or {'pv': cid}
            dictionary

        Returns
        -------
        pv_to_cid, SearchRequest
        """
        if isinstance(pvs, dict):
            pv_to_cid = pvs
        else:
            pv_to_cid = {pv: self.new_search_id() for pv in pvs}

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

    def search_response(self, guid, pv_to_cid, *, protocol='tcp'):
        """
        Generate a valid :class:`_SearchResponse`

        Parameters
        ----------
        guid : str
            Server GUID
        pv_to_cid : dict
            {pv: cid}
        protocol : str, optional
            Default 'tcp'

        Returns
        -------
        _SearchResponse
        """
        seq_id = self._sequence_id_counter()
        return self.SearchResponse(
            guid=guid,
            sequence_id=seq_id,
            server_address=self.response_addr[0],
            server_port=self.response_addr[1],
            protocol=protocol,
            search_count=len(pv_to_cid),
            search_instance_ids=list(pv_to_cid.values()),
        )

    def disconnect(self):
        ...
