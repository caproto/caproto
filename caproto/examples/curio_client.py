# This is a channel access client implemented using curio.

# It builds on the abstractions used in caproto, adding transport and some
# caches for matching requests with responses.
#
# VirtualCircuit: has a caproto.VirtualCircuit, a socket, and some caches.
# Channel: has a VirtualCircuit and a caproto.ClientChannel.
# Context: has a caproto.Broadcaster, a UDP socket, a cache of
#          search results and a cache of VirtualCircuits.
#
import os
import caproto as ca
import curio
from curio import socket


REPEATER_PORT = 5065
SERVER_PORT = 5064


class VirtualCircuit:
    "Wraps a caproto.VirtualCircuit and adds transport."
    def __init__(self, circuit):
        self.circuit = circuit  # a caproto.VirtualCircuit
        self.channels = {}  # map cid to Channel
        self.ioids = {}  # map ioid to Channel
        self.subscriptionids = {}  # map subscriptionid to Channel
        self.event = None  # used for signaling consumers about new commands
        self.socket = None

    async def create_connection(self):
        self.socket = await socket.create_connection(self.circuit.address)

    async def send(self, *commands):
        """
        Process a command and tranport it over the TCP socket for this circuit.
        """
        if self.socket is None:
            raise RuntimeError("must await create_connection() first")
        bytes_to_send = self.circuit.send(*commands)
        await self.socket.send(bytes_to_send)

    async def recv(self):
        """
        Receive bytes over TCP and cache them in this circuit's buffer.
        """
        if self.socket is None:
            raise RuntimeError("must await create_connection() first")
        bytes_received = await self.socket.recv(4096)
        self.circuit.recv(bytes_received)

    async def get_event(self):
        """
        Get a curio.Event that we will 'set' when we process the next command.

        This is a signaling mechanism for notifying all corountines awaiting an
        incoming command that a new one (maybe the one they are looking for,
        maybe not) has been processed.
        """
        if self.event is not None:
            # Some other consumer has already asked for the next command.
            # Don't ask again (yet); just wait for the first request to
            # process.
            return self.event
        else:
            # No other consumers have asked for the next command. Ask, return
            # an Event that will be set when the command is processed, and
            # stash the Event in case any other consumers ask.
            event = curio.Event()
            self.event = event
            task = await curio.spawn(self.next_command())
            return event

    async def next_command(self):
        """
        Process one incoming command.

        1. Receive data from the socket if a full comannd's worth of bytes are
           not already cached.
        2. Dispatch to caproto.VirtualCircuit.next_command which validates.
        3. Update Channel state if applicable.
        4. Notify all coroutines awaiting a command that a new command has been
           process and they should check their state for updates.
        """
        while True:
            command = self.circuit.next_command()
            if isinstance(command, ca.NEED_DATA):
                await self.recv()
                continue
            break
        if isinstance(command, ca.ReadNotifyResponse):
            chan = self.ioids.pop(command.ioid)
            chan.last_reading = command.values
        if isinstance(command, ca.WriteNotifyResponse):
            chan = self.ioids.pop(command.ioid)
        elif isinstance(command, ca.EventAddResponse):
            chan = self.subscriptionids[command.subscriptionid]
            chan.process_subscription(command)
        elif isinstance(command, ca.EventCancelResponse):
            self.subscriptionids.pop(command.subscriptionid)
        event = self.event
        self.event = None
        await event.set()
        return command


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
            event = await self.circuit.get_event()
            await event.wait()

    async def clear(self):
        "Disconnect this Channel."
        await self.circuit.send(self.channel.clear())
        while self.channel.states[ca.CLIENT] is ca.MUST_CLOSE:
            event = await self.circuit.get_event()
            await event.wait()

    async def read(self, *args, **kwargs):
        """Request a fresh reading, wait for it, return it and stash it.

        The most recent reading is always available in the ``last_reading``
        attribute.
        """
        command = self.channel.read(*args, **kwargs)
        # Stash the ioid to match the response to the request.
        ioid = command.ioid
        self.circuit.ioids[ioid] = self
        await self.circuit.send(command)
        while ioid in self.circuit.ioids:
            event = await self.circuit.get_event()
            await event.wait()
        return self.last_reading

    async def write(self, *args, **kwargs):
        "Write a new value and await confirmation from the server."
        command = self.channel.write(*args, **kwargs)
        # Stash the ioid to match the response to the request.
        ioid = command.ioid
        self.circuit.ioids[ioid] = self
        await self.circuit.send(command)
        while ioid in self.circuit.ioids:
            event = await self.circuit.get_event()
            await event.wait()
        return self.last_reading

    async def subscribe(self, *args, **kwargs):
        "Start a new subscription and spawn an async task to receive readings."
        command = self.channel.subscribe(*args, **kwargs)
        # Stash the subscriptionid to match the response to the request.
        self.circuit.subscriptionids[command.subscriptionid] = self
        await self.circuit.send(command)
        task = await curio.spawn(self._monitor())
        self.monitoring_tasks[command.subscriptionid] = task

    async def _monitor(self):
        "Apply constant suction to receive EventAddResponse commands."
        while True:
            event = await self.circuit.get_event()
            await event.wait()

    async def unsubscribe(self, subscriptionid, *args, **kwargs):
        "Cancel a subscription and await confirmation from the server."
        await self.circuit.send(self.channel.unsubscribe(subscriptionid))
        while subscriptionid in self.circuit.subscriptionids:
            event = await self.circuit.get_event()
            await event.wait()
        task = self.monitoring_tasks[subscriptionid]
        await task.cancel()


