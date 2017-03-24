import signal
import os
import time
from multiprocessing import Process
import curio


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
    curio.run(main())


def test_curio_server():
    import caproto.examples.curio_server as server
    import caproto.examples.curio_client as client

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
        ctx = server.Context('127.0.0.1', 5066, pvdb)
        await ctx.run()

    async def run_client():
        # Some user function to call when subscriptions receive data.
        called = []
        def user_callback(command):
            print("Subscription has received data.")
            called.append(True)

        ctx = client.Context(server_port=5066)
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
