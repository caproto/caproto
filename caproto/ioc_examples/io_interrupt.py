#!/usr/bin/env python3
import termios
import fcntl
import sys
import os
import threading
import atexit

from caproto.server import pvproperty, PVGroup, ioc_arg_parser, run


def start_io_interrupt_monitor(new_value_callback):
    '''
    This function monitors the terminal it was run in for keystrokes.
    On each keystroke, it calls new_value_callback with the given keystroke.

    This is used to simulate the concept of an I/O Interrupt-style signal from
    the EPICS world. Those signals depend on hardware to tell EPICS when new
    values are available to be read by way of interrupts - whereas we use
    callbacks here.
    '''

    # Thanks stackoverflow and Python 2 FAQ!
    if not sys.__stdin__.isatty():
        print('[IO Interrupt] stdin is not a TTY, exiting')
        return

    fd = sys.stdin.fileno()

    oldterm = termios.tcgetattr(fd)
    newattr = termios.tcgetattr(fd)
    newattr[3] &= ~termios.ICANON & ~termios.ECHO
    oldflags = fcntl.fcntl(fd, fcntl.F_GETFL)

    print('Started monitoring the keyboard outside of the async library')

    # When the process exits, be sure to reset the terminal settings
    @atexit.register
    def reset_terminal():
        print('Resetting the terminal settings')
        termios.tcsetattr(fd, termios.TCSAFLUSH, oldterm)
        fcntl.fcntl(fd, fcntl.F_SETFL, oldflags)
        print('Done')

    termios.tcsetattr(fd, termios.TCSANOW, newattr)
    fcntl.fcntl(fd, fcntl.F_SETFL, oldflags | os.O_NONBLOCK)

    # Loop forever, sending back keypresses to the callback
    while True:
        try:
            char = sys.stdin.read(1)
        except IOError:
            ...
        else:
            if char:
                print(f'New keypress: {char!r}')
                new_value_callback(char)


class IOInterruptIOC(PVGroup):
    keypress = pvproperty(value='', max_length=10)

    # NOTE the decorator used here:
    @keypress.startup
    async def keypress(self, instance, async_lib):
        # This method will be called when the server starts up.
        print('* keypress method called at server startup')
        queue = async_lib.ThreadsafeQueue()

        # Start a separate thread that monitors keyboard input, telling it to
        # put new values into our async-friendly queue
        thread = threading.Thread(target=start_io_interrupt_monitor,
                                  daemon=True,
                                  kwargs=dict(new_value_callback=queue.put))
        thread.start()

        # Loop and grab items from the queue one at a time
        while True:
            value = await queue.async_get()
            print(f'Saw new value on async side: {value!r}')

            # Propagate the keypress to the EPICS PV, triggering any monitors
            # along the way
            await self.keypress.write(str(value))


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='io:',
        desc='Run an IOC that updates via I/O interrupt on key-press events.')

    ioc = IOInterruptIOC(**ioc_options)
    run(ioc.pvdb, **run_options)
