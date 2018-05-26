# Functions here are imported into _utils.py only on win32

import os
import sys
import socket
import selectors
import functools


__all__ = ['socket_bytes_available']


if sys.platform != 'win32':
    raise ImportError('Do not import this outside of win32')


def socket_bytes_available(sock, *, default_buffer_size=4096,  # noqa
                           available_buffer=None):
    # No support for fcntl/termios on win32
    return default_buffer_size


def _sendmsg(self, buffers, ancdata=None, flags=None, address=None):
    # No support for sendmsg on win32
    # Additionally, sending individual buffers leads to failures, so here we
    # combine all of them (TODO performance)
    to_send = b''.join(buffers)
    self.sendall(to_send)
    return len(to_send)


# EVIL_WIN32_TODO: i know this is evil
socket.socket.sendmsg = _sendmsg


try:
    import curio
except ImportError:
    ...
else:
    # Monkey patch curio.run to use a Windows-compatible selector
    # See note here: https://github.com/dabeaz/curio/issues/75
    def windows_selector():
        dummy_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Windows fails with OSError when select([], [], []) is called - that
        # is, with three empty lists. So, add a socket that will never get used
        # here:
        selector = selectors.DefaultSelector()
        selector.register(dummy_socket, selectors.EVENT_READ)
        return selector

    @functools.wraps(curio.run)
    def curio_run(*args, selector=None, **kwargs):
        if selector is None:
            selector = windows_selector()
        return _curio_core_run(*args, selector=selector, **kwargs)

    _curio_core_run = curio.run
    curio.run = curio_run

    # EVIL_WIN32_TODO_HACK: curio set_blocking monkeypatch
    os.set_blocking = lambda file_no, blocking: None
