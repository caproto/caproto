#!/usr/bin/env python3
import threading
import time

from caproto.server import pvproperty, PVGroup, ioc_arg_parser, run


def worker(request_queue):
    while True:
        event, request = request_queue.get()

        # In this toy example, the "request" is some number of seconds to
        # sleep for, but it could be any blocking task.
        print(f'Sleeping for {request} seconds...')
        time.sleep(request)
        event.set()  # Event.set() is a synchronous method
        print('Done')


class WorkerThreadIOC(PVGroup):
    request = pvproperty(value=0, max_length=1)

    # NOTE the decorator used here:
    @request.startup
    async def request(self, instance, async_lib):
        # This method will be called when the server starts up.
        print('* request method called at server startup')
        self.request_queue = async_lib.ThreadsafeQueue()
        self.Event = async_lib.Event

        # Start a separate thread that consumes requests.
        thread = threading.Thread(target=worker,
                                  daemon=True,
                                  kwargs=dict(request_queue=self.request_queue))
        thread.start()

    @request.putter
    async def request(self, instance, value):
        print(f'Sending the request {value} to the worker.')
        event = self.Event()
        await self.request_queue.async_put((event, value))
        # The worker calls Event.set() when the work is done.
        await event.wait()
        return value


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='wt:',
        desc='Run an IOC that does blocking tasks on a worker thread.')

    ioc = WorkerThreadIOC(**ioc_options)
    run(ioc.pvdb, **run_options)
