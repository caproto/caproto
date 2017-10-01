import ast
import datetime

import pytest
import curio
import curio.subprocess

import caproto as ca
from caproto.curio.server import find_next_tcp_port
import caproto.curio.server as server

from caproto import ChType
from epics_test_utils import (run_caget, run_caput)


REPEATER_PORT = 5065
SERVER_HOST = '0.0.0.0'


str_alarm_status = ca.ChannelAlarm(
    status=ca.AlarmStatus.READ,
    severity=ca.AlarmSeverity.MINOR_ALARM,
    alarm_string='alarm string',
)

caget_pvdb = {
    'pi': ca.ChannelDouble(value=3.14,
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
                           ),
    'enum': ca.ChannelEnum(value='b',
                           enum_strings=['a', 'b', 'c', 'd'],
                           ),
    'int': ca.ChannelInteger(value=33,
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
    'str': ca.ChannelString(value='hello',
                            alarm=str_alarm_status,
                            reported_record_type='caproto'),
    }


@pytest.fixture(scope='function')
def curio_server():
    async def run_server():
        port = find_next_tcp_port(host=SERVER_HOST)
        print('Server will be on', (SERVER_HOST, port))
        ctx = server.Context(SERVER_HOST, port, caget_pvdb, log_level='DEBUG')
        try:
            await ctx.run()
        except Exception as ex:
            print('Server failed', ex)
            raise
        finally:
            print('Server exiting')

    return run_server


caget_checks = sum(
    ([(pv, dtype),
      (pv, ca.promote_type(dtype, use_status=True)),
      (pv, ca.promote_type(dtype, use_time=True)),
      (pv, ca.promote_type(dtype, use_ctrl=True)),
      (pv, ca.promote_type(dtype, use_gr=True)),
      ]
     for pv in ('int', 'pi', 'enum')
     for dtype in ca.native_types),
    []
)

caget_checks += [('char', ChType.CHAR),
                 ('char', ChType.STS_CHAR),
                 ('char', ChType.TIME_CHAR),
                 ('char', ChType.GR_CHAR),
                 ('char', ChType.CTRL_CHAR),
                 ('str', ChType.STRING),
                 ('str', ChType.STS_STRING),
                 ('str', ChType.TIME_STRING),

                 ('str', ChType.STSACK_STRING),
                 ('str', ChType.CLASS_NAME),
                 ]


@pytest.mark.parametrize('pv, dbr_type', caget_checks)
def test_with_caget(curio_server, pv, dbr_type):
    ctrl_keys = ('upper_disp_limit', 'lower_alarm_limit',
                 'upper_alarm_limit', 'lower_warning_limit',
                 'upper_warning_limit', 'lower_ctrl_limit',
                 'upper_ctrl_limit', 'precision')

    async def client():
        print('* client_test', pv, dbr_type)
        db_entry = caget_pvdb[pv]
        # native type as in the ChannelData database
        db_native = ca.native_type(db_entry.data_type)
        # native type of the request
        req_native = ca.native_type(dbr_type)

        data = await run_caget(pv, dbr_type=dbr_type)
        print('dbr_type', dbr_type, 'data:')
        print(data)

        db_value = db_entry.value

        # convert from string value to enum if requesting int
        if (db_native == ChType.ENUM and
                not (req_native == ChType.STRING
                     or dbr_type in (ChType.CTRL_ENUM,
                                     ChType.GR_ENUM))):
            db_value = db_entry.enum_strings.index(db_value)
        if req_native in (ChType.INT, ChType.LONG, ChType.SHORT, ChType.CHAR):
            if db_native == ChType.CHAR:
                assert int(data['value']) == ord(db_value)
            else:
                assert int(data['value']) == int(db_value)
        elif req_native in (ChType.STSACK_STRING, ):
            db_string_value = db_entry.alarm.alarm_string
            string_length = len(db_string_value)
            read_value = data['value'][:string_length]
            assert read_value == db_string_value
        elif req_native in (ChType.CLASS_NAME, ):
            assert data['class_name'] == 'caproto'
        elif req_native in (ChType.FLOAT, ChType.DOUBLE):
            assert float(data['value']) == float(db_value)
        elif req_native == ChType.STRING:
            if db_native == ChType.STRING:
                db_string_value = str(db_value[0])
                string_length = len(db_string_value)
                read_value = data['value'][:string_length]
                assert int(data['element_count']) == 1
                assert read_value == db_string_value
                # due to how we monitor the caget output, we get @@@s where
                # null padding bytes are. so long as we verify element_count
                # above and the set of chars that should match, this assertion
                # should pass
            else:
                assert data['value'] == str(db_value)
        elif req_native == ChType.ENUM:
            bad_strings = ['Illegal Value (', 'Enum Index Overflow (']
            for bad_string in bad_strings:
                if data['value'].startswith(bad_string):
                    data['value'] = data['value'][len(bad_string):-1]

            if (db_native == ChType.ENUM and
                    (dbr_type in (ChType.CTRL_ENUM, ChType.GR_ENUM))):
                # ctrl enum gets back the full string value
                assert data['value'] == db_value
            else:
                assert int(data['value']) == int(db_value)
        else:
            raise ValueError('TODO ' + str(dbr_type))

        # TODO metadata should be cast to requested type as well!
        same_type = (ca.native_type(dbr_type) == db_native)

        if (dbr_type in ca.control_types and same_type
                and dbr_type != ChType.CTRL_ENUM):
            for key in ctrl_keys:
                if (key == 'precision' and
                        ca.native_type(dbr_type) != ChType.DOUBLE):
                    print('skipping', key)
                    continue
                print('checking', key)
                assert float(data[key]) == getattr(db_entry, key), key

        if dbr_type in ca.time_types:
            timestamp = datetime.datetime.fromtimestamp(db_entry.timestamp)
            assert data['timestamp'] == timestamp

        if (dbr_type in ca.time_types or dbr_type in ca.status_types or
                dbr_type == ChType.STSACK_STRING):
            severity = data['severity']
            if not severity.endswith('_ALARM'):
                severity = '{}_ALARM'.format(severity)
            severity = getattr(ca._dbr.AlarmSeverity, severity)
            assert severity == db_entry.severity, key

            status = data['status']
            status = getattr(ca._dbr.AlarmStatus, status)
            assert status == db_entry.status, key

            if 'ackt' in data:
                ack_transient = data['ackt'] == 'YES'
                assert ack_transient == db_entry.alarm.acknowledge_transient

            if 'acks' in data:
                ack_severity = data['acks']
                ack_severity = getattr(ca._dbr.AlarmSeverity, ack_severity)
                assert ack_severity == db_entry.alarm.acknowledge_severity

    async def task():
        server_task = await curio.spawn(curio_server)

        try:
            await client()
        finally:
            await server_task.cancel()

    with curio.Kernel() as kernel:
        kernel.run(task)
    print('done')


caput_checks = [('int', '1', [1]),
                ('pi', '3.18', [3.18]),
                ('enum', 'd', 'd'),  # TODO inconsistency
                # ('enum2', 'cc', 'cc'),  # TODO inconsistency
                # ('str', 'resolve', [b'resolve']),  # TODO inconsistency - encoding
                # ('char', 'testing', 'testing'),  # TODO comes in as byte array
                # TODO string array, longer char array
                ]

@pytest.mark.parametrize('pv, put_value, check_value', caput_checks)
# @pytest.mark.parametrize('async_put', [True, False])
def test_with_caput(curio_server, pv, put_value, check_value, async_put=True):
    async def client():
        print('* client_test', pv, 'put value', put_value, 'check value',
              check_value)

        db_entry = caget_pvdb[pv]
        db_old = db_entry.value
        data = await run_caput(pv, put_value,
                               as_string=isinstance(db_entry, ca.ChannelChar))
        db_new = db_entry.value

        if isinstance(db_entry, (ca.ChannelInteger, ca.ChannelDouble)):
            clean_func = ast.literal_eval
        # elif isinstance(db_entry, ca.ChannelString):
        #     clean_func = lambda v: v.split(' ', 1)[1]
        else:
            clean_func = None

        if clean_func is not None:
            for key in ('old', 'new'):
                data[key] = clean_func(data[key])
        print('caput data', data)
        print('old from db', db_old)
        print('new from db', db_new)
        print('old from caput', data['old'])
        print('new from caput', data['new'])

        # check value from database compared to value from caput output
        assert db_new == data['new']
        # check value from database compared to value the test expects
        assert db_new == check_value

    async def task():
        server_task = await curio.spawn(curio_server)

        try:
            await client()
        finally:
            await server_task.cancel()

    with curio.Kernel() as kernel:
        kernel.run(task)
    print('done')
