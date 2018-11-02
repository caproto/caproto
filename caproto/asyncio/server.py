from ..server import AsyncLibraryLayer
import caproto as ca
import asyncio
import socket
import sys

from ..server.common import (VirtualCircuit as _VirtualCircuit,
                             Context as _Context)
from .._utils import bcast_socket


class ServerExit(Exception):
    ...


class Event(asyncio.Event):
    "Implement the ``timeout`` keyword to wait(), as in threading.Event."
    async def wait(self, timeout=None):
        try:
            await asyncio.wait_for(super().wait(), timeout)
        except asyncio.TimeoutError:  # somehow not just a TimeoutError...
            pass
        return self.is_set()


def _get_asyncio_queue(loop):
    class AsyncioQueue(asyncio.Queue):
        '''
        Asyncio queue modified for caproto server layer queue API compatibility

        NOTE: This is bound to a single event loop for compatibility with
        synchronous requests.
        '''

        async def async_get(self):
            return await super().get()

        async def async_put(self, value):
            return await super().put(value)

        def get(self):
            future = asyncio.run_coroutine_threadsafe(self.async_get(), loop)
            return future.result()

        def put(self, value):
            future = asyncio.run_coroutine_threadsafe(self.async_put(value), loop)
            return future.result()

    return AsyncioQueue


class AsyncioAsyncLayer(AsyncLibraryLayer):
    name = 'asyncio'
    ThreadsafeQueue = None
    library = asyncio

    def __init__(self, loop=None):
        super().__init__()

        if loop is None:
            loop = asyncio.get_event_loop()

        self.ThreadsafeQueue = _get_asyncio_queue(loop)


class VirtualCircuit(_VirtualCircuit):
    "Wraps a caproto.VirtualCircuit with a curio client."
    TaskCancelled = asyncio.CancelledError

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
        self.QueueFull = asyncio.QueueFull
        self.command_queue = asyncio.Queue(ca.MAX_COMMAND_BACKLOG,
                                           loop=self.loop)
        self.new_command_condition = asyncio.Condition(loop=self.loop)
        self.events_on = asyncio.Event(loop=self.loop)
        self.subscription_queue = asyncio.Queue(
            ca.MAX_TOTAL_SUBSCRIPTION_BACKLOG, loop=self.loop)
        self.write_event = Event(loop=self.loop)
        self._cq_task = None
        self._sq_task = None
        self._write_tasks = ()

    async def get_from_sub_queue_with_timeout(self, timeout):
        # Timeouts work very differently between our server implementations,
        # so we do this little stub in its own method.
        fut = asyncio.ensure_future(self.subscription_queue.get())
        try:
            return await asyncio.wait_for(fut, timeout, loop=self.loop)
        except asyncio.TimeoutError:
            return None

    async def send(self, *commands):
        if self.connected:
            buffers_to_send = self.circuit.send(*commands)
            await self.loop.sock_sendall(self._raw_client,
                                         b''.join(buffers_to_send))

    async def run(self):
        self._cq_task = self.loop.create_task(self.command_queue_loop())
        self._sq_task = self.loop.create_task(self.subscription_queue_loop())

    async def _start_write_task(self, handle_write):
        tsk = self.loop.create_task(handle_write())
        self._write_tasks = tuple(t for t in self._write_tasks + (tsk,)
                                  if not t.done())

    async def _wake_new_command(self):
        async with self.new_command_condition:
            self.new_command_condition.notify_all()

    async def _on_disconnect(self):
        await super()._on_disconnect()
        self._raw_client.close()
        if self._sq_task is not None:
            self._sq_task.cancel()


