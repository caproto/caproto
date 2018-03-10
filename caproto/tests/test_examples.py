import time

import pytest
import curio

import caproto as ca

from .conftest import default_setup_module as setup_module  # noqa
from .conftest import default_teardown_module as teardown_module  # noqa


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
    from caproto.ioc_examples.type_varieties import (pvdb, main as server_main)
    kernel = curio.Kernel()
    commands = []

    async def run_client():
        # Some user function to call when subscriptions receive data.

        def user_callback(command):
            print("Subscription has received data: {}".format(command))
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
        await curio.sleep(0.2)
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

        print('timestamp is', reading.metadata.stamp.as_datetime())

        actual = reading.metadata.secondsSinceEpoch
        assert actual == expected
        print('reading:', reading)

        status, severity = ca.AlarmStatus.SCAN, ca.AlarmSeverity.MAJOR_ALARM
        server_alarm = pvdb['pi'].alarm

        await server_alarm.write(status=status, severity=severity)

        # test acknowledge alarm status/severity
        reading = await chan1.read(data_type=ca.ChannelType.TIME_DOUBLE)
        assert reading.metadata.status == status
        assert reading.metadata.severity == severity

        # acknowledge the severity
        metadata = (severity + 1, )
        await chan1.write((),
                          data_type=ca.ChannelType.PUT_ACKS,
                          metadata=metadata)

        assert server_alarm.severity_to_acknowledge == 0

        # now make a transient alarm and toggle the severity
        # now require transients to be acknowledged
        metadata = (1, )
        await chan1.write((),
                          data_type=ca.ChannelType.PUT_ACKT,
                          metadata=metadata)

        assert server_alarm.must_acknowledge_transient

        await server_alarm.write(severity=severity)
        await server_alarm.write(severity=ca.AlarmSeverity.NO_ALARM)

        assert server_alarm.severity_to_acknowledge == severity

        # acknowledge the severity
        metadata = (severity + 1, )
        await chan1.write((),
                          data_type=ca.ChannelType.PUT_ACKS,
                          metadata=metadata)

        assert server_alarm.severity_to_acknowledge == 0

        severity = ca.AlarmSeverity.NO_ALARM

        reading = await chan1.read(data_type=ca.ChannelType.TIME_DOUBLE)
        # check reading (unchanged since last time)
        expected = 7
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

        print('setting alarm status...')
        await pvdb['str'].alarm.write(severity=ca.AlarmSeverity.MAJOR_ALARM)

        await curio.sleep(0.5)

        await chan2.unsubscribe(sub_id2)
        await chan3.unsubscribe(sub_id3)
        # expecting that the subscription callback should get called:
        #   1. on connection (2)
        #   2. when chan2 is written to (1)
        #   3. when chan3 is written to (1)
        #   4. when alarm status is updated for both channels (2)
        # for a total of 6
        assert len(commands) == 2 + 2 + 2

    async def task():
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


def test_curio_server_and_thread_client(curio_server):
    from caproto.threading.client import (SharedBroadcaster,
                                          PVContext)
    from .conftest import threaded_in_curio_wrapper
    curio_server, caget_pvdb = curio_server

    @threaded_in_curio_wrapper
    def client_test():
        shared_broadcaster = SharedBroadcaster()
        cntx = PVContext(broadcaster=shared_broadcaster, log_level='DEBUG')

        pv = cntx.get_pv('int')
        assert pv.get() == caget_pvdb['int'].value
        print('get', pv.get())

        monitor_values = []

        def callback(value=None, **kwargs):
            print('monitor', value)
            monitor_values.append(value[0])

        pv.add_callback(callback)
        pv.put(1, wait=True)
        pv.put(2, wait=True)
        pv.put(3, wait=True)

        for i in range(3):
            if pv.get() == 3:
                break
            else:
                time.sleep(0.1)

        assert len(monitor_values) == 4

    async def task():
        server_task = await curio.spawn(curio_server)

        try:
            await curio.run_in_thread(client_test)
            await client_test.wait()
        finally:
            await server_task.cancel()

    with curio.Kernel() as kernel:
        kernel.run(task)


