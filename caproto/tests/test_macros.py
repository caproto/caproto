from caproto.server import PVGroup, pvproperty


def test_no_double_braces():
    class ParentGroup(PVGroup):
        placeholder1 = pvproperty(value=0, name="{beamline}:{det}.VAL")
        placeholder2 = pvproperty(value=0, name="{beamline}:{det}.RBV")

    class ChildGroup(ParentGroup):
        placeholder3 = pvproperty(value=0, name="{det}:{beamline}.VAL")
        placeholder4 = pvproperty(value=0, name="{det}:{beamline}.RBV")

    child_group = ChildGroup(
        prefix="{prefix}:",
        macros={"prefix": "PREFIX", "beamline": "BEAMLINE", "det": "DET"},
    )

    assert "PREFIX:BEAMLINE:DET.VAL" in child_group.pvdb
    assert "PREFIX:BEAMLINE:DET.RBV" in child_group.pvdb
    assert "PREFIX:DET:BEAMLINE.VAL" in child_group.pvdb
    assert "PREFIX:DET:BEAMLINE.RBV" in child_group.pvdb


def test_double_braces():
    class ParentGroup(PVGroup):
        placeholder1 = pvproperty(
            value=0, name="{{beamline}}:{beamline}:{{det}}:{det}.VAL"
        )
        placeholder2 = pvproperty(
            value=0, name="{{beamline}}:{beamline}:{{det}}:{det}.RBV"
        )

    class ChildGroup(ParentGroup):
        placeholder3 = pvproperty(
            value=0, name="{{beamline}}:{beamline}:{det}:{{det}}.VAL"
        )
        placeholder4 = pvproperty(
            value=0, name="{{beamline}}:{beamline}:{det}:{{det}}.RBV"
        )

    child_group = ChildGroup(
        prefix="{{prefix}}:{prefix}:",
        macros={"prefix": "PREFIX", "beamline": "BEAMLINE", "det": "DET"},
    )

    assert "{prefix}:PREFIX:{beamline}:BEAMLINE:{det}:DET.VAL" in child_group.pvdb
    assert "{prefix}:PREFIX:{beamline}:BEAMLINE:{det}:DET.RBV" in child_group.pvdb
    assert "{prefix}:PREFIX:{beamline}:BEAMLINE:DET:{det}.VAL" in child_group.pvdb
    assert "{prefix}:PREFIX:{beamline}:BEAMLINE:DET:{det}.RBV" in child_group.pvdb
