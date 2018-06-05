import functools
from ..server import AsyncLibraryLayer
import caproto as ca
import curio
import curio.network
from curio import socket

from ..server.common import (VirtualCircuit as _VirtualCircuit,
                             Context as _Context)


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

    def __init__(self, pvdb, interfaces=None):
        super().__init__(pvdb, interfaces)
        self.command_bundle_queue = curio.Queue()
        self.subscription_queue = curio.UniversalQueue()

    async def broadcaster_udp_server_loop(self):
        for interface in self.interfaces:
            udp_sock = ca.bcast_socket(socket)
            try:
                udp_sock.bind((interface, ca.EPICS_CA1_PORT))
            except Exception:
                self.log.exception('UDP bind failure on interface %r',
                                   interface)
                raise
            self.udp_socks[interface] = udp_sock

        async with curio.TaskGroup() as g:
            for interface, udp_sock in self.udp_socks.items():
                self.log.debug('Broadcasting on %s:%d', interface,
                               ca.EPICS_CA1_PORT)
                await g.spawn(self._core_broadcaster_loop, udp_sock)

    async def run(self, *, log_pv_names=False):
        'Start the server'
        self.log.info('Server starting up...')
        try:
            for address in ca.get_beacon_address_list():
                sock = ca.bcast_socket(socket)
                await sock.connect(address)
                interface, _ = sock.getsockname()
                self.beacon_socks[address] = (interface, sock)
            port, tcp_sockets = self._bind_tcp_sockets_with_consistent_port_number(
                curio.network.tcp_server_socket)
            self.port = port
            async with curio.TaskGroup() as g:
                for interface, sock in tcp_sockets.items():
                    # Use run_server instead of tcp_server so we can hand in a
                    # socket that is already bound, avoiding a race between the
                    # moment we check for port availability and the moment the
                    # TCP server binds.
                    self.log.info("Listening on %s:%d", interface, self.port)
                    await g.spawn(curio.network.run_server,
                                  sock, self.tcp_handler)
                await g.spawn(self.broadcaster_udp_server_loop)
                await g.spawn(self.broadcaster_queue_loop)
                await g.spawn(self.subscription_queue_loop)
                await g.spawn(self.broadcast_beacon_loop)

                async_lib = CurioAsyncLayer()
                for name, method in self.startup_methods.items():
                    self.log.debug('Calling startup method %r', name)
                    await g.spawn(method, async_lib)
                self.log.info('Server startup complete.')
                if log_pv_names:
                    self.log.info('PVs available:\n%s', '\n'.join(self.pvdb))
        except curio.TaskGroupError as ex:
            self.log.exception('Curio server failed')
            for task in ex:
                self.log.error('Task %s failed: %s', task, task.exception)
        except curio.TaskCancelled as ex:
            self.log.info('Server task cancelled. Must shut down.')
            raise ServerExit() from ex
        finally:
            self.log.info('Server exiting....')


async def start_server(pvdb, *, interfaces=None, log_pv_names=False):
    '''Start a curio server with a given PV database'''
    ctx = Context(pvdb, interfaces)
    try:
        return await ctx.run(log_pv_names=log_pv_names)
    except ServerExit:
        pass


def run(pvdb, *, interfaces=None, log_pv_names=False):
    """
    A synchronous function that runs server, catches KeyboardInterrupt at exit.
    """
    try:
        return curio.run(
            functools.partial(
                start_server,
                pvdb,
                interfaces=interfaces,
                log_pv_names=log_pv_names))
    except KeyboardInterrupt:
        return
