#!/usr/bin/env python3
import time
from textwrap import dedent

import numpy as np

from caproto.server import PVGroup, ioc_arg_parser, pvproperty, run


def calculate_temperature(T0, setpoint, K, omega, Tvar):
    """
    Calculate temperature according to the following formula:

    :math:`T_{output} = T_{var} exp^{-(t - t_0)/K} sin(ω t) + T_{setpoint}`
    """
    t = time.monotonic()
    return ((Tvar *
             np.exp(-(t - T0) / K) *
             np.sin(omega * t)) +
            setpoint)


class Thermo(PVGroup):
    """
    Simulates (poorly) an oscillating temperature controller.

    The default prefix is ``"thermo:"``.

    Readonly PVs
    ------------

    I -> the current value

    Control PVs
    -----------

    SP -> where to go
    K -> the decay constant
    omega -> the oscillation frequency
    Tvar -> the scale of the oscillations
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.reset_t0()

    readback = pvproperty(
        value=0,
        dtype=float,
        read_only=True,
        name='I',
        record='ai',
        doc="Readback temperature"
    )

    setpoint = pvproperty(
        value=100,
        dtype=float,
        name='SP',
        doc="Setpoint temperature"
    )
    K = pvproperty(
        value=10,
        dtype=float,
        doc="Decay constant"
    )
    omega = pvproperty(
        value=np.pi,
        dtype=float,
        doc="Oscillation frequency"
    )
    Tvar = pvproperty(
        value=10,
        dtype=float,
        doc="Scale of oscillations",
    )

    @readback.scan(period=.1, use_scan_field=True)
    async def readback(self, instance, async_lib):
        await self.readback.write(value=calculate_temperature(
            T0=self._T0,
            setpoint=self.setpoint.value,
            K=self.K.value,
            omega=self.omega.value,
            Tvar=self.Tvar.value,
        ))

    @setpoint.putter
    async def setpoint(self, instance, value):
        self.reset_t0()
        return value

    def reset_t0(self):
        self._T0 = time.monotonic()


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='thermo:',
        desc=dedent(Thermo.__doc__))
    ioc = Thermo(**ioc_options)
    run(ioc.pvdb, **run_options)
