#!/usr/bin/env python3
from caproto.server import pvproperty, PVGroup


class MacroifiedNames(PVGroup):
    """

    """
    placeholder1 = pvproperty(value=[0], name='{beamline}:{thing}.VAL')
    placeholder2 = pvproperty(value=[0], name='{beamline}:{thing}.RBV')


if __name__ == '__main__':
    # usage: macros.py <PREFIX> <BEAMLINE> <THING>
    import sys
    import curio
    from caproto.curio.server import start_server

    try:
        prefix = sys.argv[1]
    except IndexError:
        prefix = 'prefix:'

    try:
        beamline = sys.argv[2]
    except IndexError:
        beamline = 'my_beamline'

    try:
        thing = sys.argv[3]
    except IndexError:
        thing = 'thing'

    macros = {'beamline': beamline, 'thing': thing}
    ioc = MacroifiedNames(prefix=prefix, macros=macros)
    print('PVs:', list(ioc.pvdb))
    curio.run(start_server(ioc.pvdb))
