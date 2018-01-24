#!/usr/bin/env python3
from caproto.curio.high_level_server import pvproperty, PVGroupBase


class MacroifiedNames(PVGroupBase):
    """
    
    """
    placeholder1 = pvproperty(value=[0], name='{beamline}:{thing}.VAL')
    placeholder2 = pvproperty(value=[0], name='{beamline}:{thing}.RBV')


if __name__ == '__main__':
    # usage: macros.py <PREFIX> <BEAMLINE> <THING>
    import sys
    import curio
    from caproto.curio.server import start_server

    macros = {'beamline': sys.argv[2], 'thing': sys.argv[3]}
    ioc = MacroifiedNames(prefix=sys.argv[1], macros=macros)
    print('PVs:', list(ioc.pvdb))
    curio.run(start_server(ioc.pvdb))
