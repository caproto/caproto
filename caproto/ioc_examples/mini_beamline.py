#!/usr/bin/env python3
"""
This example is quite large. It defines a range of simulated detectors and
motors and is used for demos and tutorials.
"""
import contextvars
import functools
import math
import textwrap
import time

import numpy as np

from caproto.server import PVGroup, SubGroup, ioc_arg_parser, pvproperty, run

internal_process = contextvars.ContextVar("internal_process", default=False)


def no_reentry(func):
    @functools.wraps(func)
    async def inner(*args, **kwargs):
        if internal_process.get():
            return
        try:
            internal_process.set(True)
            return await func(*args, **kwargs)
        finally:
            internal_process.set(False)

    return inner


def _arrayify(func):
    @functools.wraps(func)
    def inner(*args):
        return func(*(np.asarray(a) for a in args))

    return inner


class _JitterDetector(PVGroup):
    """
    A jittery base class which assumes the subclass implements ``_read()``.

    The pvproperty ``det`` will be periodically updated based on the result of
    the subclass ``_read()``.
    """
    det = pvproperty(
        value=0,
        dtype=float,
        read_only=True,
        doc="Scalar detector value",
    )

    @det.scan(period=0.5)
    async def det(self, instance, async_lib):
        value = await self._read()
        await self.det.write(value=value)

    mtr = pvproperty(
        value=0,
        dtype=float,
        precision=3,
        record="ai",
        doc="Motor",
    )
    exp = pvproperty(
        value=1,
        dtype=float,
        doc="Exponential value",
    )
    vel = pvproperty(
        value=1,
        dtype=float,
        doc="Velocity",
    )

    mtr_tick_rate = pvproperty(
        value=10,
        dtype=float,
        units="Hz",
        doc="Update tick rate",
    )

    @exp.putter
    async def exp(self, instance, value):
        value = np.clip(value, a_min=0, a_max=None)
        return value

    @mtr.startup
    async def mtr(self, instance, async_lib):
        instance.ev = async_lib.library.Event()
        instance.async_lib = async_lib

    @mtr.putter
    @no_reentry
    async def mtr(self, instance, value):
        # "tick" at 10Hz
        dwell = 1 / self.mtr_tick_rate.value

        disp = value - instance.value
        # compute the total movement time based an velocity
        total_time = abs(disp / self.vel.value)
        # compute how many steps, should come up short as there will
        # be a final write of the return value outside of this call
        N = int(total_time // dwell)

        for j in range(N):
            # hide a possible divide by 0
            step_size = disp / N
            await instance.write(instance.value + step_size)
            await instance.async_lib.library.sleep(dwell)

        return value


class PinHole(_JitterDetector):
    """A pinhole simulation device."""

    async def _read(self):
        sigma = 5
        center = 0
        c = -1 / (2 * sigma * sigma)

        @_arrayify
        def jitter_read(m, e, intensity):
            N = (
                self.parent.N_per_I_per_s * intensity * e *
                np.exp(c * (m - center) ** 2)
            )
            return np.random.poisson(N)

        return jitter_read(self.mtr.value, self.exp.value, self.parent.current.value)


class Edge(_JitterDetector):
    """An edge simulation device."""

    async def _read(self):
        sigma = 2.5
        center = 5
        c = 1 / sigma

        @_arrayify
        def jitter_read(m, e, intensity):
            s = math.erfc(c * (-m + center)) / 2
            N = self.parent.N_per_I_per_s * intensity * e * s
            return np.random.poisson(N)

        return jitter_read(self.mtr.value, self.exp.value, self.parent.current.value)


class Slit(_JitterDetector):
    """A slit simulation device."""

    async def _read(self):
        sigma = 2.5
        center = 7.5
        c = 1 / sigma

        @_arrayify
        def jitter_read(m, e, intensity):
            s = (math.erfc(c * (m - center)) - math.erfc(c * (m + center))) / 2

            N = self.parent.N_per_I_per_s * intensity * e * s
            return np.random.poisson(N)

        return jitter_read(self.mtr.value, self.exp.value, self.parent.current.value)


class MovingDot(PVGroup):
    N = 480
    M = 640

    sigmax = 50
    sigmay = 25

    background = 1000

    Xcen = 0
    Ycen = 0

    det = pvproperty(
        value=[0] * N * M,
        dtype=float,
        read_only=True,
        doc=f"Detector image ({N}x{M})"
    )

    @det.scan(period=2.0)
    async def det(self, instance, async_lib):
        back = np.random.poisson(self.background, (self.N, self.M))
        if not self.shutter_open.value:
            await self.img_sum.write([back.sum()])
            await instance.write(value=back.ravel())
            return

        Y, X = np.ogrid[:self.N, :self.M]

        X = X - self.M / 2 + self.mtrx.value
        Y = Y - self.N / 2 + self.mtry.value

        X /= self.sigmax
        Y /= self.sigmay

        dot = (
            np.exp(-(X ** 2 + Y ** 2) / 2) *
            np.exp(-(self.mtrx.value ** 2 + self.mtry.value ** 2) / 100 ** 2)
        )

        I = self.parent.current.value  # noqa
        e = self.exp.value
        measured = self.parent.N_per_I_per_s * dot * e * I
        ret = back + np.random.poisson(measured)
        await self.img_sum.write(value=ret.sum())
        await instance.write(value=ret.ravel())

    img_sum = pvproperty(value=0, read_only=True, dtype=float, doc="Image sum")
    mtrx = pvproperty(value=0, dtype=float, doc="Motor X")
    mtry = pvproperty(value=0, dtype=float, doc="Motor Y")

    exp = pvproperty(value=1, dtype=float)

    @exp.putter
    async def exp(self, instance, value):
        """Clip the value to be >= 0."""
        return np.clip(value, a_min=0, a_max=None)

    shutter_open = pvproperty(
        value=1,
        dtype=int,
        doc="Shutter open/close",
    )
    ArraySizeY_RBV = pvproperty(
        value=N,
        dtype=int,
        read_only=True,
        doc='Image array size Y'
    )
    ArraySizeX_RBV = pvproperty(
        value=M,
        dtype=int,
        read_only=True,
        doc='Image array size X'
    )
    ArraySize_RBV = pvproperty(
        value=[N, M],
        dtype=int,
        read_only=True,
        doc='Image array size [Y, X]',
    )


class MiniBeamline(PVGroup):
    """
    A collection of detectors coupled to motors and an oscillating beam
    current.

    An IOC that provides a simulated pinhole, edge and slit with coupled with a
    shared global current that oscillates in time.
    """

    N_per_I_per_s = 200

    current = pvproperty(value=500, dtype=float, read_only=True)

    @current.scan(period=0.1)
    async def current(self, instance, async_lib):
        current = 500 + 25 * np.sin(time.monotonic() * (2 * np.pi) / 4)
        await instance.write(value=current)

    ph = SubGroup(PinHole, doc="Simulated pinhole")
    edge = SubGroup(Edge, doc="Simulated edge")
    slit = SubGroup(Slit, doc="Simulated slit")

    dot = SubGroup(MovingDot, doc="The simulated detector")


if __name__ == "__main__":
    ioc_options, run_options = ioc_arg_parser(
        default_prefix="mini:",
        desc=textwrap.dedent(MiniBeamline.__doc__),
    )

    ioc = MiniBeamline(**ioc_options)
    run(ioc.pvdb, **run_options)
