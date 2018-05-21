#!/usr/bin/env python3
from caproto.server import (pvproperty, PVGroup, SubGroup)
import numpy as np
import time
import functools
import math


def _arrayify(func):
    @functools.wraps(func)
    def inner(*args):
        return func(*(np.asarray(a) for a in args))
    return inner


class _JitterDetector(PVGroup):

    async def read(self, instance):
        return (await self._read(instance))

    async def clip_write(self, instance, value):
        value = np.clip(value, a_min=0, a_max=None)
        return value

    det = pvproperty(get=read, value=[0],
                     dtype=float,
                     read_only=True)
    mtr = pvproperty(value=[0], dtype=float)

    exp = pvproperty(put=clip_write, value=[1], dtype=float)


class PinHole(_JitterDetector):

    async def _read(self, instance):

        sigma = 5
        center = 0
        c = - 1 / (2 * sigma * sigma)

        @_arrayify
        def jitter_read(m, e, I):
            N = (self.parent.N_per_I_per_s * I * e *
                 np.exp(c * (m - center)**2))
            return np.random.poisson(N)

        return jitter_read(self.mtr.value,
                           self.exp.value,
                           self.parent.current.value)


class Edge(_JitterDetector):
    async def _read(self, instance):

        sigma = 2.5
        center = 5
        c = 1 / sigma

        @_arrayify
        def jitter_read(m, e, I):
            s = math.erfc(c * (-m[0] + center)) / 2
            N = (self.parent.N_per_I_per_s * I * e * s)
            return np.random.poisson(N)

        return jitter_read(self.mtr.value,
                           self.exp.value,
                           self.parent.current.value)


class Slit(_JitterDetector):
    async def _read(self, instance):

        sigma = 2.5
        center = 7.5
        c = 1 / sigma

        @_arrayify
        def jitter_read(m, e, I):
            s = (math.erfc(c * (m[0] - center)) -
                 math.erfc(c * (m[0] + center))) / 2

            N = (self.parent.N_per_I_per_s * I * e * s)
            return np.random.poisson(N)

        return jitter_read(self.mtr.value,
                           self.exp.value,
                           self.parent.current.value)


class MovingDot(PVGroup):
    N = 480
    M = 640

    sigmax = 50
    sigmay = 25

    background = 1000

    Xcen = Ycen = 0

    async def read(self, instance):
        N = self.N
        M = self.M
        back = np.random.poisson(self.background, (N, M))
        x = self.mtrx.value[0]
        y = self.mtry.value[0]

        Y, X = np.ogrid[:N, :M]

        X = X - M/2 + x
        Y = Y - N/2 + y

        X /= self.sigmax
        Y /= self.sigmay

        dot = np.exp(-(X**2 + Y**2)/2)

        I = self.parent.current.value
        e = self.exp.value
        measured = (self.parent.N_per_I_per_s * dot * e * I)

        return (back + np.random.poisson(measured)).ravel()

    det = pvproperty(get=read, value=[0]*N*M,
                     dtype=float,
                     read_only=True)
    mtrx = pvproperty(value=[0], dtype=float)
    mtry = pvproperty(value=[0], dtype=float)

    async def clip_write(self, instance, value):
        value = np.clip(value, a_min=0, a_max=None)
        return value

    exp = pvproperty(put=clip_write, value=[1], dtype=float)


class JitterRead(PVGroup):
    """
    When a PV is read add some noise.
    """

    N_per_I_per_s = 200

    current = pvproperty(value=[500], dtype=float, read_only=True)

    @current.startup
    async def current(self, instance, async_lib):
        f = (2 * np.pi) / 4
        while True:
            t = time.monotonic()
            await instance.write(value=[500 + 25*np.sin(t * f)])
            await async_lib.library.sleep(.05)

    ph = SubGroup(PinHole)
    edge = SubGroup(Edge)
    slit = SubGroup(Slit)

    dot = SubGroup(MovingDot)

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
