#!/usr/bin/env python3
from caproto.server import pvproperty, PVGroup
import numpy as np
import time


class JitterRead(PVGroup):
    """
    When a PV is read add some noise.
    """
    def __init__(self, *args, func, **kwargs):
        self._func = func
        super().__init__(*args, **kwargs)

    async def my_read(self, instance):
        return self._func(self.mtr.value,
                          self.exp.value,
                          self.current.value)

    async def clip_write(self, instance, value):
        value = np.clip(value, a_min=0, a_max=None)
        return value

    det = pvproperty(get=my_read, value=[0], dtype=float,
                     read_only=True)
    mtr = pvproperty(value=[0], dtype=float)
    exp = pvproperty(put=clip_write, value=[1], dtype=float)

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

    N_per_I_per_s = 200
    sigma = 5
    center = 0

    c = - 1 / (2 * sigma * sigma)

    def jitter_read(m, e, I):
        m = np.asarray(m)
        e = np.asarray(e)
        I = np.asarray(I)
        N = N_per_I_per_s * I * e * np.exp(c * (m - center)**2)
        return np.random.poisson(N)

    try:
        prefix = sys.argv[1]
    except IndexError:
        prefix = 'jitter_read:'

    ioc = JitterRead(prefix=prefix, func=jitter_read)
    print('PVs:', list(ioc.pvdb))
    curio.run(start_server(ioc.pvdb))
