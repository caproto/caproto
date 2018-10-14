#!/usr/bin/env python3
import os
import sys

from caproto.server import pvproperty, PVGroup, ioc_arg_parser, run
import pathlib


temp_path = pathlib.Path('/tmp' if sys.platform != 'win32'
                         else os.environ.get('TEMP'))


class CustomWrite(PVGroup):
    """
    When a PV is written to, write the new value into a file as a string.
    """
    DIRECTORY = temp_path

    async def my_write(self, instance, value):
        # Compose the filename based on whichever PV this is.
        pv_name = instance.pvspec.attr  # 'A' or 'B', for this IOC
        with open(self.DIRECTORY / pv_name, 'w') as f:
            f.write(str(value))
        print(f'Wrote {value} to {self.DIRECTORY / pv_name}')
        return value

    A = pvproperty(put=my_write, value=0)
    B = pvproperty(put=my_write, value=0)


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='custom_write:',
        desc='Run an IOC with PVs that, when written to, update a file.')
    ioc = CustomWrite(**ioc_options)
    run(ioc.pvdb, **run_options)
