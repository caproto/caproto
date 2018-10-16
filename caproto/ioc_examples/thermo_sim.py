#!/usr/bin/env python3
from caproto.server import pvproperty, PVGroup, ioc_arg_parser, run
import numpy as np
import time
from textwrap import dedent


class Thermo(PVGroup):
    """
    Simulates (poorly) an oscillating temperature controller.

    Follows :math:`T_{output} = T_{var} exp^{-(t - t_0)/K} sin(ω t) + T_{setpoint}`

    The default prefix is `thermo:`

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
        self._T0 = time.monotonic()

    readback = pvproperty(value=0, dtype=float, read_only=True,
                          name='I',
                          mock_record='ai')

    setpoint = pvproperty(value=100, dtype=float, name='SP')
    K = pvproperty(value=10, dtype=float)
    omega = pvproperty(value=np.pi, dtype=float)
    Tvar = pvproperty(value=10, dtype=float)

    @readback.scan(period=.1, use_scan_field=True)
    async def readback(self, instance, async_lib):

        def t_rbv(T0, setpoint, K, omega, Tvar,):
            t = time.monotonic()
            return ((Tvar *
                     np.exp(-(t - self._T0) / K) *
                     np.sin(omega * t)) +
                    setpoint)

        T = t_rbv(T0=self._T0,
                  **{k: getattr(self, k).value
                     for k in ['setpoint', 'K', 'omega', 'Tvar']})

        await instance.write(value=T)

    @setpoint.putter
    async def setpoint(self, instance, value):
        self._T0 = time.monotonic()
        return value


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='thermo:',
        desc=dedent(Thermo.__doc__))
    ioc = Thermo(**ioc_options)
    run(ioc.pvdb, **run_options)
