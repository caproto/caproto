import time

import caproto as ca


def test_timestamp_now():
    # There's more built into this than it seems:
    # 1. time.time() -> EPICS timestamp
    # 2. EPICS timestamp -> POSIX timestamp
    # 3. And a relaxed check that we're within 1 second of `time.time()`
    #    on the way out
    now = ca.TimeStamp.now()
    assert abs(time.time() - now.timestamp) < 1.


def test_timestamp_basic():
    intval = ca.ChannelInteger(value=5)
    # Try the datetime interface:
    from_dt = intval.epics_timestamp.as_datetime().timestamp()
    assert abs(from_dt - intval.timestamp) < 1.


def test_timestamp_raw_access():
    intval = ca.ChannelInteger(value=5)
    # Try the datetime interface:
    intval.epics_timestamp.secondsSinceEpoch
    intval.epics_timestamp.nanoSeconds


def test_timestamp_flexible():
    t0 = time.time()
    ts = ca.TimeStamp.from_flexible_value(t0)
    assert abs(ts.timestamp - t0) < 1e-3


def test_timestamp_flexible_epics_tuple():
    ts = ca.TimeStamp.from_flexible_value((1, 2))
    assert ts.secondsSinceEpoch == 1
    assert ts.nanoSeconds == 2


def test_timestamp_flexible_epics_copy():
    ts = ca.TimeStamp.from_flexible_value(ca.TimeStamp(2, 3))
    assert ts.secondsSinceEpoch == 2
    assert ts.nanoSeconds == 3
