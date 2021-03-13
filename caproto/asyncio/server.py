import asyncio
import functools
import sys

import caproto as ca

from .._utils import CaprotoNetworkError
from ..server import AsyncLibraryLayer
from ..server.common import Context as _Context
from ..server.common import DisconnectedCircuit
from ..server.common import VirtualCircuit as _VirtualCircuit
from .utils import (AsyncioQueue, _create_bound_tcp_socket, _create_udp_socket,
                    _DatagramProtocol, _TaskHandler, _TransportWrapper,
                    _UdpTransportWrapper)


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


class AsyncioAsyncLayer(AsyncLibraryLayer):
    name = 'asyncio'
    Event = asyncio.Event
    library = asyncio
    sleep = staticmethod(asyncio.sleep)
    ThreadsafeQueue = AsyncioQueue


class VirtualCircuit(_VirtualCircuit):
    "Wraps a caproto.VirtualCircuit with an asyncio client."
    TaskCancelled = asyncio.CancelledError

    def __init__(self, circuit, client, context, *, loop=None):
        if loop is None:
            loop = asyncio.get_event_loop()
        self.loop = loop

        super().__init__(circuit, client, context)
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
            try:
                await self.client.send(b''.join(buffers_to_send))
            except CaprotoNetworkError as ex:
                raise DisconnectedCircuit(
                    f"Circuit disconnected: {ex}"
                ) from ex

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
        self.client.close()
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
        self.broadcaster_datagram_queue = AsyncioQueue(
            ca.MAX_COMMAND_BACKLOG
        )
        self.command_bundle_queue = asyncio.Queue(
            ca.MAX_COMMAND_BACKLOG
        )
        self.subscription_queue = asyncio.Queue()
        if loop is None:
            loop = asyncio.get_event_loop()
        self.loop = loop
        self.async_layer = AsyncioAsyncLayer()
        self.server_tasks = _TaskHandler()
        self.tcp_sockets = dict()

    async def server_accept_loop(self, sock):
        """Start a TCP server on `sock` and listen for new connections."""
        def _new_client(reader, writer):
            transport = _TransportWrapper(reader, writer)
            self.server_tasks.create(
                self.tcp_handler(transport, transport.getpeername())
            )

        # TODO: when Python 3.7 is the minimum version, the following server
        # can be an async context manager:
        await asyncio.start_server(
            _new_client,
            sock=sock,
        )

    async def run(self, *, log_pv_names=False, startup_hook=None):
        'Start the server'
        self.log.info('Asyncio server starting up...')

        self.port, self.tcp_sockets = await self._bind_tcp_sockets_with_consistent_port_number(
            _create_bound_tcp_socket
        )
        tasks = _TaskHandler()
        for interface, sock in self.tcp_sockets.items():
            self.log.info("Listening on %s:%d", interface, self.port)
            self.broadcaster.server_addresses.append((interface, self.port))
            tasks.create(self.server_accept_loop(sock))

        for address in ca.get_beacon_address_list():
            sock = _create_udp_socket()
            try:
                sock.connect(address)
            except Exception as ex:
                self.log.error(
                    'Beacon (%s:%d) socket setup failed: %s', *address, ex,
                )
                continue

            wrapped_transport = _UdpTransportWrapper(
                sock, address, loop=self.loop
            )
            self.beacon_socks[address] = (interface,   # TODO; this is incorrect
                                          wrapped_transport)

        for interface in self.interfaces:
            await self._create_broadcaster_transport(interface)

        tasks.create(self.broadcaster_receive_loop())
        tasks.create(self.broadcaster_queue_loop())
        tasks.create(self.subscription_queue_loop())
        tasks.create(self.broadcast_beacon_loop())

        async_lib = AsyncioAsyncLayer()

        if startup_hook is not None:
            self.log.debug('Calling startup hook %r', startup_hook.__name__)
            tasks.create(startup_hook(async_lib))

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
            for _, sock in self.beacon_socks.values():
                sock.close()

    async def _create_broadcaster_transport(self, interface):
        """Create broadcaster transport on the given interface."""
        old_transport = self.udp_socks.pop(interface, None)
        if old_transport is not None:
            try:
                old_transport.close()
            except OSError:
                self.log.warning(
                    "Failed to close old transport for interface %s", interface
                )

        sock = _create_udp_socket()
        sock.bind((interface, self.ca_server_port))
        transport, _ = await self.loop.create_datagram_endpoint(
            functools.partial(_DatagramProtocol, parent=self,
                              identifier=interface,
                              queue=self.broadcaster_datagram_queue),
            sock=sock,
        )
        self.udp_socks[interface] = _UdpTransportWrapper(
            transport, loop=self.loop
        )
        self.log.debug('UDP socket bound on %s:%d', interface,
                       self.ca_server_port)

    async def broadcaster_receive_loop(self):
        # UdpTransport -> broadcaster_datagram_queue -> command_bundle_queue
        queue = self.broadcaster_datagram_queue
        while True:
            interface, data, address = await queue.async_get()
            if isinstance(data, Exception):
                self.log.exception('Broadcaster failed to receive on %s',
                                   interface, exc_info=data)
                if sys.platform == 'win32':
                    self.log.warning(
                        'Re-initializing socket on interface %s', interface
                    )
            else:
                await self._broadcaster_recv_datagram(data, address)


async def start_server(pvdb, *, interfaces=None, log_pv_names=False,
                       startup_hook=None):
    '''Start an asyncio server with a given PV database'''
    ctx = Context(pvdb, interfaces)
    ret = await ctx.run(log_pv_names=log_pv_names, startup_hook=startup_hook)
    return ret


def run(pvdb, *, interfaces=None, log_pv_names=False, startup_hook=None):
    """
    Run an IOC, given its PV database dictionary.

    A synchronous function that wraps start_server and exits cleanly.

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
    loop = asyncio.get_event_loop()
    task = loop.create_task(
        start_server(pvdb, interfaces=interfaces, log_pv_names=log_pv_names,
                     startup_hook=startup_hook))
    try:
        loop.run_until_complete(task)
    except KeyboardInterrupt:
        ...
    finally:
        task.cancel()
        loop.run_until_complete(task)
