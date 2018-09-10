#!/usr/bin/env python
# unit-tests for ca interface
# Lifted almost exactly from pyepics

# The epics python module was orignally written by
#
#    Matthew Newville <newville@cars.uchicago.edu>
#    CARS, University of Chicago
#
# There have been several contributions from many others, notably Angus
# Gratton <angus.gratton@anu.edu.au>.  See the Acknowledgements section of
# the documentation for a list of more contributors.
#
# Except where explicitly noted, all files in this distribution are licensed
# under the Epics Open License.:
#
# ------------------------------------------------
#
# Copyright  2010  Matthew Newville, The University of Chicago.  All rights reserved.
#
# The epics python module is distributed subject to the following license conditions:
# SOFTWARE LICENSE AGREEMENT
# Software: epics python module
#
#    1.  The "Software", below, refers to the epics python module (in either
#    source code, or binary form and accompanying documentation). Each
#    licensee is addressed as "you" or "Licensee."
#
#    2.  The copyright holders shown above and their third-party licensors
#    hereby grant Licensee a royalty-free nonexclusive license, subject to
#    the limitations stated herein and U.S. Government license rights.
#
#    3.  You may modify and make a copy or copies of the Software for use
#    within your organization, if you meet the following conditions:
#
#        1. Copies in source code must include the copyright notice and  this
#        Software License Agreement.
#
#        2. Copies in binary form must include the copyright notice and  this
#        Software License Agreement in the documentation and/or other
#        materials provided with the copy.
#
#    4.  You may modify a copy or copies of the Software or any portion of
#    it, thus forming a work based on the Software, and distribute copies of
#    such work outside your organization, if you meet all of the following
#    conditions:
#
#        1. Copies in source code must include the copyright notice and this
#        Software License Agreement;
#
#        2. Copies in binary form must include the copyright notice and this
#        Software License Agreement in the documentation and/or other
#        materials provided with the copy;
#
#        3. Modified copies and works based on the Software must carry
#        prominent notices stating that you changed specified portions of
#        the Software.
#
#    5.  Portions of the Software resulted from work developed under a
#    U.S. Government contract and are subject to the following license: the
#    Government is granted for itself and others acting on its behalf a
#    paid-up, nonexclusive, irrevocable worldwide license in this computer
#    software to reproduce, prepare derivative works, and perform publicly
#    and display publicly.
#
#    6.  WARRANTY DISCLAIMER. THE SOFTWARE IS SUPPLIED "AS IS" WITHOUT
#    WARRANTY OF ANY KIND. THE COPYRIGHT HOLDERS, THEIR THIRD PARTY
#    LICENSORS, THE UNITED STATES, THE UNITED STATES DEPARTMENT OF ENERGY,
#    AND THEIR EMPLOYEES: (1) DISCLAIM ANY WARRANTIES, EXPRESS OR IMPLIED,
#    INCLUDING BUT NOT LIMITED TO ANY IMPLIED WARRANTIES OF MERCHANTABILITY,
#    FITNESS FOR A PARTICULAR PURPOSE, TITLE OR NON-INFRINGEMENT, (2) DO NOT
#    ASSUME ANY LEGAL LIABILITY OR RESPONSIBILITY FOR THE ACCURACY,
#    COMPLETENESS, OR USEFULNESS OF THE SOFTWARE, (3) DO NOT REPRESENT THAT
#    USE OF THE SOFTWARE WOULD NOT INFRINGE PRIVATELY OWNED RIGHTS, (4) DO
#    NOT WARRANT THAT THE SOFTWARE WILL FUNCTION UNINTERRUPTED, THAT IT IS
#    ERROR-FREE OR THAT ANY ERRORS WILL BE CORRECTED.
#
#    7.  LIMITATION OF LIABILITY. IN NO EVENT WILL THE COPYRIGHT HOLDERS,
#    THEIR THIRD PARTY LICENSORS, THE UNITED STATES, THE UNITED STATES
#    DEPARTMENT OF ENERGY, OR THEIR EMPLOYEES: BE LIABLE FOR ANY INDIRECT,
#    INCIDENTAL, CONSEQUENTIAL, SPECIAL OR PUNITIVE DAMAGES OF ANY KIND OR
#    NATURE, INCLUDING BUT NOT LIMITED TO LOSS OF PROFITS OR LOSS OF DATA,
#    FOR ANY REASON WHATSOEVER, WHETHER SUCH LIABILITY IS ASSERTED ON THE
#    BASIS OF CONTRACT, TORT (INCLUDING NEGLIGENCE OR STRICT LIABILITY), OR
#    OTHERWISE, EVEN IF ANY OF SAID PARTIES HAS BEEN WARNED OF THE
#    POSSIBILITY OF SUCH LOSS OR DAMAGES.
#
# ------------------------------------------------

