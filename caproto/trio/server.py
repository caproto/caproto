import functools
from ..server import AsyncLibraryLayer
import caproto as ca
import trio
from trio import socket

from ..server.common import (VirtualCircuit as _VirtualCircuit,
                             Context as _Context)


class ServerExit(Exception):
    ...


class Event(trio.Event):
    async def wait(self, timeout=None):
        if timeout is not None:
            with trio.move_on_after(timeout):
                await super().wait()
                return True
            return False
        else:
            await super().wait()
            return True


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

    def __init__(self, circuit, client, context):
        super().__init__(circuit, client, context)
        self.nursery = context.nursery
        self.QueueFull = trio.WouldBlock
        self.command_queue = trio.Queue(ca.MAX_COMMAND_BACKLOG)
        self.new_command_condition = trio.Condition()
        self.subscription_queue = trio.Queue(ca.MAX_TOTAL_SUBSCRIPTION_BACKLOG)
        self.write_event = Event()
        self.events_on = trio.Event()

    async def run(self):
        await self.nursery.start(self.command_queue_loop)
        await self.nursery.start(self.subscription_queue_loop)

    async def command_queue_loop(self, task_status):
        task_status.started()
        await super().command_queue_loop()

    async def subscription_queue_loop(self, task_status):
        task_status.started()
        await super().subscription_queue_loop()

    async def get_from_sub_queue_with_timeout(self, timeout):
        # Timeouts work very differently between our server implementations,
        # so we do this little stub in its own method.
        with trio.move_on_after(timeout):
            return await self.subscription_queue.get()

    async def _on_disconnect(self):
        """Executed when disconnection detected"""
        await super()._on_disconnect()
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

    def __init__(self, pvdb, interfaces=None):
        super().__init__(pvdb, interfaces)
        self.nursery = None
        self.command_bundle_queue = trio.Queue(1000)
        self.subscription_queue = trio.Queue(1000)
        self.beacon_sock = ca.bcast_socket(socket)

    async def broadcaster_udp_server_loop(self, task_status):
        for interface in self.interfaces:
            udp_sock = ca.bcast_socket(socket)
            try:
                await udp_sock.bind((interface, self.ca_server_port))
            except Exception:
                self.log.exception('UDP bind failure on interface %r',
                                   interface)
                raise
            self.log.debug('UDP socket bound on %s:%d', interface,
                           self.ca_server_port)
            self.udp_socks[interface] = udp_sock

        for interface, udp_sock in self.udp_socks.items():
            self.log.debug('Broadcasting on %s:%d', interface,
                           self.ca_server_port)
            self.nursery.start_soon(self._core_broadcaster_loop, udp_sock)

        task_status.started()

    async def broadcaster_queue_loop(self, task_status):
        task_status.started()
        await super().broadcaster_queue_loop()

    async def subscription_queue_loop(self, task_status):
        task_status.started()
        await super().subscription_queue_loop()

    async def broadcast_beacon_loop(self, task_status):
        task_status.started()
        await super().broadcast_beacon_loop()

    async def server_accept_loop(self, listen_sock, *, task_status):
            try:
                listen_sock.listen()
                task_status.started()
                while True:
                    client_sock, addr = await listen_sock.accept()
                    self.nursery.start_soon(self.tcp_handler, client_sock, addr)
            finally:
                listen_sock.close()

    async def run(self, *, log_pv_names=False):
        'Start the server'
        self.log.info('Trio server starting up...')
        try:
            async with trio.open_nursery() as self.nursery:
                for address in ca.get_beacon_address_list():
                    sock = ca.bcast_socket(socket)
                    await sock.connect(address)
                    interface, _ = sock.getsockname()
                    self.beacon_socks[address] = (interface, sock)

                async def make_socket(interface, port):
                    s = trio.socket.socket()
                    await s.bind((interface, port))
                    return s

                res = await self._bind_tcp_sockets_with_consistent_port_number(
                    make_socket)
                self.port, self.tcp_sockets = res

                for interface, listen_sock in self.tcp_sockets.items():
                    self.log.info("Listening on %s:%d", interface, self.port)
                    await self.nursery.start(self.server_accept_loop,
                                             listen_sock)
                await self.nursery.start(self.broadcaster_udp_server_loop)
                await self.nursery.start(self.broadcaster_queue_loop)
                await self.nursery.start(self.subscription_queue_loop)
                await self.nursery.start(self.broadcast_beacon_loop)

                async_lib = TrioAsyncLayer()
                for name, method in self.startup_methods.items():
                    self.log.debug('Calling startup method %r', name)

                    async def startup(task_status):
                        task_status.started()
                        await method(async_lib)

                    await self.nursery.start(startup)
                self.log.info('Server startup complete.')
                if log_pv_names:
                    self.log.info('PVs available:\n%s', '\n'.join(self.pvdb))
        except trio.Cancelled:
            self.log.info('Server task cancelled. Will shut down.')
        finally:
            self.log.info('Server exiting....')
            async_lib = TrioAsyncLayer()
            async with trio.open_nursery() as nursery:
                for name, method in self.shutdown_methods.items():
                    self.log.debug('Calling shutdown method %r', name)

                    async def shutdown(task_status):
                        task_status.started()
                        await method(async_lib)

                    await nursery.start(shutdown)
            for sock in self.tcp_sockets.values():
                sock.close()
            for sock in self.udp_socks.values():
                sock.close()
            for interface, sock in self.beacon_socks.values():
                sock.close()

    def stop(self):
        'Stop the server'
        nursery = self.nursery
        if nursery is None:
            return

        nursery.cancel_scope.cancel()


async def start_server(pvdb, *, interfaces=None, log_pv_names=False):
    '''Start a trio server with a given PV database'''
    ctx = Context(pvdb, interfaces=interfaces)
    return (await ctx.run(log_pv_names=log_pv_names))


def run(pvdb, *, interfaces=None, log_pv_names=False):
    """
    A synchronous function that runs server, catches KeyboardInterrupt at exit.
    """
    try:
        return trio.run(
            functools.partial(
                start_server,
                pvdb,
                interfaces=interfaces,
                log_pv_names=log_pv_names))
    except KeyboardInterrupt:
        return
