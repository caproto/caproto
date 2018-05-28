#!/usr/bin/env python3
import logging
from caproto.benchmarking import set_logging_level
from caproto.asyncio.server import start_server
from caproto.server import pvproperty, PVGroup
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
    # usage: currency_conversion.py [PREFIX]
    import sys
    from asyncio import get_event_loop

    try:
        prefix = sys.argv[1]
    except IndexError:
        prefix = 'bc:'

    set_logging_level(logging.DEBUG)
    ioc = BarcodeIOC(prefix=prefix,
                     event_path='/dev/input/event25')
    print('PVs:', list(ioc.pvdb))

    loop = get_event_loop()
    loop.run_until_complete(start_server(ioc.pvdb))
