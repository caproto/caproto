from __future__ import annotations

import time

import pytest

from caproto.threading.client import (PV, Context, SharedBroadcaster,
                                      Subscription)

from .conftest import run_example_ioc

issue_797_pv_suffixes = """
DR_PTN:XAXIS_MON
DR_PTN:REFERENCE_PTN_A
DR_PTN:EXT
DR_PTN:GEN_REFERENCE
BPMFB:RB:BPM_P_GAIN_DP_FLOAT
BPMFB:SET:BPM_I_GAIN_DR_FLOAT_CHANGE
DR_PTN:TIMMING_RISE
BPMFB:SET:BPM_P_GAIN_DR_FLOAT
BPMFB:SET:BPM_GAIN_2FS_FLOAT_CHANGE
DR_PTN:FB
DR_PTN:WAVE_SPAN
DR_PTN:WAVE_DELAY
BPMFB:SET:BPM_P_GAIN_DR_FLOAT_CHANGE
BPMFB:RB:BPM_I_GAIN_DR_FLOAT
BPMFB:RB:BPM_GAIN_2FS_FLOAT
BPMFB:SET:BPM_P_GAIN_DP_FLOAT
BPMFB:SET:BPM_P_GAIN_DP_FLOAT_CHANGE
BPMFB:SET:BPM_I_GAIN_DR_FLOAT
BPMFB:SET:BPM_GAIN_2FS_FLOAT
BPMFB:RB:BPM_P_GAIN_DR_FLOAT
""".split()


@pytest.fixture
def issue_797_pvnames(prefix: str) -> list[str]:
    return ["".join((prefix, suffix)) for suffix in issue_797_pv_suffixes]


@pytest.mark.parametrize("async_lib", ["asyncio", "curio", "trio"])
def test_issue_797(
    request: pytest.FixtureRequest,
    prefix: str,
    async_lib: str,
    issue_797_pvnames: list[str],
):
    run_example_ioc(
        "caproto.tests.issue_797_server",
        request=request,
        args=["--prefix", prefix, "--async-lib", async_lib],
        pv_to_check=issue_797_pvnames[-1],
    )

    shared_broadcaster = SharedBroadcaster()
    ctx = Context(broadcaster=shared_broadcaster)
    saw_subs = {}

    def user_callback(sub: Subscription, command):
        nonlocal last_callback

        print(f"{sub.pv}: {command}")
        saw_subs.setdefault(sub.pv, 0)
        saw_subs[sub.pv] += 1
        last_callback = time.monotonic()

    pvs: list[PV] = ctx.get_pvs(*issue_797_pvnames)
    for pv in pvs:
        pv.wait_for_connection()

    for pv in pvs:
        reading = pv.read()
        print(f'{pv} read back: {reading}')

    last_callback = time.monotonic()
    for pv in pvs:
        print(f"Subscribing to {pv}")
        sub = pv.subscribe(data_type="time")
        sub.add_callback(user_callback)

    pv = pvs[0]
    assert pv.circuit_manager is not None

    # Mimic what we saw in the log:
    pv.circuit_manager.events_off()
    pv.circuit_manager.events_on()
    pv.circuit_manager.events_off()
    pv.circuit_manager.events_on()

    def get_secs_since_last_sub() -> float:
        return time.monotonic() - last_callback

    # Wait until a second after subscriptions come in
    while get_secs_since_last_sub() < 1.0:
        print(
            "Waiting for subs. Last sub was this many seconds ago: ",
            get_secs_since_last_sub(),
            "So far, saw this many PVs:", len(saw_subs)
        )
        time.sleep(0.1)

    ctx.disconnect()

    print("Done.\n\n")
    print(f"Total PVs: {len(pvs)}")
    print("Saw this many subscription callbacks:")

    for pv, count in saw_subs.items():
        print(pv.name, count)

    print("Total PVs that had at least one subscription: ", len(saw_subs))
    print("Total subscriptions: ", sum(count for count in saw_subs.values()))
    assert len(saw_subs) == len(issue_797_pvnames)
