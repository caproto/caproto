import caproto as ca
import curio
from curio import socket
import time
import getpass


SERVER_PORT = 5064


class Context:
    def __init__(self, host, port, pvdb):
        self.host = host
        self.port = port
        self.pvdb = pvdb
        self.broadcaster = ca.Broadcaster(our_role=ca.SERVER)
        self.hub = ca.Hub(our_role=ca.SERVER)
        self.broadcaster.log.setLevel('DEBUG')
        self.hub.log.setLevel('DEBUG')
    
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
                    ip = await socket.gethostname()
                    res = ca.SearchResponse(self.port, ip,
                                            1, 13)
                    responses.append(res)

    async def tcp_handler(self, client, addr):
        circuit = self.hub.new_circuit(addr, None)


        bytes_received = await client.recv(4096)
        circuit.recv(bytes_received)
        # TODO Do not assume that all handshake bytes come in at once.
        circuit.next_command()
        circuit.next_command()
        circuit.next_command()
        circuit.next_command()
        bytes_to_send = circuit.send(
            ca.VersionResponse(13),
            ca.AccessRightsResponse(cid=1, access_rights=3),
            ca.CreateChanResponse(data_type=2, data_count=1, cid=1, sid=1))
        await client.sendall(bytes_to_send)
        while True:
            data = await client.recv(4096)
            if not data:
                break
            await client.sendall(data)

    async def run(self):
        tcp_server = curio.tcp_server('', self.port, self.tcp_handler)
        tcp_task = await curio.spawn(tcp_server)
        udp_task = await curio.spawn(self.udp_server())
        await udp_task.join()
        await tcp_task.join()


if __name__ == '__main__':
    pvdb = ["asdf"]
    ctx = Context('0.0.0.0', SERVER_PORT, pvdb)
    curio.run(ctx.run())


class VirtualCircuit:
    def __init__(self, circuit):
        self.circuit = circuit  # a caproto.VirtualCircuit

def send(circuit, command):
    bytes_to_send = circuit.send(command)
    connection.sendall(bytes_to_send)

def recv(circuit):
    bytes_received = connection.recv(4096)
    circuit.recv(bytes_received)
    commands = []
    while True:
        command = circuit.next_command()
        if type(command) is ca.NEED_DATA:
            break
        commands.append(command)
    return commands

