import subprocess
import sys
import time

import curio
import pytest

import caproto as ca
from caproto.sync.client import read as sync_read

from . import conftest
from .conftest import default_setup_module as setup_module  # noqa
from .conftest import default_teardown_module as teardown_module  # noqa

try:
    import numpy
except ImportError:
    # Used in pytest.mark.skipif() below.
    numpy = None


def test_asyncio_client_example(ioc):
    from caproto.examples.asyncio_client_simple import main as example_main
    coro = example_main(pv1=ioc.pvs['int'], pv2=ioc.pvs['int2'])
    ca.asyncio.utils.run(coro, debug=True)


def test_thread_client_example(curio_server):
    from caproto.examples.thread_client_simple import main as example_main
    server_runner, prefix, caget_pvdb = curio_server

    @conftest.threaded_in_curio_wrapper
    def client():
        example_main(pvname1=prefix + 'int',
                     pvname2=prefix + 'str')

    with curio.Kernel() as kernel:
        kernel.run(server_runner, client)


ioc_examples = [
    pytest.param(
        "caproto.tests.ioc_all_in_one", "MyPVGroup",
        dict(macros={"macro": "expanded"}),
    ),
    pytest.param("caproto.ioc_examples.chirp", "Chirp", {"ramp_rate": 0.75}),
    pytest.param("caproto.ioc_examples.custom_write", "CustomWrite", {}),
    pytest.param("caproto.ioc_examples.decay", "Decay", {}),
    pytest.param("caproto.tests.ioc_inline_style", "InlineStyleIOC", {}),
    pytest.param("caproto.ioc_examples.io_interrupt", "IOInterruptIOC", {}),
    pytest.param(
        "caproto.ioc_examples.macros",
        "MacroifiedNames",
        dict(macros={"beamline": "my_beamline", "suffix": "thing"}),
        # no termios support; skip on windows
        marks=pytest.mark.skipif(sys.platform == "win32", reason="No termios support"),
    ),
    pytest.param(
        "caproto.ioc_examples.mini_beamline",
        "MiniBeamline",
        {},
        marks=pytest.mark.skipif(numpy is None, reason="Requires numpy"),
    ),
    pytest.param("caproto.ioc_examples.random_walk", "RandomWalkIOC", {}),
    pytest.param(
        "caproto.ioc_examples.pathological.reading_counter", "ReadingCounter", {}
    ),
    pytest.param("caproto.ioc_examples.rpc_function", "MyPVGroup", {}),
    pytest.param("caproto.ioc_examples.scalars_and_arrays", "ArrayIOC", {}),
    pytest.param("caproto.ioc_examples.scan_rate", "ScanRateIOC", {}),
    pytest.param("caproto.ioc_examples.setpoint_rbv_pair", "Group", {}),
    pytest.param("caproto.ioc_examples.simple", "SimpleIOC", {}),
    pytest.param(
        "caproto.ioc_examples.startup_and_shutdown_hooks", "StartupAndShutdown", {}
    ),
    pytest.param("caproto.ioc_examples.subgroups", "MyPVGroup", {}),
    pytest.param(
        "caproto.ioc_examples.thermo_sim",
        "Thermo",
        {},
        marks=pytest.mark.skipif(numpy is None, reason="Requires numpy"),
    ),
    pytest.param("caproto.ioc_examples.too_clever.trigger_with_pc", "TriggeredIOC", {}),
    pytest.param("caproto.ioc_examples.worker_thread", "WorkerThreadIOC", {}),
    pytest.param("caproto.ioc_examples.worker_thread_pc", "WorkerThreadIOC", {}),
    pytest.param(
        "caproto.ioc_examples.too_clever.caproto_to_ophyd",
        "Group",
        {},
        marks=[
            pytest.mark.flaky(reruns=10, reruns_delay=2),
            pytest.mark.skipif(sys.platform == "win32", reason="No win32 support"),
            pytest.mark.skipif(numpy is None, reason="Requires numpy"),
        ],
    ),
    pytest.param(
        "caproto.ioc_examples.too_clever.areadetector_image",
        "DetectorGroup",
        {},
        marks=pytest.mark.xfail(reason="Can be flaky"),
    ),
]


