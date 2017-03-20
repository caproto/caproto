import caproto as ca
import curio
from curio import socket
import time
import getpass


SERVER_PORT = 5064


class DisconnectedCircuit(Exception):
    ...


class VirtualCircuit:
    "Wraps a caproto.VirtualCircuit with a curio client."
    def __init__(self, circuit, client):
        self.circuit = circuit  # a caproto.VirtualCircuit
        self.client = client

    async def send(self, *commands):
        """
        Process a command and tranport it over the TCP socket for this circuit.
        """
        print("send....")
        bytes_to_send = self.circuit.send(*commands)
        await self.client.sendall(bytes_to_send)

    async def recv(self):
        """
        Receive bytes over TCP and cache them in this circuit's buffer.
        """
        print('recv....')
        bytes_received = await self.client.recv(4096)
        if not bytes_received:
            raise DisconnectedCircuit()
        self.circuit.recv(bytes_received)

    async def next_command(self):
        """
        Process one incoming command.

        1. Receive data from the socket if a full comannd's worth of bytes are
           not already cached.
        2. Dispatch to caproto.VirtualCircuit.next_command which validates.
        3. Update Channel state if applicable.
        """
        while True:
            command = self.circuit.next_command()
            if isinstance(command, ca.NEED_DATA):
                await self.recv()
                continue
            break
        # TODO Split this off into _process_command.
        # Maybe also split sending into separate func?
        if isinstance(command, ca.CreateChanRequest):
            await self.send(
                ca.VersionResponse(13),
                ca.AccessRightsResponse(cid=command.cid, access_rights=3),
                # TODO Handle sid propertly
                ca.CreateChanResponse(data_type=2, data_count=1,
                                      cid=command.cid, sid=1))
        elif isinstance(command, ca.ReadNotifyRequest):
            chan = self.circuit.channels_sid[command.sid]
            await self.send(chan.read(values=(3.14,), ioid=command.ioid))
        elif isinstance(command, ca.WriteNotifyRequest):
            chan = self.circuit.channels_sid[command.sid]
            await self.send(chan.write(ioid=command.ioid))
        elif isinstance(command, ca.EventAddRequest):
            chan = self.circuit.channels_sid[command.sid]
            await self.send(chan.subscribe((3.14,), command.subscriptionid))
        elif isinstance(command, ca.EventCancelRequest):
            chan = self.circuit.channels_sid[command.sid]
            await self.send(chan.unsubscribe(command.subscriptionid))
        elif isinstance(command, ca.ClearChannelRequest):
            chan = self.circuit.channels_sid[command.sid]
            await self.send(chan.clear())
        #event = self.event
        #self.event = None
        #await event.set()
        #return command
        return command


class Context:
    def __init__(self, host, port, pvdb):
        self.host = host
        self.port = port
        self.pvdb = pvdb
        self.broadcaster = ca.Broadcaster(our_role=ca.SERVER)
        self.broadcaster.log.setLevel('DEBUG')
    
    async def udp_server(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind((self.host, self.port))
        responses = []
        while True:
            responses.clear()
            bytes_received, addr = await sock.recvfrom(1024)
            self.broadcaster.recv(bytes_received, addr)
            while True:
                command = self.broadcaster.next_command()
                if isinstance(command, ca.NEED_DATA):
                    # Respond, and then break to receive the next datagram.
                    bytes_to_send = self.broadcaster.send(*responses)
                    await sock.sendto(bytes_to_send, addr)
                    break
                if isinstance(command, ca.VersionRequest):
                    res = ca.VersionResponse(13)
                    responses.append(res)
                if isinstance(command, ca.SearchRequest):
                    known_pv = command.name.decode() in self.pvdb
                    if (not known_pv) and command.reply == ca.NO_REPLY:
                        responses.clear()
                        break  # Do not send any repsonse to this datagram.
                    ip = _get_my_ip()
                    res = ca.SearchResponse(self.port, ip, command.cid, 13)
                    responses.append(res)

    async def tcp_handler(self, client, addr):
        circuit = VirtualCircuit(ca.VirtualCircuit(ca.SERVER, addr, None), client)
        circuit.circuit.log.setLevel('DEBUG')
        while True:
            try:
                await circuit.next_command()
            except DisconnectedCircuit:
                print('disconnected')
                return

    async def run(self):
        tcp_server = curio.tcp_server('', self.port, self.tcp_handler)
        tcp_task = await curio.spawn(tcp_server)
        udp_task = await curio.spawn(self.udp_server())
        await udp_task.join()
        await tcp_task.join()


def _get_my_ip():
    # Reliably getting the IP is a surprisingly tricky problem solved by this
    # crazy one-liner from http://stackoverflow.com/a/1267524/1221924
    # This uses the synchronous socket API, not the curio one, which we should
    # eventually fix.
    import socket
    try:
        return [l for l in ([ip for ip in socket.gethostbyname_ex(socket.gethostname())[2] if not ip.startswith("127.")][:1], [[(s.connect(('8.8.8.8', 53)), s.getsockname()[0], s.close()) for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]]) if l][0][0]
    except Exception:
        return '127.0.0.1'


if __name__ == '__main__':
    pvdb = ["pi"]
    ctx = Context('0.0.0.0', SERVER_PORT, pvdb)
    curio.run(ctx.run())
