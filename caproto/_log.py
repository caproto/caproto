import logging
import warnings

try:
    import coloredlogs
except ImportError:
    coloredlogs = None

plain_log_format = "[%(levelname)1.1s %(asctime)s.%(msecs)03d %(module)s:%(lineno)d] %(message)s"
color_log_format = ("[%(levelname)1.1s %(asctime)s.%(msecs)03d "
                    "%(module)s:%(lineno)d] %(message)s")
log_date_format = "%H:%M:%S.%f"


def color_logs(enable, milliseconds=True):
    if coloredlogs is None:
        # I think this is minor enough that we can fail with a warning
        warnings.warn('coloredlogs module not installed')
        return

    logger = logging.getLogger('caproto')
    if enable:
        coloredlogs.install(logger=logger, milliseconds=milliseconds,
                            fmt=color_log_format, log_date_format=log_date_format)
        print('installed logger')
    else:
        ...
        # find ColoredFormatter handler and remove


color_logs(True)