@pytest.mark.flaky(reruns=2, reruns_delay=2)
@pytest.mark.parametrize("module_name, pvdb_class_name, class_kwargs",
                         ioc_examples)
@pytest.mark.parametrize('async_lib', ['curio', 'trio', 'asyncio'])
def test_ioc_examples(request, module_name, pvdb_class_name, class_kwargs,
                      prefix, async_lib):
    from caproto.server import PvpropertyReadOnlyData
    from caproto.sync.client import read, write

    from .conftest import run_example_ioc

    module = __import__(module_name,
                        fromlist=(module_name.rsplit('.', 1)[-1], ))

    pvdb_class = getattr(module, pvdb_class_name)

    print(f'Prefix: {prefix} PVDB class: {pvdb_class}')
    pvdb = pvdb_class(prefix=prefix, **class_kwargs).pvdb
    pvs = list(pvdb.keys())
    pv_to_check = pvs[0]

    print('PVs:', pvs)
    print(f'PV to check: {pv_to_check}')

    stdin = (subprocess.DEVNULL if 'io_interrupt' in module_name
             else None)

    run_example_ioc(module_name, request=request,
                    args=['--prefix', prefix, '--async-lib', async_lib],
                    pv_to_check=pv_to_check,
                    stdin=stdin)

    print(f'{module_name} IOC now running')

    put_values = [
        (PvpropertyReadOnlyData, None),
        (ca.ChannelNumeric, [1]),
        (ca.ChannelString, ['USD']),
        (ca.ChannelChar, 'USD'),
        (ca.ChannelByte, b'USD'),
        (ca.ChannelEnum, [0]),
    ]

    skip_pvs = [('ophyd', ':exit')]

    def find_put_value(pv, channeldata):
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
        value = find_put_value(pv, channeldata)
        if value is None:
            print(f'Skipping write to {pv}')
            continue

        print(f'Writing {value} to {pv}')
        write(pv, value, timeout=15)

        value = read(pv, timeout=15)
        print(f'Read {pv} = {value}')


@pytest.mark.xfail(reason="Flaky, and AD IOC may not be running on host")
def test_areadetector_generate():
    pytest.importorskip('numpy')
    from caproto.ioc_examples.too_clever import areadetector_image

    # smoke-test the generation code
    areadetector_image.generate_detector_code()


def test_typhos_example(request, prefix):
    pytest.importorskip('numpy')
    from .conftest import run_example_ioc
    run_example_ioc('caproto.ioc_examples.too_clever.caproto_to_ophyd', request=request,
                    args=['--prefix', prefix], pv_to_check=f'{prefix}random1')

    from caproto.ioc_examples.too_clever import caproto_to_typhos
    caproto_to_typhos.pydm = None
    caproto_to_typhos.run_typhos(prefix=prefix)


def test_records(request, prefix):
    from .conftest import run_example_ioc
    run_example_ioc('caproto.ioc_examples.records', request=request,
                    args=['--prefix', prefix], pv_to_check=f'{prefix}A')

    from caproto.sync.client import read, write

    # check that the alarm fields are linked
    b = f'{prefix}B'
    b_val = f'{prefix}B.VAL'
    b_stat = f'{prefix}B.STAT'
    b_severity = f'{prefix}B.SEVR'
    write(b_val, 0, notify=True)
    assert list(read(b_val).data) == [0]
    assert list(read(b_stat).data) == [b'NO_ALARM']
    assert list(read(b_severity).data) == [b'NO_ALARM']

    # write a special value that causes it to fail
    with pytest.raises(ca.ErrorResponseReceived):
        write(b_val, 1, notify=True)

    # status should be WRITE, MAJOR
    assert list(read(b_val).data) == [0]
    assert list(read(b_stat).data) == [b'WRITE']
    assert list(read(b_severity).data) == [b'MAJOR']

    # now a field that's linked back to the precision metadata:
    b_precision = f'{prefix}B.PREC'
    assert list(read(b_precision).data) == [3]
    write(b_precision, 4, notify=True)
    assert list(read(b_precision).data) == [4]

    # does writing to .PREC update the ChannelData metadata?
    data = read(b, data_type=ca.ChannelType.CTRL_DOUBLE)
    assert data.metadata.precision == 4


