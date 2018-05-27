import logging
from ..server import AsyncLibraryLayer
import caproto as ca
import asyncio
import socket
from caproto import find_available_tcp_port

from ..server.common import (VirtualCircuit as _VirtualCircuit,
                             Context as _Context)
logger = logging.getLogger(__name__)


class ServerExit(Exception):
    ...


class AsyncioAsyncLayer(AsyncLibraryLayer):
    name = 'asyncio'
    ThreadsafeQueue = asyncio.Queue
    library = asyncio


class VirtualCircuit(_VirtualCircuit):
    "Wraps a caproto.VirtualCircuit with a curio client."
    TaskCancelled = asyncio.CancelledError
    logger = logger

    def __init__(self, circuit, client, context, *, loop=None):
        super().__init__(circuit, client, context)
        self.command_queue = asyncio.Queue()
        self.new_command_condition = asyncio.Condition()
        if loop is None:
            loop = asyncio.get_event_loop()
        self.loop = loop

    async def run(self):
        await self.loop.create_task(self.command_queue_loop())

    async def _start_write_task(self, handle_write):
        await self.loop.create_task(handle_write())

    async def _wake_new_command(self):
        async with self.new_command_condition:
            self.new_command_condition.notify_all()


class Context(_Context):
    CircuitClass = VirtualCircuit
    async_layer = AsyncioAsyncLayer
    ServerExit = ServerExit
    TaskCancelled = asyncio.CancelledError

    def __init__(self, host, port, pvdb, *, log_level='ERROR', loop=None):
        super().__init__(host, port, pvdb, log_level=log_level)
        self.command_bundle_queue = asyncio.Queue()
        self.subscription_queue = asyncio.Queue()
        if loop is None:
            loop = asyncio.get_event_loop()
        self.loop = loop

    async def broadcaster_udp_server_loop(self):
        self.udp_sock = ca.bcast_socket(socket)
        try:
            self.udp_sock.bind((self.host, ca.EPICS_CA1_PORT))
        except Exception:
            logger.exception('[server] udp bind failure!')
            raise
        await self._core_broadcaster_loop()

    async def run(self):
        'Start the server'
        for addr, port in ca.get_server_address_list(self.port):
            logger.debug('Listening on %s:%d', addr, port)
            # self.loop.create_task(tcp_server,
            #                       addr, port, self.tcp_handler)
        self.loop.create_task(self.broadcaster_udp_server_loop)
        self.loop.create_task(self.broadcaster_queue_loop)
        self.loop.create_task(self.subscription_queue_loop)
        self.loop.create_task(self.broadcast_beacon_loop)

        async_lib = AsyncioAsyncLayer()
        for method in self.startup_methods:
            logger.debug('Calling startup method %r', method)
            self.loop.create_task(method, async_lib)

        try:
            self.loop.run_forever()
        except self.TaskCancelled as ex:
            logger.info('Server task cancelled; exiting')
            raise ServerExit() from ex


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
