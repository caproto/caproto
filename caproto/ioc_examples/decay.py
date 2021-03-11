#!/usr/bin/env python3
import time
from textwrap import dedent

import numpy as np

from caproto.server import PVGroup, ioc_arg_parser, pvproperty, run


def calculate_decay(t0, setpoint, k, t_var):
    """
    Calculate decay according to:

    :math:`T_{output} = T_{var} exp^{-(t - t_0)/K} + T_{setpoint}`
    """
    t = time.monotonic()
    return (t_var * np.exp(-(t - t0) / k)) + setpoint


def compute_done(readback, setpoint, t_var, threshold_norm=0.05):
    """Compute the done status."""
    gap = np.abs(readback - setpoint)
    gap_i = np.abs(setpoint - t_var)
    return (gap / gap_i) < threshold_norm


class Decay(PVGroup):
    """
    Simulates an exponential decay to a set point.

    Follows :math:`T_{output} = T_{var} exp^{-(t - t_0)/K} + T_{setpoint}`

    The default prefix is `decay:`

    Read-only PVs
    -------------

    I -> the current value
    done -> if the current value is 'close' to the setpoint

    Control PVs
    -----------

    SP -> where to go
    K -> the decay constant
    Tvar -> the scale of the initial excursion
    """

    readback = pvproperty(
        value=0.0,
        read_only=True,
        name="I",
        record="ai",
        doc="The current readback value.",
    )
    done = pvproperty(
        value=False,
        read_only=True,
        record="bi",
        doc="Whether the current value is 'close' to the setpoint or not.",
    )
    setpoint = pvproperty(
        value=100.0,
        name="SP",
        doc="Where to go - the setpoint.",
    )
    K = pvproperty(
        value=10.0,
        doc="The decay constant.",
    )
    Tvar = pvproperty(
        value=10.0,
        doc="The scale of the initial excursion.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.reset_t0()

    def reset_t0(self):
        self._T0 = time.monotonic()

    @readback.scan(period=0.1, use_scan_field=True)
    async def readback(self, instance, async_lib):
        await self.readback.write(value=calculate_decay(
            t0=self._T0,
            setpoint=self.setpoint.value,
            k=self.K.value,
            t_var=self.Tvar.value,
        ))
        done = compute_done(
            readback=self.readback.value,
            setpoint=self.setpoint.value,
            t_var=self.Tvar.value
        )
        if self.done.value != done:
            await self.done.write(done)

    @setpoint.putter
    async def setpoint(self, instance, value):
        self.reset_t0()


if __name__ == "__main__":
    ioc_options, run_options = ioc_arg_parser(
        default_prefix="decay:", desc=dedent(Decay.__doc__)
    )
    ioc = Decay(**ioc_options)
    run(ioc.pvdb, **run_options)
