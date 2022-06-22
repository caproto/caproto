import functools
import selectors
import socket
import sys

import curio


@functools.wraps(curio.run)
def curio_run(*args, selector=None, **kwargs):
    """
    Compatibility wrapper for curio.run on Windows.

    See note here: https://github.com/dabeaz/curio/issues/75
    """
    if sys.platform != "win32":
        return curio.run(*args, selector=selector, **kwargs)

    if selector is None:
        dummy_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Windows fails with OSError when select([], [], []) is called - that
        # is, with three empty lists. So, add a socket that will never get used
        # here:
        selector = selectors.DefaultSelector()
        selector.register(dummy_socket, selectors.EVENT_READ)

    return curio.run(*args, selector=selector, **kwargs)