import pytest
numpy = pytest.importorskip("numpy")
import time
import os
import sys
import threading
from types import SimpleNamespace
from contextlib import contextmanager
from caproto.threading.pyepics_compat import (PV, caput, caget, cainfo,
                                              caget_many, caput_many,
                                              AccessRightsException)

from .conftest import default_setup_module, default_teardown_module
from .test_threading_client import context, shared_broadcaster


def setup_module(module):
    default_setup_module(module)

    from caproto.benchmarking.util import set_logging_level

    set_logging_level('DEBUG')


def teardown_module(module):
    default_teardown_module(module)


@pytest.fixture(scope='function')
def pvnames(request, epics_base_ioc, context):
    class PVNames:
        prefix = epics_base_ioc.prefix
        double_pv = prefix + 'ao1'
        double_pv_units = 'microns'
        double_pv_prec = 4
        double_pv2 = prefix + 'ao2'

        pause_pv = prefix + 'pause'
        str_pv = prefix + 'ao1.DESC'
        int_pv = prefix + 'long2'
        long_pv = prefix + 'long2'
        float_pv = prefix + 'ao3'
        enum_pv = prefix + 'mbbo1'
        enum_pv_strs = ['Stop', 'Start', 'Pause', 'Resume']
        proc_pv = prefix + 'ao1.PROC'

        long_arr_pv = prefix + 'long2k'
        double_arr_pv = prefix + 'double2k'
        string_arr_pv = prefix + 'string128'
        char_arr_pv = prefix + 'char128'
        char_arrays = [prefix + 'char128',
                       prefix + 'char2k',
                       prefix + 'char64k']
        long_arrays = [prefix + 'long128',
                       prefix + 'long2k',
                       prefix + 'long64k']
        double_arrays = [prefix + 'double128',
                         prefix + 'double2k',
                         prefix + 'double64k']
        updating_pv1 = prefix + 'ao1'
        updating_str1 = prefix + 'char256'
        updating_pvlist = [prefix + 'ao1',
                           prefix + 'ai1',
                           prefix + 'long1',
                           prefix + 'ao2']
        non_updating_pv = prefix + 'ao4'
        alarm_pv = prefix + 'long1'

        alarm_comp = 'ge'
        alarm_trippoint = 7
        subarr_driver = prefix + 'wave_test'
        subarr1 = prefix + 'subArr1'
        subarr2 = prefix + 'subArr2'
        subarr3 = prefix + 'subArr3'
        subarr4 = prefix + 'subArr4'
        zero_len_subarr1 = prefix + 'ZeroLenSubArr1'

        # TODO: softIoc does not build with motor
        motor1 = 'sim:mtr1'
        motor2 = 'sim:mtr2'

        def __repr__(self):
            return f'<PVNames prefix={epics_base_ioc.prefix}>'

    PV._default_context = context

    def finalize_context():
        print('Cleaning up PV context')
        context.disconnect()
        assert not context._process_search_results_thread.is_alive()
        assert not context._activate_subscriptions_thread.is_alive()
        assert not context.selector.thread.is_alive()
        sb = context.broadcaster
        sb.disconnect()
        assert not sb._command_thread.is_alive()
        assert not sb.selector.thread.is_alive()
        assert not sb._retry_unanswered_searches_thread.is_alive()
        print('Done cleaning up PV context')

    request.addfinalizer(finalize_context)
    return PVNames()


