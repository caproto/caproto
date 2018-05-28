import logging
from ..server import AsyncLibraryLayer
import caproto as ca
import trio
from trio import socket
from caproto import find_available_tcp_port

from ..server.common import (VirtualCircuit as _VirtualCircuit,
                             Context as _Context)
logger = logging.getLogger(__name__)


class ServerExit(Exception):
    ...


def _universal_queue(portal, max_len=1000):
    class UniversalQueue:
        def __init__(self):
            self.queue = trio.Queue(max_len)
            self.portal = portal

        def put(self, value):
            self.portal.run(self.queue.put, value)

        async def async_put(self, value):
            await self.queue.put(value)

        def get(self):
            return self.portal.run(self.queue.get)

        async def async_get(self):
            return await self.queue.get()

    return UniversalQueue


class TrioAsyncLayer(AsyncLibraryLayer):
    def __init__(self):
        self.portal = trio.BlockingTrioPortal()
        self.ThreadsafeQueue = _universal_queue(self.portal)

    name = 'trio'
    ThreadsafeQueue = None
    library = trio


class VirtualCircuit(_VirtualCircuit):
    "Wraps a caproto.VirtualCircuit with a trio client."
    TaskCancelled = trio.Cancelled
    logger = logger

    def __init__(self, circuit, client, context):
        super().__init__(circuit, client, context)
        self.nursery = context.nursery
        self.command_queue = trio.Queue(1000)
        self.new_command_condition = trio.Condition()

    async def run(self):
        await self.nursery.start(self.command_queue_loop)

    async def command_queue_loop(self, task_status):
        task_status.started()
        await super().command_queue_loop()

    async def _on_disconnect(self):
        """Executed when disconnection detected"""
        await super()._on_disconnect()
        print('client connection closed')
        self.client.close()

    async def _start_write_task(self, handle_write):
        self.nursery.start_soon(handle_write)

    async def _wake_new_command(self):
        async with self.new_command_condition:
            self.new_command_condition.notify_all()


class Context(_Context):
    CircuitClass = VirtualCircuit
    async_layer = TrioAsyncLayer
    ServerExit = ServerExit
    TaskCancelled = trio.Cancelled

    def __init__(self, host, port, pvdb, *, log_level='ERROR'):
        super().__init__(host, port, pvdb, log_level=log_level)
        self.nursery = None
        self.command_bundle_queue = trio.Queue(1000)
        self.subscription_queue = trio.Queue(1000)

    async def broadcaster_udp_server_loop(self, task_status):
        self.udp_sock = ca.bcast_socket(socket)
        try:
            await self.udp_sock.bind((self.host, ca.EPICS_CA1_PORT))
        except Exception:
            logger.exception('[server] udp bind failure!')
            raise

        task_status.started()

        await self._core_broadcaster_loop()

    async def broadcaster_queue_loop(self, task_status):
        task_status.started()
        await super().broadcaster_queue_loop()

    async def subscription_queue_loop(self, task_status):
        task_status.started()
        await super().subscription_queue_loop()

    async def broadcast_beacon_loop(self, task_status):
        task_status.started()
        await super().broadcast_beacon_loop()

    async def server_accept_loop(self, addr, port, *, task_status):
        with trio.socket.socket() as listen_sock:
            logger.debug('Listening on %s:%d', addr, port)
            await listen_sock.bind((addr, port))
            listen_sock.listen()

            task_status.started()

            while True:
                client_sock, addr = await listen_sock.accept()
                self.nursery.start_soon(self.tcp_handler, client_sock, addr)

    async def run(self):
        'Start the server'
        try:
            async with trio.open_nursery() as self.nursery:
                for addr, port in ca.get_server_address_list(self.port):
                    await self.nursery.start(self.server_accept_loop,
                                             addr, port)
                await self.nursery.start(self.broadcaster_udp_server_loop)
                await self.nursery.start(self.broadcaster_queue_loop)
                await self.nursery.start(self.subscription_queue_loop)
                await self.nursery.start(self.broadcast_beacon_loop)

                async_lib = TrioAsyncLayer()
                for method in self.startup_methods:
                    logger.debug('Calling startup method %r', method)

                    async def startup(task_status):
                        task_status.started()
                        await method(async_lib)

                    await self.nursery.start(startup)
        except trio.Cancelled:
            logger.info('Server task cancelled')

    async def stop(self):
        'Stop the server'
        nursery = self.nursery
        if nursery is None:
            return

        nursery.cancel_scope.cancel()


async def start_server(pvdb, log_level='DEBUG', *, bind_addr='0.0.0.0'):
    '''Start a trio server with a given PV database'''
    logger.setLevel(log_level)
    ctx = Context(bind_addr, find_available_tcp_port(), pvdb,
                  log_level=log_level)
    logger.info('Server starting up on %s:%d', ctx.host, ctx.port)
    try:
        return await ctx.run()
    except ServerExit:
        print('ServerExit caught; exiting')
