import pytest

import caproto.docs.utils
import caproto.ioc_examples.chirp
import caproto.ioc_examples.custom_write
import caproto.ioc_examples.decay
import caproto.ioc_examples.macros
import caproto.ioc_examples.mini_beamline
import caproto.ioc_examples.pathological.reading_counter
import caproto.ioc_examples.random_walk
import caproto.ioc_examples.rpc_function
import caproto.ioc_examples.scalars_and_arrays
import caproto.ioc_examples.scan_rate
import caproto.ioc_examples.setpoint_rbv_pair
import caproto.ioc_examples.simple
import caproto.ioc_examples.startup_and_shutdown_hooks
import caproto.ioc_examples.subgroups
import caproto.ioc_examples.thermo_sim
import caproto.ioc_examples.too_clever.trigger_with_pc
import caproto.ioc_examples.worker_thread
import caproto.ioc_examples.worker_thread_pc

from . import ioc_all_in_one, ioc_inline_style


@pytest.fixture(
    params=[
        ioc_all_in_one.MyPVGroup,
        caproto.ioc_examples.chirp.Chirp,
        caproto.ioc_examples.decay.Decay,
        caproto.ioc_examples.thermo_sim.Thermo,
        caproto.ioc_examples.custom_write.CustomWrite,
        ioc_inline_style.InlineStyleIOC,
        caproto.ioc_examples.macros.MacroifiedNames,
        caproto.ioc_examples.mini_beamline.MiniBeamline,
        caproto.ioc_examples.random_walk.RandomWalkIOC,
        caproto.ioc_examples.pathological.reading_counter.ReadingCounter,
        caproto.ioc_examples.rpc_function.MyPVGroup,
        caproto.ioc_examples.scalars_and_arrays.ArrayIOC,
        caproto.ioc_examples.scan_rate.ScanRateIOC,
        caproto.ioc_examples.setpoint_rbv_pair.Group,
        caproto.ioc_examples.simple.SimpleIOC,
        caproto.ioc_examples.startup_and_shutdown_hooks.StartupAndShutdown,
        caproto.ioc_examples.subgroups.MyPVGroup,
        caproto.ioc_examples.too_clever.trigger_with_pc.TriggeredIOC,
        caproto.ioc_examples.worker_thread.WorkerThreadIOC,
        caproto.ioc_examples.worker_thread_pc.WorkerThreadIOC,
    ]
)
def pvgroup_cls(request):
    return request.param


def test_get_info_smoke(pvgroup_cls):
    info = caproto.docs.utils.get_pvgroup_info(pvgroup_cls.__module__, pvgroup_cls.__name__)
    assert info is not None
    assert info['pvproperty'] or info['subgroup']


def test_record_info_smoke():
    for record in caproto.docs.utils.get_all_records():
        print(record)
