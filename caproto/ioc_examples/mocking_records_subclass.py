#!/usr/bin/env python3
import time
import random

from caproto import ChannelType
from caproto.server import pvproperty, PVGroup, ioc_arg_parser, run
from caproto.server.records import register_record, MotorFields


# Subclass the motor fields here. It's important to use this 'register_record'
# decorator to tell caproto where to find this record:
@register_record
class CustomMotorFields(MotorFields):
    # The custom fields are identified by this string, which is overridden from
    # the superclass _record_type of 'motor':
    _record_type = 'my_motor'

    # To override or extend the motor fields, we have to duplicate them here:
    user_readback_value = pvproperty(name='RBV', dtype=ChannelType.DOUBLE,
                                     doc='User Readback Value', read_only=True)

    # Then we are free to extend the fields as normal pvproperties:
    @user_readback_value.scan(period=0.1)
    async def user_readback_value(self, instance, async_lib):
        setpoint = self.parent.value
        pos = setpoint + random.random() / 100.0
        # Set the use, dial, and then raw readbacks:
        timestamp = time.time()
        await instance.write(pos, timestamp=timestamp)
        await self.dial_readback_value.write(pos, timestamp=timestamp)
        await self.raw_readback_value.write(int(pos * 100000.),
                                            timestamp=timestamp)


class RecordMockingIOC(PVGroup):
    # Define two records, an analog input (ai) record:
    motor1 = pvproperty(value=1.0, mock_record='my_motor')
    motor2 = pvproperty(value=2.0, mock_record='my_motor')


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='mock:',
        desc='Run an IOC that mocks a custom motor record')

    # Instantiate the IOC, assigning a prefix for the PV names.
    ioc = RecordMockingIOC(**ioc_options)
    print('PVs:', list(ioc.pvdb))

    # ... but what you don't see are all of the analog input record fields
    print('Fields of motor1:', list(ioc.motor1.fields.keys()))

    # Run IOC.
    run(ioc.pvdb, **run_options)
