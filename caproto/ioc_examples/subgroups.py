#!/usr/bin/env python3
import logging
import random
from caproto.server import (pvproperty, PVGroup, SubGroup, ioc_arg_parser, run)


logger = logging.getLogger('caproto')


class RecordLike(PVGroup):
    'Example group, mirroring a V3 record'

    # stop : from being added to the prefix
    attr_separator = ''

    # PV #1: {prefix}.RTYP
    record_type = pvproperty(name='.RTYP', value='ai')
    # PV #2: {prefix}.VAL
    value = pvproperty(name='.VAL', value=1)
    # PV #3: {prefix}.DESC
    description = pvproperty(name='.DESC', value='Description')


class MySubGroup(PVGroup):
    'Example group of PVs, where the prefix is defined on instantiation'
    # PV: {prefix}random - defaults to dtype of int
    @pvproperty
    async def random(self, instance):
        return random.randint(1, 100)


class MyPVGroup(PVGroup):
    'Example group of PVs, a mix of pvproperties and subgroups'

    # PV: {prefix}random
    @pvproperty
    async def random(self, instance):
        logger.debug('read random from %s', type(self).__name__)
        return random.randint(1, 100)

    # PVs: {prefix}RECORD_LIKE1.RTYP, .VAL, and .DESC
    recordlike1 = SubGroup(RecordLike, prefix='RECORD_LIKE1')
    # PVs: {prefix}recordlike2.RTYP, .VAL, and .DESC
    recordlike2 = SubGroup(RecordLike)

    # PV: {prefix}group1:random
    group1 = SubGroup(MySubGroup)
    # PV: {prefix}group2-random
    group2 = SubGroup(MySubGroup, prefix='group2-')

    # PV: {prefix}group3_prefix:random
    @SubGroup(prefix='group3_prefix:')
    class group3(PVGroup):
        @pvproperty
        async def random(self, instance):
            logger.debug('read random from %s', type(self).__name__)
            return random.randint(1, 100)

    # PV: {prefix}group4:subgroup4:random
    # (TODO BUG) {prefix}subgroup4:random
    @SubGroup
    class group4(PVGroup):
        @SubGroup
        class subgroup4(PVGroup):
            @pvproperty
            async def random(self, instance):
                logger.debug('read random from %s', type(self).__name__)
                return random.randint(1, 100)


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='subgroups:',
        desc='Run an IOC with groups of groups of PVs.')
    ioc = MyPVGroup(**ioc_options)

    # here's what accessing a pvproperty descriptor looks like:
    print('random using the descriptor getter is:', ioc.random)

    # and for subgroups:
    print('subgroup4 is:', ioc.group4.subgroup4)
    print('subgroup4.random is:', ioc.group4.subgroup4.random)

    run(ioc.pvdb, **run_options)
