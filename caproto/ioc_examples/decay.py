#!/usr/bin/env python3
from caproto.server import pvproperty, PVGroup, ioc_arg_parser, run
import numpy as np
import time
from textwrap import dedent


class Decay(PVGroup):
    """
    Simulates an exponential decay to a set point.

    Follows :math:`T_{output} = T_{var} exp^{-(t - t_0)/K} + T_{setpoint}`

    The default prefix is `decay:`

    Readonly PVs
    ------------

    I -> the current value
    done -> if the current value is 'close' to the setpoint

    Control PVs
    -----------

    SP -> where to go
    K -> the decay constant
    Tvar -> the scale of the initial excursion
    """
    def _compute_done(self):
        gap = np.abs(self.readback.value - self.setpoint.value)
        gap_i = np.abs(self.setpoint.value - self.Tvar.value)
        # get with in 5%
        return (gap / gap_i) < .05

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._T0 = time.monotonic()

    readback = pvproperty(value=0, dtype=float, read_only=True,
                          name='I',
                          mock_record='ai')

    done = pvproperty(value=0, dtype=float, read_only=True,
                      mock_record='ai')

    setpoint = pvproperty(value=100, dtype=float, name='SP')
    K = pvproperty(value=10, dtype=float)
    Tvar = pvproperty(value=10, dtype=float)

    @readback.scan(period=.1, use_scan_field=True)
    async def readback(self, instance, async_lib):

        def t_rbv(T0, setpoint, K, Tvar,):
            t = time.monotonic()
            return ((Tvar *
                     np.exp(-(t - self._T0) / K)) +
                    setpoint)

        T = t_rbv(T0=self._T0,
                  **{k: getattr(self, k).value
                     for k in ['setpoint', 'K', 'Tvar']})

        await instance.write(value=T)
        done = self._compute_done()
        if self.done.value != done:
            await self.done.write(done)

    @setpoint.putter
    async def setpoint(self, instance, value):
        self._T0 = time.monotonic()
        return value


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='decay:',
        desc=dedent(Decay.__doc__))
    ioc = Decay(**ioc_options)
    run(ioc.pvdb, **run_options)
