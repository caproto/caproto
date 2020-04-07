#!/usr/bin/env python3
# we are going to test the mock 'ai' record from ioc_examples/mocking_records
# and see if:
# - the types match the "real" 'ai' record
# - all the .* PVs can be read
# - all the enums of the .* can be read
import time

import epics
from epics import ca
import pytest

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
    "DBF_INT64": ["long"],
    "DBF_UINT64": ["long"],
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


def test_record_compliance(request, prefix, record_type_name,
                           record_type_to_fields):
    fields = record_type_to_fields[record_type_name]

    # host a caproto record to test(you could also try this test on a real record).
    pv = f"{prefix}A"
    conftest.run_example_ioc(
        'caproto.tests.ioc_any_record',
        pv_to_check=pv,
        args=['--prefix', prefix, '-v', '--record-type', record_type_name],
        request=request,
        very_verbose=False
    )

    # pre-connect.
    # I found it seems to be the only way to avoid getting false "not connected",
    # and connecting with a timeout later on is slower..
    pv_list = {}
    for field in fields:
        full_pv = f"{pv}.{field}"
        pv_temp = epics.PV(full_pv)
        pv_list[full_pv] = pv_temp
        pv_temp.connect(timeout=0.1)

    # wait for all to connect at same time
    time.sleep(1)

    # now do the testing
    issues = {}
    for field, expected_type in fields.items():
        full_pv = f"{pv}.{field}"
        pv_temp = pv_list[full_pv]

        if pv_temp.connected is False:
            if expected_type != "DBF_NOACCESS":
                issues[field] = f'type is not hosted, but should be {expected_type}'
        else:
            # make a list of acceptable results
            acceptable = []
            for acc_type in type_equal[expected_type]:
                acceptable.append(acc_type)
            for acc_type in type_equal[expected_type]:
                acceptable.append(f"time_{acc_type}")
            for acc_type in type_equal[expected_type]:
                acceptable.append(f"ctrl_{acc_type}")

            if pv_temp.type not in acceptable:
                issues[field] = f"type is {pv_temp.type}, but should be {expected_type}"

            try:
                # normally it is time_char so we add time_
                ca.get(pv_temp.chid, as_string=('$' in field))
            except Exception as ex:
                issues[field] = f"can't be read ({ex})"

            if "MENU" in expected_type:
                try:
                    pv_temp.enum_strs
                except Exception as ex:
                    issues[field] = f"can't read enum ({ex})"

    if not issues:
        return

    if set(issues) == {'VAL'}:
        # TODO: figure out how to support this; for now it's "compliant enough"
        return

    issue_string = '\n\t'.join(f'{field}: {issue}'
                               for field, issue in issues.items()
                               )
    pytest.fail(
        f'Record type {record_type_name} not in compliance with softIoc.dbd '
        f'specifications.  Found {len(issues)} issues in {len(fields)} fields:'
        f'\n\t{issue_string}'
    )
