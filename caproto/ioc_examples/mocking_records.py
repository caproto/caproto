#!/usr/bin/env python3
from caproto.server import pvproperty, PVGroup


class RecordMockingIOC(PVGroup):
    A = pvproperty(value=[1.0], mock_record='ai')
    B = pvproperty(value=[2.0], mock_record='ai',
                   precision=3)

    @B.putter
    async def B(self, instance, value):
        if value == 1:
            # Mocked record will pick up the alarm status simply by use raising
            # an exception in the putter:
            raise ValueError('Invalid value!')


if __name__ == '__main__':
    # usage: simple.py [PREFIX]
    import sys
    import trio
    from caproto.trio.server import start_server

    try:
        prefix = sys.argv[1]
    except IndexError:
        prefix = 'mock:'

    # Instantiate the IOC, assigning a prefix for the PV names.
    ioc = RecordMockingIOC(prefix=prefix)
    print('PVs:', list(ioc.pvdb))

    # ... but what you don't see are all of the analog input record fields
    print('Fields of B:', list(ioc.B.fields.keys()))

    # Run IOC using trio.
    trio.run(start_server, ioc.pvdb)
