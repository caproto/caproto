import epics, time, re
import os
from epics import ca
import urllib.request  # for fetching epics-base code to compare types

# to avoid multiple server error messages when testing locally (you will need to remove this if testing a remote PV)
os.environ["EPICS_CA_ADDR_LIST"] = "127.0.0.1"  # local
os.environ["EPICS_CA_AUTO_ADDR_LIST"] = "NO"

# this is the pv name to test (first run "test_ai_mock_rec.py")
PV_name = "TEST_PV:ai_test"  # caproto mock record for testing

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
# these are from; https://github.com/epicsdeb/epics-base/tree/master/src/std/rec
#https://github.com/epics-base/epics-base/tree/3.16/src/std/rec
real_record_db_lines=[]
real_record_db_lines += urllib.request.urlopen("https://raw.githubusercontent.com/epics-base/epics-base/3.16/src/std/rec/aiRecord.dbd.pod")
real_record_db_lines += urllib.request.urlopen("https://raw.githubusercontent.com/epics-base/epics-base/3.16/src/ioc/db/dbCommon.dbd")

# or if you have some local built files
#for file in ["aiRecord.dbd", "dbCommon.dbd"]:
#    real_record_db=open(file, "r")
#    real_record_db_lines += real_record_db.readlines()
#    real_record_db.close()

# extract out the types
real_PV_types = {"RTYP": "DBF_STRING"} # the record files don't include the ".RTYP"
for line in real_record_db_lines:
    # eg line="field(VAL,DBF_DOUBLE) {"
    line=line.decode("utf-8")
    regex = re.compile("[\s].*field\((?P<name>[A-Za-z_].*)[,\s](?P<type>[A-Za-z_].*)\) {")
    m = regex.match(line)
    if m is not None:
        real_PV_types[m.group('name')] = m.group('type')

print(f"testing PV = {PV_name}")
print("connecting to all .* PVs at same time..")

# attempt to fetch the pv extensions types to be tested
# connect to all simultaneously, since there seems to be some connect delay.
pv_list = {}
for pv_name_ext in real_PV_types:
    full_pv = f"{PV_name}.{pv_name_ext}"
    pv_temp = epics.PV(full_pv)
    pv_list[full_pv] = pv_temp
    pv_temp.connect(timeout=0.1)  # just get it to try to connect once (some will not reply fast enough)

# wait for all to connect at same time
time.sleep(5) # allows a significant amount of time to connect.

for pv_name_ext in real_PV_types:
    full_pv = f"{PV_name}.{pv_name_ext}"
    connect_result = pv_list[full_pv].connected

    if connect_result is False and real_PV_types[pv_name_ext] == "DBF_NOACCESS":
        print(f"OK: .{pv_name_ext} NOT HOSTED (should be type {real_PV_types[pv_name_ext]})")
    elif connect_result is False:
        print(f" *WRONG: .{pv_name_ext} NOT HOSTED, but should be type {real_PV_types[pv_name_ext]}")
    else:
        realtype = real_PV_types[pv_name_ext]  # this is what it should be
        test_type = pv_list[full_pv].type  # this is what we are testing

        # make a list of acceptable results
        acceptable = []
        for acc_type in type_equal[realtype]:
            acceptable.append(acc_type)
        for acc_type in type_equal[realtype]:
            acceptable.append(f"time_{acc_type}")
        for acc_type in type_equal[realtype]:
            acceptable.append(f"ctrl_{acc_type}")

        if test_type in acceptable:
            test_type_ok = 1
        else:
            test_type_ok = 0

        type_read_temp_str = ""
        read_temp = -1
        try:
            chid = pv_list[full_pv].chid
            # normally it is time_char so we add time_
            type_read_temp_str = f"time_{type_equal[real_PV_types[pv_name_ext]][0]}"
            type_read_temp = pyepics_type_lookup[type_read_temp_str]
            # reading this way highlights problems, whereas pv.get() seems to just work.
            read_temp = ca.get(chid, ftype=type_read_temp)
            test_read_ok = 1
        except Exception as e:
            test_read_ok = 0
        enum_str = ""
        if "MENU" in real_PV_types[pv_name_ext]:
            try:
                enum_str = pv_list[full_pv].enum_strs
            except Exception as e:
                pass

            if enum_str != "" and test_read_ok == 1 and test_type_ok == 1:
                print(f"OK: .{pv_name_ext} type is {test_type}, ca read as type: {type_read_temp_str} = {read_temp}, "
                    f"should be {realtype}, enums = {pv_list[full_pv].enum_strs}")

            if enum_str == "":
                print(f" *WRONG: .{pv_name_ext} bad enum; type = {test_type} & reading = {read_temp}, should be "
                    f"{realtype}")


        elif test_read_ok == 1 and test_type_ok == 1:
                print(f"OK: .{pv_name_ext} type is {test_type}, ca read as type: {type_read_temp_str} = {read_temp}, "
                    f"should be {realtype}")

        if test_read_ok == 0 and test_type_ok == 0:
            print(f" *WRONG: .{pv_name_ext} wrong type & ca read failed, tried type {type_read_temp_str}, type is "
                f"{test_type}, but should be {realtype}")
        elif test_read_ok == 0:
            print(f" *WRONG: .{pv_name_ext} ca read failed; tried type {type_read_temp_str}, type is ok: is {test_type}"
                f", should be {realtype} ")

        elif test_type_ok == 0:
            print(f" *WRONG: .{pv_name_ext} type is wrong; is {test_type}, but should be {realtype}. ca read is ok = "
                f"{read_temp}")

print("END")
