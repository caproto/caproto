import copy

import pytest

from .. import (ChannelByte, ChannelChar, ChannelData, ChannelDouble,
                ChannelEnum, ChannelFloat, ChannelInteger, ChannelShort,
                ChannelString)
from ..server.server import (PVGroup, PvpropertyBoolEnum, PvpropertyBoolEnumRO,
                             PvpropertyByte, PvpropertyByteRO, PvpropertyChar,
                             PvpropertyCharRO, PvpropertyDouble,
                             PvpropertyDoubleRO, PvpropertyEnum,
                             PvpropertyEnumRO, PvpropertyFloat,
                             PvpropertyFloatRO, PvpropertyInteger,
                             PvpropertyIntegerRO, PvpropertyShort,
                             PvpropertyShortRO, PvpropertyString,
                             PvpropertyStringRO, PVSpec)


async def _fake_putter(data, value):
    ...


pvspec = PVSpec(put=_fake_putter)
group = PVGroup(prefix="abc")


sample_data = [
    pytest.param(
        ChannelInteger(value=5),
        id="ChannelInteger",
    ),
    pytest.param(
        ChannelByte(value=5),
        id="ChannelByte",
    ),
    pytest.param(
        ChannelChar(value=5),
        id="ChannelChar",
    ),
    pytest.param(
        ChannelDouble(value=5.0),
        id="ChannelDouble",
    ),
    pytest.param(
        ChannelEnum(value=0, enum_strings=["a", "b", "c"]),
        id="ChannelEnum",
    ),
    pytest.param(
        ChannelFloat(value=5.0),
        id="ChannelFloat",
    ),
    pytest.param(
        ChannelShort(value=2),
        id="ChannelShort",
    ),
    pytest.param(
        ChannelString(value="string", long_string_max_length=82),
        id="ChannelString",
    ),
    pytest.param(
        ChannelInteger(value=5),
        id="ChannelInteger",
    ),
    pytest.param(
        ChannelByte(value=5),
        id="ChannelByte",
    ),
    pytest.param(
        ChannelChar(value=5),
        id="ChannelChar",
    ),
    pytest.param(
        ChannelDouble(value=5.0),
        id="ChannelDouble",
    ),
    pytest.param(
        ChannelEnum(value=0, enum_strings=["a", "b", "c"]),
        id="ChannelEnum",
    ),
    pytest.param(
        ChannelFloat(value=5.0),
        id="ChannelFloat",
    ),
    pytest.param(
        ChannelShort(value=2),
        id="ChannelShort",
    ),
    pytest.param(
        ChannelString(value="string", long_string_max_length=82),
        id="ChannelString",
    ),
    pytest.param(
        PvpropertyChar(value=5, group=group, pvspec=pvspec, pvname="pvname"),
        id="PvpropertyChar",
    ),
    pytest.param(
        PvpropertyByte(value=5, group=group, pvspec=pvspec, pvname="pvname"),
        id="PvpropertyByte",
    ),
    pytest.param(
        PvpropertyShort(value=5, group=group, pvspec=pvspec, pvname="pvname"),
        id="PvpropertyShort",
    ),
    pytest.param(
        PvpropertyInteger(value=5, group=group, pvspec=pvspec, pvname="pvname"),
        id="PvpropertyInteger",
    ),
    pytest.param(
        PvpropertyFloat(value=5, group=group, pvspec=pvspec, pvname="pvname"),
        id="PvpropertyFloat",
    ),
    pytest.param(
        PvpropertyDouble(value=5, group=group, pvspec=pvspec, pvname="pvname"),
        id="PvpropertyDouble",
    ),
    pytest.param(
        PvpropertyString(value=5, group=group, pvspec=pvspec, pvname="pvname"),
        id="PvpropertyString",
    ),
    pytest.param(
        PvpropertyEnum(value=5, group=group, pvspec=pvspec, pvname="pvname"),
        id="PvpropertyEnum",
    ),
    pytest.param(
        PvpropertyBoolEnum(value=5, group=group, pvspec=pvspec, pvname="pvname"),
        id="PvpropertyBoolEnum",
    ),
    pytest.param(
        PvpropertyCharRO(value=5, group=group, pvspec=pvspec, pvname="pvname"),
        id="PvpropertyCharRO",
    ),
    pytest.param(
        PvpropertyByteRO(value=5, group=group, pvspec=pvspec, pvname="pvname"),
        id="PvpropertyByteRO",
    ),
    pytest.param(
        PvpropertyShortRO(value=5, group=group, pvspec=pvspec, pvname="pvname"),
        id="PvpropertyShortRO",
    ),
    pytest.param(
        PvpropertyIntegerRO(value=5, group=group, pvspec=pvspec, pvname="pvname"),
        id="PvpropertyIntegerRO",
    ),
    pytest.param(
        PvpropertyFloatRO(value=5, group=group, pvspec=pvspec, pvname="pvname"),
        id="PvpropertyFloatRO",
    ),
    pytest.param(
        PvpropertyDoubleRO(value=5, group=group, pvspec=pvspec, pvname="pvname"),
        id="PvpropertyDoubleRO",
    ),
    pytest.param(
        PvpropertyStringRO(value=5, group=group, pvspec=pvspec, pvname="pvname"),
        id="PvpropertyStringRO",
    ),
    pytest.param(
        PvpropertyEnumRO(value=5, group=group, pvspec=pvspec, pvname="pvname"),
        id="PvpropertyEnumRO",
    ),
    pytest.param(
        PvpropertyBoolEnumRO(value=5, group=group, pvspec=pvspec, pvname="pvname"),
        id="PvpropertyBoolEnumRO",
    ),
]


def compare_data(data: ChannelData, copied: ChannelData):
    for key in data._data:
        assert copied._data[key] == data._data[key]
    assert copied.value == data.value
    assert copied.timestamp == data.timestamp
    assert copied._data["timestamp"] is not data._data["timestamp"]

    if hasattr(data, "pvname"):
        assert copied.pvname == data.pvname
        assert copied.pvspec == data.pvspec
        assert copied.group is None

    _, kwargs = data.__getnewargs_ex__()
    attr_map = {
        "timestamp": "epics_timestamp",
        "record": "record_type",
    }
    for attr, expected in kwargs.items():
        copied_attr_value = getattr(copied, attr_map.get(attr, attr))

        assert copied_attr_value == expected


@pytest.mark.parametrize("data", sample_data)
def test_copy(data: ChannelData):
    copied = copy.deepcopy(data)
    compare_data(data, copied)


@pytest.mark.parametrize("data", sample_data)
def test_getnewargs(data: ChannelData):
    args, kwargs = data.__getnewargs_ex__()
    copied = type(data)(*args, **kwargs)
    compare_data(data, copied)
