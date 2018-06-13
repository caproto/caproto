#!/usr/bin/env python3
"""
NOTICE

This particular example predates the IOC class framework that makes IOC
specification much more succinct.
"""
import warnings
import caproto as ca
from caproto.server import ioc_arg_parser, run


alarm = ca.ChannelAlarm(
    status=ca.AlarmStatus.READ,
    severity=ca.AlarmSeverity.MINOR_ALARM,
    alarm_string='alarm string',
)


# Simple PV database for the server
pvdb = {'pi': ca.ChannelDouble(value=3.14,
                               lower_disp_limit=3.13,
                               upper_disp_limit=3.15,
                               lower_alarm_limit=3.12,
                               upper_alarm_limit=3.16,
                               lower_warning_limit=3.11,
                               upper_warning_limit=3.17,
                               lower_ctrl_limit=3.10,
                               upper_ctrl_limit=3.18,
                               precision=5,
                               units='doodles',
                               alarm=alarm,
                               ),
        'fib': ca.ChannelDouble(value=[1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89],
                                lower_disp_limit=3.13,
                                upper_disp_limit=3.15,
                                lower_alarm_limit=3.12,
                                upper_alarm_limit=3.16,
                                lower_warning_limit=3.11,
                                upper_warning_limit=3.17,
                                lower_ctrl_limit=3.10,
                                upper_ctrl_limit=3.18,
                                precision=5,
                                units='doodles',
                                alarm=alarm,
                                ),
        'enum': ca.ChannelEnum(value='b',
                               enum_strings=['a', 'b', 'c', 'd'],
                               ),
        'enum2': ca.ChannelEnum(value='bb',
                                enum_strings=['aa', 'bb', 'cc', 'dd'],
                                ),
        'int': ca.ChannelInteger(value=96,
                                 units='doodles',
                                 ),
        'int2': ca.ChannelInteger(value=96,
                                  units='doodles',
                                  ),
        'int3': ca.ChannelInteger(value=96,
                                  units='doodles',
                                  ),
        'char': ca.ChannelByte(value=b'3',
                               units='poodles',
                               lower_disp_limit=33,
                               upper_disp_limit=35,
                               lower_alarm_limit=32,
                               upper_alarm_limit=36,
                               lower_warning_limit=31,
                               upper_warning_limit=37,
                               lower_ctrl_limit=30,
                               upper_ctrl_limit=38,
                               ),
        'chararray': ca.ChannelChar(value=b'1234567890' * 2),
        'str': ca.ChannelString(value='hello',
                                string_encoding='latin-1',
                                alarm=alarm),
        'str2': ca.ChannelString(value='hello',
                                 string_encoding='latin-1',
                                 alarm=alarm),
        'stra': ca.ChannelString(value=['hello', 'how is it', 'going'],
                                 string_encoding='latin-1'),
        }


def main():
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='type_varieties:',
        desc='Run an IOC with PVs of various data types.')
    prefix = ioc_options['prefix']
    prefixed_pvdb = {prefix + key: value for key, value in pvdb.items()}
    warnings.warn("The IOC options are ignored by this IOC. "
                  "It needs to be updated.")
    run(prefixed_pvdb, **run_options)


if __name__ == '__main__':
    main()
