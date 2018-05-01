import collections
import logging
from types import SimpleNamespace


logger = logging.getLogger(__name__)


try:
    import numpy  # noqa
except ImportError:
    default_backend = 'array'
else:
    default_backend = 'numpy'


_backends = {}
backend = None
Backend = collections.namedtuple(
    'Backend',
    'name epics_to_python python_to_epics type_map array_types'
)


def register_backend(new_backend):
    logger.debug('Backend %r registered', new_backend.name)
    _backends[new_backend.name] = new_backend

    if default_backend == new_backend.name and backend is None:
        select_backend(new_backend.name)


def select_backend(name):
    global backend
    logger.debug('Selecting backend: %r', name)
    backend = _backends[name]
    backend_ns.backend_name = backend.name
    backend_ns.python_to_epics = backend.python_to_epics
    backend_ns.epics_to_python = backend.epics_to_python
    backend_ns.type_map = backend.type_map
    backend_ns.array_types = backend.array_types


backend_ns = SimpleNamespace(
    backend_name=None, python_to_epics=None, epics_to_python=None,
    type_map=None, array_types=None
)
