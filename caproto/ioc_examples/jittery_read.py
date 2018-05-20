#!/usr/bin/env python3
from caproto.server import pvproperty, PVGroup
import numpy as np
import time
import functools
import math

def _arrayify(func):
    @functools.wraps(func)
    def inner(*args):
        return func(*(np.asarray(a) for a in args))
    return inner


class JitterRead(PVGroup):
    """
    When a PV is read add some noise.
    """

    N_per_I_per_s = 200

    async def pin_hole_read(self, instance):

        sigma = 5
        center = 0
        c = - 1 / (2 * sigma * sigma)

        @_arrayify
        def jitter_read(m, e, I):
            N = (self.N_per_I_per_s * I * e *
                 np.exp(c * (m - center)**2))
            return np.random.poisson(N)

        return jitter_read(self.ph_mtr.value,
                           self.ph_exp.value,
                           self.current.value)

    async def clip_write(self, instance, value):
        value = np.clip(value, a_min=0, a_max=None)
        return value

    ph_det = pvproperty(get=pin_hole_read, value=[0],
                        dtype=float,
                        read_only=True)
    ph_mtr = pvproperty(value=[0], dtype=float)

    ph_exp = pvproperty(put=clip_write, value=[1], dtype=float)

    async def edge_read(self, instance):

        sigma = 2.5
        center = 5
        c = 1 / sigma

        @_arrayify
        def jitter_read(m, e, I):
            s = math.erfc(c * (-m[0] + center)) / 2
            N = (self.N_per_I_per_s * I * e * s)
            return np.random.poisson(N)

        return jitter_read(self.edge_mtr.value,
                           self.edge_exp.value,
                           self.current.value)

    async def clip_write(self, instance, value):
        value = np.clip(value, a_min=0, a_max=None)
        return value

    edge_det = pvproperty(get=edge_read, value=[0],
                          dtype=float,
                          read_only=True)
    edge_mtr = pvproperty(value=[0], dtype=float)

    edge_exp = pvproperty(put=clip_write, value=[1], dtype=float)

    current = pvproperty(value=[500], dtype=float, read_only=True)

    @current.startup
    async def current(self, instance, async_lib):
        f = (2 * np.pi) / 4
        while True:
            t = time.monotonic()
            await instance.write(value=[500 + 25*np.sin(t * f)])
            await async_lib.library.sleep(.05)


if __name__ == '__main__':
    # usage: jitter_read.py [PREFIX]
    import sys
    import curio
    from caproto.curio.server import start_server

    try:
        prefix = sys.argv[1]
    except IndexError:
        prefix = 'jitter_read:'

    ioc = JitterRead(prefix=prefix)
    print('PVs:', list(ioc.pvdb))
    curio.run(start_server(ioc.pvdb))
