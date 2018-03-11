#!/usr/bin/env python3
from caproto.curio.high_level_server import pvproperty, PVGroup


class SimpleIOC(PVGroup):
    "An IOC with two simple read/writable PVs"
    A = pvproperty(value=[1])
    B = pvproperty(value=[2])


if __name__ == '__main__':
    # usage: simple.py [PREFIX]
    import sys
    import curio
    from caproto.curio.server import start_server

    try:
        prefix = sys.argv[1]
    except IndexError:
        prefix = 'simple:'

    # Instantiate the IOC, assigning a prefix for the PV names.
    ioc = SimpleIOC(prefix=prefix)
    print('PVs:', list(ioc.pvdb))

    # Run IOC using curio.
    curio.run(start_server(ioc.pvdb))