def simulator_main(prefix, ready_event, exit_event):
    'simulator.py from pyepics testioc (same license as above)'
    import random
    from epics import caput as _caput, PV as _PV

    class PV(_PV):
        def put(self, value, **kw):
            rval = repr(value)[:50]
            print(f'(simulator: put {self.pvname} {rval})')
            return super().put(value, **kw)

    def caput(pv, value, **kw):
        rval = repr(value)[:50]
        print(f'(simulator: caput {pv} {rval})')
        return _caput(pv, value, **kw)

    NEEDS_INIT = True
    SLEEP_TIME = 0.10

    def onConnect(pvname=None, conn=None, **kws):
        nonlocal NEEDS_INIT
        NEEDS_INIT = conn

    def make_pvs(*args, **kwds):
        # print("Make PVS '  ", prefix,  args)
        # print( [("%s%s" % (prefix, name)) for name in args])
        pvlist = [PV("%s%s" % (prefix, name)) for name in args]
        for pv in pvlist:
            pv.connect()
            pv.connection_callbacks.append(onConnect)
        return pvlist

    mbbos    = make_pvs("mbbo1", "mbbo2")
    pause_pv = make_pvs("pause",)[0]
    longs    = make_pvs("long1", "long2", "long3", "long4")
    strs     = make_pvs("str1", "str2")
    analogs  =  make_pvs("ao1", "ai1", "ao2", "ao3")
    binaries = make_pvs("bo1", "bi1")

    char_waves = make_pvs("char128", "char256", "char2k", "char64k")
    double_waves = make_pvs("double128", "double2k", "double64k")
    long_waves = make_pvs("long128", "long2k", "long64k")
    str_waves = make_pvs("string128", "string2k", "string64k")

    subarrays =  make_pvs("subArr1", "subArr2", "subArr3", "subArr4" )
    subarray_driver = make_pvs("wave_test",)[0]

    def initialize_data():
        subarray_driver.put(numpy.arange(64)/12.0)

        for p in mbbos:
            p.put(1)

        for i, p in enumerate(longs):
            p.put((i+1))

        for i, p in enumerate(strs):
            p.put(("String %s" % (i+1)))

        for i, p in enumerate(binaries):
            p.put((i+1))

        for i, p in enumerate(analogs):
            p.put((i+1)*1.7135000 )

        caput(f'{prefix}ao1.EGU', 'microns')
        caput(f'{prefix}ao1.PREC', 4)
        caput(f'{prefix}ai1.PREC', 2)
        caput(f'{prefix}ao2.PREC', 3)

        char_waves[0].put([60+random.randrange(30) for i in range(128)])
        char_waves[1].put([random.randrange(256) for i in range(256)])
        char_waves[2].put([random.randrange(256) for i in range(2048)])
        char_waves[3].put([random.randrange(256) for i in range(65536)])

        long_waves[0].put([i+random.randrange(2) for i in range(128)])
        long_waves[1].put([i+random.randrange(128) for i in range(2048)])
        long_waves[2].put([i  for i in range(65536)])

        double_waves[0].put([i+random.randrange(2) for i in range(128)])
        double_waves[1].put([random.random() for i in range(2048)])
        double_waves[2].put([random.random() for i in range(65536)])

        pause_pv.put(0)
        str_waves[0].put([(" String %i" % (i+1)) for i in range(128)])
        print('Data initialized')

    text = '''line 1
this is line 2
and line 3
here is another line
this is the 5th line
line 6
line 7
line 8
line 9
line 10
line 11
'''.split('\n')

    start_time = time.time()
    count = 0
    long_update = 0
    lcount = 1
    initialized_at = 0

    while not exit_event.is_set():
        if NEEDS_INIT:
            initialize_data()
            time.sleep(SLEEP_TIME)
            NEEDS_INIT = False
            initialized_at = count

        time.sleep(SLEEP_TIME)

        count = count + 1
        if not NEEDS_INIT and count >= initialized_at + 4:
            if not ready_event.is_set():
                ready_event.set()
                print('[Pyepics simulator running!]')
        if count > 99999999:
            count = 1

        t0 = time.time()
        if pause_pv.get() == 1:
            # pause for up to 120 seconds if pause was selected
            t0 = time.time()
            while time.time()-t0 < 120:
                time.sleep(SLEEP_TIME)
                if pause_pv.get() == 0:
                    break
                elif exit_event.is_set():
                    break
            pause_pv.put(0)

        if exit_event.is_set():
            break

        noise = numpy.random.normal

        analogs[0].put(100*(random.random()-0.5))
        analogs[1].put(76.54321*(time.time()-start_time))
        analogs[2].put(0.3*numpy.sin(time.time() / 2.302) + noise(scale=0.4))
        char_waves[0].put([45+random.randrange(64)
                           for i in range(128)])

        if count % 3 == 0:
            analogs[3].put(
                numpy.exp((max(0.001, noise(scale=0.03) +
                               numpy.sqrt((count/16.0) % 87.)))))

            long_waves[1].put([i+random.randrange(128)
                               for i in range(2048)])
            str_waves[0].put([("Str%i_%.3f" % (i+1, 100*random.random()))
                              for i in range(128)])

        if t0-long_update >= 1.0:
            long_update=t0
            lcount = (lcount + 1) % 10
            longs[0].put(lcount)
            char_waves[1].put(text[lcount])
            double_waves[2].put([random.random()
                                 for i in range(65536)])
            double_waves[1].put([random.random()
                                 for i in range(2048)])

    print('[Simulator loop exiting]')


