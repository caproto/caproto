import os
import datetime
import logging
import time
from multiprocessing import Process

import pytest
import curio
import curio.subprocess

import caproto as ca
from caproto.curio.server import find_next_tcp_port
import caproto.curio.server as server

from caproto import ChType


REPEATER_PORT = 5065
SERVER_HOST = '0.0.0.0'

_repeater_process = None


def get_broadcast_addr_list():
    import netifaces

    interfaces = [netifaces.ifaddresses(interface)
                  for interface in netifaces.interfaces()
                  ]
    bcast = [af_inet_info['broadcast']
             if 'broadcast' in af_inet_info
             else af_inet_info['peer']

             for interface in interfaces
             if netifaces.AF_INET in interface
             for af_inet_info in interface[netifaces.AF_INET]
             ]

    print('Broadcast address list:', bcast)
    return ' '.join(bcast)


def setup_module(module):
    global _repeater_process
    from caproto.asyncio.repeater import main
    logging.getLogger('caproto').setLevel(logging.DEBUG)
    logging.basicConfig()

    _repeater_process = Process(target=main)
    _repeater_process.start()

    print('Waiting for the repeater to start up...')
    time.sleep(2)


def teardown_module(module):
    global _repeater_process
    print('teardown_module: killing repeater process')
    _repeater_process.terminate()
    _repeater_process = None


def test_synchronous_client():
    from caproto.sync.simple_client import main
    main(skip_monitor_section=True)


def test_curio_client():
    from caproto.curio.client import main
    with curio.Kernel() as kernel:
        kernel.run(main())


def test_thread_client():
    from caproto.threading.client import Context

    pv1 = "XF:31IDA-OP{Tbl-Ax:X1}Mtr.VAL"
    pv2 = "XF:31IDA-OP{Tbl-Ax:X2}Mtr.VAL"

    # Some user function to call when subscriptions receive data.
    called = []

    def user_callback(command):
        print("Subscription has received data.")
        called.append(True)

    ctx = Context()
    ctx.register()
    ctx.search(pv1)
    ctx.search(pv2)
    # Send out connection requests without waiting for responses...
    chan1 = ctx.create_channel(pv1)
    chan2 = ctx.create_channel(pv2)
    # Set up a function to call when subscriptions are received.
    chan1.register_user_callback(user_callback)

    reading = chan1.read()
    print('reading:', reading)
    chan1.subscribe()
    chan2.read()
    chan1.unsubscribe(0)
    chan1.write((5,))
    reading = chan1.read()
    assert reading.data == 5
    print('reading:', reading)
    chan1.write((6,))
    reading = chan1.read()
    assert reading.data == 6
    print('reading:', reading)
    chan2.clear()
    chan1.clear()
    assert called


def test_thread_pv():
    from caproto.threading.client import Context, PV

    pv1 = "XF:31IDA-OP{Tbl-Ax:X1}Mtr.VAL"
    # pv2 = "XF:31IDA-OP{Tbl-Ax:X2}Mtr.VAL"

    # Some user function to call when subscriptions receive data.
    called = []

    def user_callback(*, value, **kwargs):
        print()
        print('-- user callback', value)
        called.append(True)

    ctx = Context()
    ctx.register()

    time_pv = PV(pv1, context=ctx, form='time')
    ctrl_pv = PV(pv1, context=ctx, form='ctrl')

    time_pv.wait_for_connection()
    time_pv.add_callback(user_callback)
    print('time read', time_pv.get())
    print('ctrl read', ctrl_pv.get())

    time_pv.put(3)
    time_pv.put(6)

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
    kernel = curio.Kernel()

    async def run_server():
        pvdb = {'pi': server.DatabaseRecordDouble(value=3.14,
                                                  lower_disp_limit=3.13,
                                                  upper_disp_limit=3.15,
                                                  lower_alarm_limit=3.12,
                                                  upper_alarm_limit=3.16,
                                                  lower_warning_limit=3.11,
                                                  upper_warning_limit=3.17,
                                                  lower_ctrl_limit=3.10,
                                                  upper_ctrl_limit=3.18,
                                                  precision=5,
                                                  units='doodles')}
        port = find_next_tcp_port(host=SERVER_HOST)
        print('Server will be on', (SERVER_HOST, port))
        ctx = server.Context(SERVER_HOST, port, pvdb)
        await ctx.run()

    async def run_client():
        # Some user function to call when subscriptions receive data.
        called = []

        def user_callback(command):
            print("Subscription has received data.")
            called.append(True)

        ctx = client.Context()
        await ctx.register()
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
        await chan1.clear()
        assert called
        await chan1.circuit.socket.close()

    async def task():
        # os.environ['EPICS_CA_ADDR_LIST'] = '255.255.255.255'
        try:
            server_task = await curio.spawn(run_server())
            await curio.sleep(1)  # Give server some time to start up.
            await run_client()
            print('client is done')
        finally:
            await server_task.cancel()
            print('server is canceled', server_task.cancelled)  # prints True
            print(kernel._tasks)

    with kernel:
        kernel.run(task)
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