class Context:
    "Wraps a caproto.Broadcaster, a UDP socket, and cache of VirtualCircuits." 
    def __init__(self, repeater_port=REPEATER_PORT, server_port=SERVER_PORT):
        self.repeater_port = repeater_port
        self.server_port = server_port
        self.broadcaster = ca.Broadcaster(our_role=ca.CLIENT)
        self.broadcaster.log.setLevel('DEBUG')

        # UDP socket broadcasting to CA servers
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,
                             socket.IPPROTO_UDP)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        self.udp_sock = sock

        self.registered = False  # refers to RepeaterRegisterRequest
        self.circuits = []  # list of VirtualCircuits
        self.unanswered_searches = {}  # map search id (cid) to name
        self.search_results = {}  # map name to address
        self.event = None  # used for signaling consumers about new commands

    async def send(self, port, *commands):
        """
        Process a command and tranport it over the UDP socket.
        """
        bytes_to_send = self.broadcaster.send(*commands)
        hosts = os.environ['EPICS_CA_ADDR_LIST']
        await self.udp_sock.sendto(bytes_to_send, (hosts, port))

    async def recv(self):
        """
        Receive bytes over TCP and cache them in this circuit's buffer.
        """
        bytes_received, address = await self.udp_sock.recvfrom(4096)
        self.broadcaster.recv(bytes_received, address)

    async def register(self):
        "Register this client with the CA Repeater."
        command = self.broadcaster.register('0.0.0.0')
        await self.send(self.repeater_port, command)
        while not self.registered:
            event = await self.get_event()
            await event.wait()

    async def search(self, name):
        "Generate, process, and the transport a search request."
        # Discard any old search result for this name.
        self.search_results.pop(name, None)
        ver_command, search_command = self.broadcaster.search(name)
        # Stash the search ID for recognizes the SearchResponse later.
        self.unanswered_searches[search_command.cid] = name
        await self.send(self.server_port, ver_command, search_command)
        # Wait for the SearchResponse.
        while search_command.cid in self.unanswered_searches:
            event = await self.get_event()
            await event.wait()

    def get_circuit(self, address, priority):
        """
        Return a VirtualCircuit with this address, priority.

        Make a new one if necessary.
        """
        for circuit in self.circuits:
            if (circuit.circuit.address == address and
                    circuit.circuit.priority == priority):
                return circuit
        circuit = VirtualCircuit(ca.VirtualCircuit(our_role=ca.CLIENT,
                                                   address=address,
                                                   priority=priority))
        circuit.circuit.log.setLevel('DEBUG')
        self.circuits.append(circuit)
        return circuit

    async def create_channel(self, name, priority=0):
        """
        Create a new channel.
        """
        address = self.search_results[name]
        circuit = self.get_circuit(address, priority)
        chan = ca.ClientChannel(name, circuit.circuit)

        async def connect():
            if chan.circuit.states[ca.SERVER] is ca.IDLE:
                await circuit.create_connection()
                await circuit.send(chan.version())
                await circuit.send(chan.host_name())
                await circuit.send(chan.client_name())
            await circuit.send(chan.create())

        # Spawn an async task to connect the channel and return a Channel
        # instance immediately. User can use ``Channel.wait_for_connection()``
        # to wait for connect() to complete.
        await connect()
        return Channel(circuit, chan)

    async def get_event(self):
        """
        Get a curio.Event that we will 'set' when we process the next command.

        This is a signaling mechanism for notifying all corountines awaiting an
        incoming command that a new one (maybe the one they are looking for,
        maybe not) has been processed.
        """
        if self.event is not None:
            # Some other consumer has already asked for the next command.
            # Don't ask again (yet); just wait for the first request to
            # process.
            return self.event
        else:
            # No other consumers have asked for the next command. Ask, return
            # an Event that will be set when the command is processed, and
            # stash the Event in case any other consumers ask.
            event = curio.Event()
            self.event = event
            task = await curio.spawn(self.next_command())
            return event

    async def next_command(self):
        "Receive and process and next command broadcasted over UDP."
        while True:
            command = self.broadcaster.next_command()
            if isinstance(command, ca.NEED_DATA):
                await self.recv()
                continue
            break
        if isinstance(command, ca.RepeaterConfirmResponse):
            self.registered = True
        if isinstance(command, ca.VersionResponse):
            # Check that the server version is one we can talk to.
            assert command.version > 11
        if isinstance(command, ca.SearchResponse):
            name = self.unanswered_searches.pop(command.cid, None)
            if name is not None:
                self.search_results[name] = ca.extract_address(command)
            else:
                # This is a redundant response, which the spec tell us
                # we must ignore.
                pass
        event = self.event
        self.event = None
        await event.set()
        return command


