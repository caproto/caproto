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
import asyncio
import logging
import socket
import time

import caproto


logger = logging.getLogger('repeater')


class RepeaterAlreadyRunning(RuntimeError):
    ...


class ProxyDatagramProtocol(asyncio.DatagramProtocol):

    def __init__(self):
        self.remotes = {}

        self.broadcaster = caproto.Broadcaster(our_role=caproto.SERVER)
        super().__init__()
        self._last_check = time.time()

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        commands = self.broadcaster.recv(data, addr)
        self.broadcaster.process_commands(commands)
        self._commands_received(addr, commands)

    def _commands_received(self, addr, commands):
        if not commands:
            return

        # TODO thoughts on this? far from ideal
        data = b''.join(bytes(command) for command in commands)

        for command in commands:
            if isinstance(command, caproto.RepeaterRegisterRequest):
                if addr in self.remotes:
                    # hack: re-sending registration can be necessary for
                    # caproto clients
                    remote = self.remotes[addr]
                    if hasattr(remote, 'transport'):
                        remote.connection_made(remote.transport)
                    return
                loop = asyncio.get_event_loop()
                self._check_clients()
                self.remotes[addr] = RemoteDatagramProtocol(self, addr, data)
                coro = loop.create_datagram_endpoint(
                    lambda: self.remotes[addr], remote_addr=addr)
                # as in the epics-base repeater, check for dead clients when a
                # new one connects
                asyncio.ensure_future(coro)

        if addr in self.remotes:
            if hasattr(self.remotes[addr], 'transport'):
                self.remotes[addr].transport.sendto(data)
            return

    def _check_clients(self):
        if (time.time() - self._last_check) < 5:
            # Don't check for stale clients too often
            return
        self._last_check = time.time()

        no_op = bytes(caproto.VersionRequest(priority=0, version=0).header)
        for addr, remote in list(self.remotes.items()):
            transport = getattr(remote, 'transport', None)
            if not transport:
                logger.debug('Removing client %r', self.addr)
                del self.remotes[addr]
            else:
                remote.transport.sendto(no_op)
        logger.debug('Active clients: %d', len(self.remotes))


class RemoteDatagramProtocol(asyncio.DatagramProtocol):

    def __init__(self, proxy, addr, data):
        self.proxy = proxy
        self.addr = addr
        self.data = data
        logger.debug('Received registration request from %r', self.addr)
        super().__init__()

    def connection_made(self, transport):
        self.transport = transport
        confirmation = caproto.RepeaterConfirmResponse(self.addr[0])
        confirmation_bytes = self.proxy.broadcaster.send(confirmation)
        self.transport.sendto(confirmation_bytes)
        logger.debug('Sent registration confirmation to %r', self.addr)

    def datagram_received(self, data, sender_addr):
        self.proxy.transport.sendto(data, self.addr)

    def connection_lost(self, exc):
        super().connection_lost(exc)
        logger.debug('Lost connection to %r', self.addr)
        self.proxy.remotes.pop(self.addr)

    def error_received(self, exc):
        super().error_received(exc)
        logger.debug('Lost connection to %r (%s)', self.addr, exc)
        self.proxy.remotes.pop(self.addr)


async def start_datagram_proxy(bind, port):
    loop = asyncio.get_event_loop()
    protocol = ProxyDatagramProtocol()
    try:
        return await loop.create_datagram_endpoint(
            lambda: protocol, local_addr=(bind, port))
    except OSError as ex:
        if 'Address already in use' in str(ex):
            raise RepeaterAlreadyRunning(str(ex))
        else:
            raise


def check_for_running_repeater(addr):
    '''If a repeater is already running, this raises RepeaterAlreadyRunning

    Parameters
    ----------
    addr : (ip, port)
    '''
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(addr)
    except OSError as ex:
        if 'Address already in use' in str(ex):
            raise RepeaterAlreadyRunning(str(ex))
        else:
            raise


def run(host='0.0.0.0'):
    loop = asyncio.get_event_loop()
    port = caproto.get_environment_variables()['EPICS_CA_REPEATER_PORT']
    addr = (host, port)
    logger.debug('Checking for another repeater')

    # NOTE: This check is performed separately because
    # loop.create_datagram_endpoint is not consistent on different platforms
    # with tregard to addresses already in use. On Darwin, OSError is raised,
    # whereas on Linux it is not.
    try:
        check_for_running_repeater(addr)
    except RepeaterAlreadyRunning:
        logger.error('Another repeater is already running; exiting')
        return

    logger.info(f'Starting datagram proxy on {addr}...')
    coro = start_datagram_proxy(*addr)

    try:
        transport, _ = loop.run_until_complete(coro)
    except RepeaterAlreadyRunning as ex:
        logger.info('Another repeater is already running; exiting')
        return

    logger.info("Datagram proxy is running.")
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    logger.info("Closing transport...")
    transport.close()
    loop.close()
