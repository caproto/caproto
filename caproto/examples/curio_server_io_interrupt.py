import termios
import fcntl
import sys
import os
import logging
import threading

import curio
import asks  # for http requests through curio

from caproto.benchmarking import set_logging_level
from caproto.curio.server import start_server
from caproto.curio.high_level_server import pvproperty, PVGroupBase


def start_io_interrupt_monitor(new_value_callback):
    'Thanks stackoverflow and Python 2 FAQ'
    # In actuality, we'd be getting some sort of callback from a 3rd party
    # library, and not polling in a non-async background thread...
    # if you have a better example idea, let me know!

    fd = sys.stdin.fileno()

    oldterm = termios.tcgetattr(fd)
    newattr = termios.tcgetattr(fd)
    newattr[3] &= ~termios.ICANON & ~termios.ECHO
    oldflags = fcntl.fcntl(fd, fcntl.F_GETFL)

    print('Started monitoring the keyboard outside of the async library')
    try:
        termios.tcsetattr(fd, termios.TCSANOW, newattr)
        fcntl.fcntl(fd, fcntl.F_SETFL, oldflags | os.O_NONBLOCK)
        while True:
            try:
                char = sys.stdin.read(1)
            except IOError:
                ...
            else:
                if char:
                    print(f'New keypress: {char!r}')
                    new_value_callback(char)

    finally:
        termios.tcsetattr(fd, termios.TCSAFLUSH, oldterm)
        fcntl.fcntl(fd, fcntl.F_SETFL, oldflags)

    return char


class IOInterruptIOC(PVGroupBase):
    keypress = pvproperty(value=[''])

    @keypress.startup
    async def keypress(self, instance, async_lib):
        'Periodically update the value'
        print('Starting currency conversion')
        queue = async_lib.ThreadsafeQueue()

        thread = threading.Thread(target=start_io_interrupt_monitor,
                                  daemon=True,
                                  kwargs=dict(new_value_callback=queue.put))
        thread.start()

        while True:
            value = await queue.get()
            print(f'Saw new value on async side: {value!r}')
            await self.keypress.write(str(value))


def main(prefix, macros):
    set_logging_level(logging.DEBUG)
    asks.init('curio')
    ioc = IOInterruptIOC(prefix=prefix, macros=macros)
    curio.run(start_server, ioc.pvdb)


if __name__ == '__main__':
    main(prefix='io:', macros={})
