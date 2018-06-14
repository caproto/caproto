#!/usr/bin/env python3
"""
This example requires a barcode reader and the Python library evdev.
"""
from caproto.server import pvproperty, PVGroup, ioc_arg_parser, run
from evdev import InputDevice, categorize


class BarcodeIOC(PVGroup):
    def __init__(self, *args, event_path, **kwargs):
        super().__init__(*args, **kwargs)
        self._event_path = event_path

    barcode = pvproperty(value=[''])

    @barcode.startup
    async def barcode(self, instance, async_lib):
        local = []
        dev = InputDevice(self._event_path)
        with dev.grab_context():
            async for ev in dev.async_read_loop():
                if ev.type != 1:
                    continue
                ev = categorize(ev)
                if ev.keycode == 'KEY_ENTER':
                    read = ''.join([ev.keycode.split('_')[1]
                                    for ev in local
                                    if ev.keystate])
                    if not read:
                        continue
                    await instance.write(value=read)
                    local.clear()

                else:
                    local.append(ev)


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='bc:',
        desc='Run an IOC that updates when a barcode is read.',
        supported_async_libs=('asyncio',))
    ioc = BarcodeIOC(event_path='/dev/input/event17', **ioc_options)
    run(ioc.pvdb, **run_options)
