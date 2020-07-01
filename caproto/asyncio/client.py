# This is a channel access client implemented using asyncio.

# It builds on the abstractions used in caproto, adding transport and some
# caches for matching requests with responses.
#
# VirtualCircuit: has a caproto.VirtualCircuit, a socket, and some caches.
# Channel: has a VirtualCircuit and a caproto.ClientChannel.
# Context: has a caproto.Broadcaster, a UDP socket, a cache of
#          search results and a cache of VirtualCircuits.
#
import getpass
import logging
import time

import caproto as ca

import socket
import asyncio

from collections import defaultdict, OrderedDict

from .._constants import (STALE_SEARCH_EXPIRATION, SEARCH_MAX_DATAGRAM_BYTES)
from .._utils import (batch_requests, ThreadsafeCounter,
                      get_environment_variables, safe_getsockname)
from ..client.common import (VirtualCircuit as _VirtualCircuit)
from .utils import _get_asyncio_queue


class ChannelReadError(Exception):
    ...


def _make_tcp_socket():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
    s.setblocking(False)
    return s


def create_datagram_protocol(parent, recv_func):
    class Protocol(asyncio.Protocol):
        def __init__(self, *args, **kwargs):
            self.transport = None
            self._tasks = ()

        def connection_made(self, transport):
            self.transport = transport

        def datagram_received(self, data, addr):
            if not data:
                return

            task = asyncio.create_task(recv_func(data, addr))
            self._tasks = tuple(t for t in self._tasks + (task, )
                                if not t.done())

        def error_received(self, exc):
            parent.log.error('%s received error', self, exc_info=exc)

    return Protocol


class TransportWrapper:
    """Make an asyncio transport something you can call sendto on."""
    # NOTE: taken from the server - combine usage
    def __init__(self, transport):
        self.transport = transport

    def getsockname(self):
        return self.transport.get_extra_info('sockname')

    async def sendto(self, bytes_to_send, addr_port):
        try:
            self.transport.sendto(bytes_to_send, addr_port)
        except OSError as exc:
            host, port = addr_port
            raise ca.CaprotoNetworkError(f"Failed to send to {host}:{port}") from exc

    def close(self):
        return self.transport.close()


