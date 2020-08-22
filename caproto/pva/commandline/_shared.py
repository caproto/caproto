import logging

from ..._log import _set_handler_with_logger, set_handler

serialization_logger = logging.getLogger('caproto.pva.serialization')


def configure_logging(verbose: int = 0, *, color=False):
    if not verbose:
        return

    if verbose <= 2:
        for name in ('caproto.pva.ch', 'caproto.pva.ctx'):
            _set_handler_with_logger(color=color, level='DEBUG',
                                     logger_name=name)
    else:
        set_handler(color=color, level='DEBUG')

    if verbose >= 4:
        _set_handler_with_logger(color=color,
                                 level='DEBUG',
                                 logger_name=serialization_logger.name)
    else:
        serialization_logger.setLevel('WARNING')