@pytest.fixture(scope='function')
def simulator(request, pvnames):
    prefix = pvnames.prefix
    ready_event = threading.Event()
    exit_event = threading.Event()
    kwargs = dict(prefix=pvnames.prefix,
                  ready_event=ready_event,
                  exit_event=exit_event)

    print()
    print()
    print(f'* Starting up simulator for prefix: {prefix}')
    thread = threading.Thread(target=simulator_main, kwargs=kwargs)
    thread.start()

    def stop_simulator():
        print()
        print(f'* Joining simulator thread')
        exit_event.set()
        thread.join(timeout=2)
        print()
        if thread.is_alive():
            print(f'* Dangling simulator thread (prefix={prefix})... :(')
        else:
            print(f'* Simulator thread exited cleanly (prefix={prefix})')

    request.addfinalizer(stop_simulator)
    ok = ready_event.wait(15)

    if not ok:
        raise TimeoutError('Simulator thread failed to start!')

    print()
    print(f'* Simulator thread started up! (prefix={prefix})')
    return thread


@contextmanager
def no_simulator_updates(pvnames):
    '''Context manager which pauses and resumes simulator PV updating'''
    try:
        caput(pvnames.pause_pv, 1)
        time.sleep(0.1)
        yield
    finally:
        caput(pvnames.pause_pv, 0)
        # Give the simulator some time to start back up
        time.sleep(0.5)


@pytest.mark.flaky(reruns=5, reruns_delay=2)
def testA_CreatePV(pvnames):
    print('Simple Test: create pv\n')
    pv = PV(pvnames.double_pv)
    assert pv is not None


@pytest.mark.flaky(reruns=5, reruns_delay=2)
def testA_CreatedWithConn(pvnames):
    print('Simple Test: create pv with conn callback\n')
    CONN_DAT = {}

    def onConnect(pvname=None, conn=None, chid=None, **kws):
        nonlocal CONN_DAT
        print('  :Connection status changed:  %s  connected=%s\n' % (pvname, conn))
        CONN_DAT[pvname] = conn

    print(f'Connecting to {pvnames.int_pv}')
    pv = PV(pvnames.int_pv, connection_callback=onConnect)
    val = pv.get(timeout=5)

    conn = CONN_DAT.get(pvnames.int_pv, None)
    assert conn


def test_caget(pvnames):
    print('Simple Test of caget() function\n')
    pvs = (pvnames.double_pv, pvnames.enum_pv, pvnames.str_pv)
    for p in pvs:
        val = caget(p)
        assert val is not None
    sval = caget(pvnames.str_pv)
    assert sval == 'ao'


def test_smoke_cainfo(pvnames):
    print('Simple Test of caget() function\n')
    pvs = (pvnames.double_pv, pvnames.enum_pv, pvnames.str_pv)
    for p in pvs:
        for print_out in (True, False):
            val = cainfo(p, print_out=print_out)
            if not print_out:
                assert val is not None


def test_caget_many(pvnames):
    print('Simple Test of caget_many() function\n')
    pvs = [pvnames.double_pv, pvnames.enum_pv, pvnames.str_pv]
    vals = caget_many(pvs)
    assert len(vals) == len(pvs)
    assert isinstance(vals[0], float)
    print(type(vals[1]))
    assert isinstance(vals[1], (int, numpy.uint16))
    assert isinstance(vals[2], str)


def test_caput_many_wait_all(pvnames):
    print('Test of caput_many() function, waiting for all.\n')
    pvs = [pvnames.double_pv, pvnames.enum_pv, 'ceci nest pas une PV']
    vals = [0.5, 0, 23]
    t0 = time.time()
    success = caput_many(pvs, vals, wait='all', connection_timeout=0.5,
                         put_timeout=5.0)
    t1 = time.time()
    assert len(success) == len(pvs)
    assert success[0] == 1
    assert success[1] == 1
    assert success[2] < 0


def test_caput_many_wait_each(pvnames):
    print('Simple Test of caput_many() function, waiting for each.\n')
    pvs = [pvnames.double_pv, pvnames.enum_pv, 'ceci nest pas une PV']
    #pvs = ["MTEST:Val1", "MTEST:Val2", "MTEST:SlowVal"]
    vals = [0.5, 0, 23]
    success = caput_many(pvs, vals, wait='each', connection_timeout=0.5,
                         put_timeout=1.0)
    assert len(success) == len(pvs)
    assert success[0] == 1
    assert success[1] == 1
    assert success[2] < 0


