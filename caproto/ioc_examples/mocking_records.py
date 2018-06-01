#!/usr/bin/env python3
from caproto.server import pvproperty, PVGroup, ioc_arg_parser, run


class RecordMockingIOC(PVGroup):
    A = pvproperty(value=[1.0], mock_record='ai')
    B = pvproperty(value=[2.0], mock_record='ai',
                   precision=3)

    @B.putter
    async def B(self, instance, value):
        if list(value) == [1]:
            # Mocked record will pick up the alarm status simply by use raising
            # an exception in the putter:
            raise ValueError('Invalid value!')


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='mock:',
        desc='Run an IOC that mocks at ai record.')

    # Instantiate the IOC, assigning a prefix for the PV names.
    ioc = RecordMockingIOC(**ioc_options)
    print('PVs:', list(ioc.pvdb))

    # ... but what you don't see are all of the analog input record fields
    print('Fields of B:', list(ioc.B.fields.keys()))

    # Run IOC.
    run(ioc.pvdb, **run_options)
