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
        self.beacon_sock = ca.bcast_socket(socket)

    async def broadcaster_udp_server_loop(self):
        for interface in self.interfaces:
            udp_sock = ca.bcast_socket(socket)
            try:
                udp_sock.bind((interface, ca.EPICS_CA1_PORT))
            except Exception:
                self.log.exception('[server] udp bind failure on interface %r',
                                   interface)
                raise
        self.udp_socks[interface] = udp_sock

        async with curio.TaskGroup() as g:
            for udp_sock in self.udp_socks.values():
                self.log.debug('Broadcasting on %s:%d', interface,
                               ca.EPICS_CA1_PORT)
                await g.spawn(self._core_broadcaster_loop, udp_sock)

    async def run(self, *, log_pv_names=False):
        'Start the server'
        self.log.info('Server starting up...')
        try:
            # TODO Should this interface be configurable?
            self.beacon_sock.bind(('0.0.0.0', 0))
            # Find a random port number that is free on all self.interfaces,
            # and get a bound TCP socket with that port number on each
            # interface.
            tcp_sockets = {}  # maps interface to bound socket
            stashed_ex = None
            for port in ca.random_ports(100):
                try:
                    for interface in self.interfaces:
                        s = curio.network.tcp_server_socket(interface, port)
                        tcp_sockets[interface] = s
                except IOError as ex:
                    stashed_ex = ex
                    for s in tcp_sockets.values():
                        s.close()
                    tcp_sockets.clear()
                else:
                    break
            else:
                raise RuntimeError('No available ports and/or bind failed') from stashed_ex
            self.port = port
            async with curio.TaskGroup() as g:
                for interface, sock in tcp_sockets.items():
                    self.log.debug('Listening on %s:%d', interface, port)
                    # Use run_server instead of tcp_server so we can hand in a
                    # socket that is already bound, avoiding a race between the
                    # moment we check for port availability and the moment the
                    # TCP server binds.
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
