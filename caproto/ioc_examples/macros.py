#!/usr/bin/env python3
from caproto.server import pvproperty, PVGroup, ioc_arg_parser, run


class MacroifiedNames(PVGroup):
    """

    """
    placeholder1 = pvproperty(value=0, name='{beamline}:{thing}.VAL')
    placeholder2 = pvproperty(value=0, name='{beamline}:{thing}.RBV')


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='macros:',
        desc='Run an IOC with PVs that have macro-ified names.',
        # Provide default values for macros.
        # Passing None as a default value makes a parameter required.
        macros=dict(beamline='my_beamline', thing='thing'))
    ioc = MacroifiedNames(**ioc_options)
    run(ioc.pvdb, **run_options)
