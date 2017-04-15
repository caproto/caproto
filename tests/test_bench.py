import os
import time

import curio
import epics
import pytest

import util


waveform_pv = 'wfioc:wf'

@pytest.fixture(scope='module')
def waveform_ioc():
    # NOTE: have to increase EPICS_CA_MAX_ARRAY_BYTES if NELM >= 4096
    #       (remember default is 16384 bytes / sizeof(int32) = 4096)
    max_array_bytes = 1000000
    env = dict(EPICS_CA_MAX_ARRAY_BYTES=str(max_array_bytes))
    nelm = (max_array_bytes // 4) - 4  # timeouts

    db_text = util.make_database(
        {(waveform_pv, 'waveform'): dict(FTVL='LONG', NELM=nelm),
         },
    )

    with util.softioc(db_text=db_text, env=env) as ioc:
        time.sleep(0.5)
        yield ioc


def test_waveform(waveform_ioc):
    from caproto.examples.curio_client import Context

    os.environ['EPICS_CA_MAX_ARRAY_BYTES'] = '1000000'
    print(epics.caget(waveform_pv))

    pv = epics.PV(waveform_pv, auto_monitor=False)

    pyepics_results = []
    curio_results = []
    iters = 1000
    sizes = [4000, 8000, 240000]

    for num in sizes:
        pv.put(list(range(num)))

        with util.timer() as t:
            for i in range(iters):
                values = pv.get(timeout=0.5, as_numpy=True)

        assert list(values) == list(range(num))
        pyepics_results.append((num, t.elapsed))

    async def curio_main():
        # os.environ['EPICS_CA_ADDR_LIST'] = '127.0.0.1'

        ctx = Context()
        await ctx.register()
        await ctx.search(waveform_pv)
        chan1 = await ctx.create_channel(waveform_pv)
        await chan1.wait_for_connection()

        print('connected')
        for num in sizes:
            pv.put(list(range(num)))

            with util.timer() as t:
                for i in range(iters):
                    reading = await chan1.read()
            # TODO
            # assert list(values) == list(range(num))
            curio_results.append((num, t.elapsed))

        await chan1.clear()

    with curio.Kernel() as kernel:
        kernel.run(curio_main())

    time.sleep(1.5)
    print()
    print()
    for name, results in zip(('pyepics', 'caproto/curio'),
                             (pyepics_results, curio_results)):
        print('-- {} --'.format(name))
        for num, elapsed in results:
            print('elements', num, 'elapsed', elapsed, 'iters', iters,
                  'per iter', (elapsed / iters) * 1000, 'ms')
