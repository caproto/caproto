#!/usr/bin/env python3
from textwrap import dedent

from caproto.server import PVGroup
from caproto.server import PvpropertyDoubleRO as DoubleRO
from caproto.server import PvpropertyInteger as Integer
from caproto.server import ioc_arg_parser, pvproperty, run


class SimpleIOC(PVGroup):
    """
    An IOC with three uncoupled read/writable PVs.

    Scalar PVs
    ----------
    A (int)
    B (float)
        Read-only double.

    Array PVs
    ---------
    C (array of int)
    """
    # caproto will pick up the data type from the type specifier here:
    A = pvproperty[Integer](value=1, doc="An integer")
    # This is equivalent to:
    # A = pvproperty(value=1, dtype=Integer, doc="An integer")
    # Here we have a read-only double type, using the dtype kwarg.
    # Your static code analyzer should pick up on it just fine:
    B = pvproperty(
        value=2.0,
        dtype=DoubleRO,
        doc="A read-only floating point value"
    )
    C = pvproperty[Integer](
        value=[1, 2, 3],
        doc='An array of integers (max length 3)'
    )

    # If you use mypy, you could use the following in this class definition:
    # reveal_locals()
    # Then
    # $ mypy simple_with_type_hints.py --follow-imports=silent
    # simple_with_type_hints.py:38: note: Revealed local types are:
    # simple_with_type_hints.py:38: note:     A: pvproperty[PvpropertyInteger*]
    # simple_with_type_hints.py:38: note:     B: pvproperty[PvpropertyDoubleRO*]
    # simple_with_type_hints.py:38: note:     C: pvproperty[PvpropertyInteger*]


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='simple:',
        desc=dedent(SimpleIOC.__doc__))

    ioc = SimpleIOC(**ioc_options)
    print("A is", ioc.A.data_type)
    print("B is", ioc.B.data_type)
    print("C is", ioc.C.data_type)

    run(ioc.pvdb, **run_options)
