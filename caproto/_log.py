# The LogFormatter is adapted light from tornado, which is licensed under
# Apache 2.0. See other_licenses/ in the repository directory.
import fnmatch
import logging
import sys
import warnings
try:
    import colorama
    colorama.init()
except ImportError:
    colorama = None
try:
    import curses
except ImportError:
    curses = None
from ._utils import CaprotoValueError

__all__ = ('color_logs', 'set_handler')


def _stderr_supports_color():
    try:
        if hasattr(sys.stderr, 'isatty') and sys.stderr.isatty():
            if curses:
                curses.setupterm()
                if curses.tigetnum("colors") > 0:
                    return True
            elif colorama:
                if sys.stderr is getattr(colorama.initialise, 'wrapped_stderr',
                                         object()):
                    return True
    except Exception:
        # Very broad exception handling because it's always better to
        # fall back to non-colored logs than to break at startup.
        pass
    return False


class LogFormatter(logging.Formatter):
    """Log formatter used in Tornado, modified for Python3-only caproto.
    Key features of this formatter are:
    * Color support when logging to a terminal that supports it.
    * Timestamps on every log line.
    * Robust against str/bytes encoding problems.
    This formatter is enabled automatically by
    `tornado.options.parse_command_line` or `tornado.options.parse_config_file`
    (unless ``--logging=none`` is used).
    Color support on Windows versions that do not support ANSI color codes is
    enabled by use of the colorama__ library. Applications that wish to use
    this must first initialize colorama with a call to ``colorama.init``.
    See the colorama documentation for details.
    __ https://pypi.python.org/pypi/colorama
    .. versionchanged:: 4.5
       Added support for ``colorama``. Changed the constructor
       signature to be compatible with `logging.config.dictConfig`.
    """
    DEFAULT_FORMAT = \
        '%(color)s[%(levelname)1.1s %(asctime)s %(module)s:%(lineno)d]%(end_color)s %(message)s'
    DEFAULT_DATE_FORMAT = '%y%m%d %H:%M:%S'
    DEFAULT_COLORS = {
        logging.DEBUG: 4,  # Blue
        logging.INFO: 2,  # Green
        logging.WARNING: 3,  # Yellow
        logging.ERROR: 1,  # Red
    }

    def __init__(self, fmt=DEFAULT_FORMAT, datefmt=DEFAULT_DATE_FORMAT,
                 style='%', color=True, colors=DEFAULT_COLORS):
        r"""
        :arg bool color: Enables color support.
        :arg str fmt: Log message format.
          It will be applied to the attributes dict of log records. The
          text between ``%(color)s`` and ``%(end_color)s`` will be colored
          depending on the level if color support is on.
        :arg dict colors: color mappings from logging level to terminal color
          code
        :arg str datefmt: Datetime format.
          Used for formatting ``(asctime)`` placeholder in ``prefix_fmt``.
        .. versionchanged:: 3.2
           Added ``fmt`` and ``datefmt`` arguments.
        """
        super().__init__(datefmt=datefmt)
        self._fmt = fmt

        self._colors = {}
        if color and _stderr_supports_color():
            if curses is not None:
                # The curses module has some str/bytes confusion in
                # python3.  Until version 3.2.3, most methods return
                # bytes, but only accept strings.  In addition, we want to
                # output these strings with the logging module, which
                # works with unicode strings.  The explicit calls to
                # unicode() below are harmless in python2 but will do the
                # right conversion in python 3.
                fg_color = (curses.tigetstr("setaf") or
                            curses.tigetstr("setf") or "")

                for levelno, code in colors.items():
                    self._colors[levelno] = str(curses.tparm(fg_color, code), "ascii")
                self._normal = str(curses.tigetstr("sgr0"), "ascii")
            else:
                # If curses is not present (currently we'll only get here for
                # colorama on windows), assume hard-coded ANSI color codes.
                for levelno, code in colors.items():
                    self._colors[levelno] = '\033[2;3%dm' % code
                self._normal = '\033[0m'
        else:
            self._normal = ''

    def format(self, record):
        record.message = record.getMessage()
        if hasattr(record, 'their_address'):
            record.message = '[%s] %s' % (record.their_address[0] + ':' + str(record.their_address[1]), record.message)
        if hasattr(record, 'direction'):
            record.message = '%s %s' % (record.direction, record.message)
        if hasattr(record, 'our_address'):
            record.message = '[%s] %s' % (record.our_address[0] + ':' + str(record.our_address[1]), record.message)
        if hasattr(record, 'pv'):
            record.message = '[%s] %s' % (record.pv, record.message)
        if hasattr(record, 'role'):
            record.message = '[%s] %s' % (record.role, record.message)

        record.asctime = self.formatTime(record, self.datefmt)

        try:
            record.color = self._colors[record.levelno]
            record.end_color = self._normal
        except KeyError:
            record.color = ''
            record.end_color = ''

        formatted = self._fmt % record.__dict__

        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            formatted = '{}\n{}'.format(formatted.rstrip(), record.exc_text)
        return formatted.replace("\n", "\n    ")


plain_log_format = "[%(levelname)1.1s %(asctime)s.%(msecs)03d %(module)15s:%(lineno)5d] %(message)s"
color_log_format = ("%(color)s[%(levelname)1.1s %(asctime)s.%(msecs)03d "
                    "%(module)15s:%(lineno)5d]%(end_color)s %(message)s")


