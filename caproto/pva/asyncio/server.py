import asyncio
import functools
import socket
import sys

import caproto as ca

from ...asyncio.server import AsyncioAsyncLayer, Event, ServerExit
from ...asyncio.utils import (AsyncioQueue, _DatagramProtocol, _TaskHandler,
                              _TransportWrapper)
from ..server.common import Context as _Context
from ..server.common import VirtualCircuit as _VirtualCircuit


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

            def getsockname(self):
                return self.client.getsockname()

            async def recv(self, nbytes):
                return (await self.loop.sock_recv(self.client, nbytes))

        self._raw_lock = asyncio.Lock()
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
        self.tasks = _TaskHandler()
        self._sub_task = None

    async def get_from_sub_queue(self, timeout=None):
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
            # lock to make sure a AddEvent does not write bytes
            # to the socket while we are sending
            async with self._raw_lock:
                await self.loop.sock_sendall(self._raw_client,
                                             b''.join(buffers_to_send))

    async def run(self):
        self.tasks.create(self.command_queue_loop())
        self._sub_task = self.tasks.create(self.subscription_queue_loop())

    async def _start_write_task(self, handle_write):
        self.tasks.create(handle_write())

    async def _wake_new_command(self):
        async with self.new_command_condition:
            self.new_command_condition.notify_all()

    async def _on_disconnect(self):
        await super()._on_disconnect()
        self._raw_client.close()
        if self._sub_task is not None:
            await self.tasks.cancel(self._sub_task)
            self._sub_task = None


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
        self.async_layer = AsyncioAsyncLayer()
        self.server_tasks = _TaskHandler()
        self.tcp_sockets = dict()

    async def server_accept_loop(self, sock):
        sock.listen()

        while True:
            client_sock, addr = await self.loop.sock_accept(sock)
            self.server_tasks.create(self.tcp_handler(client_sock, addr))

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
        tasks = _TaskHandler()
        for interface, sock in self.tcp_sockets.items():
            self.log.info("Listening on %s:%d", interface, self.port)
            self.broadcaster.server_addresses.append((interface, self.port))
            tasks.create(self.server_accept_loop(sock))

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

        reuse_port = sys.platform not in ('win32', ) and hasattr(socket, 'SO_REUSEPORT')
        for address in ca.get_beacon_address_list():
            transport, _ = await self.loop.create_datagram_endpoint(
                functools.partial(_DatagramProtocol, parent=self,
                                  recv_func=self._datagram_received),
                remote_addr=address, allow_broadcast=True,
                reuse_port=reuse_port)
            wrapped_transport = ConnectedTransportWrapper(transport, address)
            self.beacon_socks[address] = (interface,   # TODO; this is incorrect
                                          wrapped_transport)

        for interface in self.interfaces:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,
                                 socket.IPPROTO_UDP)
            # Python says this is unsafe, but we need it to have
            # multiple servers live on the same host.
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if reuse_port:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.setblocking(False)
            sock.bind((interface, self.pva_broadcast_port))

            transport, _ = await self.loop.create_datagram_endpoint(
                functools.partial(_DatagramProtocol, parent=self,
                                  recv_func=self._datagram_received),
                sock=sock)
            self.udp_socks[interface] = _TransportWrapper(transport)
            self.log.debug('UDP socket bound on %s:%d', interface,
                           self.pva_broadcast_port)

        tasks.create(self.broadcaster_queue_loop())
        # tasks.create(self.subscription_queue_loop())
        tasks.create(self.broadcast_beacon_loop())

        async_lib = AsyncioAsyncLayer()
        for name, method in self.startup_methods.items():
            self.log.debug('Calling startup method %r', name)
            tasks.create(method(async_lib))
        self.log.info('Server startup complete.')
        if log_pv_names:
            self.log.info('PVs available:\n%s', '\n'.join(self.pvdb))

        try:
            await asyncio.gather(*tasks.tasks)
        except asyncio.CancelledError:
            self.log.info('Server task cancelled. Will shut down.')
            await tasks.cancel_all()
            await self.server_tasks.cancel_all()
            for circuit in self.circuits:
                await circuit.tasks.cancel_all()
            return
        except Exception:
            self.log.exception('Server error. Will shut down')
            raise
        finally:
            self.log.info('Server exiting....')
            shutdown_tasks = []
            async_lib = AsyncioAsyncLayer()
            for name, method in self.shutdown_methods.items():
                self.log.debug('Calling shutdown method %r', name)
                task = self.loop.create_task(method(async_lib))
                shutdown_tasks.append(task)
            await asyncio.gather(*shutdown_tasks)
            for sock in self.tcp_sockets.values():
                sock.close()
            for sock in self.udp_socks.values():
                sock.close()
            for _interface, sock in self.beacon_socks.values():
                sock.close()

    def _datagram_received(self, pair):
        bytes_received, address = pair
        try:
            commands = self.broadcaster.recv(bytes_received, address)
        except ca.RemoteProtocolError:
            self.log.exception('Broadcaster received bad packet')
        else:
            self.command_bundle_queue.put_nowait((address, commands))


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
        ...
    finally:
        task.cancel()
        loop.run_until_complete(task)
