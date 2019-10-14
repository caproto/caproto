#!/usr/bin/env python3
# we are going to test the mock 'ai' record from ioc_examples/mocking_records
# and see if:
# - the types match the "real" 'ai' record
# - all the .* PVs can be read
# - all the enums of the .* can be read
import epics
import time
import re
import os
from epics import ca
import urllib.request  # for fetching "epics-base" code to compare types
import subprocess
import sys
import signal

# only want local responses.
os.environ["EPICS_CA_ADDR_LIST"] = "127.0.0.1"  # local
os.environ["EPICS_CA_AUTO_ADDR_LIST"] = "NO"

# type equality between pyepics and "real" epics, **this is assumed **
type_equal = {
    "DBF_STRING": ["string"],
    "DBF_CHAR": ["char"],
    "DBF_UCHAR": ["char"],
    "DBF_SHORT": ["short"],
    "DBF_USHORT": ["short"],
    "DBF_LONG": ["int", "long"],
    "DBF_ULONG": ["int", "long"],
    "DBF_FLOAT": ["float"],
    "DBF_DOUBLE": ["double"],
    "DBF_ENUM": ["enum"],  # have an associated set of ASCII strings
    "DBF_MENU": ["enum"],  # have an associated set of ASCII strings
    "DBF_DEVICE": ["enum"],  # have an associated set of ASCII strings
    "DBF_INLINK": ["string"],  # is a link structure
    "DBF_OUTLINK": ["string"],  # is a link structure
    "DBF_FWDLINK": ["string"],  # is a link structure
    "DBF_NOACCESS": [""]  # for private use by record processing routines
}

pyepics_type_lookup = {
    "string": 0,
    "int": 1,
    "short": 1,
    "float": 2,
    "enum": 3,
    "char": 4,
    "long": 5,
    "double": 6,
    "time_string": 14,
    "time_int": 15,
    "time_short": 15,
    "time_float": 16,
    "time_enum": 17,
    "time_char": 18,
    "time_long": 19,
    "time_double": 20,
    "ctrl_string": 28,
    "ctrl_int": 29,
    "ctrl_short": 29,
    "ctrl_float": 30,
    "ctrl_enum": 31,
    "ctrl_char": 32,
    "ctrl_long": 33,
    "ctrl_double": 34
}


def run_example_ioc(module_name, *, pv_to_check):
    os.environ['COVERAGE_PROCESS_START'] = '.coveragerc'
    print(f'Running {module_name}')
    args = list([]) + ['-vvv']
    with open(os.devnull, 'w') as nowhere:
    #nowhere=None
        p = subprocess.Popen([sys.executable, '-um', 'caproto.tests.example_runner',
                          module_name] + list(args),
                         stdout=nowhere, stderr=None, stdin=nowhere,
                         env=os.environ)

    poll_readiness_pye(pv_to_check)

    import atexit
    @atexit.register
    def stop_ioc():
        if p.poll() is None:
            if sys.platform != 'win32':
                print('Sending Ctrl-C to the example IOC')
                p.send_signal(signal.SIGINT)
                print('Waiting on process...')

            try:
                p.wait(timeout=1)
            except subprocess.TimeoutExpired:
                print('IOC did not exit in a timely fashion')
                p.terminate()
                print('IOC terminated')
            else:
                print('IOC has exited')
        else:
            print('Example IOC has already exited')
    return p



def poll_readiness_pye(pv_to_check, attempts=5, timeout=1):
    print(f'polling PV {pv_to_check}..')
    pv_temp_connected = False
    for attempt in range(attempts):
        try:
            pv_temp = epics.PV(pv_to_check)
            pv_temp_connected = pv_temp.connect(timeout=timeout)
        except TimeoutError:
            continue
        if pv_temp_connected is True:
            break

    if pv_temp_connected is False:
        raise TimeoutError(f"ioc fixture failed to start in "
                           f"{attempts * timeout} seconds (pv: {pv_to_check})")
    print(f'connected to PV: {pv_to_check}')