class SharedBroadcaster:
    def __init__(self):
        self.broadcaster = ca.Broadcaster(our_role=ca.CLIENT)
        self.log = self.broadcaster.log
        self.command_queue = asyncio.Queue()
        self.broadcaster_command_condition = asyncio.Condition()
        self._cleanup_condition = asyncio.Condition()
        self._cleanup_event = asyncio.Event()
        self._tasks = []

        # UDP socket broadcasting to CA servers
        self.udp_sock = None
        self.registered = False  # refers to RepeaterRegisterRequest
        self.unanswered_searches = {}  # map search id (cid) to name
        self.search_results = {}  # map name to address
        self.new_id = ThreadsafeCounter(
            dont_clash_with=self.unanswered_searches)

        self.environ = get_environment_variables()
        self.ca_server_port = self.environ['EPICS_CA_SERVER_PORT']

    async def send(self, port, *commands):
        """
        Process a command and tranport it over the UDP socket.
        """
        bytes_to_send = self.broadcaster.send(*commands)
        tags = {'role': 'CLIENT',
                'our_address': self.broadcaster.client_address,
                'direction': '--->>>'}

        loop = asyncio.get_running_loop()
        for host in ca.get_address_list():
            if ':' in host:
                host, _, port_as_str = host.partition(':')
                specified_port = int(port_as_str)
            else:
                specified_port = port
            tags['their_address'] = (host, specified_port)
            self.broadcaster.log.debug(
                '%d commands %dB',
                len(commands), len(bytes_to_send), extra=tags)
            try:
                await self.wrapped_transport.sendto(bytes_to_send,
                                                    (host, specified_port))
            except OSError as ex:
                raise ca.CaprotoNetworkError(
                    f'{ex} while sending {len(bytes_to_send)} bytes to '
                    f'{host}:{specified_port}') from ex

    async def disconnect(self):
        'Disconnect the broadcaster and stop listening'
        async with self._cleanup_condition:
            self._cleanup_event.set()
            self.log.debug('Broadcaster: Disconnecting the command queue loop')
            await self.command_queue.send.send(ca.DISCONNECTED)
            self.log.debug('Broadcaster: Closing the UDP socket')
            self.udp_sock = None
            self._cleanup_condition.notify_all()

        for task in self._tasks:
            task.cancel()

        # TODO tasks from BcastLoop as well

        await asyncio.wait(self._tasks)
        self._tasks.clear()
        self.log.debug('Broadcaster disconnect complete')

    async def register(self):
        "Register this client with the CA Repeater."
        # TODO don't spawn these more than once

        self.udp_sock = ca.bcast_socket(socket_module=socket)

        loop = asyncio.get_running_loop()
        transport, self.protocol = await loop.create_datagram_endpoint(
            create_datagram_protocol(self, self._broadcaster_recv_datagram),
            sock=self.udp_sock)
        self.wrapped_transport = TransportWrapper(transport)

        # Must bind or getsocketname() will raise on Windows.
        # See https://github.com/caproto/caproto/issues/514.
        self.udp_sock.bind(('', 0))
        self.broadcaster.our_address = safe_getsockname(self.udp_sock)
        command = self.broadcaster.register('127.0.0.1')
        await self.send(ca.EPICS_CA2_PORT, command)

        self._tasks.append(asyncio.create_task(self._broadcaster_queue_loop()))
        self._tasks.append(asyncio.create_task(self._broadcaster_recv_loop()))

    async def _broadcaster_recv_datagram(self, bytes_received, address):
        try:
            commands = self.broadcaster.recv(bytes_received, address)
        except ca.RemoteProtocolError:
            self.log.exception('Broadcaster received bad packet')
        else:
            await self.command_queue.put((address, commands))

    async def _broadcaster_recv_loop(self):
        while True:
            async with self._cleanup_condition:
                if self._cleanup_event.is_set():
                    self.udp_sock.close()
                    self.log.debug('Exiting broadcaster recv loop')
                    break

            try:
                bytes_received, address = await asyncio.wait_for(
                    self.udp_sock.recvfrom(4096), timeout=0.5)
            except asyncio.TimeoutError:
                continue

            if bytes_received:
                if bytes_received is ca.DISCONNECTED:
                    break
                commands = self.broadcaster.recv(bytes_received, address)
                await self.command_queue.send.send(commands)

    async def _broadcaster_queue_loop(self):
        while True:
            try:
                addr, commands = await self.command_queue.get()
                if commands is ca.DISCONNECTED:
                    break
                self.broadcaster.process_commands(commands)
            except Exception as ex:
                self.log.error('Broadcaster command queue evaluation failed',
                               exc_info=ex)
                continue

            for command in commands:
                if isinstance(command, ca.RepeaterConfirmResponse):
                    self.registered = True
                elif isinstance(command, ca.VersionResponse):
                    # Check that the server version is one we can talk to.
                    if command.version <= 11:
                        self.log.debug('Old client on version %s',
                                       command.version)
                        continue
                elif isinstance(command, ca.SearchResponse):
                    try:
                        name = self.unanswered_searches.pop(command.cid)
                    except KeyError:
                        # This is a redundant response, which the EPICS
                        # spec tells us to ignore. (The first responder
                        # to a given request wins.)
                        if name in self.search_results:
                            accepted_address = self.search_results[name]
                            new_address = ca.extract_address(command)
                            self.log.warning("PV found on multiple servers. "
                                             "Accepted address is %s. "
                                             "Also found on %s",
                                             accepted_address, new_address)
                    else:
                        address = ca.extract_address(command)
                        self.log.debug('Found %s at %s:%d', name, *address)
                        self.search_results[name] = address

                async with self.broadcaster_command_condition:
                    self.broadcaster_command_condition.notify_all()

    def get_cached_search_result(self, name, *,
                                 threshold=STALE_SEARCH_EXPIRATION):
        'Returns address if found, raises KeyError if missing or stale.'
        address, timestamp = self.search_results[name]
        if time.monotonic() - timestamp > threshold:
            # TODO i have no idea which contexts are using me and are still
            #      alive as in the threaded client
            # Clean up expired result.
            self.search_results.pop(name, None)
            raise KeyError(f'{name!r}: stale search result')

        return address

    async def search(self, name):
        "Generate, process, and transport a search request."
        # Discard any old search result for this name.
        self.search_results.pop(name, None)
        ver_command, search_command = self.broadcaster.search(
            name, cid=self.new_id())
        # Stash the search ID for recognizes the SearchResponse later.
        self.unanswered_searches[search_command.cid] = name
        # Wait for the SearchResponse.
        while search_command.cid in self.unanswered_searches:
            await self.send(self.ca_server_port, ver_command, search_command)
            try:
                await asyncio.wait_for(self.wait_on_new_command(), timeout=1)
            except TimeoutError:
                ...
        return name

    async def search_many(self, *names):
        "Generate, process, and transport search request(s)"
        # We have have already searched for these names recently.
        # Filter `pv_names` down to a subset, `needs_search`.
        needs_search = []
        use_cached_search = defaultdict(list)
        for name in names:
            try:
                address = self.get_cached_search_result(name)
            except KeyError:
                needs_search.append((self.new_id(), name))
            else:
                use_cached_search[address].append(name)

        for names in use_cached_search.values():
            yield (address, names)

        use_cached_search.clear()

        # Generate search_ids and stash them on Context state so they can
        # be used to match SearchResponses with SearchRequests.
        for search_id, name in needs_search:
            self.unanswered_searches[search_id] = name

        results = defaultdict(list)

        while needs_search:
            self.log.debug('Searching for %r PVs....', len(needs_search))
            requests = (ca.SearchRequest(name, search_id,
                                         ca.DEFAULT_PROTOCOL_VERSION)
                        for search_id, name in needs_search)
            for batch in batch_requests(requests, SEARCH_MAX_DATAGRAM_BYTES):
                await self.send(self.ca_server_port,
                                ca.VersionRequest(0, ca.DEFAULT_PROTOCOL_VERSION),
                                *batch)

            try:
                await asyncio.wait_for(self.wait_on_new_command(), timeout=1)
            except TimeoutError:
                ...

            results.clear()
            found = [(search_id, name) for search_id, name in needs_search
                     if search_id not in self.unanswered_searches]
            needs_search = [key for key in needs_search
                            if key not in found]
            for _search_id, name in found:
                address, timestamp = self.search_results[name]
                results[address].append(name)

            for names in results.values():
                yield (address, names)

    async def wait_on_new_command(self):
        '''Wait for a new broadcaster command to come in'''
        async with self.broadcaster_command_condition:
            await self.broadcaster_command_condition.wait()


