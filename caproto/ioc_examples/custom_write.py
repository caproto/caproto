#!/usr/bin/env python3
import pathlib
import tempfile
import textwrap

from caproto.server import PVGroup, ioc_arg_parser, pvproperty, run


class CustomWrite(PVGroup):
    """
    When a PV is written to, write the new value into a file as a string.
    """

    async def my_write(self, instance, value):
        # Compose the filename based on whichever PV this is.
        # For this IOC, the following will be: 'A' or 'B'
        filename = pathlib.Path(self.directory.value) / instance.name[-1]
        with open(filename, 'wt') as f:
            print(f"{value}", file=f)

        self.log.warning(f'Wrote {value} to {filename}')
        return value

    directory = pvproperty(
        value=tempfile.gettempdir(),
        doc="The directory to write data to",
        string_encoding='utf-8',
        report_as_string=True,
        max_length=255,
    )

    A = pvproperty(put=my_write, value=0, doc="Writes to (DIRECTORY)/A")
    B = pvproperty(put=my_write, value=0, doc="Writes to (DIRECTORY)/B")


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='custom_write:',
        desc=textwrap.dedent(CustomWrite.__doc__)
    )
    ioc = CustomWrite(**ioc_options)
    run(ioc.pvdb, **run_options)
