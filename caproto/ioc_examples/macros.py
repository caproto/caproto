#!/usr/bin/env python3
from textwrap import dedent

from caproto.server import PVGroup, ioc_arg_parser, pvproperty, run


class MacroifiedNames(PVGroup):
    """
    An IOC with PVs that have macro-ified names.

    Required macros: "beamline" and "suffix"

    PVs
    ---
    {beamline}:{suffix}.VAL
    {beamline}:{suffix}.RBV
    """
    placeholder1 = pvproperty(value=0, name='{beamline}:{suffix}.VAL')
    placeholder2 = pvproperty(value=0, name='{beamline}:{suffix}.RBV')


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='macros:',
        desc=dedent(MacroifiedNames.__doc__),
        # Provide default values for macros.
        # Passing None as a default value makes a parameter required.
        macros=dict(beamline='my_beamline', suffix='thing'))
    ioc = MacroifiedNames(**ioc_options)
    run(ioc.pvdb, **run_options)
