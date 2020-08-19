#!/usr/bin/env python3
from caproto.server import pvproperty, PVGroup, SubGroup, ioc_arg_parser, run
from textwrap import dedent

from caproto.server.records import MotorFields


async def broadcast_precision_to_fields(record):
    """Update precision of all fields to that of the given record."""

    precision = record.precision
    for field, prop in record.field_inst.pvdb.items():
        if hasattr(prop, 'precision'):
            await prop.write_metadata(precision=precision)


class FakeMotor(PVGroup):
    motor = pvproperty(value=0.0, name='', record='motor',
                       precision=3)

    def __init__(self, *args,
                 velocity=0.1,
                 precision=3,
                 acceleration=1.0,
                 resolution=1e-6,
                 tick_rate_hz=10.,
                 **kwargs):
        super().__init__(*args, **kwargs)
        self.tick_rate_hz = tick_rate_hz
        self.defaults = {
            'velocity': velocity,
            'precision': precision,
            'acceleration': acceleration,
            'resolution': resolution,
        }

    @motor.startup
    async def motor(self, instance, async_lib):
        self.async_lib = async_lib

        await self.motor.write_metadata(precision=self.defaults['precision'])
        await broadcast_precision_to_fields(self.motor)

        fields = self.motor.field_inst  # type: MotorFields
        await fields.velocity.write(self.defaults['velocity'])
        await fields.seconds_to_velocity.write(self.defaults['acceleration'])
        await fields.motor_step_size.write(self.defaults['resolution'])

        while True:
            dwell = 1. / self.tick_rate_hz
            target_pos = self.motor.value
            diff = (target_pos - fields.user_readback_value.value)
            # compute the total movement time based an velocity
            total_time = abs(diff / fields.velocity.value)
            # compute how many steps, should come up short as there will
            # be a final write of the return value outside of this call
            num_steps = int(total_time // dwell)

            if abs(diff) < 1e-9:
                await async_lib.library.sleep(dwell)
                continue

            await fields.done_moving_to_value.write(1)
            await fields.done_moving_to_value.write(0)
            await fields.motor_is_moving.write(1)

            readback = fields.user_readback_value.value
            step_size = diff / num_steps if num_steps > 0 else 0.0
            resolution = max((fields.motor_step_size.value, 1e-10))
            for _ in range(num_steps):
                if fields.stop.value != 0:
                    await fields.stop.write(0)
                    await self.motor.write(readback)
                    break
                if fields.stop_pause_move_go.value == 'Stop':
                    await self.motor.write(readback)
                    break

                readback += step_size
                raw_readback = readback / resolution
                await fields.user_readback_value.write(readback)
                await fields.dial_readback_value.write(readback)
                await fields.raw_readback_value.write(raw_readback)
                await async_lib.library.sleep(dwell)
            else:
                # Only executed if we didn't break
                await fields.user_readback_value.write(target_pos)

            await fields.motor_is_moving.write(0)
            await fields.done_moving_to_value.write(1)


class FakeMotorIOC(PVGroup):
    """
    A fake motor IOC, with 3 fake motors.

    PVs
    ---
    mtr1 (motor)
    mtr2 (motor)
    mtr3 (motor)
    """

    motor1 = SubGroup(FakeMotor, velocity=1., precision=3, prefix='mtr1')
    motor2 = SubGroup(FakeMotor, velocity=2., precision=2, prefix='mtr2')
    motor3 = SubGroup(FakeMotor, velocity=3., precision=2, prefix='mtr3')


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='sim:',
        desc=dedent(FakeMotorIOC.__doc__))
    ioc = FakeMotorIOC(**ioc_options)
    run(ioc.pvdb, **run_options)
