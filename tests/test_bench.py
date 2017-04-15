import epics
import pytest
import util
import time


waveform_pv = 'wfioc:wf'

@pytest.fixture(scope='module')
def waveform_ioc():
    # NOTE: have to increase EPICS_CA_MAX_ARRAY_BYTES if NELM >= 4096
    #       (remember default is 16384 bytes / sizeof(int32) = 4096)
    db_text = util.make_database(
        {(waveform_pv, 'waveform'): dict(FTVL='LONG', NELM=4000),
         },
    )

    with util.softioc(db_text=db_text) as ioc:
        time.sleep(0.5)
        yield ioc


def test_waveform(waveform_ioc):
    print(epics.caget(waveform_pv))

    pv = epics.PV(waveform_pv, auto_monitor=False)
    pv.put(list(range(4000)))

    iters = 10000
    with util.timer() as t:
        for i in range(iters):
            pv.get(timeout=0.5)

    time.sleep(1.5)
    print()
    print()
    print('elapsed', t.elapsed, 'iters', iters,
          'per iter', t.elapsed / iters)
