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

import sys
import time
import unittest
import numpy
from contextlib import contextmanager
from caproto.threading.pyepics_compat import (PV, caput, caget, cainfo,
                                              caget_many, caput_many)
from caproto.threading.client import Context, SharedBroadcaster

from .conftest import default_setup_module, default_teardown_module
import pytest


def setup_module(module):
    default_setup_module(module)

    from caproto.benchmarking.util import set_logging_level

    set_logging_level('DEBUG')

    shared_broadcaster = SharedBroadcaster()
    PV._default_context = Context(broadcaster=shared_broadcaster,
                                  log_level='DEBUG')


def teardown_module(module):
    default_teardown_module(module)

    broadcaster = PV._default_context.broadcaster
    broadcaster.disconnect()

    PV._default_context.disconnect()
    PV._default_context = None


@pytest.fixture(scope='function')
def pvnames(epics_base_ioc):
    prefix = epics_base_ioc.prefix

    class PVNames:
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
            return f'<PVNames prefix={prefix}>'

    return PVNames()


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


def testA_CreatePV(pvnames):
    print('Simple Test: create pv\n')
    pv = PV(pvnames.double_pv)
    assert pv is not None


def testA_CreatedWithConn(pvnames):
    print('Simple Test: create pv with conn callback\n')
    CONN_DAT = {}

    def onConnect(pvname=None, conn=None, chid=None, **kws):
        nonlocal CONN_DAT
        print('  :Connection status changed:  %s  connected=%s\n' % (pvname, conn))
        CONN_DAT[pvname] = conn

    pv = PV(pvnames.int_pv, connection_callback=onConnect)
    val = pv.get()

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
    with no_simulator_updates(pvnames):
        pv = PV(pvnames.int_pv)
        val = pv.get()
        cval = pv.get(as_string=True)

        assert int(cval) == val


def test_get_string_waveform(pvnames):
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
    global put_callback_called
    put_callback_called = False

    def onPutdone(pvname=None, **kws):
        print('put done ', pvname, kws)
        global put_callback_called
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


def test_get_callback(pvnames):
    print("Callback test:  changing PV must be updated\n")
    global NEWVALS
    mypv = PV(pvnames.updating_pv1)
    NEWVALS = []

    def onChanges(pvname=None, value=None, char_value=None, **kw):
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


    driver.put(full_data) ;
    time.sleep(0.1)
    subval = subarr1.get()

    assert len(subval) == len_sub1
    assert numpy.all(subval == full_data[:len_sub1])
    print("Subarray test:  C\n")
    caput("%s.NELM" % pvnames.subarr2, 19)
    caput("%s.INDX" % pvnames.subarr2, 3)

    subarr2 = PV(pvnames.subarr2)
    subarr2.get()

    driver.put(full_data) ;   time.sleep(0.1)
    subval = subarr2.get()

    assert len(subval) == 19
    assert numpy.all(subval == full_data[3:3+19])

    caput("%s.NELM" % pvnames.subarr2, 5)
    caput("%s.INDX" % pvnames.subarr2, 13)

    driver.put(full_data) ;   time.sleep(0.1)
    subval = subarr2.get()

    assert len(subval) == 5
    assert numpy.all(subval == full_data[13:5+13])


def test_subarray_zerolen(pvnames):
    subarr1 = PV(pvnames.zero_len_subarr1)
    subarr1.wait_for_connection()

    val = subarr1.get(use_monitor=True, as_numpy=True)
    assert isinstance(val, numpy.ndarray, msg='using monitor')
    assert len(val) == 0, 'using monitor'
    # caproto returns things in big endian, not native type
    # assert val.dtype == numpy.float64, 'using monitor'

    val = subarr1.get(use_monitor=False, as_numpy=True)
    assert isinstance(val, numpy.ndarray, msg='no monitor')
    assert len(val) == 0, 'no monitor'
    # caproto returns things in big endian, not native type
    # assert val.dtype == numpy.float64, 'no monitor'


def test_waveform_get_with_count_arg(pvnames):
    with no_simulator_updates(pvnames):
        wf = PV(pvnames.char_arr_pv, count=32)
        val=wf.get()
        assert len(val) == 32

        val=wf.get(count=wf.nelm)
        assert len(val) == wf.nelm


def test_waveform_callback_with_count_arg(pvnames):
    values = []

    wf = PV(pvnames.char_arr_pv, count=32)
    def onChanges(pvname=None, value=None, char_value=None, **kw):
        print('PV %s %s, %s Changed!\n' % (pvname, repr(value), char_value))
        values.append( value)

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
    with no_simulator_updates(pvnames):
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
    with no_simulator_updates(pvnames):
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


def test_DoubleVal(pvnames):
    pvn = pvnames.double_pv
    pv = PV(pvn)
    print('pv', pv)
    value = pv.get()
    print('pv get', value)
    assert pv.connected

    print('%s get value %s' % (pvn, value))
    cdict  = pv.get_ctrlvars()
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
    assert len(val), 1


def test_subarray_1elem(pvnames):
    with no_simulator_updates(pvnames):
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


def test_pyepics_pv():
    pv1 = "sim:mtr1"

    # Some user function to call when subscriptions receive data.
    called = []

    def user_callback(*, value, **kwargs):
        print()
        print('-- user callback', value)
        called.append(True)

    shared_broadcaster = SharedBroadcaster(log_level='DEBUG')
    ctx = Context(broadcaster=shared_broadcaster, log_level='DEBUG')
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
