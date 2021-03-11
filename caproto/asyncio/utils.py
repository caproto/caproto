import asyncio
import functools
import inspect
import socket
import sys
import threading

import caproto as ca


class AsyncioQueue:
    '''
    Asyncio queue modified for caproto server layer queue API compatibility

    NOTE: This is bound to a single event loop for compatibility with
    synchronous requests.
    '''

    def __init__(self, maxsize=0):
        self._queue = asyncio.Queue(maxsize)
        try:
            self._loop = get_running_loop()
        except Exception as ex:
            raise RuntimeError('AsyncioQueue must be instantiated in the '
                               'event loop it is to be used in.') from ex

    async def async_get(self):
        return await self._queue.get()

    async def async_put(self, value):
        return await self._queue.put(value)

    def get(self):
        future = asyncio.run_coroutine_threadsafe(
            self._queue.get(), self._loop)

        return future.result()

    def put(self, value):
        asyncio.run_coroutine_threadsafe(
            self._queue.put(value), self._loop)


class _DatagramProtocol(asyncio.Protocol):
    def __init__(self, parent, identifier, queue):
        self.transport = None
        self.parent = parent
        self.identifier = identifier
        self.queue = queue

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        if not data:
            return

        self.queue.put((self.identifier, data, addr))

    def error_received(self, ex):
        self.queue.put((self.identifier, ex, None))


class _TransportWrapper:
    """
    A wrapped transport with awaitable sendto and recv.

    Parameters
    ----------
    sock : socket.socket
        The socket.

    loop : asyncio.AbstractEventLoop, optional
        The event loop.
    """

    sock: socket.socket
    loop: asyncio.AbstractEventLoop
    transport: asyncio.BaseTransport

    def __init__(self, reader, writer, loop=None):
        self.reader = reader
        self.writer = writer
        self.loop = loop or get_running_loop()
        self.sock = self.writer.get_extra_info('socket')
        self.lock = asyncio.Lock()

    def getsockname(self):
        return self.writer.get_extra_info('sockname')

    def getpeername(self):
        return self.writer.get_extra_info('peername')

    async def send(self, bytes_to_send):
        """Sends data over a connected socket."""
        try:
            async with self.lock:
                self.writer.write(bytes_to_send)
                await self.writer.drain()
        except OSError as exc:
            try:
                host, port = self.getpeername()
            except Exception:
                destination = ''
            else:
                destination = f' to {host}:{port}'

            raise ca.CaprotoNetworkError(
                f"Failed to send{destination}"
            ) from exc

    async def recv(self, nbytes=4096):
        """Receive from the socket."""
        try:
            return await self.reader.read(nbytes)
        except OSError as exc:
            raise ca.CaprotoNetworkError(
                f"Failed to receive: {exc}"
            ) from exc

    def close(self):
        return self.writer.close()

    def __repr__(self):
        try:
            host, port = self.getpeername()
        except Exception:
            return f'<{self.__class__.__name__}>'

        return f'<{self.__class__.__name__} address="{host}:{port}">'


class _UdpTransportWrapper:
    """Make an asyncio transport something you can call send on."""
    def __init__(self, transport, address=None, loop=None):
        self.transport = transport
        self.address = address
        self.loop = loop or get_running_loop()

    async def send(self, bytes_to_send):
        """Sends data."""
        if self.address is None:
            raise ca.CaprotoNetworkError(
                "Cannot send on a disconnected UDP transport"
            )
        try:
            self.transport.send(bytes_to_send)
        except OSError as exc:
            raise ca.CaprotoNetworkError(
                f"Failed to send to {self.address[0]}:{self.address[1]}"
            ) from exc

    async def sendto(self, bytes_to_send, address):
        """Sends data to address."""
        try:
            self.transport.sendto(bytes_to_send, address)
        except OSError as exc:
            raise ca.CaprotoNetworkError(
                f"Failed to send to {self.address[0]}:{self.address[1]}"
            ) from exc

    def close(self):
        self.transport.close()

    def __repr__(self):
        return f'<{self.__class__.__name__} address={self.address}>'


class _TaskHandler:
    def __init__(self):
        self.tasks = []
        self._lock = threading.Lock()

    def create(self, coro):
        """Schedule the execution of a coroutine object in a spawn task."""
        task = create_task(coro)
        with self._lock:
            self.tasks.append(task)
        task.add_done_callback(self._remove_completed_task)
        return task

    def _remove_completed_task(self, task):
        try:
            with self._lock:
                self.tasks.remove(task)
        except ValueError:
            # May have been cancelled or removed otherwise
            ...

    async def cancel(self, task):
        task.cancel()
        await task

    async def cancel_all(self, wait=False):
        with self._lock:
            tasks = list(self.tasks)
            self.tasks.clear()

        for task in list(tasks):
            task.cancel()

        if wait and len(tasks):
            await asyncio.wait(tasks)


class _CallbackExecutor:
    def __init__(self, log):
        self.callbacks = AsyncioQueue()
        self.tasks = _TaskHandler()
        self.tasks.create(self._callback_loop())
        self.log = log

    async def shutdown(self):
        await self.tasks.cancel_all()

    async def _callback_loop(self):
        loop = get_running_loop()
        # self.user_callback_executor = concurrent.futures.ThreadPoolExecutor(
        #      max_workers=self.context.max_workers,
        #      thread_name_prefix='user-callback-executor'
        # )

        while True:
            callback, args, kwargs = await self.callbacks.async_get()
            if inspect.iscoroutinefunction(callback):
                try:
                    await callback(*args, **kwargs)
                except Exception:
                    self.log.exception('Callback failure')
            else:
                try:
                    loop.run_in_executor(None, functools.partial(callback, *args,
                                                                 **kwargs))
                except Exception:
                    self.log.exception('Callback failure')

    def submit(self, callback, *args, **kwargs):
        self.callbacks.put((callback, args, kwargs))


async def _create_bound_tcp_socket(addr, port):
    """Create a TCP socket and bind it to (addr, port)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setblocking(False)
    sock.bind((addr, port))
    return sock


def _create_udp_socket():
    """Create a UDP socket for usage with a datagram endpoint."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    # Python says this is unsafe, but we need it to have
    # multiple servers live on the same host.
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if sys.platform not in ('win32', ) and hasattr(socket, 'SO_REUSEPORT'):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setblocking(False)
    return sock


if sys.version_info < (3, 7):
    # python <= 3.6 compatibility
    def get_running_loop():
        return asyncio.get_event_loop()

    def run(coro, debug=False):
        return get_running_loop().run_until_complete(coro)

    def create_task(coro):
        return get_running_loop().create_task(coro)

else:
    get_running_loop = asyncio.get_running_loop
    run = asyncio.run
    create_task = asyncio.create_task
