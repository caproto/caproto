import logging
from ..server import AsyncLibraryLayer
import caproto as ca
import asyncio
import socket
from caproto import find_available_tcp_port

from ..server.common import (VirtualCircuit as _VirtualCircuit,
                             Context as _Context)
from .._utils import bcast_socket


logger = logging.getLogger(__name__)


class ServerExit(Exception):
    ...


class AsyncioAsyncLayer(AsyncLibraryLayer):
    name = 'asyncio'
    ThreadsafeQueue = None
    library = asyncio


class VirtualCircuit(_VirtualCircuit):
    "Wraps a caproto.VirtualCircuit with a curio client."
    TaskCancelled = asyncio.CancelledError
    logger = logger

    def __init__(self, circuit, client, context, *, loop=None):
        if loop is None:
            loop = asyncio.get_event_loop()
        self.loop = loop

        class SockWrapper:
            def __init__(self, loop, client):
                self.loop = loop
                self.client = client

            async def recv(self, nbytes):
                return (await self.loop.sock_recv(self.client, 4096))

        self._raw_client = client
        super().__init__(circuit, SockWrapper(loop, client), context)
        self.command_queue = asyncio.Queue()
        self.new_command_condition = asyncio.Condition()
        self._cq_task = None

    async def send(self, *commands):
        if self.connected:
            buffers_to_send = self.circuit.send(*commands)
            await self.loop.sock_sendall(self._raw_client,
                                         b''.join(buffers_to_send))

    async def run(self):
        self._cq_task = self.loop.create_task(self.command_queue_loop())

    async def _start_write_task(self, handle_write):
        self.loop.create_task(handle_write())

    async def _wake_new_command(self):
        async with self.new_command_condition:
            self.new_command_condition.notify_all()

    async def _on_disconnect(self):
        await super()._on_disconnect()
        self._raw_client.close()
        if self._cq_task is not None:
            self._cq_task.cancel()


class Context(_Context):
    CircuitClass = VirtualCircuit
    async_layer = AsyncioAsyncLayer
    ServerExit = ServerExit
    TaskCancelled = asyncio.CancelledError
    logger = logger

    def __init__(self, host, port, pvdb, *, log_level='ERROR', loop=None):
        super().__init__(host, port, pvdb, log_level=log_level)
        self.command_bundle_queue = asyncio.Queue()
        self.subscription_queue = asyncio.Queue()
        if loop is None:
            loop = asyncio.get_event_loop()
        self.loop = loop
        self.udp_sock = None
        self._server_tasks = []

    async def server_accept_loop(self, addr, port):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        logger.debug('Listening on %s:%d', addr, port)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.setblocking(False)
        s.bind((addr, port))
        s.listen()

        try:
            while True:
                client_sock, addr = await self.loop.sock_accept(s)
                tsk = self.loop.create_task(self.tcp_handler(client_sock,
                                                             addr))
                self._server_tasks.append(tsk)
        finally:
            s.shutdown(socket.SHUT_WR)
            s.close()
            s = None

    async def run(self):
        'Start the server'
        tasks = []
        for addr, port in ca.get_server_address_list(self.port):
            logger.debug('Listening on %s:%d', addr, port)
            tasks.append(self.loop.create_task(self.server_accept_loop(addr, port)))
            # self.loop.create_task(tcp_server,
            #                       addr, port, self.tcp_handler)

        class BcastLoop(asyncio.Protocol):
            parent = self
            loop = self.loop

            def connection_made(self, transport):
                self.transport = transport

            def datagram_received(self, data, addr):
                self.loop.create_task(self.parent._broadcaster_recv_datagram(
                                      data, addr))

        class TransportWrapper:
            def __init__(self, transport):
                self.transport = transport

            async def sendto(self, bytes_to_send, addr_port):
                self.transport.sendto(bytes_to_send, addr_port)

            def close(self):
                self.transport.close()

        udp_sock = bcast_socket()
        try:
            udp_sock.bind((self.host, ca.EPICS_CA1_PORT))
        except Exception:
            logger.exception('[server] udp bind failure!')
            raise

        transport, self.p = await self.loop.create_datagram_endpoint(
            BcastLoop, sock=udp_sock)
        self.udp_sock = TransportWrapper(transport)

        tasks.append(self.loop.create_task(self.broadcaster_queue_loop()))
        tasks.append(self.loop.create_task(self.subscription_queue_loop()))
        tasks.append(self.loop.create_task(self.broadcast_beacon_loop()))

        async_lib = AsyncioAsyncLayer()
        for method in self.startup_methods:
            logger.debug('Calling startup method %r', method)
            tasks.append(self.loop.create_task(method(async_lib)))

        try:
            await asyncio.gather(*tasks)
        except Exception as ex:
            self.udp_sock.close()
            raise
        finally:
            for t in tasks + self._server_tasks:
                t.cancel()


async def start_server(pvdb, log_level='DEBUG', *, bind_addr='0.0.0.0'):
    '''Start a curio server with a given PV database'''
    logger.setLevel(log_level)
    ctx = Context(bind_addr, find_available_tcp_port(), pvdb,
                  log_level=log_level)
    logger.info('Server starting up on %s:%d', ctx.host, ctx.port)
    try:
        return await ctx.run()
    except ServerExit:
        print('ServerExit caught; exiting')