def test_caput_many_no_wait(pvnames):
    print('Simple Test of caput_many() function, without waiting.\n')
    pvs = [pvnames.double_pv, pvnames.enum_pv, 'ceci nest pas une PV']
    vals = [0.5, 0, 23]
    success = caput_many(pvs, vals, wait=None, connection_timeout=0.5)
    assert len(success) == len(pvs)
    # If you don't wait, ca.put returns 1 as long as the PV connects
    # and the put request is valid.
    assert success[0] == 1
    assert success[1] == 1
    assert success[2] < 0


def test_get1(pvnames):
    print('Simple Test: test value and char_value on an integer\n')
    pv = PV(pvnames.int_pv)
    val = pv.get()
    cval = pv.get(as_string=True)

    assert int(cval) == val


@pytest.mark.xfail(os.environ.get('BASE') in ('R3.16.1', 'R7.0.1.1'),
                   reason='known issues with simulator on some BASE versions')
def test_get_string_waveform(pvnames, simulator):
    print('String Array: \n')
    with no_simulator_updates(pvnames):
        pv = PV(pvnames.string_arr_pv)
        val = pv.get()
        assert len(val) > 10
        assert isinstance(val[0], str)
        assert len(val[0]) > 1
        assert isinstance(val[1], str)
        assert len(val[1]) > 1


def test_put_string_waveform(pvnames):
    print('String Array: \n')
    with no_simulator_updates(pvnames):
        pv = PV(pvnames.string_arr_pv)
        put_value = ['a', 'b', 'c']
        pv.put(put_value)
        get_value = pv.get(use_monitor=False, count=len(put_value))
        numpy.testing.assert_array_equal(get_value, put_value)


@pytest.mark.skipif(os.environ.get("CAPROTO_SKIP_MOTORSIM_TESTS") is not None,
                    reason='No motorsim IOC')
@pytest.mark.skipif(sys.platform == 'win32',
                    reason='win32 motorsim IOC')
def test_putcomplete(pvnames):
    print('Put with wait and put_complete (using real motor!) \n')
    vals = (1.35, 1.50, 1.44, 1.445, 1.45, 1.453, 1.446, 1.447, 1.450,
            1.450, 1.490, 1.5, 1.500)
    p = PV(pvnames.motor1)
    if not p.wait_for_connection():
        raise TimeoutError('simulated motor connection failed?')

    see_complete = []
    for v in vals:
        t0 = time.time()
        p.put(v, use_complete=True)
        count = 0
        for i in range(100000):
            time.sleep(0.001)
            count = count + 1
            if p.put_complete:
                see_complete.append(True)
                print('See completion')
                break
            # print('made it to value= %.3f, elapsed time= %.4f sec (count=%i)' % (v, time.time()-t0, count))
    assert len(see_complete) > (len(vals) - 5)


@pytest.mark.skipif(os.environ.get("CAPROTO_SKIP_MOTORSIM_TESTS") is not None,
                    reason='No motorsim IOC')
@pytest.mark.skipif(sys.platform == 'win32',
                    reason='win32 motorsim IOC')
def test_putwait(pvnames):
    print('Put with wait (using real motor!) \n')
    pv = PV(pvnames.motor1)
    if not pv.wait_for_connection():
        raise TimeoutError('simulated motor connection failed?')

    val = pv.get()

    t0 = time.time()
    if val < 5:
        pv.put(val + 1.0, wait=True)
    else:
        pv.put(val - 1.0, wait=True)
    dt = time.time()-t0
    print('    put took %s sec\n' % dt)
    assert dt > 0.1

    # now with a callback!
    put_callback_called = False

    def onPutdone(pvname=None, **kws):
        print('put done ', pvname, kws)
        nonlocal put_callback_called
        put_callback_called = True
    val = pv.get()
    if  val < 5:
        pv.put(val + 1.0, callback=onPutdone)
    else:
        pv.put(val - 1.0, callback=onPutdone)

    t0 = time.time()
    while time.time()-t0 < dt*1.50:
        time.sleep(0.02)

    print('    put should be done by now?  %s \n' % put_callback_called)
    assert put_callback_called

    # now using pv.put_complete
    val = pv.get()
    if  val < 5:
        pv.put(val + 1.0, use_complete=True)
    else:
        pv.put(val - 1.0, use_complete=True)
    t0 = time.time()
    count = 0
    while time.time()-t0 < dt*1.50:
        if pv.put_complete:
            break
        count = count + 1
        time.sleep(0.02)
    print('    put_complete=%s (should be True), and count=%i (should be>3)\n' %
          (pv.put_complete, count))
    assert pv.put_complete
    assert count > 3


