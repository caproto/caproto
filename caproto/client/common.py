# This is a channel access client implemented in a asyncio-agnostic way.

# It builds on the abstractions used in caproto, adding transport and some
# caches for matching requests with responses.
#
# VirtualCircuit: has a caproto.VirtualCircuit, a socket, and some caches.
# Channel: has a VirtualCircuit and a caproto.ClientChannel.
# Context: has a caproto.Broadcaster, a UDP socket, a cache of
#          search results and a cache of VirtualCircuits.
#
import getpass

import caproto as ca


class ChannelReadError(Exception):
    ...


class VirtualCircuit:
    "Wraps a caproto.VirtualCircuit and adds transport."
    def __init__(self, circuit):
        self.circuit = circuit  # a caproto.VirtualCircuit
        self.log = circuit.log
        self.channels = {}  # map cid to Channel
        self.ioids = {}  # map ioid to Channel
        self.ioid_data = {}  # map ioid to server response
        self.subscriptionids = {}  # map subscriptionid to Channel
        self.connected = True
        self.socket = None

        # These must be provided by the implementation #
        self.new_command_condition = None  # A Condition with awaitable
        self._socket_lock = None  # A non-recursive lock

    async def connect(self):
        await self._connect()
        # Send commands that initialize the Circuit.
        await self.send(ca.VersionRequest(
            version=ca.DEFAULT_PROTOCOL_VERSION,
            priority=self.circuit.priority))
        host_name = await self._get_host_name()
        await self.send(ca.HostNameRequest(name=host_name))
        client_name = getpass.getuser()
        await self.send(ca.ClientNameRequest(name=client_name))
