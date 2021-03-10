#!/usr/bin/env python3
from textwrap import dedent

from caproto.server import PVGroup, SubGroup, ioc_arg_parser, pvproperty, run
from caproto.server.autosave import AutosaveHelper, autosaved


class AutosavedSubgroup(PVGroup):
    A = autosaved(pvproperty(value=1, record='ao'))
    B = pvproperty(value=2.0)
    C = autosaved(pvproperty(value=[1, 2, 3]))


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

    subgroup = SubGroup(AutosavedSubgroup)


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='autosaved_simple:',
        desc=dedent(AutosavedSimpleIOC.__doc__))
    ioc = AutosavedSimpleIOC(**ioc_options)
    run(ioc.pvdb, **run_options)
