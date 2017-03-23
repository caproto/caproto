import signal
import os
import datetime
import time
from multiprocessing import Process
import curio
import curio.subprocess
import caproto as ca
from caproto import ChType


TEST_SERVER_PORT = 5064


def test_synchronous_client():
    from caproto.examples.synchronous_client import main

    pid = os.getpid()

    def sigint(delay):
        time.sleep(delay)
        # By now the example should be subscribed and waiting for Ctrl+C.
        os.kill(pid, signal.SIGINT)

    p = Process(target=sigint, args=(2,))
    p.start()
    main()
    p.join()


def test_curio_client():
    from caproto.examples.curio_client import main
    main()


def test_curio_server():
    import caproto.examples.curio_server as server
    import caproto.examples.curio_client as client

    kernel = curio.Kernel()

    async def run_server():
        pvdb = ["pi"]
        ctx = server.Context('127.0.0.1', TEST_SERVER_PORT, pvdb)
        await ctx.run()

    async def run_client():
        # Some user function to call when subscriptions receive data.
        called = []
        def user_callback(command):
            print("Subscription has received data.")
            called.append(True)

        ctx = client.Context(server_port=TEST_SERVER_PORT)
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
        os.environ['EPICS_CA_ADDR_LIST'] = '127.0.0.1'
        server_task = await curio.spawn(run_server())
        await curio.sleep(1)  # Give server some time to start up.
        client_task = await run_client()
        print('client is done')
        await server_task.cancel()
        print('server is canceled', server_task.cancelled)  # prints True
        print(kernel._tasks)

    with kernel:
        kernel.run(task)
    # seems to hang here
    print('done')


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
    args = ['/usr/bin/env', 'caget', '-F', sep]
    if dbr_type is None:
        args += ['-a']
        wide_mode = True
    else:
        dbr_type = int(dbr_type)
        args += ['-d', str(dbr_type)]
        wide_mode = False
    args.append(pv)

    print('* Executing', args)
    output = await curio.subprocess.check_output(args)
    output = output.decode('latin-1')
    print('* output:')
    print(output)
    print('.')

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
    }

    lines = [line.strip() for line in output.split('\n')
             if line.strip()]

    if wide_mode:
        pv, timestamp, value, stat, sevr = lines[0].split(sep)
        info = dict(pv=pv,
                    timestamp=timestamp,
                    value=value,
                    status=stat,
                    severity=sevr)
    else:
        info = dict(pv=lines[0])
        for line in lines[1:]:
            if line:
                key, value = line.split(':', 1)
                info[key_map[key]] = value.strip()

    if 'timestamp' in info:
        info['timestamp'] = datetime.datetime.strptime(info['timestamp'],
                                                       '%Y-%m-%d %H:%M:%S.%f')

    return info


def test_curio_server_with_caget():
    import caproto.examples.curio_server as server

    pvdb = {'pi': server.DatabaseRecordDouble(
                    value=3.14,
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
            }

    ctrl_keys = ('upper_disp_limit', 'lower_alarm_limit',
                 'upper_alarm_limit', 'lower_warning_limit',
                 'upper_warning_limit', 'lower_ctrl_limit',
                 'upper_ctrl_limit', 'precision')

    status_keys = ('status', 'severity')

    async def run_server():
        nonlocal pvdb
        ctx = server.Context('0.0.0.0', TEST_SERVER_PORT, pvdb)
        await ctx.run()

    async def run_client_test(pv):
        print('* client_test', pv)
        data = await run_caget(pv)

        db_entry = pvdb[pv]
        db_native = ca.native_type(db_entry.data_type)

        for dbr_type in (ChType.DOUBLE, ChType.TIME_DOUBLE, ChType.CTRL_DOUBLE,
                         ChType.STS_DOUBLE, ChType.LONG, ChType.STS_LONG,
                         ChType.TIME_LONG, ChType.CTRL_LONG):

            data = await run_caget(pv, dbr_type=dbr_type)
            print('dbr_type', dbr_type, 'data:')
            print(data)

            db_value = db_entry.value

            # convert from string value to enum if requesting int
            if (db_native == ChType.ENUM and
                    ca.native_type(dbr_type) not in (ChType.ENUM,
                                                     ChType.STRING)):
                db_value = db_entry.strs.index(db_value)

            if ca.native_type(dbr_type) == ChType.LONG:
                assert int(data['value']) == int(db_value)
            elif ca.native_type(dbr_type) == ChType.DOUBLE:
                assert float(data['value']) == float(db_value)
            else:
                raise ValueError('TODO')

            # TODO metadata should be cast to requested type as well!
            same_type = (ca.native_type(dbr_type) == db_native)

            if dbr_type in ca.control_types and same_type:
                for key in ctrl_keys:
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
        nonlocal pvdb

        server_task = await curio.spawn(run_server())
        await curio.sleep(1)  # Give server some time to start up.

        try:
            for pv in pvdb:
                await run_client_test(pv)
        finally:
            await server_task.cancel()

    with curio.Kernel() as kernel:
        kernel.run(task)
    print('done')
