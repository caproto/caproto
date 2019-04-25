#!/usr/bin/env python3
from caproto.server import pvproperty, PVGroup, ioc_arg_parser, run
from textwrap import dedent


class ComplexIOC(PVGroup):
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
    A = pvproperty(value=1)
    B = pvproperty(value=2.0)
    C = pvproperty(value=[1, 2, 3])


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='complex:',
        desc=dedent(ComplexIOC.__doc__))
    ioc = ComplexIOC(**ioc_options)
    run(ioc.pvdb, **run_options)
