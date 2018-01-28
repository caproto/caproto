import logging
import random

from caproto.benchmarking import set_logging_level
from caproto.curio.server import start_server
from caproto.curio.high_level_server import (pvproperty, PVGroupBase,
                                             PVFunction)


logger = logging.getLogger(__name__)


class MyPVGroup(PVGroupBase):
    'Example group of PVs, where the prefix is defined on instantiation'
    # PV #1: {prefix}random - defaults to dtype of int
    @pvproperty
    async def fixed_random(self, instance):
        logger.debug('read random')
        return random.randint(1, 100)

    @PVFunction(default=[0])
    async def get_random(self,
                         random_low: int=100,
                         random_high: int=1000) -> int:
        random_low, random_high = random_low[0], random_high[0]
        return random.randint(random_low, random_high)


def main(prefix, macros):
    import curio
    from pprint import pprint

    set_logging_level(logging.DEBUG)
    logger.setLevel(logging.DEBUG)
    logging.basicConfig()

    logger.info('Starting up: prefix=%r macros=%r', prefix, macros)
    ioc = MyPVGroup(prefix=prefix, macros=macros)

    # here's what accessing a pvproperty descriptor looks like:
    print(f'fixed_random using the descriptor getter is: {ioc.fixed_random}')
    print(f'get_random using the descriptor getter is: {ioc.get_random}')
    print('get_random has a PVSpec list:')
    for pvspec in ioc.get_random:
        print(f'\t{pvspec!r}')

    # here is the auto-generated pvdb:
    pprint(ioc.pvdb)

    curio.run(start_server, ioc.pvdb)


if __name__ == '__main__':
    main(prefix='prefix:', macros=dict(macro='expanded'))
