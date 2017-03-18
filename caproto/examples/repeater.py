"""UDP proxy server."""
# Based on https://gist.github.com/vxgmichel/b2cf8536363275e735c231caef35a5df
import socket
import asyncio
import caproto


class ProxyDatagramProtocol(asyncio.DatagramProtocol):

    def __init__(self):
        self.host = socket.gethostbyname(socket.gethostname())
        self.remotes = {}
        self.broadcaster = caproto.Broadcaster(our_role=caproto.SERVER)
        super().__init__()

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        self.broadcaster.recv(data, addr)
        command = self.broadcaster.next_command()
        print(command, addr)
        if addr in self.remotes:
            self.remotes[addr].transport.sendto(data)
            return
        loop = asyncio.get_event_loop()
        self.remotes[addr] = RemoteDatagramProtocol(self, addr, data)
        coro = loop.create_datagram_endpoint(
            lambda: self.remotes[addr], remote_addr=addr)
        asyncio.ensure_future(coro)


class RemoteDatagramProtocol(asyncio.DatagramProtocol):

    def __init__(self, proxy, addr, data):
        self.proxy = proxy
        self.addr = addr
        print('new remote with addr', addr)
        self.data = data
        super().__init__()

    def connection_made(self, transport):
        self.transport = transport
        confirmation = caproto.RepeaterConfirmResponse(self.addr[0])
        confirmation_bytes = self.proxy.broadcaster.send(confirmation)
        self.transport.sendto(confirmation_bytes)
        print('sent confirmation to', self.addr)

    def datagram_received(self, data, sender_addr):
        self.proxy.transport.sendto(data, self.addr)

    def connection_lost(self, exc):
        self.proxy.remotes.pop(self.attr)


async def start_datagram_proxy(bind, port):
    loop = asyncio.get_event_loop()
    protocol = ProxyDatagramProtocol()
    return await loop.create_datagram_endpoint(
        lambda: protocol, local_addr=(bind, port))


def main(bind='0.0.0.0', port=5065):
    print('hi')
    loop = asyncio.get_event_loop()
    print("Starting datagram proxy...")
    coro = start_datagram_proxy(bind, port)
    transport, _ = loop.run_until_complete(coro)
    print("Datagram proxy is running...")
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    print("Closing transport...")
    transport.close()
    loop.close()

if __name__ == '__main__':
    main()