def get_real_pv_types():
    '''
    fetch "aiRecord.dbd" & "dbCommon.dbd" from the community, and
    make a {PV extension:type} dict
    (this could similarly be done for the other PV types).
    '''
    try:
        real_record_db_lines = []
        real_record_db_lines += urllib.request.urlopen(
            "https://raw.githubusercontent.com/epics-base/epics-base/3.16/src/std/rec/aiRecord.dbd.pod")
        real_record_db_lines += urllib.request.urlopen(
            "https://raw.githubusercontent.com/epics-base/epics-base/3.16/src/ioc/db/dbCommon.dbd")
    except Exception as e:
        assert False, "need the internet to fetch the real record db files."

    # extract out the types
    # the record files don't include "RTYP" & ".RTYP$"
    real_PV_types = {"RTYP": "DBF_STRING", "RTYP$": "DBF_CHAR"}
    for line in real_record_db_lines:
        # eg line="field(VAL,DBF_DOUBLE) {"
        line = line.decode("utf-8")
        regex = re.compile(
            r"[\s].*field\((?P<name>[A-Za-z_].*)[,\s](?P<type>[A-Za-z_].*)\) {")
        m = regex.match(line)
        if m is not None:
            real_PV_types[m.group('name')] = m.group('type')
            if m.group('type') in ["DBF_STRING", "DBF_FWDLINK", "DBF_INLINK"]:
                real_PV_types[f"{m.group('name')}$"] = "DBF_CHAR"

    return real_PV_types


def test_ai_compliance():
    real_PV_types = get_real_pv_types()

    # host a caproto record to test(you could also try this test on a real record).
    # NOTE: using the below will actually run a seperate program from command line,
    # bypassing whatever virtual env you are using for this test..
    pv = f"mock:A"
    p = run_example_ioc('caproto.ioc_examples.mocking_records',
                        pv_to_check=f"{pv}")

    # pre-connect.
    # I found it seems to be the only way to avoid getting false "not connected",
    # and connecting with a timeout later on is slower..
    pv_list = {}
    for extension in real_PV_types:
        full_pv = f"{pv}.{extension}"
        pv_temp = epics.PV(full_pv)
        pv_list[full_pv] = pv_temp
        pv_temp.connect(timeout=0.1)

    # wait for all to connect at same time
    time.sleep(5)

    # now do the testing
    ai_compliant = True
    for extension in real_PV_types:
        full_pv = f"{pv}.{extension}"
        pv_temp = pv_list[full_pv]

        expected_type=real_PV_types[extension]

        if pv_temp.connected is False:
            #assert expected_type == "DBF_NOACCESS"
            if expected_type != "DBF_NOACCESS":
                print("**************************************************************")
                print(f"{extension}: type is not hosted, but should be {expected_type}")
                ai_compliant = False
        else:
            # make a list of acceptable results
            acceptable = []
            for acc_type in type_equal[expected_type]:
                acceptable.append(acc_type)
            for acc_type in type_equal[expected_type]:
                acceptable.append(f"time_{acc_type}")
            for acc_type in type_equal[expected_type]:
                acceptable.append(f"ctrl_{acc_type}")

            #assert pv_temp.type in acceptable
            if pv_temp.type not in acceptable:
                print("**************************************************************")
                print(f"{extension}: type is {pv_temp.type} , but should be {expected_type}")
                ai_compliant = False
            try:
                # normally it is time_char so we add time_
                type_read_temp_str = f"time_{type_equal[expected_type][0]}"
                type_read_temp = pyepics_type_lookup[type_read_temp_str]

                # reading with ca.get highlights problems, whereas pv.get() seems to just work.
                if "$" in extension:
                    read_temp = ca.get(pv_temp.chid, as_string=True) #, ftype=type_read_temp)
                else:
                    read_temp = ca.get(pv_temp.chid) #, ftype=type_read_temp)
            except Exception as e:
                #assert False, "can't be read"
                print("**************************************************************")
                print(f"{extension}: can't be read")
                print(e)
                ai_compliant = False

            enum_str = ""
            if "MENU" in expected_type:
                try:
                    enum_str = pv_temp.enum_strs
                except Exception as e:
                    #assert False, "enum not readable"
                    print("**************************************************************")
                    print(f"{extension}: can't read enum")
                    print(e)
                    ai_compliant = False

    # because I can't fetch the epics db files and feed them into the parameterize,
    # and I want to startup one ioc and connect to all the pv's at the same time
    # I have to do it like this, sorry
    assert ai_compliant is True
