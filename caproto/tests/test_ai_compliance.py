# we are going to test the ai record from ioc_examples/mocking_records
# and see if it matches the "real" 'ai' record
import epics, time, re
import os
from epics import ca
import urllib.request  # for fetching "epics-base" code to compare types
import pytest
import subprocess, sys

# this is to run on windows
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

# load up the db and type
# fetching "aiRecord.dbd" & "dbCommon.dbd" from the community
# this could similarly be done for the other PV types.
# these are from; 
# https://github.com/epicsdeb/epics-base/tree/master/src/std/rec
# eg https://github.com/epics-base/epics-base/tree/3.16/src/std/rec
real_record_db_lines=[]
real_record_db_lines += urllib.request.urlopen("https://raw.githubusercontent.com/epics-base/epics-base/3.16/src/std/rec/aiRecord.dbd.pod")
real_record_db_lines += urllib.request.urlopen("https://raw.githubusercontent.com/epics-base/epics-base/3.16/src/ioc/db/dbCommon.dbd")

# extract out the types
# the record files don't include the, "RTYP" & ".RTYP$"
real_PV_types = [("RTYP", "DBF_STRING"), ("RTYP$", "DBF_STRING")]
for line in real_record_db_lines:
    # eg line="field(VAL,DBF_DOUBLE) {"
    line=line.decode("utf-8")
    regex = re.compile(r"[\s].*field\((?P<name>[A-Za-z_].*)[,\s](?P<type>[A-Za-z_].*)\) {")
    m = regex.match(line)
    if m is not None:
        real_PV_types.append((m.group('name'), m.group('type')))
        if m.group('type') in ["DBF_STRING", "DBF_FWDLINK", "DBF_INLINK"]:
            real_PV_types.append((f"{m.group('name')}$", "DBF_CHAR"))


def run_example_ioc(module_name, *, pv_to_check,
                    stdin=None, stdout=None, stderr=None):

    os.environ['COVERAGE_PROCESS_START'] = '.coveragerc'
    print(f'Running {module_name}')
    args = list([]) + ['-vvv']
    p = subprocess.Popen([sys.executable, '-um', 'caproto.tests.example_runner',
                          module_name] + list(args),
                         stdout=stdout, stderr=stderr, stdin=stdin,
                         env=os.environ)

    poll_readiness_pye(pv_to_check)

    return p


def stop_ioc(p):
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


def poll_readiness_pye(pv_to_check, attempts=5, timeout=1):
    print(f'polling PV {pv_to_check}')
    for attempt in range(attempts):
        try:
            epics.caget(pv_to_check, timeout=timeout)
        except TimeoutError:
            continue
        else:
            break
    else:
        raise TimeoutError(f"ioc fixture failed to start in "
                           f"{attempts * timeout} seconds (pv: {pv_to_check})")

#host a caproto record to test, you could also try this test on a real record.
pv = f"mock:A" #
p = run_example_ioc('caproto.ioc_examples.mocking_records',
                    pv_to_check=f"{pv}")

# i pre-connect like this because it seems to be the only way not to get
# false "not connected", and connecting with a timeout later on is slower..
pv_list = {}
for pv_name_ext,dbf_type in real_PV_types:
    full_pv = f"{pv}.{pv_name_ext}"
    pv_temp = epics.PV(full_pv)
    pv_list[full_pv] = pv_temp
    pv_temp.connect(timeout=0.1)  # just get it to try to connect once (some will not reply fast enough)

# wait for all to connect at same time
time.sleep(5) # allows a significant amount of time to connect.


@pytest.mark.parametrize("extension,expected_type", real_PV_types)
def test_pv_types(extension, expected_type):
    global pv_list
    full_pv = f"{pv}.{extension}"
    pv_temp = pv_list[full_pv] #epics.PV(full_pv)

    temp_real_pv_type=""
    for i in range(len(real_PV_types)):
        if real_PV_types[i][0] == extension:
            temp_real_pv_type = real_PV_types[i][1] #real_PV_types[extension]

    #if pv_temp.connect(10) is False:
    if pv_temp.connected is False:
        assert temp_real_pv_type == "DBF_NOACCESS"
    else:
        # make a list of acceptable results
        acceptable = []
        for acc_type in type_equal[expected_type]:
            acceptable.append(acc_type)
        for acc_type in type_equal[expected_type]:
            acceptable.append(f"time_{acc_type}")
        for acc_type in type_equal[expected_type]:
            acceptable.append(f"ctrl_{acc_type}")

        assert pv_temp.type in acceptable


        try:
            chid = pv_temp.chid #pv_list[full_pv].chid #


            # normally it is time_char so we add time_
            type_read_temp_str = f"time_{type_equal[temp_real_pv_type][0]}"
            type_read_temp = pyepics_type_lookup[type_read_temp_str]
            # reading this way highlights problems, whereas pv.get() seems to just work.
            
            if "$" in extension:
                read_temp = ca.get(chid, ftype=type_read_temp, as_string=True)
            else:
                read_temp = ca.get(chid, ftype=type_read_temp)
        except Exception as e:
            assert False, "can't be read"

        enum_str = ""
        if "MENU" in temp_real_pv_type: # real_PV_types[extension]
            try:
                enum_str = pv_temp.enum_strs
            except Exception as e:
                assert False, "enum not readable" # assert enum_str != "" #pass



#test_pv_types(real_PV_types[0][0],real_PV_types[0][1])

stop_ioc(p)
print("END")
