import sys
import caproto as ca
import time
from curio import socket
import curio
import getpass


REPEATER_PORT = 5065
SERVER_PORT = 5064


class Channel:
    "Wrap caproto.ClientChannel, adding async methods."
    def __init__(self, client, channel):
        self.client = client
        self.channel = channel
        self.last_reading = None
        self.stale = False

    async def wait_for_connection(self):
        while not self.channel._state[ca.CLIENT] == ca.CONNECTED:
            await self.client.next_command(self.channel.circuit)

    async def read(self, *args, **kwargs):
        self.client.send(*self.channel.read(*args, **kwargs))
        while self.stale:
            await self.client.next_command(self.channel.cricuit)
        return self.reading


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

    async def send(self, circuit, command):
        """
        Process a command and tranport it over the TCP socket for this circuit.
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
        Receive bytes over TCP and cache them in the circuit's buffer.
        """
        key = circuit.key
        # circuit.key is (address, priority), which uniquely identifies a Channel
        # Access 'VirtualCircuit'. We have to open one socket per VirtualCircuit.
        if key not in self.tcp_socks:
            self.tcp_socks[key] = await socket.create_connection(circuit.address)
        bytes_received = await self.tcp_socks[circuit.key].recv(4096)
        circuit.recv(bytes_received)

    async def next_command(self, circuit):
        while True:
            command = circuit.next_command()
            if isinstance(command, ca.NEED_DATA):
                await self.recv(circuit)
                continue
            if isinstance(command, ca.ReadNotifyResponse):
                self.channels[command.cid].last_reading = command.values
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
        "Wait for search result."
        while True:
            print('SEARCH_RESULTS', self.search_results)
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
        address = self.search_results[name]
        chan = self.hub.new_channel(name, address=address, priority=priority)
        self.channels[chan.cid] = chan
        async def connect():
            await self.send(*chan.version())
            await self.send(*chan.host_name())
            await self.send(*chan.client_name())
            await self.send(*chan.create())
            await self.recv(chan.circuit)

        task = await curio.spawn(connect())
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
    print('about to wait')
    await client.wait_for_search(pv1)
    await client.wait_for_search(pv2)
    print('done waiting')
    # Send out connection requests without waiting for responses...
    chan1 = await client.create_channel(pv1)
    chan2 = await client.create_channel(pv2)
    # ...and then wait for all the responses.
    await chan1.wait_for_connection()
    await chan2.wait_for_connection()
    await chan1.read()
    print(chan1.reading)
    
curio.run(main())

# Create an Channel. This implicitly creates a VirtualCircuit too.


#### STOP HERE FOR NOW ###
sys.exit(0)

_, event_req = chan1.subscribe()

send(chan1.circuit, event_req)
subscriptionid = event_req.subscriptionid
recv(chan1.circuit)
command = chan1.circuit.next_command()
assert type(command) is ca.EventAddResponse

try:
    print('Monitoring until Ctrl-C is hit')
    while True:
        recv(chan1.circuit)
        command = chan1.circuit.next_command()
        assert type(command) is ca.EventAddResponse
except KeyboardInterrupt:
    pass


_, cancel_req = chan1.unsubscribe(subscriptionid)

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
