# This is a channel access client implemented using trio.

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
import trio

from collections import OrderedDict, defaultdict
from trio import socket
from .._utils import (batch_requests, CaprotoError, ThreadsafeCounter,
                      get_environment_variables)
from .._constants import (STALE_SEARCH_EXPIRATION, SEARCH_MAX_DATAGRAM_BYTES)


class TrioClientError(CaprotoError):
    ...


class ChannelReadError(TrioClientError):
    ...


if not hasattr(trio.SocketStream, 'sendmsg'):
    # monkey-patch in sendmsg in trio
    async def sendmsg(self, buffers):
        from trio._highlevel_socket import _translate_socket_errors_to_stream_errors  # noqa
        if self.socket.did_shutdown_SHUT_WR:
            await trio._core.checkpoint()
            raise trio.ClosedStreamError("can't send data after sending EOF")
        with self._send_conflict_detector.sync:
            with _translate_socket_errors_to_stream_errors():
                return (await self.socket.sendmsg(buffers))

    trio.SocketStream.sendmsg = sendmsg
    del sendmsg


class VirtualCircuit:
    "Wraps a caproto.VirtualCircuit and adds transport."
    def __init__(self, circuit, *, nursery):
        self.circuit = circuit  # a caproto.VirtualCircuit
        self.log = self.circuit.log
        self.nursery = nursery
        self.channels = {}  # map cid to Channel
        self.ioids = {}  # map ioid to Channel
        self.ioid_data = {}  # map ioid to server response
        self.subscriptionids = {}  # map subscriptionid to Channel
        self.connected = True
        self.socket = None
        self.command_queue = trio.Queue(capacity=1000)
        self.new_command_condition = trio.Condition()
        self._socket_lock = trio.Lock()

    async def connect(self):
        async with self._socket_lock:
            self.socket = await trio.open_tcp_stream(*self.circuit.address)
        # Kick off background loops that read from the socket
        # and process the commands read from it.
        self.nursery.start_soon(self._receive_loop)
        self.nursery.start_soon(self._command_queue_loop)
        # Send commands that initialize the Circuit.
        await self.send(ca.VersionRequest(version=ca.DEFAULT_PROTOCOL_VERSION,
                                          priority=self.circuit.priority))
        host_name = socket.gethostname()
        await self.send(ca.HostNameRequest(name=host_name))
        client_name = getpass.getuser()
        await self.send(ca.ClientNameRequest(name=client_name))

    async def _receive_loop(self):
        num_bytes_needed = 0
        while True:
            bytes_to_recv = max(32768, num_bytes_needed)
            bytes_received = await self.socket.receive_some(bytes_to_recv)
            if not len(bytes_received):
                self.connected = False
                break
            commands, num_bytes_needed = self.circuit.recv(bytes_received)
            for c in commands:
                await self.command_queue.put(c)

    async def _command_queue_loop(self):
        while True:
            try:
                command = await self.command_queue.get()
                self.circuit.process_command(command)
            except Exception as ex:
                self.log.error('Command queue evaluation failed: {!r}'
                               ''.format(command), exc_info=ex)
                continue

            if command is ca.DISCONNECTED:
                self.log.debug('Command queue loop exiting')
                break
            elif isinstance(command, (ca.ReadNotifyResponse,
                                      ca.ReadResponse,
                                      ca.WriteNotifyResponse)):
                user_event = self.ioids.pop(command.ioid)
                self.ioid_data[command.ioid] = command
                user_event.set()
            elif isinstance(command, ca.EventAddResponse):
                user_queue = self.subscriptionids[command.subscriptionid]
                await user_queue.put(command)
            elif isinstance(command, ca.EventCancelResponse):
                self.subscriptionids.pop(command.subscriptionid)
            elif isinstance(command, ca.ErrorResponse):
                original_req = command.original_request
                cmd_class = ca.get_command_class(ca.CLIENT, original_req)
                if cmd_class in (ca.ReadNotifyRequest, ca.ReadRequest,
                                 ca.WriteNotifyRequest):
                    ioid = original_req.parameter2
                    user_event = self.ioids.pop(ioid)
                    self.ioid_data[ioid] = command
                    user_event.set()
            async with self.new_command_condition:
                self.new_command_condition.notify_all()

    async def send(self, *commands):
        """
        Process a command and tranport it over the TCP socket for this circuit.
        """
        if self.connected:
            buffers_to_send = self.circuit.send(*commands)
            async with self._socket_lock:
                if self.socket is None:
                    raise RuntimeError('socket connection failed')

                await ca.async_send_all(buffers_to_send, self.socket.sendmsg)


