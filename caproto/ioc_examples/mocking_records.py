#!/usr/bin/env python3
from caproto.server import pvproperty, PVGroup, ioc_arg_parser, run


class RecordMockingIOC(PVGroup):
    # Define three records, an analog input (ai) record:
    A = pvproperty(value=1.0, mock_record='ai')
    # And an analog output (ao) record:
    B = pvproperty(value=2.0, mock_record='ao',
                   precision=3)
    # and an ai with all the bells and whistles
    C = pvproperty(value=0.0,
                   mock_record='ai',
                   upper_alarm_limit=2.0,
                   lower_alarm_limit=-2.0,
                   upper_warning_limit=1.0,
                   lower_warning_limit=-1.0,
                   upper_ctrl_limit=3.0,
                   lower_ctrl_limit=-3.0,
                   units="mm",
                   precision=3)

    @B.putter
    async def B(self, instance, value):
        if value == 1:
            # Mocked record will pick up the alarm status simply by us raising
            # an exception in the putter:
            raise ValueError('Invalid value!')

    # It's also possible to modify some of the behavior of fields on a per-
    # record basis. The following function is called whenever A.RVAL is put to:
    @A.fields.current_raw_value.putter
    async def A(fields, instance, value):
        # However, somewhat confusingly, 'self' in this case is the fields
        # associated with 'A'. To access the IOC (i.e., the main PV group)
        # use the following:
        ioc = fields.parent.group
        print(f'A.RVAL: Writing values to A and B: {value}')
        await ioc.B.write(value)
        await ioc.A.write(value)

    # Similarly, you can refer to the fields by their usual PV name:
    @B.fields.RVAL.putter
    async def B(fields, instance, value):
        ioc = fields.parent.group
        print(f'B.RVAL: Writing modified values to A, B')
        await ioc.B.write(value + 10)
        await ioc.A.write(value - 10)

    # Now that the field specification has been set on B, it can be reused:
    D = pvproperty(value=2.0, mock_record='ao',
                   precision=3, field_spec=B.field_spec)


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='mock:',
        desc='Run an IOC that mocks an ai (analog input) record.')

    # Instantiate the IOC, assigning a prefix for the PV names.
    ioc = RecordMockingIOC(**ioc_options)
    print('PVs:', list(ioc.pvdb))

    # ... but what you don't see are all of the analog input record fields
    print('Fields of B:', list(ioc.B.fields.keys()))

    print('Custom field specifications of A:', RecordMockingIOC.A.fields)
    print('Custom field specifications of B:', RecordMockingIOC.B.fields)

    # Run IOC.
    run(ioc.pvdb, **run_options)
