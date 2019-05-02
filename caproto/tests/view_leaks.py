import sys
import ast

import xml.etree.ElementTree as ET


def parse_properties(fn):
    et = ET.parse(fn)

    test_cases = list(et.getroot().iter('testcase'))

    all_properties = {}

    for i, test_case in enumerate(test_cases):
        name = '{file}::{name}'.format(**test_case.attrib)
        properties = {
            prop.attrib['name']: ast.literal_eval(prop.attrib['value'])
            for prop in test_case.iter('property')
        }
        all_properties[name] = properties

        fmt = '{:<150}' + '\t{}' * len(properties)

        if i == 0:
            print(fmt.format(name, *properties.keys()))
            sorted_keys = list(sorted(properties.keys()))
            if not sorted_keys:
                sorted_keys = ['total_threads', 'dangling_threads',
                               'total_sockets', 'open_sockets']
        print(fmt.format(name, *[properties.get(key, 'N/A')
                                 for key in sorted_keys]))

    return all_properties


if __name__ == '__main__':
    properties = parse_properties(sys.argv[1])

    try:
        import pandas as pd
    except ImportError:
        ...
    else:
        df = pd.DataFrame(properties).transpose()
        print(df)