class Channel:
    """Wraps a VirtualCircuit and a caproto.ClientChannel."""
    def __init__(self, circuit, channel):
        self.circuit = circuit  # a VirtualCircuit
        self.channel = channel  # a caproto.ClientChannel
        self.last_reading = None
        self.monitoring_queues = {}  # maps subscriptionid to trio.Task
        self._callback = None  # user func to call when subscriptions are run

    @property
    def nursery(self):
        return self.circuit.nursery

    def register_user_callback(self, func):
        """
        Func to be called when a subscription receives a new EventAdd command.

        This function will be called by a Task in the main thread. If ``func``
        needs to do CPU-intensive or I/O-related work, it should execute that
        work in a separate thread of process.
        """
        self._callback = func

    def process_subscription(self, event_add_command):
        if self._callback is None:
            return
        else:
            self._callback(event_add_command)

    async def wait_for_connection(self):
        """Wait for this Channel to be connected, ready to use.

        The method ``Context.create_channel`` spawns an asynchronous task to
        initialize the connection in the fist place. This method waits for it
        to complete.
        """
        while not self.channel.states[ca.CLIENT] is ca.CONNECTED:
            await self.wait_on_new_command()

    async def disconnect(self):
        "Disconnect this Channel."
        if self.channel.states[ca.CLIENT] is ca.CONNECTED:
            await self.circuit.send(self.channel.clear())
        while self.channel.states[ca.CLIENT] is ca.MUST_CLOSE:
            await self.wait_on_new_command()

        for sub_id, queue in self.circuit.subscriptionids.items():
            self.log.debug("Disconnecting subscription id %s", sub_id)
            await queue.put(ca.DISCONNECTED)

    async def read(self, *args, **kwargs):
        """Request a fresh reading, wait for it, return it and stash it.

        The most recent reading is always available in the ``last_reading``
        attribute.
        """
        command = self.channel.read(*args, **kwargs)
        # Stash the ioid to match the response to the request.
        ioid = command.ioid
        event = trio.Event()
        self.circuit.ioids[ioid] = event
        await self.circuit.send(command)
        await event.wait()

        reading = self.circuit.ioid_data.pop(ioid)
        if isinstance(reading, (ca.ReadResponse, ca.ReadNotifyResponse)):
            self.last_reading = reading
            return self.last_reading
        else:
            raise ChannelReadError(str(reading))

    async def write(self, *args, notify=False, **kwargs):
        "Write a new value and await confirmation from the server."
        command = self.channel.write(*args, notify=notify, **kwargs)
        if notify:
            # Stash the ioid to match the response to the request.
            ioid = command.ioid
            event = trio.Event()
            self.circuit.ioids[ioid] = event
        await self.circuit.send(command)
        if notify:
            await event.wait()
            return self.circuit.ioid_data.pop(ioid)

    async def subscribe(self, *args, **kwargs):
        "Start a new subscription and spawn an async task to receive readings."
        command = self.channel.subscribe(*args, **kwargs)
        # Stash the subscriptionid to match the response to the request.
        queue = trio.Queue(capacity=100)
        self.circuit.subscriptionids[command.subscriptionid] = queue
        await self.circuit.send(command)

        async def _queue_loop(task_status):
            task_status.started()
            while True:
                command = await queue.get()
                if command is ca.DISCONNECTED:
                    break
                self.process_subscription(command)

        await self.nursery.start(_queue_loop)
        return command.subscriptionid

    async def unsubscribe(self, subscriptionid, *args, **kwargs):
        "Cancel a subscription and await confirmation from the server."
        # queue = self.circuit.subscriptionids[subscriptionid]
        await self.circuit.send(self.channel.unsubscribe(subscriptionid))
        while subscriptionid in self.circuit.subscriptionids:
            await self.wait_on_new_command()

    async def wait_on_new_command(self):
        '''Wait for a new command to come in'''
        async with self.circuit.new_command_condition:
            await self.circuit.new_command_condition.wait()


