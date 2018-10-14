#!/usr/bin/env python3
import logging
from caproto.server import pvproperty, PVGroup, ioc_arg_parser, run


logger = logging.getLogger('caproto')


class MyPVGroup(PVGroup):
    'Example group of PVs, where the prefix is defined on instantiation'
    # starting off with something like old-style property-like PVs:

    # PV #1: {prefix}single
    # - has custom read/write methods defined in the wrapped function
    async def single_read(self, instance):
        # NOTE: self is the group, instance is the channeldata instance
        logger.debug('read single')
        return ['a']

    async def single_write(self, instance, value):
        logger.debug('write single %r', value)
        return value

    single = pvproperty(single_read, single_write, value='b')

    async def read_int(self, instance):
        logger.debug('read_int of %s', instance.pvspec.attr)
        return instance.value

    # a set of 3 PVs re-using the same spec-func
    # PV #2: {prefix}testa
    testa = pvproperty(read_int, value=1)
    # PV #3: {prefix}testa
    testb = pvproperty(read_int, value=2)
    # PV #4: {prefix}testa
    testc = pvproperty(read_int, value=3)

    # PV #5: {prefix}{macro}
    macroified = pvproperty(value=0, name='{macro}')

    # - section 2 - with new-style property-like PVs
    # PV #6: {prefix}newstyle
    @pvproperty(value='c')
    async def newstyle(self, instance):
        logger.debug('read newstyle')
        return instance.value

    @newstyle.putter
    async def newstyle(self, instance, value):
        logger.debug('write newstyle %r', value)
        return value

    # PV #7: {prefix}random - defaults to dtype of int
    @pvproperty
    async def random(self, instance):
        logger.debug('read random')
        import random
        return random.randint(1, 100)


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='all_in_one:',
        desc='Run an IOC that is an amalgam of several other examples.',
        macros=dict(macro='expanded'))
    ioc = MyPVGroup(**ioc_options)

    # here's what accessing a pvproperty descriptor looks like:
    print('random using the descriptor getter is:', ioc.random)

    # and the pvspec is accessible as well:
    print('single pvspec is:', ioc.single.pvspec)
    run(ioc.pvdb, **run_options)
