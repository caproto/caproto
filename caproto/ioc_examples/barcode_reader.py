#!/usr/bin/env python3
"""
This example requires a barcode reader and the Python library evdev.

This only works on linux (as it uses the linux kernel input events).  You
must edit this file to point at the correct file descriptor in /dev/input
for your barcode reader.
"""
from caproto.server import pvproperty, PVGroup, ioc_arg_parser, run
from evdev import InputDevice, categorize


class BarcodeIOC(PVGroup):
    def __init__(self, event_path, **kwargs):
        super().__init__(**kwargs)
        self._event_path = event_path

    barcode = pvproperty(value=[''])

    @barcode.startup
    async def barcode(self, instance, async_lib):
        async for read in barcode_driver(InputDevice(self._event_path)):
            await instance.write(value=read)


async def barcode_driver(dev):
    local = []
    with dev.grab_context():
        async for ev in dev.async_read_loop():
            if ev.type != 1:
                continue
            ev = categorize(ev)
            if ev.keycode == 'KEY_ENTER':
                read = ''.join([
                    ev.keycode.split('_')[1]
                    for ev in local
                    if (ev.keystate and 'SHIFT' not in ev.keycode)
                ])
                if not read:
                    continue
                yield read
                local.clear()

            else:
                local.append(ev)


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='bc:',
        desc='Run an IOC that updates when a barcode is read.',
        supported_async_libs=('asyncio',))
    # Edit this line to point at the correct event
    ioc = BarcodeIOC(event_path='/dev/input/event17', **ioc_options)
    run(ioc.pvdb, **run_options)