async def main():
    # Connect to two motorsim PVs. Test reading, writing, and subscribing.
    pv1 = "XF:31IDA-OP{Tbl-Ax:X1}Mtr.VAL"
    pv2 = "XF:31IDA-OP{Tbl-Ax:X2}Mtr.VAL"

    # Some user function to call when subscriptions receive data.
    called = []
    def user_callback(command):
        print("Subscription has received data.")
        called.append(True)

    ctx = Context()
    await ctx.register()
    await ctx.search(pv1)
    await ctx.search(pv2)
    # Send out connection requests without waiting for responses...
    chan1 = await ctx.create_channel(pv1)
    chan2 = await ctx.create_channel(pv2)
    # Set up a function to call when subscriptions are received.
    chan1.register_user_callback(user_callback)
    # ...and then wait for all the responses.
    await chan1.wait_for_connection()
    await chan2.wait_for_connection()
    reading = await chan1.read()
    print('reading:', reading)
    await chan1.subscribe()
    await chan2.read()
    await chan1.unsubscribe(0)
    await chan1.write((5,))
    reading = await chan1.read()
    print('reading:', reading)
    await chan1.write((6,))
    reading = await chan1.read()
    print('reading:', reading)
    await chan2.clear()
    await chan1.clear()
    assert called
    

if __name__ == '__main__':
    curio.run(main())
