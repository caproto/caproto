#!/usr/bin/env python3

import collections
import ctypes
import multiprocessing
import multiprocessing.managers
import multiprocessing.shared_memory
import textwrap
import threading
import time

import numpy as np

from caproto.server import PVGroup, ioc_arg_parser, pvproperty, run

UPDATE_PERIOD_SEC = 0.001
IMAGE_DTYPE = ctypes.c_uint8
MAX_SIZE = 1024 * 1024 * 3
MAX_BYTE_SIZE = MAX_SIZE * ctypes.sizeof(IMAGE_DTYPE)
NUM_SLOTS = 5


class ImageSlot(ctypes.Structure):
    _fields_ = [
        ('in_use', ctypes.c_bool),
        ('timestamp', ctypes.c_double),
        # ('image', np.ndarray; here in shared memory)
    ]


def find_free_slot(slots):
    """
    Find a free slot to update given a list of :class:`ImageSlot`.

    Returns
    -------
    (index, slot, image)

    Raises
    ------
    RuntimeError
        If no slots are available
    """
    for index, (slot, image) in enumerate(slots):
        if not slot.in_use:
            slot.in_use = True
            return index, slot, image

    raise RuntimeError('No buffers available')


def _slot_from_shared_memory(shm):
    """
    Allocated shared memory buffer -> (ImageSlot, np.ndarray)
    """
    slot = ImageSlot.from_buffer(shm.buf, 0)
    image = np.ndarray(MAX_SIZE, dtype=IMAGE_DTYPE,
                       buffer=shm.buf[ctypes.sizeof(ImageSlot):])
    return slot, image


def image_generator(shared_slots, pipe):
    """
    [multiprocessing subprocess] Generates images + notifies parent

    Parameters
    ----------
    shared_slots : list of multiprocessing.shared_memory.SharedMemory
        Raw shared memory items
    pipe : multiprocessing.Pipe
        Pipe to notify parent process when a new image exists
    """
    index = 0

    slots = [_slot_from_shared_memory(shm) for shm in shared_slots]

    print('Starting up image generator process.')

    iter_count = 0
    while True:
        iter_count = (iter_count + 1) % 255
        try:
            index, slot, image = find_free_slot(slots)
        except RuntimeError:
            # pipe.send('dropped_frame')
            # time.sleep(UPDATE_PERIOD_SEC)
            continue

        slot.timestamp = time.time()
        # set the entire image here:
        image[:] = iter_count
        pipe.send(index)
        time.sleep(UPDATE_PERIOD_SEC)

        ...


def queue_handler_thread(pipe, async_queue):
    """Multiprocessing pipe -> async queue."""
    try:
        while True:
            async_queue.put(pipe.recv())
    except EOFError:
        ...
    except Exception as ex:
        print('Pipe -> queue handler exiting', type(ex), ex)


class SharedMemoryIOC(PVGroup):
    """
    A multiprocessing.shared_memory.SharedMemory-backed IOC.

    ``image`` has a shape (``MAX_SIZE``, ) and is generated in a separate
    process running :func:`image_generator`.

    A :class:`multiprocessing.Pipe` notifies the main process that a new image
    is available in a given shared memory slot, which has some associated
    metadata in :class:`ImageSlot`.

    This pipe is read out and synchronized with the async framework by way
    of :func:`queue_handler_thread`.  This simply receives information from
    the pipe and sends it along to an async_lib-defined ThreadsafeQueue.
    The pvproperty startup hook for ``image`` waits on the queue, updating
    the value and metadata internally and shipping it off to clients by the
    usual :meth:`ChannelData.write` mechanism.

    Vectors PVs
    -----------
    image (int)
    """

    image = pvproperty(value=b'0',
                       max_length=MAX_SIZE,
                       read_only=True,
                       strip_null_terminator=False,
                       )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.manager = multiprocessing.managers.SharedMemoryManager()
        self.manager.start()

        self._shared_slots = [
            self.manager.SharedMemory(
                ctypes.sizeof(ImageSlot) + MAX_BYTE_SIZE
            )
            for _ in range(NUM_SLOTS)
        ]

        self._slots = [
            _slot_from_shared_memory(slot)
            for slot in self._shared_slots
        ]

        self.receive_pipe, send_pipe = multiprocessing.Pipe(duplex=False)

        self.generator_process = multiprocessing.Process(
            target=image_generator,
            kwargs=dict(shared_slots=self._shared_slots,
                        pipe=send_pipe,
                        )
        )

        self.generator_process.start()

    @image.startup
    async def image(self, instance, async_lib):
        """A startup hook for ``image``, which is effectively its main loop."""
        self.async_queue = async_lib.ThreadsafeQueue()
        self.queue_thread = threading.Thread(
            target=queue_handler_thread,
            args=(self.receive_pipe, self.async_queue),
            daemon=True
        )
        self.queue_thread.start()
        timestamp_deltas = collections.deque([], 1000)
        last_timestamp = None

        print_interval = int(1 / UPDATE_PERIOD_SEC) / 2
        slot_counts = {idx: 0 for idx in range(len(self._slots))}
        update_count = 0

        while True:
            idx = await self.async_queue.async_get()
            slot_counts[idx] += 1

            shared_slot, shared_image = self._slots[idx]

            timestamp = shared_slot.timestamp

            await instance.write(memoryview(shared_image).cast('b'),
                                 timestamp=timestamp)

            shared_slot.in_use = False

            if last_timestamp is not None:
                timestamp_deltas.append(timestamp - last_timestamp)
                if update_count % print_interval == 0:
                    average = sum(timestamp_deltas) / len(timestamp_deltas)
                    self.log.warning('Average delta: %f slots: %s', average,
                                     slot_counts)

            last_timestamp = timestamp

            update_count += 1

    @image.shutdown
    async def image(self, instance, async_lib):
        self.log.error('Shutting down the multiprocessing manager...')
        self.manager.shutdown()


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='shm:',
        desc=textwrap.dedent(SharedMemoryIOC.__doc__)
    )
    ioc = SharedMemoryIOC(**ioc_options)
    run(ioc.pvdb, **run_options)
