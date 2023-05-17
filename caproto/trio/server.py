import functools
import threading

import trio
from trio import socket

import caproto as ca

from .._utils import safe_getsockname
from ..server import AsyncLibraryLayer
from ..server.common import Context as _Context
from ..server.common import DisconnectedCircuit, LoopExit
from ..server.common import VirtualCircuit as _VirtualCircuit
from .util import open_memory_channel


class ServerExit(Exception):
    ...


class Event:
    """
    The class wraps `trio.Event` and implements `Event.clear()`
    method that is used in the code, but deprecated in `trio`.
    The event is cleared by creating the new event that if the
    event is set. If the event is not set, then old event is left.
    The class is not intended to be thread safe.
    """
    def __init__(self):
        self._create_event()

    def _create_event(self):
        self._event = trio.Event()

    def set(self):
        self._event.set()

    def clear(self):
        """
        Clearing of the event is implemented by creating a new
        event if the event is set. It is assumed that if the event
        is set, then it is not waited on.
        """
        if self._event.is_set():
            self._create_event()

    def is_set(self):
        return self._event.is_set()

    async def wait(self, timeout=None):
        if timeout is not None:
            with trio.move_on_after(timeout):
                await self._event.wait()
                return True
            return False
        else:
            await self._event.wait()
            return True


def _universal_queue(max_len=1000):
    class UniversalQueue:
        def __init__(self):
            self._send, self._recv = open_memory_channel(max_len)

        def put(self, value):
            trio.from_thread.run(self._send.send, value)

        async def async_put(self, value):
            await self._send.send(value)

        def get(self):
            return trio.from_thread.run(self._recv.receive)

        async def async_get(self):
            return await self._recv.receive()

    return UniversalQueue


class TrioAsyncLayer(AsyncLibraryLayer):
    def __init__(self):
        self.ThreadsafeQueue = _universal_queue()

    name = 'trio'
    ThreadsafeQueue = None
    Event = Event
    library = trio
    sleep = staticmethod(trio.sleep)


class TrioSocketStreamCompat:
    _sock: socket.socket  # trio._socket._SocketType
    _stream: trio.SocketStream
    _token: trio.lowlevel.TrioToken
    _send_lock: trio.StrictFIFOLock

    def __init__(self, sock: socket.socket, token: trio.lowlevel.TrioToken):
        self._sock = sock
        self._stream = trio.SocketStream(sock)
        self._token = token
        self._send_lock = trio.StrictFIFOLock()

    async def recv(self, max_bytes=None):
        return await self._stream.receive_some(max_bytes)

    def close(self, *args, **kwargs):
        def _close():
            trio.from_thread.run(self._stream.aclose, trio_token=self._token)

        threading.Thread(target=_close, daemon=True).start()

    def getsockname(self, *args, **kwargs):
        return self._sock.getsockname()

    async def send_all(self, data):
        try:
            async with self._send_lock:
                return await self._stream.send_all(data)
        except trio.BrokenResourceError:
            raise DisconnectedCircuit("Disconnected while sending to client")


