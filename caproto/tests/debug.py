import contextlib
import weakref
import socket
import threading

import caproto


def make_debug_socket(sockets, counter):
    class DebugSocket(socket.socket):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            counter()
            sockets.add(self)

        def close(self):
            try:
                sockets.remove(self)
            except KeyError:
                ...
            super().close()

    return DebugSocket


def make_debug_thread(counter):
    class DebugThread(threading.Thread):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            counter()

    return DebugThread


_orig_socket = socket.socket
_orig_thread = threading.Thread


@contextlib.contextmanager
def use_debug_socket():
    sockets = weakref.WeakSet()
    counter = caproto.ThreadsafeCounter()
    try:
        socket.socket = make_debug_socket(sockets, counter)
        yield sockets, counter
    finally:
        socket.socket = _orig_socket


@contextlib.contextmanager
def use_thread_counter():
    counter = caproto.ThreadsafeCounter()
    dangling_threads = []
    threads_at_start = set(threading.enumerate())
    try:
        threading.Thread = make_debug_thread(counter)
        yield dangling_threads, counter
    finally:
        final_threads = set(threading.enumerate())
        dangling_threads[:] = list(sorted(final_threads - threads_at_start,
                                          key=lambda th: th.name))
        threading.Thread = _orig_thread
