# flake8: noqa F403
from ._utils import *
from ._broadcaster import *
from ._circuit import *
from ._constants import *
from ._commands import *
from ._dbr import *
from ._status import *
from ._data import *
from ._backend import *
from ._array_backend import Array
from . import _numpy_backend  # registers backend on import
del _numpy_backend
from ._log import *

from ._version import get_versions
__version__ = get_versions()['version']
del get_versions

import sys
if sys.platform == 'win32':
    # On Windows, there are some ugly compatibility hacks we need to make.
    from . import _windows_compat  # noqa
del sys