def color_logs(color):
    """
    If True, add colorful logging handler and ensure plain one is removed.

    If False, do the opposite.
    """
    warnings.warn(f"The function color_logs is deprecated. "
                  f"Use `set_handler(color={color})` instead.")
    set_handler(color=color)


logger = logging.getLogger('caproto')
ch_logger = logging.getLogger('caproto.ch')
search_logger = logging.getLogger('caproto.bcast.search')
current_handler = None  # overwritten below


class LoggerNameFilter(logging.Filter):
    def __init__(self, logger_names, level='NOSET'):
        self.logger_names = logger_names
        self.levelno = validate_level(level)

    def filter(self, record):
        for i in self.logger_names:
            if fnmatch.fnmatch(record.name, i) and record.levelno >= self.levelno:
                return True
        return False


def validate_level(level)-> int:
    '''
    Return a int for level comparison

    '''
    if isinstance(level, int):
        return levelno
        levelno = logging.getLevelName(level)

        return levelno
    else:
        raise CaprotoValueError("The target addresses should given as a list of strings "
                "like 'XX.XX.XX.XX:YYYY' "
                "or tuples like ('XX.XX.XX.XX', YYYY).")

class PVFilter(logging.Filter):
    '''
    Pass through only messages relevant to one or more PV names and
    pv-unrelated messages.

    Parameters
    ----------
    names : string or list of string
        PV name or PV name list which will be filtered in.

    Returns
    -------
    Bool: True or False
        True if message is not PV related which doesn't have 'pv' as key in extra
        True if 'pv' as key exists and pv name exists in Filter list.
        False if message is PV related but pv name isn't in Filter list.
    '''
    def __init__(self, names, level='NOTSET', exclusive=False):
        self.names = names
        self.levelno = validate_level(level)
        self.exclusive = exclusive

    def filter(self, record):
        if record.levelno >= self.levelno:
            return True
        elif hasattr(record, 'pv'):
            for i in self.names:
                if fnmatch.fnmatch(record.pv, i):
                    return True
            return False
        else:
            return not self.exclusive


class AddressFilter(logging.Filter):

    def __init__(self, addresses_list, level='NOTSET', exclusive=False):
        self.addresses_list = []
        self.hosts_list = []
        for address in addresses_list:
            if isinstance(address, str):
                if ':' in address:
                    host, port_as_str = address.split(':')
                    self.addresses_list.append((host, int(port_as_str)))
                else:
                    self.hosts_list.append(address)
            elif isinstance(address, tuple):
                if len(address) == 2:
                    self.addresses_list.append(address)
                else:
                    raise CaprotoValueError("The target addresses should given as a list of strings "
                            "like 'XX.XX.XX.XX:YYYY' "
                            "or tuples like ('XX.XX.XX.XX', YYYY).")
            else:
                raise CaprotoValueError("The target addresses should given as a list of strings "
                        "like 'XX.XX.XX.XX:YYYY' "
                        "or tuples like ('XX.XX.XX.XX', YYYY).")

        self.levelno = validate_level(level)
        self.exclusive = exclusive

    def filter(self, record):
        if record.levelno >= self.levelno:
            return True
        elif hasattr(record, 'our_address') or hasattr(record, 'their_address'):
            return (record.our_address in self.addresses_list
                    or record.our_address[0] in self.hosts_list
                    or record.their_address in self.addresses_list
                    or record.their_address[0] in self.hosts_list)
        else:
            return not self.exclusive


class RoleFilter(logging.Filter):
    def __init__(self, role, level='NOTSET', exclusive=False):
        self.roles = role
        self.levelno = validate_level(level)
        self.exclusive = exclusive

    def filter(self, record):
        if record.levelno >= self.levelno:
            return True
        elif hasattr(record, 'role'):
            return record.role is self.role
        else:
            return not exclusive


def set_handler(file=sys.stdout, datefmt='%H:%M:%S', color=True, level='WARNING'):
    """
    Set a new handler on the ``logging.getLogger('caproto')`` logger.

    This function is run at import time with default paramters. If it is run
    again by the user, the handler from the previous invocation is removed (if
    still present) and replaced.

    Parameters
    ----------
    file : object with ``write`` method or filename string
        Default is ``sys.stdout``.
    datefmt : string
        Date format. Default is ``'%H:%M:%S'``.
    color : boolean
        Use ANSI color codes. True by default.
    level : String of python logging level
        Default is 'WARNING'.

    Returns
    -------
    handler : logging.Handler
        The handler, which has already been added to the 'caproto' logger.

    Examples
    --------
    Log to a file.

    >>> set_handler(file='/tmp/what_is_happening.txt')

    Include the date along with the time. (The log messages will always include
    microseconds, which are configured separately, not as part of 'datefmt'.)

    >>> set_handler(datefmt="%Y-%m-%d %H:%M:%S")

    Turn off ANSI color codes.

    >>> set_handler(color=False)

    Increase verbosity: show level INFO or higher.

    >>> set_handler(level='INFO')
    """
    global current_handler
    if isinstance(file, str):
        handler = logging.FileHandler(file)
    else:
        handler = logging.StreamHandler(file)
    handler.setLevel(level)
    if color:
        format = color_log_format
    else:
        format = plain_log_format
    handler.setFormatter(
        LogFormatter(format, datefmt=datefmt))
    if current_handler in logger.handlers:
        logger.removeHandler(current_handler)
    logger.addHandler(handler)
    current_handler = handler
    return handler


def get_handler():
    return current_handler


# Add a handler with the default parameters at import time.
current_handler = set_handler()
