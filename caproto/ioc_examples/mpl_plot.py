#!/usr/bin/env python3
from caproto.server import pvproperty, PVGroup, ioc_arg_parser, run
from caproto import ChannelType
import numpy as np
import time
from textwrap import dedent
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvas


class Plot(PVGroup):
    """
    Simulates (poorly) an oscillating temperature controller.

    Follows :math:`T_{output} = T_{var} exp^{-(t - t_0)/K} sin(ω t) + T_{setpoint}`

    The default prefix is `thermo:`

    Readonly PVs
    ------------

    fig -> RGBA array of the figure
    x_size, y_size -> size of the figure

    Control PVs
    -----------

    x, y -> the x and y values to plot
    xlabel, ylabel -> axis labels
    lcolor -> line color
    """
    max_data_length = 1040

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._fig = Figure(dpi=200)
        self._canvas = FigureCanvas(self._fig)
        self._ax = self._fig.subplots()
        self._ln, = self._ax.plot([], [])

    fig = pvproperty(value=[], dtype=ChannelType.CHAR, read_only=True,
                     max_length=2000 * 2000 * 4)
    x_size = pvproperty(value=0, dtype=int, read_only=True)
    y_size = pvproperty(value=0, dtype=int, read_only=True)

    x = pvproperty(value=[], dtype=float,
                   max_length=max_data_length)
    y = pvproperty(value=[], dtype=float,
                   max_length=max_data_length)

    async def _render_plot(self, x, y):
        mdl = self.max_data_length

        def fix_data_length(v):
            out = np.ones(mdl) * np.nan
            out[:min(len(v), mdl)] = v[:mdl]
            return out

        x = fix_data_length(x)
        y = fix_data_length(y)

        self._ln.set_data(x, y)
        self._ax.relim()
        self._ax.autoscale_view()
        self._fig.canvas.draw()
        r = self._fig.canvas.get_renderer()
        img = r.buffer_rgba()
        xs, ys = r.get_canvas_width_height()
        await self.fig.write(img)
        await self.x_size.write(xs)
        await self.y_size.write(ys)

    @x.putter
    async def x(self, instance, value):
        y = self.y.value
        await self._render_plot(value, y)

        return value

    @y.putter
    async def y(self, instance, value):
        x = self.x.value
        await self._render_plot(x, value)

        return value


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='plot:',
        desc=dedent(Plot.__doc__))
    ioc = Plot(**ioc_options)
    run(ioc.pvdb, **run_options)