class SharedBroadcaster:
    def __init__(self, *, nursery):
        self.nursery = nursery
        self.broadcaster = ca.Broadcaster(our_role=ca.CLIENT)
        self.log = self.broadcaster.log
        self.command_bundle_queue = trio.Queue(capacity=1000)
        self.broadcaster_command_condition = trio.Condition()
        self._cleanup_condition = trio.Condition()
        self._cleanup_event = trio.Event()

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
        for host in ca.get_address_list():
            if ':' in host:
                host, _, port_as_str = host.partition(':')
                specified_port = int(port_as_str)
            else:
                specified_port = port
            self.broadcaster.log.debug(
                'Sending %d bytes to %s:%d',
                len(bytes_to_send), host, specified_port)
            try:
                await self.udp_sock.sendto(bytes_to_send,
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
            await self.command_bundle_queue.put(ca.DISCONNECTED)
            self.log.debug('Broadcaster: Closing the UDP socket')
            self._cleanup_condition.notify_all()
        self.log.debug('Broadcaster disconnect complete')

    async def register(self):
        "Register this client with the CA Repeater."
        # TODO don't spawn these more than once
        self.nursery.start_soon(self._broadcaster_queue_loop)
        await self.nursery.start(self._broadcaster_recv_loop)

    async def _broadcaster_recv_loop(self, task_status):
        self.udp_sock = ca.bcast_socket(socket_module=socket)
        command = self.broadcaster.register('127.0.0.1')
        await self.send(ca.EPICS_CA2_PORT, command)
        task_status.started()

        while True:
            async with self._cleanup_condition:
                if self._cleanup_event.is_set():
                    self.log.debug('Exiting broadcaster recv loop')
                    break

            try:
                with trio.fail_after(0.5):
                    bytes_received, address = await self.udp_sock.recvfrom(4096)
            except trio.TooSlowError:
                continue

            if bytes_received:
                if bytes_received is ca.DISCONNECTED:
                    break
                commands = self.broadcaster.recv(bytes_received, address)
                await self.command_bundle_queue.put(commands)

    async def _broadcaster_queue_loop(self):
        while True:
            try:
                commands = await self.command_bundle_queue.get()
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
                        self.log.debug('Found %s at %s', name, address)
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
            with trio.move_on_after(1):
                await self.wait_on_new_command()
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

        for addr, names in use_cached_search.items():
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

            with trio.move_on_after(1):
                await self.wait_on_new_command()

            results.clear()
            found = [(search_id, name) for search_id, name in needs_search
                     if search_id not in self.unanswered_searches]
            needs_search = [key for key in needs_search
                            if key not in found]
            for search_id, name in found:
                address, timestamp = self.search_results[name]
                results[address].append(name)

            for addr, names in results.items():
                yield (address, names)

    async def wait_on_new_command(self):
        '''Wait for a new broadcaster command to come in'''
        async with self.broadcaster_command_condition:
            await self.broadcaster_command_condition.wait()


class Context:
    "Wraps a caproto.Broadcaster, a UDP socket, and cache of VirtualCircuits."
    def __init__(self, broadcaster=None, *, nursery):
        self.nursery = nursery
        self.circuits = []  # list of VirtualCircuits
        if broadcaster is None:
            broadcaster = SharedBroadcaster(nursery=nursery)
        self.broadcaster = broadcaster
        self.log = logging.getLogger(f'caproto.ctx.{id(self)}')

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
        circuit = VirtualCircuit(ca_circuit, nursery=self.nursery)
        self.circuits.append(circuit)
        self.nursery.start_soon(circuit.connect)
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
                for name, channel in channels.items():
                    await channel.wait_for_connection()

        if move_on_after is not None:
            with trio.move_on_after(move_on_after):
                async with trio.open_nursery() as nursery:
                    nursery.start_soon(connect_outer, names)
        else:
            async with trio.open_nursery() as nursery:
                nursery.start_soon(connect_outer, names)
        return channels
