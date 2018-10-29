import functools
import threading

import caproto as ca
import curio
import curio.network
from curio import socket

from ..server import AsyncLibraryLayer
from ..server.common import (VirtualCircuit as _VirtualCircuit,
                             Context as _Context)


class ServerExit(curio.KernelExit):
    ...


class Event(curio.Event):
    async def wait(self, timeout=None):
        if timeout is not None:
            async with curio.ignore_after(timeout):
                await super().wait()
                return True
            return False
        else:
            await super().wait()
            return True


class UniversalQueue(curio.UniversalQueue):
    def put(self, value):
        super().put(value)

    async def async_put(self, value):
        await super().put(value)

    def get(self):
        return super().get()

    async def async_get(self):
        return await super().get()


class QueueFull(Exception):
    ...


# Curio queues just block if they are full. We want one that raises.
class QueueWithFullError(curio.Queue):
    async def put(self, item):
        if self.full():
            raise QueueFull
        await super().put(item)


class CurioAsyncLayer(AsyncLibraryLayer):
    name = 'curio'
    ThreadsafeQueue = UniversalQueue
    library = curio


class VirtualCircuit(_VirtualCircuit):
    "Wraps a caproto.VirtualCircuit with a curio client."
    TaskCancelled = curio.TaskCancelled

    def __init__(self, circuit, client, context):
        super().__init__(circuit, client, context)
        self.QueueFull = QueueFull
        self.command_queue = QueueWithFullError(ca.MAX_COMMAND_BACKLOG)
        self.new_command_condition = curio.Condition()
        self.pending_tasks = curio.TaskGroup()
        self.events_on = curio.Event()
        self.subscription_queue = QueueWithFullError(
            ca.MAX_TOTAL_SUBSCRIPTION_BACKLOG)
        self.write_event = Event()

    async def run(self):
        await self.pending_tasks.spawn(self.command_queue_loop())
        await self.pending_tasks.spawn(self.subscription_queue_loop())

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

    async def get_from_sub_queue_with_timeout(self, timeout):
        # Timeouts work very differently between our server implementations,
        # so we do this little stub in its own method.
        # Returns weakref(EventAddResponse) or None
        return await curio.ignore_after(timeout, self.subscription_queue.get)


class Context(_Context):
    CircuitClass = VirtualCircuit
    async_layer = CurioAsyncLayer
    ServerExit = ServerExit
    TaskCancelled = curio.TaskCancelled

    def __init__(self, pvdb, interfaces=None):
        super().__init__(pvdb, interfaces)
        self._task_group = None
        self._stop_event = threading.Event()
        self.command_bundle_queue = curio.Queue()
        self.subscription_queue = curio.UniversalQueue()

    async def broadcaster_udp_server_loop(self):
        for interface in self.interfaces:
            udp_sock = ca.bcast_socket(socket)
            try:
                udp_sock.bind((interface, self.ca_server_port))
            except Exception:
                self.log.exception('UDP bind failure on interface %r',
                                   interface)
                raise
            self.log.debug('UDP socket bound on %s:%d', interface,
                           self.ca_server_port)
            self.udp_socks[interface] = udp_sock

        async with curio.TaskGroup() as g:
            for interface, udp_sock in self.udp_socks.items():
                self.log.debug('Broadcasting on %s:%d', interface,
                               self.ca_server_port)
                await g.spawn(self._core_broadcaster_loop, udp_sock)

    async def run(self, *, log_pv_names=False):
        'Start the server'
        self.log.info('Curio server starting up...')
        try:
            for address in ca.get_beacon_address_list():
                sock = ca.bcast_socket(socket)
                await sock.connect(address)
                interface, _ = sock.getsockname()
                self.beacon_socks[address] = (interface, sock)

            async def make_socket(interface, port):
                return curio.network.tcp_server_socket(interface, port)

            self.port, self.tcp_sockets = await self._bind_tcp_sockets_with_consistent_port_number(
                make_socket)

            async with curio.TaskGroup() as self._task_group:
                g = self._task_group
                for interface, sock in self.tcp_sockets.items():
                    # Use run_server instead of tcp_server so we can hand in a
                    # socket that is already bound, avoiding a race between the
                    # moment we check for port availability and the moment the
                    # TCP server binds.
                    self.log.info("Listening on %s:%d", interface, self.port)
                    await g.spawn(curio.network.run_server,
                                  sock, self.tcp_handler)

                await g.spawn(self._await_stop)
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
            async_lib = CurioAsyncLayer()
            async with curio.TaskGroup() as task_group:
                for name, method in self.shutdown_methods.items():
                    self.log.debug('Calling shutdown method %r', name)
                    await task_group.spawn(method, async_lib)
            for sock in self.tcp_sockets.values():
                await sock.close()
            for sock in self.udp_socks.values():
                await sock.close()
            for interface, sock in self.beacon_socks.values():
                await sock.close()
            self._task_group = None

    async def _await_stop(self):
        await curio.abide(self._stop_event.wait)
        await self._task_group.cancel_remaining()

    def stop(self):
        self._stop_event.set()


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
