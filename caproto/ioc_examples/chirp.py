#!/usr/bin/env python3
import argparse
import textwrap

from caproto.server import PVGroup, pvproperty, run, template_arg_parser


class Chirp(PVGroup):
    """
    One PV updates at a steady rate; another "chirps" (accelerating updates).

    This is useful for benchmarking:

    1. How far can the chirp PV ramp up before a client cannot keep up?
    2. Are the updates from the steady PV processed at regular intervals,
       or are they drowned out by the floor of updates from the chirping one?
    """

    def __init__(self, *args, ramp_rate, **kwargs):
        super().__init__(*args, **kwargs)
        self.ramp_rate = ramp_rate

    chirp = pvproperty(
        value=0.0,
        read_only=True,
        doc="The chirping signal",
    )
    steady = pvproperty(
        value=0,
        read_only=True,
        doc="A steadily updating signal",
    )

    @chirp.startup
    async def chirp(self, instance, async_lib):
        update_period = 0.5
        chirp_value = 0
        while True:
            await instance.write(value=chirp_value)
            await async_lib.sleep(update_period)
            update_period *= self.ramp_rate
            chirp_value += 1
            if update_period < 10e-15:
                update_period = 0.5
                chirp_value = 0

    @steady.scan(period=0.1)
    async def steady(self, instance, async_lib):
        await instance.write(value=(self.steady.value + 1) % 1000)


if __name__ == "__main__":
    parser, split_args = template_arg_parser(
        default_prefix="chirp:",
        desc=textwrap.dedent(Chirp.__doc__),
    )

    def in_range(v):
        v = float(v)
        if not (0 < v < 1):
            raise argparse.ArgumentTypeError(f" {v} not in range [0, 1]")
        return v

    parser.add_argument(
        "--ramprate",
        help="The multiplicative factor to apply when chirping.",
        type=in_range,
        default=0.75,
    )

    args = parser.parse_args()
    ioc_options, run_options = split_args(args)
    ioc = Chirp(ramp_rate=args.ramprate, **ioc_options)
    run(ioc.pvdb, **run_options)
