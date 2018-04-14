#!/usr/bin/env python3
import logging
import sys

import curio
from caproto.curio.server import (Context, logger, ServerExit)
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


async def main(pvdb, prefix=None, port=None):
    if prefix is not None:
        pvdb = {prefix + key: value
                for key, value in pvdb.items()}
    if port is None:
        port = ca.find_available_tcp_port()
    ctx = Context('0.0.0.0', port, pvdb, log_level='DEBUG')
    logger.info('Server starting up on %s:%d', ctx.host, ctx.port)
    logger.info("Available PVs: %s", ' '.join(pvdb))
    try:
        return await ctx.run()
    except ServerExit:
        print('ServerExit caught; exiting')


if __name__ == '__main__':
    # TODO Use new IOC code.
    logging.basicConfig()
    logger.setLevel('DEBUG')
    prefix = sys.argv[1] if len(sys.argv) > 1 else None
    curio.run(main(pvdb, prefix=prefix))
