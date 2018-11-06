# This is a channel access client implemented using curio.

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

import caproto as ca
import curio

from collections import OrderedDict
from curio import socket


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
        self.command_queue = curio.Queue()
        self.new_command_condition = curio.Condition()
        self._socket_lock = curio.RLock()

    async def connect(self):
        async with self._socket_lock:
            self.socket = await socket.create_connection(self.circuit.address)
            # Kick off background loops that read from the socket
            # and process the commands read from it.
            await curio.spawn(self._receive_loop, daemon=True)
            await curio.spawn(self._command_queue_loop, daemon=True)
            # Send commands that initialize the Circuit.
            await self.send(ca.VersionRequest(
                version=ca.DEFAULT_PROTOCOL_VERSION,
                priority=self.circuit.priority))
            host_name = await socket.gethostname()
            await self.send(ca.HostNameRequest(name=host_name))
            client_name = getpass.getuser()
            await self.send(ca.ClientNameRequest(name=client_name))

    async def _receive_loop(self):
        num_bytes_needed = 0
        while True:
            bytes_received = await self.socket.recv(max(32768,
                                                        num_bytes_needed))
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
            except curio.TaskCancelled:
                break
            except Exception as ex:
                self.log.error('Command queue evaluation failed: {!r}'
                               ''.format(command), exc_info=ex)
                continue

            if isinstance(command, (ca.ReadNotifyResponse,
                                    ca.ReadResponse,
                                    ca.WriteNotifyResponse)):
                user_event = self.ioids.pop(command.ioid)
                self.ioid_data[command.ioid] = command
                await user_event.set()
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
                    await user_event.set()
            async with self.new_command_condition:
                await self.new_command_condition.notify_all()

    async def send(self, *commands):
        """
        Process a command and tranport it over the TCP socket for this circuit.
        """
        if self.connected:
            buffers_to_send = self.circuit.send(*commands)
            async with self._socket_lock:
                if self.socket is None:
                    raise RuntimeError('socket connection failed')

                # send bytes over the wire using some caproto utilities
                await ca.async_send_all(buffers_to_send, self.socket.sendmsg)


class Channel:
    """Wraps a VirtualCircuit and a caproto.ClientChannel."""
    def __init__(self, circuit, channel):
        self.circuit = circuit  # a VirtualCircuit
        self.channel = channel  # a caproto.ClientChannel
        self.last_reading = None
        self.monitoring_tasks = {}  # maps subscriptionid to curio.Task
        self._callback = None  # user func to call when subscriptions are run

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
        await self.circuit.send(self.channel.clear())
        while self.channel.states[ca.CLIENT] is ca.MUST_CLOSE:
            await self.wait_on_new_command()

    async def read(self, *args, **kwargs):
        """Request a fresh reading, wait for it, return it and stash it.

        The most recent reading is always available in the ``last_reading``
        attribute.
        """
        command = self.channel.read(*args, **kwargs)
        # Stash the ioid to match the response to the request.
        ioid = command.ioid
        # TODO this could be implemented as a concurrent.Future and use
        #      curio.traps._future_wait. A Future is really what we want here,
        #      but it doesn't seem like curio provides such a primitive for us
        ioid = command.ioid
        event = curio.Event()
        self.circuit.ioids[ioid] = event
        await self.circuit.send(command)
        await event.wait()

        reading = self.circuit.ioid_data.pop(ioid)
        if isinstance(reading, (ca.ReadNotifyResponse, ca.ReadResponse)):
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
            event = curio.Event()
        self.circuit.ioids[ioid] = event
        if notify:
            await self.circuit.send(command)
            await event.wait()
            return self.circuit.ioid_data.pop(ioid)

    async def subscribe(self, *args, **kwargs):
        "Start a new subscription and spawn an async task to receive readings."
        command = self.channel.subscribe(*args, **kwargs)
        # Stash the subscriptionid to match the response to the request.
        queue = curio.Queue()
        self.circuit.subscriptionids[command.subscriptionid] = queue
        await self.circuit.send(command)

        async def _queue_loop():
            while True:
                command = await queue.get()
                self.process_subscription(command)

        task = await curio.spawn(_queue_loop, daemon=True)
        self.monitoring_tasks[command.subscriptionid] = task
        return command.subscriptionid

    async def unsubscribe(self, subscriptionid, *args, **kwargs):
        "Cancel a subscription and await confirmation from the server."
        await self.circuit.send(self.channel.unsubscribe(subscriptionid))
        while subscriptionid in self.circuit.subscriptionids:
            await self.wait_on_new_command()
        task = self.monitoring_tasks.pop(subscriptionid)
        await task.cancel()

    async def wait_on_new_command(self):
        '''Wait for a new command to come in'''
        async with self.circuit.new_command_condition:
            await self.circuit.new_command_condition.wait()


