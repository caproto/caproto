#!/usr/bin/env python3
from caproto.server import pvproperty, SubGroup, PVGroup, ioc_arg_parser, run
from caproto.server.autosave import autosaved, AutosaveHelper
from textwrap import dedent


class AutosavedSimpleIOC(PVGroup):
    """
    An IOC with three uncoupled read/writable PVs

    Scalar PVs
    ----------
    A (int)
    B (float)

    Vectors PVs
    -----------
    C (vector of int)
    """
    autosave_helper = SubGroup(AutosaveHelper)

    A = autosaved(pvproperty(value=1, record='ao'))
    B = pvproperty(value=2.0)
    C = autosaved(pvproperty(value=[1, 2, 3]))


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='autosaved_simple:',
        desc=dedent(AutosavedSimpleIOC.__doc__))
    ioc = AutosavedSimpleIOC(**ioc_options)
    run(ioc.pvdb, **run_options)