caget_pvdb = {
    'pi': server.DatabaseRecordDouble(value=3.14,
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
    'enum': server.DatabaseRecordEnum(value='b',
                                      strs=['a', 'b', 'c', 'd'],
                                      ),
    'int': server.DatabaseRecordInteger(value=33,
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
    }


@pytest.fixture(scope='function')
def curio_server():
    async def run_server():
        port = find_next_tcp_port(host=SERVER_HOST)
        print('Server will be on', (SERVER_HOST, port))
        ctx = server.Context(SERVER_HOST, port, caget_pvdb)
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
     for pv in caget_pvdb
     for dtype in ca.native_types),
    []
)


@pytest.mark.parametrize('pv, dbr_type', caget_checks)
def test_curio_server_with_caget(curio_server, pv, dbr_type):
    ctrl_keys = ('upper_disp_limit', 'lower_alarm_limit',
                 'upper_alarm_limit', 'lower_warning_limit',
                 'upper_warning_limit', 'lower_ctrl_limit',
                 'upper_ctrl_limit', 'precision')

    status_keys = ('status', 'severity')

    async def run_client_test():
        print('* client_test', pv, dbr_type)
        db_entry = caget_pvdb[pv]
        db_native = ca.native_type(db_entry.data_type)

        data = await run_caget(pv, dbr_type=dbr_type)
        print('dbr_type', dbr_type, 'data:')
        print(data)

        db_value = db_entry.value

        # convert from string value to enum if requesting int
        if (db_native == ChType.ENUM and
                not (ca.native_type(dbr_type) == ChType.STRING
                     or dbr_type == ChType.CTRL_ENUM)):
            db_value = db_entry.strs.index(db_value)

        if ca.native_type(dbr_type) in (ChType.INT, ChType.LONG,
                                        ChType.CHAR):
            assert int(data['value']) == int(db_value)
        elif ca.native_type(dbr_type) in (ChType.FLOAT, ChType.DOUBLE):
            assert float(data['value']) == float(db_value)
        elif ca.native_type(dbr_type) == ChType.STRING:
            assert data['value'] == str(db_value)
        elif ca.native_type(dbr_type) == ChType.ENUM:
            bad_strings = ['Illegal Value (', 'Enum Index Overflow (']
            for bad_string in bad_strings:
                if data['value'].startswith(bad_string):
                    data['value'] = data['value'][len(bad_string):-1]

            if db_native == ChType.ENUM and dbr_type == ChType.CTRL_ENUM:
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

        if dbr_type in ca.time_types or dbr_type in ca.status_types:
            for key in status_keys:
                value = getattr(ca._dbr, data[key])
                assert value == getattr(db_entry, key), key

    async def task():
        server_task = await curio.spawn(curio_server)

        try:
            await run_client_test()
        finally:
            await server_task.cancel()

    with curio.Kernel() as kernel:
        kernel.run(task)
    print('done')


if __name__ == '__main__':
    setup_module(None)
    os.environ['EPICS_CA_ADDR_LIST'] = get_broadcast_addr_list()
    os.environ['EPICS_CA_AUTO_ADDR_LIST'] = 'no'
    try:
        test_curio_client()
        test_curio_server()
        test_curio_server_with_caget()
    finally:
        teardown_module(None)
