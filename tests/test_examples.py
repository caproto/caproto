import time

import pytest
import curio
import curio.subprocess

import caproto as ca


def setup_module(module):
    from conftest import start_repeater
    start_repeater()


def teardown_module(module):
    from conftest import stop_repeater
    stop_repeater()


def test_synchronous_client():
    from caproto.sync.simple_client import main
    main(skip_monitor_section=True)


def test_curio_client_example():
    from caproto.examples.curio_client_simple import main
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


def test_thread_client_example(threading_broadcaster):
    from caproto.examples.thread_client_simple import main
    main()


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


def test_curio_server_example():
    import caproto.curio.client as client
    from caproto.examples.curio_server_simple import (pvdb,
                                                      main as server_main)
    kernel = curio.Kernel()
    commands = []

    async def run_client():
        # Some user function to call when subscriptions receive data.

        def user_callback(command):
            print("Subscription has received data.")
            commands.append(command)

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
        sub_id = await chan1.subscribe()
        await chan1.unsubscribe(sub_id)
        await chan1.write((5,))
        reading = await chan1.read()
        expected = 5
        actual, = reading.data
        assert actual == expected
        print('reading:', reading)
        await chan1.write((6,))
        reading = await chan1.read()
        expected = 6
        actual, = reading.data
        assert actual == expected
        print('reading:', reading)

        # Test updating metadata...
        # _fields_ = [
        #     ('status', short_t),
        #     ('severity', short_t),
        #     ('secondsSinceEpoch', ctypes.c_uint32),
        #     ('nanoSeconds', ctypes.c_uint32),
        #     ('RISC_Pad', long_t),
        # ]
        metadata = (0, 0, ca.TimeStamp(4, 0), 0)  # set timestamp to 4 seconds
        await chan1.write((7,), data_type=ca.ChannelType.TIME_DOUBLE,
                          metadata=metadata)
        reading = await chan1.read(data_type=20)
        # check reading
        expected = 7
        actual, = reading.data
        assert actual == expected
        # check timestamp
        expected = 4
        actual = reading.metadata.secondsSinceEpoch
        assert actual == expected
        print('reading:', reading)

        # test updating alarm status/severity
        status, severity = ca.AlarmStatus.SCAN, ca.AlarmSeverity.MAJOR_ALARM
        metadata = (status, severity, ca.TimeStamp(0, 0), 0)
        await chan1.write((8,), data_type=ca.ChannelType.TIME_DOUBLE,
                          metadata=metadata)
        reading = await chan1.read(data_type=ca.ChannelType.TIME_DOUBLE)
        # check reading
        expected = 8
        actual, = reading.data
        assert actual == expected
        # check status
        actual = reading.metadata.status
        assert actual == status
        # check severity
        actual = reading.metadata.severity
        assert actual == severity

        await chan1.disconnect()
        assert commands, 'subscription not called in client'
        # await chan1.circuit.socket.close()

        commands.clear()
        await ctx.search('str')
        await ctx.search('str2')
        print('done searching')
        chan2 = await ctx.create_channel('str')
        chan3 = await ctx.create_channel('str2')
        chan2.register_user_callback(user_callback)
        chan3.register_user_callback(user_callback)
        await chan2.wait_for_connection()
        await chan3.wait_for_connection()
        sub_id2 = await chan2.subscribe()
        sub_id3 = await chan3.subscribe()
        print('write...')
        await chan2.write(b'hell')
        await chan3.write(b'good')
        print('write again...')
        metadata = (status, severity, ca.TimeStamp(0, 0))
        # Because this write touches the alarm, it should cause
        # chan3 to issue an EventAddResponse also.
        await chan2.write(b'hell', data_type=ca.ChannelType.TIME_STRING,
                          metadata=metadata)
        await chan2.unsubscribe(sub_id2)
        await chan3.unsubscribe(sub_id3)
        await curio.sleep(0.2)  # Ensure the subs have time to spin.
        assert len(commands) == 2 + 2 + 2

    async def task():
        # os.environ['EPICS_CA_ADDR_LIST'] = '255.255.255.255'
        try:
            server_task = await curio.spawn(server_main(pvdb))
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
