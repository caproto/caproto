import time

import curio
import pytest

import caproto as ca
from caproto.sync import client as sync

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


@pytest.mark.flaky(reruns=2, reruns_delay=2)
@pytest.mark.parametrize(
    "module_name",
    [pytest.param(name, marks=info["marks"])
     for name, info in conftest.ioc_example_to_info.items()
     ]
)
@pytest.mark.parametrize('async_lib', ['curio', 'trio', 'asyncio'])
def test_ioc_examples(request, module_name, async_lib):
    from caproto.server import PvpropertyReadOnlyData
    info = conftest.run_example_ioc_by_name(
        module_name, async_lib=async_lib, request=request
    )

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

    for pv, channeldata in info.pvdb.items():
        value = find_put_value(pv, channeldata)
        if value is None:
            print(f'Skipping write to {pv}')
            continue

        print(f'Writing {value} to {pv}')
        sync.write(pv, value, timeout=15)

        value = sync.read(pv, timeout=15)
        print(f'Read {pv} = {value}')


@pytest.mark.xfail(reason="Flaky, and AD IOC may not be running on host")
def test_areadetector_generate():
    pytest.importorskip('numpy')
    from caproto.ioc_examples.too_clever import areadetector_image

    # smoke-test the generation code
    areadetector_image.generate_detector_code()


@conftest.parametrize_iocs(
    "caproto.ioc_examples.too_clever.caproto_to_ophyd"
)
def test_typhos_example(request, ioc_name):
    info = conftest.run_example_ioc_by_name(ioc_name, request=request)
    from caproto.ioc_examples.too_clever import caproto_to_typhos
    caproto_to_typhos.pydm = None
    caproto_to_typhos.run_typhos(prefix=info.prefix)


def test_records(request):
    info = conftest.run_example_ioc_by_name(
        'caproto.ioc_examples.records', request=request,
    )
    prefix = info.prefix

    # check that the alarm fields are linked
    b = f'{prefix}B'
    b_val = f'{prefix}B.VAL'
    b_stat = f'{prefix}B.STAT'
    b_severity = f'{prefix}B.SEVR'
    sync.write(b_val, 0, notify=True)
    assert list(sync.read(b_val).data) == [0]
    assert list(sync.read(b_stat).data) == [b'NO_ALARM']
    assert list(sync.read(b_severity).data) == [b'NO_ALARM']

    # write a special value that causes it to fail
    with pytest.raises(ca.ErrorResponseReceived):
        sync.write(b_val, 1, notify=True)

    # status should be WRITE, MAJOR
    assert list(sync.read(b_val).data) == [0]
    assert list(sync.read(b_stat).data) == [b'WRITE']
    assert list(sync.read(b_severity).data) == [b'MAJOR']

    # now a field that's linked back to the precision metadata:
    b_precision = f'{prefix}B.PREC'
    assert list(sync.read(b_precision).data) == [3]
    sync.write(b_precision, 4, notify=True)
    assert list(sync.read(b_precision).data) == [4]

    # does writing to .PREC update the ChannelData metadata?
    data = sync.read(b, data_type=ca.ChannelType.CTRL_DOUBLE)
    assert data.metadata.precision == 4


@conftest.parametrize_iocs(
    "caproto.ioc_examples.records_subclass"
)
def test_records_subclass(request, prefix, ioc_name):
    info = conftest.run_example_ioc_by_name(ioc_name, request=request)
    prefix = info.prefix

    motor = f'{prefix}motor1'
    motor_val = f'{motor}.VAL'
    motor_rbv = f'{motor}.RBV'
    motor_drbv = f'{motor}.DRBV'

    sync.write(motor_val, 100, notify=True)
    # sleep for a few pollling periods:
    time.sleep(0.5)
    assert abs(sync.read(motor_rbv).data[0] - 100) < 0.1
    assert abs(sync.read(motor_drbv).data[0] - 100) < 0.1


@conftest.parametrize_iocs(
    "caproto.ioc_examples.scalars_and_arrays"
)
def test_pvproperty_string_array(request, ioc_name):
    info = conftest.run_example_ioc_by_name(ioc_name, request=request)
    array_string_pv = f'{info.prefix}array_string'

    sync.write(array_string_pv, ['array', 'of', 'strings'], notify=True)
    time.sleep(0.5)
    assert sync.read(array_string_pv).data == [b'array', b'of', b'strings']


@conftest.parametrize_iocs(
    "caproto.ioc_examples.enums"
)
def test_enum_linking(request, ioc_name):
    info = conftest.run_example_ioc_by_name(ioc_name, request=request)
    prefix = info.prefix

    def string_read(pv):
        return b''.join(sync.read(pv, data_type=ca.ChannelType.STRING).data)

    for pv, znam, onam in [(f'{prefix}bi', b'a', b'b'),
                           (f'{prefix}bo', b'Zero Value', b'One Value')]:
        assert string_read(f'{pv}.ZNAM') == znam
        assert string_read(f'{pv}.ONAM') == onam

        for value, expected in ([0, znam], [1, onam]):

            sync.write(pv, [value], notify=True)
            assert string_read(pv) == expected


@pytest.mark.parametrize('async_lib', ['curio', 'trio', 'asyncio'])
def test_event_read_collision(request, prefix, async_lib):
    # this is testing that monitors do not get pushed into
    # the socket while a ReadResponse is being pushed in parts.
    conftest.run_example_ioc(
        'caproto.ioc_examples.big_image_noisy_neighbor',
        request=request,
        args=['--prefix', prefix, '--async-lib', async_lib],
        pv_to_check=f'{prefix}t1'
    )
    from caproto.threading.pyepics_compat import Context, get_pv
    with Context() as cntx:
        image = get_pv(pvname=f'{prefix}image', context=cntx)
        t1 = get_pv(pvname=f'{prefix}t1', context=cntx)
        t1.add_callback(lambda value, **kwargs: None)

        for _ in range(4):
            image.get(timeout=45)

        image.disconnect()
        t1.disconnect()


@conftest.parametrize_iocs(
    "caproto.ioc_examples.records"
)
def test_long_strings(request, ioc_name):
    info = conftest.run_example_ioc_by_name(ioc_name, request=request)
    prefix = info.prefix
    stringin = f'{prefix}E'
    regular = sync.read(f'{stringin}.VAL', data_type='native')
    assert regular.data_type == ca.ChannelType.STRING
    data, = regular.data
    length = len(data)
    assert length > 1  # based on the default value in the test

    for dtype in ('native', 'control', 'time', 'graphic'):
        longstr = sync.read(f'{stringin}.VAL$', data_type=dtype)
        longstr_data = b''.join(longstr.data)
        expected_dtype = ca._dbr.field_types[dtype][ca.ChannelType.CHAR]
        assert longstr.data_type == expected_dtype
        assert len(longstr.data) == length
        assert longstr_data == data

    with pytest.raises(TimeoutError):
        # an analog input .VAL has no long string option
        sync.read(f'{prefix}A.VAL$', data_type='native')