class Context(_Context):
    CircuitClass = VirtualCircuit
    async_layer = None
    ServerExit = ServerExit
    TaskCancelled = asyncio.CancelledError

    def __init__(self, pvdb, interfaces=None, *, loop=None):
        super().__init__(pvdb, interfaces)
        self.command_bundle_queue = asyncio.Queue()
        self.subscription_queue = asyncio.Queue()
        if loop is None:
            loop = asyncio.get_event_loop()
        self.loop = loop
        self.async_layer = AsyncioAsyncLayer(self.loop)
        self._server_tasks = []

    async def server_accept_loop(self, sock):
        sock.listen()

        while True:
            client_sock, addr = await self.loop.sock_accept(sock)
            task = self.loop.create_task(
                self.tcp_handler(client_sock, addr))
            self._server_tasks.append(task)

    async def run(self, *, log_pv_names=False):
        'Start the server'
        self.log.info('Asyncio server starting up...')

        async def make_socket(interface, port):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.setblocking(False)
            s.bind((interface, port))
            return s
        self.port, self.tcp_sockets = await self._bind_tcp_sockets_with_consistent_port_number(
            make_socket)
        tasks = []
        for interface, sock in self.tcp_sockets.items():
            self.log.info("Listening on %s:%d", interface, self.port)
            tasks.append(self.loop.create_task(self.server_accept_loop(sock)))

        class BcastLoop(asyncio.Protocol):
            parent = self
            loop = self.loop

            def __init__(self, *args, **kwargs):
                self.transport = None
                self._tasks = ()

            def connection_made(self, transport):
                self.transport = transport

            def datagram_received(self, data, addr):
                tsk = self.loop.create_task(self.parent._broadcaster_recv_datagram(
                    data, addr))
                self._tasks = tuple(t for t in self._tasks + (tsk,)
                                    if not t.done())

            def error_received(self, exc):
                self.parent.log.error('BcastLoop received error', exc_info=exc)

        class TransportWrapper:
            """Make an asyncio transport something you can call sendto on."""
            def __init__(self, transport):
                self.transport = transport

            async def sendto(self, bytes_to_send, addr_port):
                try:
                    self.transport.sendto(bytes_to_send, addr_port)
                except OSError as exc:
                    host, port = addr_port
                    raise ca.CaprotoNetworkError(f"Failed to send to {host}:{port}") from exc

            def close(self):
                return self.transport.close()

        class ConnectedTransportWrapper:
            """Make an asyncio transport something you can call send on."""
            def __init__(self, transport, address):
                self.transport = transport
                self.address = address

            async def send(self, bytes_to_send):
                try:
                    self.transport.sendto(bytes_to_send, self.address)
                except OSError as exc:
                    host, port = self.address
                    raise ca.CaprotoNetworkError(
                        f"Failed to send to {host}:{port}") from exc

            def close(self):
                return self.transport.close()

        for address in ca.get_beacon_address_list():
            # Win wants a connected socket; UNIX wants an un-connected one.
            temp_sock = ca.bcast_socket(socket)
            temp_sock.connect(address)
            interface, _ = temp_sock.getsockname()
            if sys.platform == 'win32':
                sock = temp_sock
            else:
                temp_sock.close()
                sock = ca.bcast_socket(socket)
            transport, _ = await self.loop.create_datagram_endpoint(
                BcastLoop, sock=sock)
            wrapped_transport = ConnectedTransportWrapper(transport, address)
            self.beacon_socks[address] = (interface, wrapped_transport)

        for interface in self.interfaces:
            udp_sock = bcast_socket()
            try:
                udp_sock.bind((interface, self.ca_server_port))
            except Exception:
                self.log.exception('UDP bind failure on interface %r',
                                   interface)
                raise

            transport, self.p = await self.loop.create_datagram_endpoint(
                BcastLoop, sock=udp_sock)
            self.udp_socks[interface] = TransportWrapper(transport)
            self.log.debug('UDP socket bound on %s:%d', interface,
                           self.ca_server_port)

        tasks.append(self.loop.create_task(self.broadcaster_queue_loop()))
        tasks.append(self.loop.create_task(self.subscription_queue_loop()))
        tasks.append(self.loop.create_task(self.broadcast_beacon_loop()))

        async_lib = AsyncioAsyncLayer(self.loop)
        for name, method in self.startup_methods.items():
            self.log.debug('Calling startup method %r', name)
            tasks.append(self.loop.create_task(method(async_lib)))
        self.log.info('Server startup complete.')
        if log_pv_names:
            self.log.info('PVs available:\n%s', '\n'.join(self.pvdb))

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            self.log.info('Server task cancelled. Will shut down.')
            udp_sock.close()
            all_tasks = (tasks + self._server_tasks +
                         [c._cq_task for c in self.circuits if c._cq_task is not None] +
                         [c._sq_task for c in self.circuits if c._sq_task is not None] +
                         [t for c in self.circuits for t in c._write_tasks] +
                         list(self.p._tasks))
            for t in all_tasks:
                t.cancel()
            await asyncio.wait(all_tasks)
            return
        except Exception:
            self.log.exception('Server error. Will shut down')
            raise
        finally:
            self.log.info('Server exiting....')
            shutdown_tasks = []
            async_lib = AsyncioAsyncLayer(self.loop)
            for name, method in self.shutdown_methods.items():
                self.log.debug('Calling shutdown method %r', name)
                task = self.loop.create_task(method(async_lib))
                shutdown_tasks.append(task)
            await asyncio.gather(*shutdown_tasks)
            for sock in self.tcp_sockets.values():
                sock.close()
            for sock in self.udp_socks.values():
                sock.close()
            for interface, sock in self.beacon_socks.values():
                sock.close()


async def start_server(pvdb, *, interfaces=None, log_pv_names=False):
    '''Start an asyncio server with a given PV database'''
    ctx = Context(pvdb, interfaces)
    ret = await ctx.run(log_pv_names=log_pv_names)
    return ret


def run(pvdb, *, interfaces=None, log_pv_names=False):
    """
    A synchronous function that wraps start_server and exits cleanly.
    """
    loop = asyncio.get_event_loop()
    task = loop.create_task(
        start_server(pvdb, interfaces=interfaces, log_pv_names=log_pv_names))
    try:
        loop.run_until_complete(task)
    except KeyboardInterrupt:
        task.cancel()
        loop.run_until_complete(task)
