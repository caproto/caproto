# Channel Access Repeater
#
# The CA Repeater is basically a UDP proxy server. Its only role is to forward
# server beacons (a.k.a RsrvIsUp commands) to all clients on a host. It exists
# to cope with older system that do not broadcast correctly, failing to fan out
# the message to all clients reliably.

# Operation:
# 1. Try to bind to 0.0.0.0 on the CA REPEATER PORT. This may be set by the
#    environment variable EPICS_CA_REPEATER_PORT. The default is 5065.
# 2. If binding fails, assume a CA Repeater is already running. Exit.
# 3. When a UDP datagram is received from an unknown port:
#    - Check that the source host is localhost. If it is not, ignore it.
#    - The datagram data may be a RegisterRepeaterRequest (recent versions of
#      Channel Access) or blank (old versions of Channel Access).
#    - Stash the source port number.
#    - Send a RepeaterConfirmResponse to that source port.
#    - Send an empty datagram to any other ports we have stashed.
#    - Forward all subsequent messages to all ports we know about.


# This implementation owes something to a StackOverflow-linked gist, which
# provides a basic asyncio UDP proxy server.
# https://gist.github.com/vxgmichel/b2cf8536363275e735c231caef35a5df
import os
import socket
import asyncio
import caproto
import caproto as ca


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
        while True:
            command = self.broadcaster.next_command()
            if command is ca.NEED_DATA:
                break
            if isinstance(command,  ca.RepeaterRegisterRequest):
                loop = asyncio.get_event_loop()
                self.remotes[addr] = RemoteDatagramProtocol(self, addr, data)
                coro = loop.create_datagram_endpoint(
                    lambda: self.remotes[addr], remote_addr=addr)
                asyncio.ensure_future(coro)
            else:
                if addr in self.remotes:
                    if hasattr(self.remotes[addr], 'transport'):
                        self.remotes[addr].transport.sendto(data)
                    return


class RemoteDatagramProtocol(asyncio.DatagramProtocol):

    def __init__(self, proxy, addr, data):
        self.proxy = proxy
        self.addr = addr
        self.data = data
        super().__init__()

    def connection_made(self, transport):
        self.transport = transport
        confirmation = caproto.RepeaterConfirmResponse(self.addr[0])
        confirmation_bytes = self.proxy.broadcaster.send(confirmation)
        self.transport.sendto(confirmation_bytes)

    def datagram_received(self, data, sender_addr):
        self.proxy.transport.sendto(data, self.addr)

    def connection_lost(self, exc):
        self.proxy.remotes.pop(self.attr)


async def start_datagram_proxy(bind, port):
    loop = asyncio.get_event_loop()
    protocol = ProxyDatagramProtocol()
    return await loop.create_datagram_endpoint(
        lambda: protocol, local_addr=(bind, port))


def main():
    import logging
    logging.getLogger('caproto').setLevel(logging.INFO)
    loop = asyncio.get_event_loop()
    addr = ('0.0.0.0', os.environ.get('EPICS_CA_REPEATER_PORT', 5065))
    print("Starting datagram proxy on {}...".format(addr))
    coro = start_datagram_proxy(*addr)
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
