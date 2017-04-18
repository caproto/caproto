import os
import time

import curio
import epics

from . import util
from caproto.examples.curio_client import Context


WAVEFORM_PV = 'wfioc:wf'


class _TimeWaveform:
    ITERS = 100

    def setup(self):
        # NOTE: have to increase EPICS_CA_MAX_ARRAY_BYTES if NELM >= 4096
        #       (remember default is 16384 bytes / sizeof(int32) = 4096)
        MAX_ARRAY_BYTES = 1000000
        env = dict(EPICS_CA_MAX_ARRAY_BYTES=str(MAX_ARRAY_BYTES))
        nelm = (MAX_ARRAY_BYTES // 4) - 4  # timeouts

        db_text = util.make_database(
            {(WAVEFORM_PV, 'waveform'): dict(FTVL='LONG', NELM=nelm),
            },
        )

        self.cm = util.softioc(db_text=db_text, env=env)
        self.cm.__enter__()
        time.sleep(1)

        os.environ['EPICS_CA_MAX_ARRAY_BYTES'] = str(MAX_ARRAY_BYTES)
        self.pv = epics.PV(WAVEFORM_PV, auto_monitor=False)
        self.pv.put(list(range(self.num)))
        assert self.pv.get(timeout=0.5, as_numpy=True) is not None

        async def curio_setup():
            # os.environ['EPICS_CA_ADDR_LIST'] = '127.0.0.1'

            ctx = Context()
            # await ctx.register()
            ctx.broadcaster._registered = True  # cheat
            ctx.broadcaster.log.setLevel('ERROR')
            await ctx.search(WAVEFORM_PV)
            chan1 = await ctx.create_channel(WAVEFORM_PV)
            await chan1.wait_for_connection()
            self.chan1 = chan1
            chan1.circuit.circuit.log.setLevel('ERROR')

        with curio.Kernel() as kernel:
            kernel.run(curio_setup())

    def teardown(self):
        async def curio_cleanup():
            await self.chan1.clear()

        with curio.Kernel() as kernel:
            kernel.run(curio_cleanup())

        self.cm.__exit__(StopIteration, None, None)

    def time_pyepics(self):
        for i in range(self.ITERS):
            values = self.pv.get(timeout=0.5, as_numpy=True)

    def time_caproto_curio(self):
        async def curio_reading():
            for i in range(self.ITERS):
                reading = await self.chan1.read()

        with curio.Kernel() as kernel:
            kernel.run(curio_reading())


class TimeWaveform4000(_TimeWaveform):
    num = 4000


class TimeWaveformMillion(_TimeWaveform):
    num = int(1e6)