@pytest.mark.xfail(os.environ.get('BASE') in ('R3.16.1', 'R7.0.1.1'),
                   reason='known issues with simulator on some BASE versions')
def test_get_callback(pvnames, simulator):
    print("Callback test:  changing PV must be updated\n")
    mypv = PV(pvnames.updating_pv1)
    NEWVALS = []

    def onChanges(pvname=None, value=None, char_value=None, **kw):
        nonlocal NEWVALS
        print('PV %s %s, %s Changed!\n' % (pvname, repr(value), char_value))
        NEWVALS.append(repr(value))

    mypv.add_callback(onChanges)
    print('Added a callback.  Now wait for changes...\n')

    t0 = time.time()
    while time.time() - t0 < 3:
        time.sleep(1.e-4)
    print('   saw %i changes.\n' % len(NEWVALS))
    assert len(NEWVALS) > 3
    mypv.clear_callbacks()


def test_subarrays(pvnames):
    print("Subarray test:  dynamic length arrays\n")
    driver = PV(pvnames.subarr_driver)
    subarr1 = PV(pvnames.subarr1)
    subarr1.connect()

    len_full = 64
    len_sub1 = 16
    full_data = numpy.arange(len_full)/1.0

    caput("%s.NELM" % pvnames.subarr1, len_sub1)
    caput("%s.INDX" % pvnames.subarr1, 0)

    driver.put(full_data)
    time.sleep(0.1)
    subval = subarr1.get()

    assert len(subval) == len_sub1
    assert numpy.all(subval == full_data[:len_sub1])
    print("Subarray test:  C\n")
    caput("%s.NELM" % pvnames.subarr2, 19)
    caput("%s.INDX" % pvnames.subarr2, 3)

    subarr2 = PV(pvnames.subarr2)
    subarr2.get()

    driver.put(full_data)
    time.sleep(0.1)
    subval = subarr2.get()

    assert len(subval) == 19
    assert numpy.all(subval == full_data[3:3+19])

    caput("%s.NELM" % pvnames.subarr2, 5)
    caput("%s.INDX" % pvnames.subarr2, 13)

    driver.put(full_data)
    time.sleep(0.1)
    subval = subarr2.get()

    assert len(subval) == 5
    assert numpy.all(subval == full_data[13:5+13])


def test_subarray_zerolen(pvnames):
    subarr1 = PV(pvnames.zero_len_subarr1)
    subarr1.wait_for_connection()

    val = subarr1.get(use_monitor=True, as_numpy=True)
    assert isinstance(val, numpy.ndarray), 'using monitor'
    assert len(val) == 0, 'using monitor'
    # caproto returns things in big endian, not native type
    # assert val.dtype == numpy.float64, 'using monitor'

    val = subarr1.get(use_monitor=False, as_numpy=True)
    assert isinstance(val, numpy.ndarray), 'no monitor'
    assert len(val) == 0, 'no monitor'
    # caproto returns things in big endian, not native type
    # assert val.dtype == numpy.float64, 'no monitor'


def test_waveform_get_with_count_arg(pvnames):
    wf = PV(pvnames.char_arr_pv, count=32)
    val=wf.get()
    assert len(val) == 32

    val=wf.get(count=wf.nelm)
    assert len(val) == wf.nelm


@pytest.mark.xfail(os.environ.get('BASE') in ('R3.16.1', 'R7.0.1.1'),
                   reason='known issues with simulator on some BASE versions')
def test_waveform_callback_with_count_arg(pvnames, simulator):
    values = []

    wf = PV(pvnames.char_arr_pv, count=32)
    def onChanges(pvname=None, value=None, char_value=None, **kw):
        print('PV %s %s, %s Changed!\n' % (pvname, repr(value), char_value))
        values.append(value)

    wf.add_callback(onChanges)
    print('Added a callback.  Now wait for changes...\n')

    t0 = time.time()
    while time.time() - t0 < 3:
        time.sleep(1.e-4)
        if len(values)>0:
            break

    assert len(values) > 0
    assert len(values[0]) == 32

    wf.clear_callbacks()


