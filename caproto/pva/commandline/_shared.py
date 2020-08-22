import logging

from ..._log import _set_handler_with_logger, set_handler

serialization_logger = logging.getLogger('caproto.pva.serialization')


def configure_logging(verbose: int = 0, *, color=False):
    if not verbose:
        return

    if verbose == 1:
        for name in ('caproto.pva.ch', 'caproto.pva.ctx'):
            _set_handler_with_logger(color=color, level='DEBUG',
                                     logger_name=name)
    elif verbose == 2:
        # Everything is debug:
        set_handler(color=color, level='DEBUG')
        # But no noisy serialization logger
        serialization_logger.setLevel('WARNING')
    else:
        # Everything is debug:
        set_handler(color=color, level='DEBUG')
        # Even the serialization info
        # serialization_logger.setLevel('DEBUG')
