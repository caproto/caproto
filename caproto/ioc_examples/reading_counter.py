#!/usr/bin/env python3
from caproto.server import pvproperty, PVGroup
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
        await instance.write(self.tallies[pv_name])
        return instance.value

    A = pvproperty(get=my_read, value=[0])
    B = pvproperty(get=my_read, value=[0])


if __name__ == '__main__':
    # usage: reading_counter.py <PREFIX>
    import sys
    import curio
    from caproto.curio.server import start_server

    try:
        prefix = sys.argv[1]
    except IndexError:
        prefix = 'reading_counter:'

    ioc = ReadingCounter(prefix=prefix)
    print('PVs:', list(ioc.pvdb))
    curio.run(start_server(ioc.pvdb))
