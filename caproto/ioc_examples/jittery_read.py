#!/usr/bin/env python3
from caproto.server import pvproperty, PVGroup
import numpy as np


class JitterRead(PVGroup):
    """
    When a PV is read add some noise.
    """
    def __init__(self, *args, func, **kwargs):
        self._func = func
        super().__init__(*args, **kwargs)

    async def my_read(self, instance):
        return self._func(self.mtr.value, self.exp.value)

    async def clip_write(self, instance, value):
        value = np.clip(value, a_min=0, a_max=None)
        return value

    det = pvproperty(get=my_read, value=[0], dtype=int,
                     read_only=True)
    mtr = pvproperty(value=[0], dtype=float)
    exp = pvproperty(put=clip_write, value=[1], dtype=float)


if __name__ == '__main__':
    # usage: jitter_read.py [PREFIX]
    import sys
    import curio
    from caproto.curio.server import start_server

    N_max = 10000
    sigma = 5
    center = 0

    c = - 1 / (2 * sigma * sigma)

    def jitter_read(m, e):
        print(m, e)
        m = np.asarray(m)
        e = np.asarray(e)
        N = N_max * e * np.exp(c * (m - center)**2)
        print(N.shape)
        return np.random.poisson(N)

    try:
        prefix = sys.argv[1]
    except IndexError:
        prefix = 'jitter_read:'

    ioc = JitterRead(prefix=prefix, func=jitter_read)
    print('PVs:', list(ioc.pvdb))
    curio.run(start_server(ioc.pvdb))
