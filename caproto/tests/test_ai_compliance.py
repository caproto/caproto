#!/usr/bin/env python3
# we are going to test the mock 'ai' record from ioc_examples/mocking_records
# and see if:
# - the types match the "real" 'ai' record
# - all the .* PVs can be read
# - all the enums of the .* can be read
import re
import time

import caproto
import epics
from epics import ca

from . import conftest


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


def test_ai_compliance(request, prefix, record_type_to_fields):
    real_PV_types = record_type_to_fields['ai']

    # host a caproto record to test(you could also try this test on a real record).
    # NOTE: using the below will actually run a seperate program from command line,
    # bypassing whatever virtual env you are using for this test..
    pv = f"{prefix}A"
    conftest.run_example_ioc('caproto.ioc_examples.mocking_records',
                             pv_to_check=pv,
                             args=['--prefix', prefix],
                             request=request)

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
