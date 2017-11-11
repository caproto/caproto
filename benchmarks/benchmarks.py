import os
import logging

os.environ['EPICS_CA_MAX_ARRAY_BYTES'] = '10000000'

import curio  # noqa
import epics  # noqa
import caproto as ca  # noqa
from caproto.threading.client import (PV as ThreadingPV,  # noqa
                                      SharedBroadcaster,
                                      Context as ThreadingContext)

from caproto.curio.client import Context as CurioContext  # noqa


class _TimeBase:
    ITERS = 100

    def setup(self):
        # epics.ca.clear_cache()
        self.kernel = curio.Kernel()

    def teardown(self):
        pass


def setup():
    shared_broadcaster = SharedBroadcaster()
    ThreadingPV._default_context = ThreadingContext(
        broadcaster=shared_broadcaster, log_level='DEBUG')


def teardown():
    pass


class _TimeWaveform(_TimeBase):
    def setup_pyepics(self):
        self.pyepics_pv = epics.PV(self.waveform_pv, auto_monitor=False)
        assert self.pyepics_pv.wait_for_connection()

        self.pyepics_pv.put(list(range(self.num)), wait=True)
        assert self.pyepics_pv.get(timeout=10., as_numpy=True) is not None

    def setup_threading_client(self):
        self.threading_pv = ThreadingPV(self.waveform_pv, auto_monitor=False)
        assert self.threading_pv.wait_for_connection()

    def setup_curio_client(self):
        async def curio_setup():
            from caproto.curio.client import SharedBroadcaster
            broadcaster = SharedBroadcaster(log_level='ERROR')
            await broadcaster.register()
            ctx = CurioContext(broadcaster, log_level='ERROR')

            await ctx.search(self.waveform_pv)
            chan1 = await ctx.create_channel(self.waveform_pv)
            await chan1.wait_for_connection()
            self.curio_chan1 = chan1

        self.kernel.run(curio_setup())

        assert self.curio_chan1.channel.states[ca.CLIENT] is ca.CONNECTED

    def setup(self):
        super().setup()

        os.system('caget -# 10 {}'.format(self.waveform_pv))
        self.setup_pyepics()
        self.setup_threading_client()
        self.setup_curio_client()

    def teardown(self):
        super().teardown()
        self.kernel.run(shutdown=True)
        self.pyepics_pv.disconnect()

    def time_pyepics(self):
        for i in range(self.ITERS):
            values = self.pyepics_pv.get(timeout=0.5, as_numpy=True)
            assert len(values) == self.num

    def time_caproto_curio(self):
        async def curio_reading():
            for i in range(self.ITERS):
                reading = await self.curio_chan1.read()
                assert len(reading.data) == self.num

        self.kernel.run(curio_reading())

    def time_caproto_threading(self):
        for i in range(self.ITERS):
            values = self.threading_pv.get(timeout=0.5, as_numpy=True)
            assert len(values) == self.num


class TimeWaveform4000(_TimeWaveform):
    waveform_pv = 'wfioc:wf4000'
    num = 4000


class TimeWaveformMillion(_TimeWaveform):
    waveform_pv = 'wfioc:wf1m'
    num = int(1e6)


class TimeWaveform2Million(_TimeWaveform):
    waveform_pv = 'wfioc:wf2m'
    num = int(2e6)


def _bench_test(cls):
    inst = cls()
    print('Setting up bench test...')
    inst.setup()
    for attr in sorted(dir(inst)):
        if attr.startswith('time_'):
            time_fcn = getattr(inst, attr)

            print()
            print('---- {}.{} ----'.format(cls.__name__, attr))
            time_fcn()

    inst.teardown()


if __name__ == '__main__':
    logging.basicConfig()
    logging.getLogger('caproto').setLevel('INFO')
    logging.getLogger('benchmarks.util').setLevel('DEBUG')
    setup()
    _bench_test(TimeWaveform4000)
    _bench_test(TimeWaveformMillion)
    teardown()
