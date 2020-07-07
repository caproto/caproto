import asyncio


def _get_asyncio_queue(loop: asyncio.AbstractEventLoop = None):
    if loop is None:
        loop = asyncio.get_running_loop()

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
