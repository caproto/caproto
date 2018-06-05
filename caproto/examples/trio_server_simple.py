import logging

import trio
from caproto.trio.server import Context
import caproto as ca


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
        'enum': ca.ChannelEnum(value='b',
                               enum_strings=['a', 'b', 'c', 'd'],
                               ),
        'enum2': ca.ChannelEnum(value='bb',
                                enum_strings=['aa', 'bb', 'cc', 'dd'],
                                ),
        'int': ca.ChannelInteger(value=96,
                                 units='doodles',
                                 ),
        'char': ca.ChannelChar(value=b'3',
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


async def main(pvdb):
    ctx = Context(pvdb)
    return await ctx.run()


if __name__ == '__main__':
    logging.getLogger('caproto').setLevel('DEBUG')
    trio.run(main, pvdb)