class VirtualCircuit(_VirtualCircuit):
    "Wraps a caproto.VirtualCircuit and adds transport."
    def __init__(self, circuit):
        super().__init__(circuit)
        loop = asyncio.get_running_loop()
        self.command_queue = _get_asyncio_queue(loop)
        self.new_command_condition = asyncio.Condition()
        self._socket = _make_tcp_socket()
        self._socket_lock = asyncio.Lock()
        self.tasks = {}

    async def send(self, *commands):
        if self.connected:
            buffers_to_send = self.circuit.send(*commands)
            # lock to make sure a AddEvent does not write bytes
            # to the socket while we are sending
            async with self._socket_lock:
                await asyncio.get_running_loop().sock_sendall(
                    self._socket, b''.join(buffers_to_send))

    async def _connect(self):
        # very confused
        ...


class Context:
    "Wraps a caproto.Broadcaster, a UDP socket, and cache of VirtualCircuits."
    def __init__(self, broadcaster=None):
        self.circuits = []  # list of VirtualCircuits
        if broadcaster is None:
            broadcaster = SharedBroadcaster()
        self.broadcaster = broadcaster
        self.log = logging.getLogger('caproto.ctx')

    async def get_circuit(self, address, priority):
        """
        Return a VirtualCircuit with this address, priority.

        Make a new one if necessary.
        """
        for circuit in self.circuits:
            if (circuit.circuit.address == address and
                    circuit.circuit.priority == priority):
                return circuit

        ca_circuit = ca.VirtualCircuit(our_role=ca.CLIENT, address=address,
                                       priority=priority)
        circuit = VirtualCircuit(ca_circuit)
        self.circuits.append(circuit)
        loop = asyncio.get_running_loop()

        # TODO: track this task
        loop.create_task(circuit.connect())
        return circuit

    async def search(self, name):
        "Generate, process, transport a search request with the broadcaster"
        return await self.broadcaster.search(name)

    async def create_channel(self, name, priority=0):
        """
        Create a new channel.
        """
        address = self.broadcaster.search_results[name]
        circuit = await self.get_circuit(address, priority)
        chan = ca.ClientChannel(name, circuit.circuit)
        # Wait for the SERVER to agree that we have an initialized circuit.
        while True:
            async with circuit.new_command_condition:
                state = circuit.circuit.states[ca.SERVER]
                if state is ca.CONNECTED:
                    break
                await circuit.new_command_condition.wait()
        # Send command that creates the Channel.
        await circuit.send(chan.create())
        return Channel(circuit, chan)

    async def create_many_channels(self, *names, priority=0,
                                   wait_for_connection=True,
                                   move_on_after=5):
        '''Create many channels in parallel through this context

        Parameters
        ----------
        *names : str
            Channel / PV names
        priority : int, optional
            Set priority of circuits
        wait_for_connection : bool, optional
            Wait for connections

        Returns
        -------
        channel_dict : OrderedDict
            Ordered dictionary of name to Channel
        '''

        channels = OrderedDict()

        async def connect_outer(names):
            nonlocal channels

            async for addr, names in self.broadcaster.search_many(*names):
                for name in names:
                    channels[name] = await self.create_channel(name,
                                                               priority=priority)

            if wait_for_connection:
                for channel in channels.values():
                    await channel.wait_for_connection()

        if move_on_after is not None:
            try:
                await asyncio.wait_for(
                    connect_outer(), timeout=move_on_after)
            except asyncio.TimeoutError:
                ...
        else:
            await connect_outer()

        return channels