def test_records_subclass(request, prefix):
    from .conftest import run_example_ioc
    run_example_ioc('caproto.ioc_examples.records_subclass',
                    request=request,
                    args=['--prefix', prefix], pv_to_check=f'{prefix}motor1')

    from caproto.sync.client import read, write
    motor = f'{prefix}motor1'
    motor_val = f'{motor}.VAL'
    motor_rbv = f'{motor}.RBV'
    motor_drbv = f'{motor}.DRBV'

    write(motor_val, 100, notify=True)
    # sleep for a few pollling periods:
    time.sleep(0.5)
    assert abs(read(motor_rbv).data[0] - 100) < 0.1
    assert abs(read(motor_drbv).data[0] - 100) < 0.1


def test_pvproperty_string_array(request, prefix):
    from .conftest import run_example_ioc
    run_example_ioc('caproto.ioc_examples.scalars_and_arrays',
                    request=request,
                    args=['--prefix', prefix], pv_to_check=f'{prefix}scalar_int')

    from caproto.sync.client import read, write
    array_string_pv = f'{prefix}array_string'

    write(array_string_pv, ['array', 'of', 'strings'], notify=True)
    time.sleep(0.5)
    assert read(array_string_pv).data == [b'array', b'of', b'strings']


def test_enum_linking(request, prefix):
    from .conftest import run_example_ioc
    run_example_ioc('caproto.ioc_examples.enums',
                    request=request,
                    args=['--prefix', prefix], pv_to_check=f'{prefix}bi')

    from caproto.sync.client import read, write

    def string_read(pv):
        return b''.join(read(pv, data_type=ca.ChannelType.STRING).data)

    for pv, znam, onam in [(f'{prefix}bi', b'a', b'b'),
                           (f'{prefix}bo', b'Zero Value', b'One Value')]:
        assert string_read(f'{pv}.ZNAM') == znam
        assert string_read(f'{pv}.ONAM') == onam

        for value, expected in ([0, znam], [1, onam]):

            write(pv, [value], notify=True)
            assert string_read(pv) == expected


@pytest.mark.parametrize('async_lib', ['curio', 'trio', 'asyncio'])
def test_event_read_collision(request, prefix, async_lib):
    # this is testing that monitors do not get pushed into
    # the socket while a ReadResponse is being pushed in parts.
    from .conftest import run_example_ioc
    run_example_ioc('caproto.ioc_examples.big_image_noisy_neighbor',
                    request=request,
                    args=['--prefix', prefix, '--async-lib', async_lib],
                    pv_to_check=f'{prefix}t1')
    from caproto.threading.pyepics_compat import Context, get_pv
    cntx = Context()
    image = get_pv(pvname=f'{prefix}image', context=cntx)
    t1 = get_pv(pvname=f'{prefix}t1', context=cntx)
    t1.add_callback(lambda value, **kwargs: None)

    for _ in range(4):
        image.get(timeout=45)

    image.disconnect()
    t1.disconnect()

    cntx.disconnect()


def test_long_strings(request, prefix):
    from .conftest import run_example_ioc
    run_example_ioc('caproto.ioc_examples.records', request=request,
                    args=['--prefix', prefix], pv_to_check=f'{prefix}E')

    stringin = f'{prefix}E'
    regular = sync_read(f'{stringin}.VAL', data_type='native')
    assert regular.data_type == ca.ChannelType.STRING
    data, = regular.data
    length = len(data)
    assert length > 1  # based on the default value in the test

    for dtype in ('native', 'control', 'time', 'graphic'):
        longstr = sync_read(f'{stringin}.VAL$', data_type=dtype)
        longstr_data = b''.join(longstr.data)
        expected_dtype = ca._dbr.field_types[dtype][ca.ChannelType.CHAR]
        assert longstr.data_type == expected_dtype
        assert len(longstr.data) == length
        assert longstr_data == data

    with pytest.raises(TimeoutError):
        # an analog input .VAL has no long string option
        sync_read(f'{prefix}A.VAL$', data_type='native')
