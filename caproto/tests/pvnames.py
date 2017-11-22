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



#
# list of local pv names to use for testing


#### 1
# this pv should be a DOUBLE.  It will NOT be set, but
# you should provide the host_name, units, and precision.  It
# is assumed to have count=1
double_pv = 'Py:ao1'
double_pv_units = 'microns'
double_pv_prec = 4

double_pv2 = 'Py:ao2'

pause_pv  = 'Py:pause'
#### 2
# this pv should be an ENUM. It will NOT be set.
# provide the names of the ENUM states

#### Theae are PVs of the various native types
###  They will NOT be set.
str_pv   = 'Py:ao1.DESC'
int_pv   = 'Py:long2'
long_pv  = 'Py:long2'
float_pv = 'Py:ao3'
enum_pv  = 'Py:mbbo1'
enum_pv_strs = ['Stop', 'Start', 'Pause', 'Resume']

proc_pv = 'Py:ao1.PROC'

## Here are some waveform / array data PVs
long_arr_pv   = 'Py:long2k'
double_arr_pv = 'Py:double2k'
string_arr_pv = 'Py:string128'
# char / byte array
char_arr_pv   = 'Py:char128'
char_arrays   = ['Py:char128', 'Py:char2k', 'Py:char64k']
long_arrays   = ['Py:long128', 'Py:long2k', 'Py:long64k']
double_arrays   = ['Py:double128', 'Py:double2k', 'Py:double64k']


####
# provide a single motor prefix (to which '.VAL' and '.RBV' etc will be added)

motor1 = 'XF:31IDA-OP{Tbl-Ax:X1}Mtr'
motor2 = 'XF:31IDA-OP{Tbl-Ax:X2}Mtr'

####
#  Here, provide a PV that changes at least once very 10 seconds
updating_pv1  = 'Py:ao1'
updating_str1 = 'Py:char256'

####
#  Here, provide a list of PVs that  change at least once very 10 seconds
updating_pvlist = ['Py:ao1', 'Py:ai1', 'Py:long1', 'Py:ao2']
#### alarm test

non_updating_pv = 'Py:ao4'

alarm_pv = 'Py:long1'
alarm_comp='ge'
alarm_trippoint = 7


#### subarray test
subarr_driver = 'Py:wave_test'
subarr1       = 'Py:subArr1'
subarr2       = 'Py:subArr2'
subarr3       = 'Py:subArr3'
subarr4       = 'Py:subArr4'
zero_len_subarr1 = 'Py:ZeroLenSubArr1'
