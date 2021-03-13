"""
View leaks found when running the test suite, based on its JUnit XML output.

Usage:

    $ pytest -vv --junitxml=junit.xml
    $ python tests/view_leaks.py junit.xml
"""

import ast
import os
import sys
import traceback
import xml.etree.ElementTree as ET

DEFAULT_KEYS = ['total_threads', 'dangling_threads', 'total_sockets',
                'open_sockets']


def get_properties(test_case):
    """
    Get all properties from a given JUnit XML test case.

    Returns
    -------
    name : str
        Fully-qualified test case name.

    properties : dict
        Properties of the given test.
    """

    name = '{file}::{name}'.format(**test_case.attrib)

    properties = {
        prop.attrib['name']: ast.literal_eval(prop.attrib['value'])
        for prop in test_case.iter('property')
    }
    return name, properties


def parse_properties(fn):
    """
    Parse all test case properties from a given JUnit XML file.

    Parameters
    ----------
    fn : str
        The JUnit XML filename to read.

    Returns
    -------
    all_properties : dict
        Aggregated property information, keyed on the fully-qualified test
        name (``file::test_name``).
    """

    et = ET.parse(fn)
    all_properties = {}

    for i, test_case in enumerate(et.getroot().iter('testcase')):
        try:
            name, properties = get_properties(test_case)
        except Exception:
            continue

        all_properties[name] = properties

        fmt = '{:<150}' + '\t{}' * len(properties)

        if i == 0:
            print(fmt.format(name, *properties.keys()))
            sorted_keys = list(sorted(properties.keys())) or DEFAULT_KEYS
        print(fmt.format(name, *[properties.get(key, 'N/A')
                                 for key in sorted_keys]))

    return all_properties


if __name__ == '__main__':
    fn = sys.argv[1]
    if not os.path.exists(fn):
        print(f"ERROR: File does not exist: {fn}")
        sys.exit(0)

    try:
        properties = parse_properties(fn)
        import pandas as pd
    except Exception:
        print("Error occurred while looking for leaks :(")
        traceback.print_exc()
        sys.exit(0)

    df = pd.DataFrame(properties).transpose()
    print(df)
