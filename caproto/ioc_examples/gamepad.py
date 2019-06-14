#!/usr/bin/env python3
"""
This example requires a gamepad and the Python library evdev.

This only works on linux (as it uses the linux kernel input events).
"""
from caproto.server import pvproperty, PVGroup, template_arg_parser, run
from evdev import InputDevice


class GampadIOC(PVGroup):
    def __init__(self, event_path, **kwargs):
        super().__init__(**kwargs)
        self._event_path = event_path

    # normal buttons
    a = pvproperty(value=0)
    b = pvproperty(value=0)
    x = pvproperty(value=0)
    y = pvproperty(value=0)
    lb = pvproperty(value=0)
    rb = pvproperty(value=0)

    # joysticks

    # left joystick
    lx = pvproperty(value=0)
    ly = pvproperty(value=0)
    ld = pvproperty(value=0)

    # right joystick, always analog
    rx = pvproperty(value=0)
    ry = pvproperty(value=0)
    rd = pvproperty(value=0)

    # DPAD, depending on mode, may also come from left joystick
    dx = pvproperty(value=0)
    dy = pvproperty(value=0)

    # Trigger buttons
    lt = pvproperty(value=0)
    rt = pvproperty(value=0)

    # admin
    sel = pvproperty(value=0)
    back = pvproperty(value=0)

    alive = pvproperty(value=0)

    @alive.startup
    async def alive(self, instance, async_lib):
        await instance.write(value=1)
        async for target, value in gp_driver(InputDevice(self._event_path)):
            await getattr(self, target).write(value=value)
        await instance.write(value=0)


async def gp_driver(dev):
    analog_mapping = {
        # game pad
        17: 'dy',
        16: 'dx',
        # left joystick
        0: 'lx',
        1: 'ly',
        # triggers
        2: 'lt',
        5: 'rt',
        # right joystick
        4: 'ry',
        3: 'rx',
    }

    digital_mapping = {
        # main buttons
        307: 'x',
        308: 'y',
        305: 'b',
        304: 'a',
        # the triggers
        311: 'rb',
        310: 'lb',

        # admin
        315: 'sel',
        314: 'back',

        # joystick down
        317: 'ld',
        318: 'rd',
    }
    with dev.grab_context():
        async for ev in dev.async_read_loop():
            if ev.type not in (1, 3):
                continue

            # TODO also yield the event timestamp
            if ev.type == 1:
                key = digital_mapping[ev.code]
                yield key, ev.value
            elif ev.type == 3:
                key = analog_mapping[ev.code]
                yield key, ev.value


if __name__ == '__main__':
    parser, split_args = template_arg_parser(
        default_prefix='gp:',
        desc='Run an IOC that updates when gamepad buttons are pressed.',
        supported_async_libs=('asyncio',))

    parser.add_argument('--event',
                        help='The file descriptor in /dev/input to use',
                        required=True, type=str)

    args = parser.parse_args()
    ioc_options, run_options = split_args(args)
    ioc = GampadIOC(event_path=args.event, **ioc_options)
    run(ioc.pvdb, **run_options)
