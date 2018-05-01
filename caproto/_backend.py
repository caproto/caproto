# The module global 'backend' is a SimpleNamespace. When a Backend in selected,
# its values are filled into 'backend'. At import time, a default Backend is
# registered and selected. The default depends on whether numpy is available.
import collections
import logging
from types import SimpleNamespace


__all__ = ('backend', 'Backend', 'register_backend', 'select_backend')
logger = logging.getLogger('caproto')


try:
    import numpy  # noqa
except ImportError:
    default_backend = 'array'
else:
    default_backend = 'numpy'


_backends = {}
_initialized = False  # Has any backend be selected yet?
Backend = collections.namedtuple(
    'Backend',
    'name epics_to_python python_to_epics type_map array_types'
)


def register_backend(new_backend):
    logger.debug('Backend %r registered', new_backend.name)
    _backends[new_backend.name] = new_backend

    # Automatically select upon registration if no backend has been selected
    # yet and this backend is the default one.
    if default_backend == new_backend.name and not _initialized:
        select_backend(new_backend.name)


def select_backend(name):
    global _initialized
    _initialized = True
    logger.debug('Selecting backend: %r', name)
    _backend = _backends[name]
    backend.backend_name = _backend.name
    backend.python_to_epics = _backend.python_to_epics
    backend.epics_to_python = _backend.epics_to_python
    backend.type_map = _backend.type_map
    backend.array_types = _backend.array_types


backend = SimpleNamespace(
    backend_name=None, python_to_epics=None, epics_to_python=None,
    type_map=None, array_types=None
)
