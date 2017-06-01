import os
import datetime
import time

import pytest
import curio
import curio.subprocess

import caproto as ca
from caproto.curio.server import find_next_tcp_port
import caproto.curio.server as server

from caproto import ChType


REPEATER_PORT = 5065
SERVER_HOST = '0.0.0.0'


def setup_module(module):
    from conftest import start_repeater
    start_repeater()


def teardown_module(module):
    from conftest import stop_repeater
    stop_repeater()


def test_synchronous_client():
    from caproto.sync.simple_client import main
    main(skip_monitor_section=True)


def test_curio_client():
    from caproto.curio.client import main
    with curio.Kernel() as kernel:
        kernel.run(main())


@pytest.fixture(scope='module')
def threading_broadcaster(request):
    from caproto.threading.client import SharedBroadcaster
    broadcaster = SharedBroadcaster()

    def cleanup():
        broadcaster.disconnect()

    request.addfinalizer(cleanup)
    return broadcaster


def test_thread_client(threading_broadcaster):
    from caproto.threading.client import _test as thread_client_test
    thread_client_test()


def test_thread_pv(threading_broadcaster):
    from caproto.threading.client import Context, PV

    pv1 = "XF:31IDA-OP{Tbl-Ax:X1}Mtr.VAL"
    # pv2 = "XF:31IDA-OP{Tbl-Ax:X2}Mtr.VAL"

    # Some user function to call when subscriptions receive data.
    called = []

    def user_callback(*, value, **kwargs):
        print()
        print('-- user callback', value)
        called.append(True)

    ctx = Context(threading_broadcaster, log_level='DEBUG')
    ctx.register()

    time_pv = PV(pv1, context=ctx, form='time')
    ctrl_pv = PV(pv1, context=ctx, form='ctrl')

    time_pv.wait_for_connection()
    time_pv.add_callback(user_callback)
    print('time read', time_pv.get())
    print('ctrl read', ctrl_pv.get())

    time_pv.put(3, wait=True)
    time_pv.put(6, wait=True)

    time.sleep(0.1)
    assert time_pv.get() == 6
    assert called

    print('read', time_pv.get())
    print('done')

    repr(time_pv)

    for k, v in PV.__dict__.items():
        if isinstance(v, property):
            getattr(time_pv, k)
            getattr(ctrl_pv, k)


def test_curio_server():
    import caproto.curio.client as client
    from caproto.curio.server import _test as example_server
    kernel = curio.Kernel()
    called = []

    async def run_client():
        # Some user function to call when subscriptions receive data.

        def user_callback(command):
            print("Subscription has received data.")
            called.append(True)

        broadcaster = client.SharedBroadcaster(log_level='DEBUG')
        await broadcaster.register()
        ctx = client.Context(broadcaster, log_level='DEBUG')
        await ctx.search('pi')
        print('done searching')
        chan1 = await ctx.create_channel('pi')
        chan1.register_user_callback(user_callback)
        # ...and then wait for all the responses.
        await chan1.wait_for_connection()
        reading = await chan1.read()
        print('reading:', reading)
        await chan1.subscribe()
        await chan1.unsubscribe(0)
        await chan1.write((5,))
        reading = await chan1.read()
        print('reading:', reading)
        await chan1.write((6,))
        reading = await chan1.read()
        print('reading:', reading)
        await chan1.disconnect()
        await chan1.circuit.socket.close()

    async def task():
        # os.environ['EPICS_CA_ADDR_LIST'] = '255.255.255.255'
        try:
            server_task = await curio.spawn(example_server())
            await curio.sleep(1)  # Give server some time to start up.
            await run_client()
            print('client is done')
        finally:
            await server_task.cancel()
            print('server is canceled', server_task.cancelled)  # prints True
            print(kernel._tasks)

    with kernel:
        kernel.run(task)
    assert called, 'subscription not called in client'
    print('done')


async def run_epics_base_binary(*args):
    '''Run an EPICS-base binary with the environment variables set

    Returns
    -------
    stdout, stderr
        Decoded standard output and standard error text
    '''
    args = ['/usr/bin/env'] + list(args)

    print()
    print('* Executing', args)

    epics_env = ca.get_environment_variables()
    env = dict(PATH=os.environ['PATH'],
               EPICS_CA_AUTO_ADDR_LIST=epics_env['EPICS_CA_AUTO_ADDR_LIST'],
               EPICS_CA_ADDR_LIST=epics_env['EPICS_CA_ADDR_LIST'])

    p = curio.subprocess.Popen(args, env=env,
                               stdout=curio.subprocess.PIPE,
                               stderr=curio.subprocess.PIPE)
    await p.wait()
    raw_stdout = await p.stdout.read()
    raw_stderr = await p.stderr.read()
    stdout = raw_stdout.decode('latin-1')
    stderr = raw_stderr.decode('latin-1')
    return stdout, stderr


