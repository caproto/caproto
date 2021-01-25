import asyncio
import functools
import inspect
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
    def __init__(self, parent, recv_func):
        self.transport = None
        self.parent = parent
        self.recv_func = recv_func

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        if not data:
            return

        self.recv_func((data, addr))

    def error_received(self, ex):
        self.parent.log.error('%s receive error', self, exc_info=ex)


class _StreamProtocol(asyncio.Protocol):
    def __init__(self, parent, connection_callback, recv_func):
        self.connection_callback = connection_callback
        self.parent = parent
        self.recv_func = recv_func
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport
        self.connection_callback(True, transport)

    def eof_received(self):
        self.connection_callback(False, None)
        return False

    def connection_lost(self, exc):
        self.transport = None
        self.connection_callback(False, exc)

    def data_received(self, data):
        self.recv_func(data)

    def error_received(self, ex):
        self.parent.log.error('%s receive error', self, exc_info=ex)


class _TransportWrapper:
    """Make an asyncio transport something you can call sendto on."""
    # NOTE: taken from the server - combine usage
    def __init__(self, transport):
        self.transport = transport

    def getsockname(self):
        return self.transport.get_extra_info('sockname')

    async def sendto(self, bytes_to_send, addr_port):
        try:
            self.transport.sendto(bytes_to_send, addr_port)
        except OSError as exc:
            host, port = addr_port
            raise ca.CaprotoNetworkError(
                f"Failed to send to {host}:{port}") from exc

    def close(self):
        return self.transport.close()


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


ProactorEventLoop = getattr(asyncio, 'ProactorEventLoop', None)


def is_proactor_event_loop() -> bool:
    """Is the currently running event loop a ProactorEventLoop?"""
    if ProactorEventLoop is None:
        return False

    return isinstance(get_running_loop(), ProactorEventLoop)


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
