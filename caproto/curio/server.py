import logging
from ..server import AsyncLibraryLayer
import caproto as ca
import curio
from curio import socket
from caproto import find_available_tcp_port

from ..server.common import (VirtualCircuit as _VirtualCircuit,
                             Context as _Context)
logger = logging.getLogger(__name__)


class ServerExit(curio.KernelExit):
    ...


class UniversalQueue(curio.UniversalQueue):
    def put(self, value):
        super().put(value)

    async def async_put(self, value):
        await super().put(value)

    def get(self):
        return super().get()

    async def async_get(self):
        return await super().get()


class CurioAsyncLayer(AsyncLibraryLayer):
    name = 'curio'
    ThreadsafeQueue = UniversalQueue
    library = curio


class VirtualCircuit(_VirtualCircuit):
    "Wraps a caproto.VirtualCircuit with a curio client."
    TaskCancelled = curio.TaskCancelled
    logger = logger

    def __init__(self, circuit, client, context):
        super().__init__(circuit, client, context)
        self.command_queue = curio.Queue()
        self.new_command_condition = curio.Condition()
        self.pending_tasks = curio.TaskGroup()

    async def run(self):
        await self.pending_tasks.spawn(self.command_queue_loop())

    async def _on_disconnect(self):
        """Executed when disconnection detected"""
        await super()._on_disconnect()
        # TODO this may cancel some caputs in progress, need to rethink it
        # await self.pending_tasks.cancel_remaining()

    async def _start_write_task(self, handle_write):
        await self.pending_tasks.spawn(handle_write, ignore_result=True)

    async def _wake_new_command(self):
        async with self.new_command_condition:
            await self.new_command_condition.notify_all()


class Context(_Context):
    CircuitClass = VirtualCircuit
    async_layer = CurioAsyncLayer
    ServerExit = ServerExit
    TaskCancelled = curio.TaskCancelled

    def __init__(self, host, port, pvdb, *, log_level='ERROR'):
        super().__init__(host, port, pvdb, log_level=log_level)
        self.command_bundle_queue = curio.Queue()
        self.subscription_queue = curio.UniversalQueue()

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
        try:
            async with curio.TaskGroup() as g:
                for addr, port in ca.get_server_address_list(self.port):
                    logger.debug('Listening on %s:%d', addr, port)
                    await g.spawn(curio.tcp_server,
                                  addr, port, self.tcp_handler)
                await g.spawn(self.broadcaster_udp_server_loop)
                await g.spawn(self.broadcaster_queue_loop)
                await g.spawn(self.subscription_queue_loop)
                await g.spawn(self.broadcast_beacon_loop)

                async_lib = CurioAsyncLayer()
                for method in self.startup_methods:
                    logger.debug('Calling startup method %r', method)
                    await g.spawn(method, async_lib)
        except curio.TaskGroupError as ex:
            logger.error('Curio server failed: %s', ex.errors)
            for task in ex:
                logger.error('Task %s failed: %s', task, task.exception)
        except curio.TaskCancelled as ex:
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