async def run_caget(pv, *, dbr_type=None):
    '''Execute epics-base caget and parse results into a dictionary

    Parameters
    ----------
    pv : str
        PV name
    dbr_type : caproto.ChType, optional
        Specific dbr_type to request
    '''
    sep = '@'
    args = ['caget', '-w', '0.2', '-F', sep]
    if dbr_type is None:
        args += ['-a']
        wide_mode = True
    else:
        dbr_type = int(dbr_type)
        args += ['-d', str(dbr_type)]
        wide_mode = False
    args.append(pv)

    output, stderr = await run_epics_base_binary(*args)

    print('----------------------------------------------------------')
    print(output)
    print()

    key_map = {
        'Native data type': 'native_data_type',
        'Request type': 'request_type',
        'Element count': 'element_count',
        'Value': 'value',
        'Status': 'status',
        'Severity': 'severity',
        'Units': 'units',
        'Lo disp limit': 'lower_disp_limit',
        'Hi disp limit': 'upper_disp_limit',
        'Lo alarm limit': 'lower_alarm_limit',
        'Lo warn limit': 'lower_warning_limit',
        'Hi warn limit': 'upper_warning_limit',
        'Hi alarm limit': 'upper_alarm_limit',
        'Lo ctrl limit': 'lower_ctrl_limit',
        'Hi ctrl limit': 'upper_ctrl_limit',
        'Timestamp': 'timestamp',
        'Precision': 'precision',
        'Enums': 'enums',
        'Class Name': 'class_name',
        'Ack transient?': 'ackt',
        'Ack severity': 'acks',
    }

    lines = [line.strip() for line in output.split('\n')
             if line.strip()]

    if not lines:
        raise RuntimeError('caget failed: {}'.format(stderr))

    if wide_mode:
        pv, timestamp, value, stat, sevr = lines[0].split(sep)
        info = dict(pv=pv,
                    timestamp=timestamp,
                    value=value,
                    status=stat,
                    severity=sevr)
    else:
        info = dict(pv=lines[0])
        in_enum_section = False
        enums = {}
        for line in lines[1:]:
            if line:
                if in_enum_section:
                    num, name = line.split(']', 1)
                    num = int(num[1:])
                    enums[num] = name.strip()
                else:
                    key, value = line.split(':', 1)
                    info[key_map[key]] = value.strip()

                    if key == 'Enums':
                        in_enum_section = True
        if enums:
            info['enums'] = enums

    if 'timestamp' in info:
        if info['timestamp'] != '<undefined>':
            info['timestamp'] = datetime.datetime.strptime(
                info['timestamp'], '%Y-%m-%d %H:%M:%S.%f')

    return info

# ca_test does not exist in our builds
# async def run_base_catest(pv, *, dbr_type=None):
#     '''Execute epics-base ca_test and parse results into a dictionary
#
#     Parameters
#     ----------
#     pv : str
#         PV name
#     '''
#     output, stderr = await run_epics_base_binary('ca_test', pv)
#
#     print('----------------------------------------------------------')
#
#     lines = []
#     line_starters = ['name:', 'native type:', 'native count:']
#     for line in output.split('\n'):
#         line = line.rstrip()
#         if line.startswith('DBR'):
#             lines.append(line)
#         else:
#             if any(line.startswith(starter) for starter in line_starters):
#                 lines.append(line)
#             else:
#                 lines[-1] += line
#
#     return lines

str_alarm_status = ca.ChannelAlarmStatus(
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
                            alarm_status=str_alarm_status,
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
def test_curio_server_with_caget(curio_server, pv, dbr_type):
    ctrl_keys = ('upper_disp_limit', 'lower_alarm_limit',
                 'upper_alarm_limit', 'lower_warning_limit',
                 'upper_warning_limit', 'lower_ctrl_limit',
                 'upper_ctrl_limit', 'precision')

    async def run_client_test():
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
                db_string_value = str(db_value)
                string_length = len(db_string_value)
                read_value = data['value'][:string_length]
                assert int(data['element_count']) == string_length
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
            await run_client_test()
        finally:
            await server_task.cancel()

    with curio.Kernel() as kernel:
        kernel.run(task)
    print('done')
