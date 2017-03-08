import sys
import collections
import caproto as ca
import time
from curio import socket
import curio
import getpass


REPEATER_PORT = 5065
SERVER_PORT = 5064


class Channel:
    """Wrap an instance of caproto.ClientChannel and a Client."""
    def __init__(self, client, channel):
        self.client = client
        self.channel = channel
        self.last_reading = None
        self.subscriptionids = set()
        self.monitoring_tasks = {}

    async def wait_for_connection(self):
        while not self.channel._state[ca.CLIENT] == ca.CONNECTED:
            event = await self.client.get_event(self.channel.circuit)
            await event.wait()

    async def read(self, *args, **kwargs):
        stale = True
        circuit, command = self.channel.read(*args, **kwargs)
        # Stash the ioid to match the response to the request.
        self.client.ioids[command.ioid] = self
        await self.client.send(circuit, command)
        while stale:
            event = await self.client.get_event(self.channel.circuit)
            await event.wait()
            stale = False
        return self.last_reading

    async def subscribe(self, *args, **kwargs):
        circuit, command = self.channel.subscribe(*args, **kwargs)
        # Stash the subscriptionid to match the response to the request.
        self.client.subscriptionids[command.subscriptionid] = self
        await self.client.send(circuit, command)
        while command.subscriptionid not in self.subscriptionids:
            event = await self.client.get_event(self.channel.circuit)
            print('wait')
            await event.wait()
        print('spawn')
        task = await curio.spawn(self._monitor())
        self.monitoring_tasks[command.subscriptionid] = task

    async def _monitor(self):
        "Apply constant in-bound pressure to a circuit to receive EventAdds."
        while True:
            print("MONITOR")
            event = await self.client.get_event(self.channel.circuit)
            await event.wait()

    async def unsubscribe(self, subscriptionid, *args, **kwargs):
        print('unsubscribe')
        await self.client.send(*self.channel.unsubscribe(subscriptionid))
        print('sent')
        while subscriptionid not in self.subscriptionids:
            event = await self.client.get_event(self.channel.circuit)
            await event
        task = self.monitoring_tasks[subscriptionid]
        await task.cancel()


