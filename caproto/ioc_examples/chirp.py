#!/usr/bin/env python3
import argparse
import itertools
from caproto.server import pvproperty, PVGroup, template_arg_parser, run


class Chirp(PVGroup):
    """
    One PV updates at a steady rate; another "chirps" (accelerating updates).

    This is useful for benchmarking:

    1. How far can the chirp PV ramp up before a client cannot keep up?
    2. Are the updates from the steady PV processed at regular intervals,
       or are they drowned out by the floor of updates from the chirping one?
    """

    def __init__(self, *args, ramprate, **kwargs):
        super().__init__(*args, **kwargs)
        self.ramprate = ramprate

    chirp = pvproperty(value=0, dtype=float, read_only=True)
    steady = pvproperty(value=0, dtype=float, read_only=True)

    @chirp.startup
    async def chirp(self, instance, async_lib):
        rr = self.ramprate
        period = 0.5
        j = 0
        while True:
            await instance.write(value=j)
            await async_lib.library.sleep(period)
            period *= rr
            j += 1
            if period < 10e-15:
                period = 0.5
                j = 0

    @steady.startup
    async def steady(self, instance, async_lib):
        period = .1
        for j in itertools.count():
            await instance.write(value=j % 1000)
            await async_lib.library.sleep(period)


if __name__ == '__main__':
    parser, split_args = template_arg_parser(
        default_prefix='chirp:',
        desc='One PV updates at a steady rate; another "chirps" (accelerating updates).')

    def in_range(v):
        v = float(v)
        if not (0 < v < 1):
            raise argparse.ArguementTypeError(f" {v} not in range [0, 1]")
        return v

    parser.add_argument('--ramprate',
                        help='The multiplicative factor to apply to the',
                        type=in_range,
                        default=0.75)

    args = parser.parse_args()
    ioc_options, run_options = split_args(args)
    ioc = Chirp(ramprate=args.ramprate, **ioc_options)
    run(ioc.pvdb, **run_options)