def test_emptyish_char_waveform_no_monitor(pvnames):
    '''a test of a char waveform of length 1 (NORD=1): value "\0"
    without using auto_monitor
    '''
    zerostr = PV(pvnames.char_arr_pv, auto_monitor=False)
    zerostr.wait_for_connection()

    # elem_count = 128, requested count = None, libca returns count = 1
    zerostr.put([0], wait=True)
    assert zerostr.get(as_string=True) == ''
    numpy.testing.assert_array_equal(zerostr.get(as_string=False), [0])
    assert zerostr.get(as_string=True, as_numpy=False) == ''
    numpy.testing.assert_array_equal(zerostr.get(as_string=False, as_numpy=False), [0])

    # elem_count = 128, requested count = None, libca returns count = 2
    zerostr.put([0, 0], wait=True)
    assert zerostr.get(as_string=True) == ''
    numpy.testing.assert_array_equal(zerostr.get(as_string=False), [0, 0])
    assert zerostr.get(as_string=True, as_numpy=False) == ''
    numpy.testing.assert_array_equal(zerostr.get(as_string=False,
                                                 as_numpy=False), [0, 0])


def test_emptyish_char_waveform_monitor(pvnames):
    '''a test of a char waveform of length 1 (NORD=1): value "\0"
    with using auto_monitor
    '''
    zerostr = PV(pvnames.char_arr_pv, auto_monitor=True)
    zerostr.wait_for_connection()

    zerostr.put([0], wait=True)
    time.sleep(0.2)

    assert zerostr.get(as_string=True) == ''
    numpy.testing.assert_array_equal(zerostr.get(as_string=False), [0])
    assert zerostr.get(as_string=True, as_numpy=False) == ''
    numpy.testing.assert_array_equal(zerostr.get(as_string=False, as_numpy=False), [0])

    zerostr.put([0, 0], wait=True)
    time.sleep(0.2)

    assert zerostr.get(as_string=True) == ''
    numpy.testing.assert_array_equal(zerostr.get(as_string=False), [0, 0])
    assert zerostr.get(as_string=True, as_numpy=False) == ''
    numpy.testing.assert_array_equal(zerostr.get(as_string=False, as_numpy=False), [0, 0])

    zerostr.disconnect()


def testEnumPut(pvnames):
    pv = PV(pvnames.enum_pv)
    assert pv is not None
    pv.put('Stop')
    time.sleep(0.1)
    val = pv.get()
    assert val == 0
    assert pv.get(as_string=True) == 'Stop'


@pytest.mark.xfail(os.environ.get('BASE') in ('R3.16.1', 'R7.0.1.1'),
                   reason='known issues with simulator on some BASE versions')
def test_DoubleVal(pvnames, simulator):
    pvn = pvnames.double_pv
    pv = PV(pvn)
    print('pv', pv)
    value = pv.get()
    print('pv get', value)
    assert pv.connected

    print('%s get value %s' % (pvn, value))
    cdict = pv.get_ctrlvars()
    print('Testing CTRL Values for a Double (%s)\n'   % (pvn))
    assert 'severity' in cdict
    assert len(pv.host) > 1
    assert pv.count == 1
    assert pv.precision == pvnames.double_pv_prec
    assert pv.units == pvnames.double_pv_units
    assert pv.access.startswith('read')


def test_waveform_get_1elem(pvnames):
    pv = PV(pvnames.double_arr_pv)
    val = pv.get(count=1, use_monitor=False)
    assert isinstance(val, numpy.ndarray)
    assert len(val) == 1


def test_subarray_1elem(pvnames):
    # pv = PV(pvnames.zero_len_subarr1)
    pv = PV(pvnames.double_arr_pv)
    pv.wait_for_connection()
    val = pv.get(count=1, use_monitor=False)
    print('val is', val, type(val))
    assert isinstance(val, numpy.ndarray)
    assert len(val) == 1

    val = pv.get(count=1, as_numpy=False, use_monitor=False)
    print('val is', val, type(val))
    assert isinstance(val, list)
    assert len(val) == 1


@pytest.mark.skipif(os.environ.get("CAPROTO_SKIP_MOTORSIM_TESTS") is not None,
                    reason='No motorsim IOC')
@pytest.mark.skipif(sys.platform == 'win32',
                    reason='win32 motorsim IOC')
def test_pyepics_pv(context):
    pv1 = "sim:mtr1"
    ctx = context

    # Some user function to call when subscriptions receive data.
    called = []

    def user_callback(*, value, **kwargs):
        print()
        print('-- user callback', value)
        called.append(True)

    time_pv = PV(pv1, context=ctx, form='time')
    ctrl_pv = PV(pv1, context=ctx, form='ctrl')

    time_pv.wait_for_connection()
    time_pv.add_callback(user_callback)
    print('time read', time_pv.get())
    print('ctrl read', ctrl_pv.get())

    time_pv.put(3, wait=True)
    time_pv.put(6, wait=True)

    time.sleep(0.1)
    assert time_pv.get() == 6
    assert called

    print('read', time_pv.get())
    print('done')

    repr(time_pv)

    for k, v in PV.__dict__.items():
        if isinstance(v, property):
            getattr(time_pv, k)
            getattr(ctrl_pv, k)



