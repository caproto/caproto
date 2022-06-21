import os
import sys

__all__ = ()


if sys.platform != 'win32':
    raise ImportError('Do not import this outside of win32')


try:
    import curio  # noqa: F401
except ImportError:
    ...
else:
    if not hasattr(os, "set_blocking"):
        # EVIL_WIN32_TODO_HACK: curio set_blocking monkeypatch
        os.set_blocking = lambda file_no, blocking: None
