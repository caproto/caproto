#!/usr/bin/env python3
from textwrap import dedent

from caproto.server import PVGroup, ioc_arg_parser, pvproperty, run


class SimpleIOC(PVGroup):
    """
    An IOC with three uncoupled read/writable PVs.

    Scalar PVs
    ----------
    A (int)
    B (float)

    Array PVs
    ---------
    C (array of int)
    """
    A = pvproperty(
        value=1,
        doc='An integer',
    )
    B = pvproperty(
        value=2.0,
        doc='A float'
    )
    C = pvproperty(
        value=[1, 2, 3],
        doc='An array of integers (max length 3)'
    )


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='simple:',
        desc=dedent(SimpleIOC.__doc__))
    ioc = SimpleIOC(**ioc_options)
    run(ioc.pvdb, **run_options)