class VirtualCircuit(_VirtualCircuit):
    "Wraps a caproto.VirtualCircuit with a trio client."
    TaskCancelled = trio.Cancelled

    def __init__(self, circuit, client: TrioSocketStreamCompat, context):
        super().__init__(circuit, client, context)
        self.nursery = context.nursery
        self.QueueFull = trio.WouldBlock

        self.command_chan = open_memory_channel(ca.MAX_COMMAND_BACKLOG)

        # For compatibility with server common:
        self.command_queue = self.command_chan.send

        self.new_command_condition = trio.Condition()
        self.subscription_chan = open_memory_channel(ca.MAX_TOTAL_SUBSCRIPTION_BACKLOG)

        # For compatibility with server common:
        self.subscription_queue = self.subscription_chan.send

        self.write_event = Event()
        self.events_on = Event()

    async def run(self):
        await self.nursery.start(self.command_queue_loop)
        await self.nursery.start(self.subscription_queue_loop)

    async def _send_buffers(self, *buffers):
        """Send ``buffers`` over the wire."""
        await self.client.send_all(b"".join(buffers))

    async def command_queue_loop(self, task_status):
        self.write_event.set()

        send, recv = self.command_chan
        async with send:
            async with recv:
                task_status.started()
                try:
                    async for command in recv:
                        response = await self._command_queue_iteration(command)
                        if response is not None:
                            await self.send(*response)
                        await self._wake_new_command()
                except DisconnectedCircuit:
                    await self._on_disconnect()
                    self.circuit.disconnect()
                    await self.context.circuit_disconnected(self)
                except trio.Cancelled:
                    ...
                except LoopExit:
                    ...

    async def subscription_queue_loop(self, task_status):
        task_status.started()
        await super().subscription_queue_loop()

    async def get_from_sub_queue(self, timeout=None):
        # Timeouts work very differently between our server implementations,
        # so we do this little stub in its own method.
        _, recv = self.subscription_chan
        if timeout is None:
            return await recv.receive()

        with trio.move_on_after(timeout):
            return await recv.receive()

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
        self.command_chan = open_memory_channel(ca.MAX_COMMAND_BACKLOG)
        self.command_bundle_queue = self.command_chan.send

        self.subscription_chan = open_memory_channel(ca.MAX_TOTAL_SUBSCRIPTION_BACKLOG)
        self.subscription_queue = self.subscription_chan.send
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
            self.broadcaster.server_addresses.append(
                safe_getsockname(udp_sock)
            )
            self.log.debug('UDP socket bound on %s:%d', interface,
                           self.ca_server_port)
            self.udp_socks[interface] = udp_sock

        for interface, udp_sock in self.udp_socks.items():
            self.log.debug('Broadcasting on %s:%d', interface,
                           self.ca_server_port)
            self.nursery.start_soon(self._core_broadcaster_loop, udp_sock)

        task_status.started()

    async def broadcaster_queue_loop(self, task_status):
        send, recv = self.command_chan
        async with send:
            async with recv:
                try:
                    task_status.started()
                    async for addr, commands in recv:
                        await super()._broadcaster_queue_iteration(addr, commands)
                except trio.Cancelled:
                    ...
                except LoopExit:
                    ...

    async def subscription_queue_loop(self, task_status):
        send, recv = self.subscription_chan
        async with send:
            async with recv:
                task_status.started()
                async for item in recv:
                    sub_specs, metadata, values, flags, sub = item
                    await self._subscription_queue_iteration(
                        sub_specs, metadata, values, flags, sub)

    async def broadcast_beacon_loop(self, task_status):
        task_status.started()
        await super().broadcast_beacon_loop()

    async def server_accept_loop(self, listen_sock, *, task_status):
        try:
            listen_sock.listen()
            task_status.started()
            while True:
                trio_sock, addr = await listen_sock.accept()
                stream = TrioSocketStreamCompat(
                    sock=trio_sock,
                    token=trio.lowlevel.current_trio_token()
                )
                self.nursery.start_soon(
                    self.tcp_handler, stream, addr
                )
        finally:
            listen_sock.close()

    async def run(self, *, log_pv_names=False, startup_hook=None):
        'Start the server'
        self.log.info('Trio server starting up...')
        try:
            async with trio.open_nursery() as self.nursery:
                for address in ca.get_beacon_address_list():
                    sock = ca.bcast_socket(socket)
                    await sock.connect(address)
                    interface, _ = safe_getsockname(sock)
                    self.beacon_socks[address] = (interface, sock)

                async def make_socket(interface, port):
                    s = trio.socket.socket()
                    await s.bind((interface, port))
                    return s

                res = await self._bind_tcp_sockets_with_consistent_port_number(
                    make_socket)
                self.port, self.tcp_sockets = res

                await self.nursery.start(self.broadcaster_udp_server_loop)
                await self.nursery.start(self.broadcaster_queue_loop)
                await self.nursery.start(self.subscription_queue_loop)
                await self.nursery.start(self.broadcast_beacon_loop)

                # Only after all loops have been started, begin listening:
                for interface, listen_sock in self.tcp_sockets.items():
                    self.log.info("Listening on %s:%d", interface, self.port)
                    await self.nursery.start(self.server_accept_loop,
                                             listen_sock)

                async_lib = TrioAsyncLayer()

                if startup_hook is not None:
                    self.log.debug('Calling startup hook %r',
                                   startup_hook.__name__)

                    async def _startup(task_status):
                        task_status.started()
                        await startup_hook(async_lib)

                    await self.nursery.start(_startup)

                for name, method in self.startup_methods.items():
                    self.log.debug('Calling startup method %r', name)

                    async def _startup(task_status):
                        task_status.started()
                        await method(async_lib)

                    await self.nursery.start(_startup)
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
            for _interface, sock in self.beacon_socks.values():
                sock.close()

    def stop(self):
        'Stop the server'
        nursery = self.nursery
        if nursery is None:
            return

        nursery.cancel_scope.cancel()


async def start_server(pvdb, *, interfaces=None, log_pv_names=False,
                       startup_hook=None):
    '''Start a trio server with a given PV database'''
    ctx = Context(pvdb, interfaces=interfaces)
    return await ctx.run(
        log_pv_names=log_pv_names,
        startup_hook=startup_hook
    )


def run(pvdb, *, interfaces=None, log_pv_names=False, startup_hook=None):
    """
    Run an IOC, given its PV database dictionary.

    A synchronous function that runs server, catches KeyboardInterrupt at exit.

    Parameters
    ----------
    pvdb : dict
        The PV database.

    interfaces : list, optional
        List of interfaces to listen on.

    log_pv_names : bool, optional
        Log PV names at startup.

    startup_hook : coroutine, optional
        Hook to call at startup with the ``async_lib`` shim.
    """
    try:
        return trio.run(
            functools.partial(
                start_server,
                pvdb,
                interfaces=interfaces,
                log_pv_names=log_pv_names,
                startup_hook=startup_hook,
            ))
    except KeyboardInterrupt:
        return