@pytest.mark.parametrize(
    'module_name, pvdb_class_name, class_kwargs',
    [('caproto.ioc_examples.currency_conversion_polling', 'CurrencyPollingIOC',
      {}),
     ('caproto.ioc_examples.currency_conversion', 'CurrencyConversionIOC', {}),
     ('caproto.ioc_examples.custom_write', 'CustomWrite', {}),
     ('caproto.ioc_examples.inline_style', 'InlineStyleIOC', {}),
     ('caproto.ioc_examples.io_interrupt', 'IOInterruptIOC', {}),
     ('caproto.ioc_examples.macros', 'MacroifiedNames',
      dict(macros={'beamline': 'my_beamline', 'thing': 'thing'})),
     ('caproto.ioc_examples.reading_counter', 'ReadingCounter', {}),
     ('caproto.ioc_examples.rpc_function', 'MyPVGroup', {}),
     ('caproto.ioc_examples.simple', 'SimpleIOC', {}),
     ('caproto.ioc_examples.subgroups', 'MyPVGroup', {}),
     ('caproto.ioc_examples.caproto_to_ophyd', 'Group', {}),
     ('caproto.ioc_examples.areadetector_image', 'DetectorGroup', {}),
     ]
)
def test_ioc_examples(request, module_name, pvdb_class_name, class_kwargs,
                      prefix):
    from .conftest import run_example_ioc
    from caproto._cli import get, put
    from caproto.curio import high_level_server
    import subprocess

    module = __import__(module_name,
                        fromlist=(module_name.rsplit('.', 1)[-1], ))

    pvdb_class = getattr(module, pvdb_class_name)

    print(f'Prefix: {prefix} PVDB class: {pvdb_class}')
    pvdb = pvdb_class(prefix=prefix, **class_kwargs).pvdb
    pvs = list(pvdb.keys())
    pv_to_check = pvs[0]

    print(f'PVs:', pvs)
    print(f'PV to check: {pv_to_check}')

    stdin = (subprocess.DEVNULL if 'io_interrupt' in module_name
             else None)

    print('stdin=', stdin)
    run_example_ioc(module_name, request=request,
                    args=[prefix],
                    pv_to_check=pv_to_check,
                    stdin=stdin)

    print(f'{module_name} IOC now running')

    put_values = [
        (high_level_server.PvpropertyReadOnlyData, None),
        (ca.ChannelNumeric, [1]),
        (ca.ChannelString, ['USD']),
    ]

    skip_pvs = [('ophyd', ':exit')]

    def find_put_value(pv):
        'Determine value to write to pv'
        for skip_ioc, skip_suffix in skip_pvs:
            if skip_ioc in module_name:
                if pv.endswith(skip_suffix):
                    return None

        for put_class, put_value in put_values:
            if isinstance(channeldata, put_class):
                return put_value
        else:
            raise Exception('Failed to set default value for channeldata:'
                            f'{channeldata.__class__}')

    for pv, channeldata in pvdb.items():
        value = find_put_value(pv)
        if value is None:
            print(f'Skipping write to {pv}')
            continue

        print(f'Writing {value} to {pv}')
        put(pv, value, verbose=True)

        value = get(pv, verbose=True)
        print(f'Read {pv} = {value}')


def test_areadetector_generate():
    from caproto.ioc_examples import areadetector_image

    # smoke-test the generation code
    areadetector_image.generate_detector_code()


def test_typhon_example(request, prefix):
    from .conftest import run_example_ioc
    run_example_ioc('caproto.ioc_examples.caproto_to_ophyd', request=request,
                    args=[prefix], pv_to_check=f'{prefix}random1')

    from caproto.ioc_examples import caproto_to_typhon
    caproto_to_typhon.pydm = None

    caproto_to_typhon.run_typhon(prefix=prefix)