@pytest.fixture(scope='function')
def access_security_softioc(request, prefix, context):
    'From pyepics test_cas.py'
    access_rights_db = {
        ('{}:ao'.format(prefix), 'ao') : {
            'ASG': "rps_threshold",
            'DRVH': "10",
            'DRVL': "0",
        },
        ('{}:bo'.format(prefix), 'bo') : {
            'ASG': "rps_lock",
            'ZNAM': "OUT",
            'ONAM': "IN",
        },
        ('{}:ao2'.format(prefix), 'ao') : {
            'DRVH': "5",
            'DRVL': "1",
        },
        ('{}:permit'.format(prefix), 'bo') : {
            'VAL': "0",
            'PINI': "1",
            'ZNAM': "DISABLED",
            'ONAM': "ENABLED",
        },
    }

    access_rights_asg_rules = '''
        ASG(DEFAULT) {
            RULE(1,READ)
            RULE(1,WRITE,TRAPWRITE)
        }
        ASG(rps_threshold) {
            INPA("$(P):permit")
            RULE(1, READ)
            RULE(0, WRITE, TRAPWRITE) {
                CALC("A=1")
            }
            RULE(1, WRITE, TRAPWRITE) {
                CALC("A=0")
            }
        }
        ASG(rps_lock) {
            INPA("$(P):permit")
            RULE(1, READ)
            RULE(1, WRITE, TRAPWRITE) {
                CALC("A=0")
            }
        }
    '''

    from .conftest import run_softioc, poll_readiness

    handler = run_softioc(request, db=access_rights_db,
                          access_rules_text=access_rights_asg_rules,
                          macros={'P': prefix},
                          )

    PV._default_context = context

    process = handler.processes[-1]
    pvs = {pv[len(prefix) + 1:]: PV(pv)
           for pv, rtype in access_rights_db
           }
    pvs['ao.DRVH'] = PV(prefix + ':ao.DRVH')

    poll_readiness(pvs['ao'].pvname)

    for pv in pvs.values():
        pv.wait_for_connection()

    def finalize_context():
        print('Cleaning up PV context')
        broadcaster = PV._default_context.broadcaster
        broadcaster.disconnect()

        PV._default_context.disconnect()
        PV._default_context = None
        print('Done cleaning up PV context')
    request.addfinalizer(finalize_context)

    return SimpleNamespace(process=process, prefix=prefix,
                           name='access_rights', pvs=pvs, type='epics-base')


def test_permit_disabled(access_security_softioc):
    # with the permit disabled, all test pvs should be readable/writable
    pvs = access_security_softioc.pvs

    for pv in pvs.values():
        assert pv.read_access and pv.write_access


def test_permit_enabled(access_security_softioc):
    pvs = access_security_softioc.pvs
    # set the run-permit
    pvs['permit'].put(1, wait=True)
    assert pvs['permit'].get(as_string=True, use_monitor=False) == 'ENABLED'

    # rps_lock rule should disable write access
    assert pvs['bo'].write_access is False
    with pytest.raises(AccessRightsException):
        pvs['bo'].put(1, wait=True)

    # rps_threshold rule should disable write access to metadata, not VAL
    assert pvs['ao'].write_access is True
    assert pvs['ao.DRVH'].write_access is False
    with pytest.raises(AccessRightsException):
        pvs['ao.DRVH'].put(100, wait=True)


def test_pv_access_event_callback(access_security_softioc):
    pvs = access_security_softioc.pvs

    # clear the run-permit
    pvs['permit'].put(0, wait=True)
    assert pvs['permit'].get(as_string=True, use_monitor=False) == 'DISABLED'

    def lcb(read_access, write_access, pv=None):
        assert pv.read_access == read_access
        assert pv.write_access == write_access
        pv.flag = True

    bo = PV(pvs['bo'].pvname, access_callback=lcb)
    bo.flag = False

    # set the run-permit to trigger an access rights event
    pvs['permit'].put(1, wait=True)
    assert pvs['permit'].get(as_string=True, use_monitor=False) == 'ENABLED'

    # give the callback a bit of time to run
    time.sleep(0.2)

    assert bo.flag is True
