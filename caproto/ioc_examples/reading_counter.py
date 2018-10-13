#!/usr/bin/env python3
from caproto.server import pvproperty, PVGroup, ioc_arg_parser, run
import collections


class ReadingCounter(PVGroup):
    """
    Count the number of times that a PV is read.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tallies = collections.Counter()

    async def my_read(self, instance):
        pv_name = instance.pvspec.attr
        self.tallies.update({pv_name: 1})
        print('tallies:', self.tallies)
        # The act of reading this PV changes its value!
        # Weird but sort of interesting.
        await instance.write(self.tallies[pv_name])
        return instance.value

    A = pvproperty(get=my_read, value=0)
    B = pvproperty(get=my_read, value=0)


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='reading_counter:',
        desc="PVs whose value equals the number of times they've been read.")
    ioc = ReadingCounter(**ioc_options)
    run(ioc.pvdb, **run_options)