class SharedBroadcaster:
    def __init__(self):
        self.broadcaster = ca.Broadcaster(our_role=ca.CLIENT)
        self.log = self.broadcaster.log
        self.command_bundle_queue = curio.Queue()
        self.broadcaster_command_condition = curio.Condition()

        # UDP socket broadcasting to CA servers
        self.udp_sock = ca.bcast_socket(socket)
        self.registered = False  # refers to RepeaterRegisterRequest
        self.loop_ready_event = curio.Event()
        self.unanswered_searches = {}  # map search id (cid) to name
        self.search_results = {}  # map name to address

        self.environ = ca.get_environment_variables()
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

    async def register(self):
        "Register this client with the CA Repeater."
        # TODO don't spawn this more than once
        await curio.spawn(self._broadcaster_queue_loop, daemon=True)
        await self.loop_ready_event.wait()

    async def _broadcaster_recv_loop(self):
        command = self.broadcaster.register('127.0.0.1')
        await self.send(ca.EPICS_CA2_PORT, command)
        await self.loop_ready_event.set()

        while True:
            bytes_received, address = await self.udp_sock.recvfrom(4096)
            if bytes_received:
                commands = self.broadcaster.recv(bytes_received, address)
                await self.command_bundle_queue.put(commands)

    async def _broadcaster_queue_loop(self):
        await curio.spawn(self._broadcaster_recv_loop, daemon=True)

        while True:
            try:
                commands = await self.command_bundle_queue.get()
                self.broadcaster.process_commands(commands)
            except curio.TaskCancelled:
                break
            except Exception as ex:
                self.log.error('Broadcaster command queue evaluation failed',
                               exc_info=ex)
                continue

            for command in commands:
                if isinstance(command, ca.RepeaterConfirmResponse):
                    self.registered = True
                if isinstance(command, ca.VersionResponse):
                    # Check that the server version is one we can talk to.
                    if command.version <= 11:
                        self.log.debug('Old client on version %s',
                                       command.version)
                        continue
                if isinstance(command, ca.SearchResponse):
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
                    await self.broadcaster_command_condition.notify_all()

    async def search(self, name):
        "Generate, process, and transport a search request."
        # Discard any old search result for this name.
        self.search_results.pop(name, None)
        ver_command, search_command = self.broadcaster.search(name)
        # Stash the search ID for recognizes the SearchResponse later.
        self.unanswered_searches[search_command.cid] = name
        # Wait for the SearchResponse.
        while search_command.cid in self.unanswered_searches:
            await self.send(self.ca_server_port, ver_command, search_command)
            await curio.ignore_after(1, self.wait_on_new_command)
        return name

    async def wait_on_new_command(self):
        '''Wait for a new broadcaster command to come in'''
        async with self.broadcaster_command_condition:
            await self.broadcaster_command_condition.wait()


class Context:
    "Wraps a caproto.Broadcaster, a UDP socket, and cache of VirtualCircuits."
    def __init__(self, broadcaster=None):
        self.circuits = []  # list of VirtualCircuits
        if broadcaster is None:
            broadcaster = SharedBroadcaster()
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
        circuit = VirtualCircuit(ca_circuit)
        self.circuits.append(circuit)
        await curio.spawn(circuit.connect, daemon=True)
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
                                   move_on_after=2):
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

        async def connect_one(name):
            await self.search(name)
            chan = await self.create_channel(name, priority=priority)
            if wait_for_connection:
                await chan.wait_for_connection()

            return name, chan

        async def create_many_outer():
            async with curio.TaskGroup() as task:
                for name in names:
                    await task.spawn(connect_one, name)
                while True:
                    res = await task.next_done()
                    if res is None:
                        break

                    name, chan = res.result
                    channels[name] = chan

        channels = OrderedDict()

        if move_on_after is not None:
            async with curio.ignore_after(move_on_after):
                await create_many_outer()
        else:
            await create_many_outer()

        return channels
