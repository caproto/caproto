"""
This module contains only the Broadcaster object, encapsulating the state of
one pvAccess UDP connection, intended to be used as a companion to a UDP
socket provided by a client or server implementation.
"""
import ctypes
import logging
from typing import Dict, List, Optional, Type

from . import _utils as utils
from ._core import (BIG_ENDIAN, LITTLE_ENDIAN, SYS_ENDIAN, AddressTuple,
                    UserFacingEndian)
from ._data import FieldDescAndData
from ._messages import (BeaconMessage, BeaconMessageBE, BeaconMessageLE,
                        MessageFlags, MessageHeaderBE, MessageHeaderLE,
                        SearchFlags, SearchRequest, SearchRequestBE,
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

    broadcast_port : int
        UDP socket port for responses.

    server_port : int, optional
        TCP port for connections, if ``our_role`` is ``SERVER``.

    endian : LITTLE_ENDIAN or BIG_ENDIAN, optional
        Default is SYS_ENDIAN.

    guid : str, optional
        The globally unique identifier for responses to search requests.  Must
        be 12 characters long.

    response_addr : str, optional
         The desired response address for search replies.  The address may be
         '0.0.0.0' as an indicator to reply to the IP-layer defined source
         address of the packet.
    """

    _SearchRequest: Type[SearchRequest]
    _SearchResponse: Type[SearchResponse]
    _BeaconMessage: Type[BeaconMessage]
    server_addresses: List[AddressTuple]
    client_address: AddressTuple
    endian: UserFacingEndian
    our_role: Role
    broadcast_port: int
    server_port: Optional[int]
    response_addr: str
    guid: str
    unanswered_searches: Dict[int, str]

    def __init__(self,
                 our_role: Role,
                 broadcast_port: int,
                 server_port: Optional[int] = None,
                 endian: UserFacingEndian = SYS_ENDIAN,
                 guid: str = None,
                 response_addr: str = '0.0.0.0',
                 ):
        if our_role not in (SERVER, CLIENT):
            raise CaprotoValueError("role must be caproto.SERVER or "
                                    "caproto.CLIENT")
        self.our_role = our_role
        self.endian = endian
        if endian == LITTLE_ENDIAN:
            self._SearchRequest = SearchRequestLE
            self._SearchResponse = SearchResponseLE
            self._BeaconMessage = BeaconMessageLE
        elif endian == BIG_ENDIAN:
            self._SearchRequest = SearchRequestBE
            self._SearchResponse = SearchResponseBE
            self._BeaconMessage = BeaconMessageBE
        else:
            raise ValueError('Invalid endian setting')

        self.broadcast_port = broadcast_port
        self.server_port = server_port
        self.response_addr = response_addr
        self.guid = guid or utils.new_guid()

        if len(self.guid) != 12:
            raise ValueError(
                f'GUID must be 12 characters long. Got: {self.guid}'
            )

        if our_role is CLIENT:
            self.their_role = SERVER
        else:
            self.their_role = CLIENT

        self.server_addresses = []
        self.client_address = None

        self.unanswered_searches = {}  # map search id (cid) to name
        # Unlike VirtualCircuit and Channel, there is very little state to
        # track for the Broadcaster. We don't need a full state machine.
        self._sequence_id_counter = utils.ThreadsafeCounter()
        self._search_id_counter = utils.ThreadsafeCounter(
            dont_clash_with=self.unanswered_searches
        )
        self._beacon_counter = utils.ThreadsafeCounter()
        self._beacon_counter.MAX_ID = 255  # 8-bit, not the usual 16-bit

        self.log = logging.getLogger("caproto.pva.bcast")
        self.beacon_log = logging.getLogger('caproto.pva.bcast.beacon')
        self.search_log = logging.getLogger('caproto.pva.bcast.search')

    @property
    def our_addresses(self):
        if self.our_role is CLIENT:
            return [self.client_address]  # always return a list
        return self.server_addresses

    @property
    def their_addresses(self):
        if self.their_role is CLIENT:
            return [self.client_address]  # always return a list
        return self.server_addresses

    def send(self, *messages):
        """
        Convert one or more high-level messages into bytes that may be
        broadcast together in one UDP datagram. Update our internal
        state machine.

        Parameters
        ----------
        *messages :
            any number of :class:`Message` objects

        Returns
        -------
        bytes_to_send : bytes
            bytes to send over a socket
        """
        bytes_to_send = b''
        self.log.debug("Serializing %d messages into one datagram",
                       len(messages))
        for i, message in enumerate(messages):
            self.log.debug("%d of %d %r", 1 + i, len(messages), message)
            self._process_command(self.our_role, message)

            if self.our_role == SERVER:
                flags = MessageFlags.FROM_SERVER
            else:
                flags = MessageFlags.FROM_CLIENT

            if message._ENDIAN == LITTLE_ENDIAN:
                flags |= MessageFlags.LITTLE_ENDIAN
                header_cls = MessageHeaderLE
            else:
                flags |= MessageFlags.BIG_ENDIAN
                header_cls = MessageHeaderBE

            command_bytes = message.serialize()
            header = header_cls(
                flags=MessageFlags.APP_MESSAGE | flags,  # TODO
                command=message.ID,
                payload_size=len(command_bytes)
            )
            bytes_to_send += bytes(header) + command_bytes

        return bytes_to_send

    def recv(self, byteslike, address):
        """
        Parse messages from a UDP datagram.

        When the caller is ready to process the messages, each message should
        first be passed to :meth:`Broadcaster.process_command` to validate it
        against the protocol and update the Broadcaster's state.

        Parameters
        ----------
        byteslike : bytes-like
        address : tuple
            ``(host, port)`` as a string and an integer respectively

        Returns
        -------
        messages : list
        """
        tags = {
            'their_address': address,
            'direction': '<<<---',
            'role': repr(self.our_role)
        }

        deserialized = read_datagram(
            byteslike, address, role=self.their_role,
            # fixed_byte_order=LITTLE_ENDIAN
        )

        messages = deserialized.data
        for message in messages:
            tags['bytesize'] = ctypes.sizeof(message)
            for address in self.our_addresses:
                tags['our_address'] = address
                if isinstance(message, BeaconMessage):
                    log = self.beacon_log
                else:
                    log = self.log
                log.debug("%r", message, extra=tags)

        return deserialized.data

    def process_commands(self, messages):
        """
        Update internal state machine and raise if protocol is violated.

        Received messages should be passed through here before any additional
        processing by a server or client layer.
        """
        for message in messages:
            self._process_command(self.their_role, message)

    def _process_command(self, role, message):
        """
        All comands go through here.

        Parameters
        ----------
        role : ``CLIENT`` or ``SERVER``
        message : Message
        """
        # All messages go through here.
        if isinstance(message, SearchRequest):
            for info in message.channels:
                id_ = info['id']
                channel_name = info['channel_name']
                self.unanswered_searches[id_] = channel_name
        elif isinstance(message, SearchResponse):
            for cid in message.search_instance_ids:
                self.unanswered_searches.pop(cid, None)

    def search(self, pvs) -> SearchRequest:
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
        req = self._SearchRequest(
            sequence_id=self._sequence_id_counter(),
            response_address=(self.response_addr, self.broadcast_port),
            channels=[{'id': search_id, 'channel_name': pv}
                      for pv, search_id in pv_to_cid.items()]
            # flags=(SearchFlags.reply_required | SearchFlags.broadcast),
        )

        return pv_to_cid, req

    def search_response(self,
                        pv_to_cid: Dict[str, int],
                        *,
                        protocol: str = 'tcp',
                        guid: Optional[str] = None
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
        return self._SearchResponse(
            guid=guid or self.guid,
            sequence_id=self._sequence_id_counter(),
            server_address=(self.response_addr, self.server_port),
            protocol=protocol,
            search_instance_ids=list(pv_to_cid.values()),
            found=True,
        )

    def beacon(self,
               server_status: FieldDescAndData,
               *,
               flags: int = 0,
               protocol: str = 'tcp',
               guid: Optional[str] = None,
               ) -> BeaconMessage:
        """
        Generate a valid :class:`SearchResponse`

        Parameters
        ----------
        server_status : FieldDescAndData
            Server-defined status information.

        flags : int, optional
            Currently unused / reserved.

        protocol : str, optional
            Defaults to 'tcp'.

        guid : str, optional
            Override the Broadcaster guid.

        Returns
        -------
        BeaconMessage
        """
        if self.server_port is None:
            raise RuntimeError('Server port was not set.')

        if not isinstance(server_status, FieldDescAndData):
            server_status = FieldDescAndData(data=server_status)

        return self._BeaconMessage(
            guid=guid or self.guid,
            flags=SearchFlags.broadcast,
            sequence_id=self._beacon_counter(),
            change_count=0,
            server_address=(self.response_addr, self.server_port),
            protocol=protocol,
            server_status=server_status,
        )

    def disconnect(self):
        ...