class Client:
    def __init__(self, repeater_port=REPEATER_PORT, server_port=SERVER_PORT):
        self.repeater_port = repeater_port
        self.server_port = server_port
        self.broadcaster = ca.Broadcaster(our_role=ca.CLIENT)
        self.hub = ca.Hub(our_role=ca.CLIENT)
        self.broadcaster.log.setLevel('DEBUG')
        self.hub.log.setLevel('DEBUG')

        # UDP socket broadcasting to CA servers
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,
                             socket.IPPROTO_UDP)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        self.udp_sock = sock

        self.tcp_socks = {}  # maps (address, priority) to socket
        self.unanswered_searches = {}  # map search id (cid) to name
        self.search_results = {}  # map name to address
        self.channels = {}  # map cid to Channel
        self.ioids = {}  # map ioid to Channel
        self.subscriptionids = {}  # map subscriptionid to Channel
        self.events = {}  # map (address, priority) to curio.Event

    async def send(self, circuit, command):
        """
        Process a command and tranport it over the TCP socket for a circuit.
        """
        bytes_to_send = circuit.send(command)
        key = circuit.key
        # circuit.key is (address, priority), which uniquely identifies a Channel
        # Access 'VirtualCircuit'. We have to open one socket per VirtualCircuit.
        if key not in self.tcp_socks:
            self.tcp_socks[key] = await socket.create_connection(circuit.address)
        await self.tcp_socks[key].send(bytes_to_send)

    async def recv(self, circuit):
        """
        Receive bytes over TCP and cache them in a circuit's buffer.
        """
        key = circuit.key
        # circuit.key is (address, priority), which uniquely identifies a Channel
        # Access 'VirtualCircuit'. We have to open one socket per VirtualCircuit.
        if key not in self.tcp_socks:
            self.tcp_socks[key] = await socket.create_connection(circuit.address)
        bytes_received = await self.tcp_socks[key].recv(4096)
        circuit.recv(bytes_received)

    async def get_event(self, circuit):
        """
        Get a curio.Event that we will 'set' when we process the next command.

        This is a signaling mechanism for notifying all corountines awaiting an
        incoming command that a new one (maybe the one they are looking for,
        maybe not) has been processed.
        """
        try:
            # Some other consumer has already asked for the next command.
            # Don't ask again (yet); just wait for the first request to
            # process.
            return self.events[circuit.key]
        except KeyError:
            # No other consumers have asked for the next command. Ask, return
            # an Event that will be set when the command is processed, and
            # stash the Event in case any other consumers ask.
            event = curio.Event()
            self.events[circuit.key] = event
            task = await curio.spawn(self.next_command(circuit))
            return event

    async def next_command(self, circuit):
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
            command = circuit.next_command()
            if isinstance(command, ca.NEED_DATA):
                await self.recv(circuit)
                continue
            if isinstance(command, ca.ReadNotifyResponse):
                chan = self.ioids[command.ioid]
                chan.last_reading = command.values
            elif isinstance(command, ca.EventAddResponse):
                chan = self.subscriptionids[command.subscriptionid]
                chan.subscriptionids.add(command.subscriptionid)
            elif isinstance(command, ca.EventCancelResponse):
                chan.subscriptionids.remove(command.subscriptionid)
            event = self.events.pop(circuit.key)
            await event.set()

            return command

    async def register(self):
        # Send data
        command = self.broadcaster.register()
        bytes_to_send = self.broadcaster.send(command)
        await self.udp_sock.sendto(bytes_to_send, ('', self.repeater_port))
        # Receive response
        bytes_received, address = await self.udp_sock.recvfrom(4096)
        self.broadcaster.recv(bytes_received, address)
        command = self.broadcaster.next_command()
        assert type(command) is ca.RepeaterConfirmResponse

    async def search(self, name):
        "Generate, process, and the transport a search request."
        # Discard any old search result for this name.
        self.search_results.pop(name, None)
        ver_command, search_command = self.broadcaster.search(name)
        # Stash the search ID for recognizes the SearchResponse later.
        self.unanswered_searches[search_command.cid] = name
        bytes_to_send = self.broadcaster.send(ver_command, search_command)
        await self.udp_sock.sendto(bytes_to_send, ('', self.server_port))

    async def wait_for_search(self, name):
        "Wait for search response."
        while True:
            if name in self.search_results:
                return
            await self.next_broadcast_command()

    async def next_broadcast_command(self):
        "Receive and process and next command broadcasted over UDP."
        while True:
            command = self.broadcaster.next_command()
            if isinstance(command, ca.NEED_DATA):
                bytes_received, address = await self.udp_sock.recvfrom(4096)
                self.broadcaster.recv(bytes_received, address)
                continue
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
            return command

    async def create_channel(self, name, priority=0):
        """
        Asynchronously request a new channel.

        This immediately return a new Channel object which at first is not
        connected. Use its ``wait_for_connection`` method.
        """
        address = self.search_results[name]
        chan = self.hub.new_channel(name, address=address, priority=priority)
        self.channels[chan.cid] = chan

        async def connect():
            if not chan.circuit._state[ca.SERVER] is ca.IDLE:
                await self.send(*chan.version())
                await self.send(*chan.host_name())
                await self.send(*chan.client_name())
            await self.send(*chan.create())

        await connect()
        return Channel(self, chan)



pv1 = "XF:31IDA-OP{Tbl-Ax:X1}Mtr.VAL"
pv2 = "XF:31IDA-OP{Tbl-Ax:X2}Mtr.VAL"

async def main():
    client = Client()
    await client.register()
    # Send out searches to the network without waiting for responses...
    await client.search(pv1)
    await client.search(pv2)
    # ... and then wait for all the responses.
    await client.wait_for_search(pv1)
    await client.wait_for_search(pv2)
    # Send out connection requests without waiting for responses...
    chan1 = await client.create_channel(pv1)
    chan2 = await client.create_channel(pv2)
    # ...and then wait for all the responses.
    await chan1.wait_for_connection()
    await chan2.wait_for_connection()
    await chan1.read()
    print('reading:', chan1.last_reading)
    await chan1.subscribe()
    await curio.sleep(1)
    print('done sleeping')
    print(chan1)
    print(chan1.subscriptionids)
    await chan1.unsubscribe(0)
    # reading = await chan1.read()
    
curio.run(main())


#### STOP HERE FOR NOW ###
sys.exit(0)

try:
    print('Monitoring until Ctrl-C is hit')
    while True:
        recv(chan1.circuit)
        command = chan1.circuit.next_command()
        assert type(command) is ca.EventAddResponse
except KeyboardInterrupt:
    pass


send(chan1.circuit, cancel_req)
recv(chan1.circuit)
command = chan1.circuit.next_command()
assert type(command) is ca.EventAddResponse

send(*chan1.read(data_count=3, data_type=13))
recv(chan1.circuit)
command = chan1.circuit.next_command()
assert type(command) is ca.ReadNotifyResponse
print('VALUES', command.values)
send(*chan1.write((3,)))
recv(chan1.circuit)
command = chan1.circuit.next_command()
assert type(command) is ca.WriteNotifyResponse
time.sleep(2)
send(*chan1.read())
recv(chan1.circuit)
command = chan1.circuit.next_command()
assert type(command) is ca.ReadNotifyResponse
send(*chan1.clear())
recv(chan1.circuit)

for sock in sockets.values():
    sock.close()
