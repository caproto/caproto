#!/usr/bin/env python
"""
Based on code provided by @tkurita in issue 797:
https://github.com/caproto/caproto/issues/797
"""

from .. import config_caproto_logging
from ..server import PVGroup
from ..server import PvpropertyDouble as Double
from ..server import PvpropertyInteger as Integer
from ..server import PvpropertyIntegerRO as IntegerRO
from ..server import SubGroup, ioc_arg_parser, pvproperty, run

PTN_LENGTH = 65536
MON_LENGTH = 40960


class BPMFBGroup(PVGroup):
    @SubGroup(prefix="MIRROR:")
    class MIRROR(PVGroup):
        BPM_P_GAIN_DP_CNST = pvproperty(
            value=0, dtype=IntegerRO
        )
        BPM_P_SHIFT_DP = pvproperty(
            value=0, dtype=IntegerRO
        )
        BPM_P_GAIN_DR_CNST = pvproperty(
            value=0, dtype=IntegerRO
        )
        BPM_P_SHIFT_DR = pvproperty(
            value=0, dtype=IntegerRO
        )
        BPM_I_GAIN_DR_CNST = pvproperty(
            value=0, dtype=IntegerRO
        )
        BPM_I_SHIFT_DR = pvproperty(
            value=0, dtype=IntegerRO
        )
        BPM_PERIOD_IACC_DR_SET = pvproperty(
            value=0, dtype=IntegerRO
        )
        BPM_GAIN_2FS_CNST = pvproperty(
            value=0, dtype=IntegerRO
        )
        BPM_GN_SHIFT_2FS = pvproperty(
            value=0, dtype=IntegerRO
        )

    @SubGroup(prefix="RB:")
    class RB(PVGroup):

        BPM_P_GAIN_DP_FLOAT = pvproperty(value=0, dtype=Double)
        BPM_P_GAIN_DR_FLOAT = pvproperty(value=0, dtype=Double)
        BPM_I_GAIN_DR_FLOAT = pvproperty(value=0, dtype=Double)
        BPM_GAIN_2FS_FLOAT = pvproperty(value=0, dtype=Double)

    @SubGroup(prefix="SET:")
    class SET(PVGroup):
        BPM_P_GAIN_DP_FLOAT = pvproperty(value=0, dtype=Double)
        BPM_P_GAIN_DR_FLOAT = pvproperty(value=0, dtype=Double)
        BPM_I_GAIN_DR_FLOAT = pvproperty(value=0, dtype=Double)
        BPM_GAIN_2FS_FLOAT = pvproperty(value=0, dtype=Double)
        BPM_P_GAIN_DP_FLOAT_CHANGE = pvproperty(
            value=0, dtype=Double
        )
        BPM_P_GAIN_DR_FLOAT_CHANGE = pvproperty(
            value=0, dtype=Double
        )
        BPM_I_GAIN_DR_FLOAT_CHANGE = pvproperty(
            value=0, dtype=Double
        )
        BPM_GAIN_2FS_FLOAT_CHANGE = pvproperty(
            value=0, dtype=Double
        )


class DelRPatternGroup(PVGroup):
    GEN_REFERENCE = pvproperty(value=0, dtype=Integer)
    FB = pvproperty(value=0, dtype=Double)
    EXT = pvproperty(value=20, dtype=Double)
    TIMMING_RISE = pvproperty(value=400.0, dtype=Double)
    REFERENCE_PTN = pvproperty(value=[0] * PTN_LENGTH, dtype=Integer)  # short
    REFERENCE_PTN_A = pvproperty(
        value=[0.0] * MON_LENGTH, dtype=Double
    )
    WAVE_SPAN = pvproperty(value=2000.0, dtype=Double)
    WAVE_DELAY = pvproperty(value=0.0, dtype=Double)
    XAXIS_MON = pvproperty(
        value=[float(v) for v in range(0, MON_LENGTH)], dtype=Double
    )


class CAVFBGroup(PVGroup):
    @SubGroup(prefix="MIRROR:")
    class MIRROR(PVGroup):
        CAV_P_GAIN_HN1_CNST = pvproperty(
            value=0, dtype=IntegerRO
        )
        CAV_P_GAIN_HN2_CNST = pvproperty(
            value=0, dtype=IntegerRO
        )
        CAV_P_SHIFT = pvproperty(value=0, dtype=IntegerRO)
        CAV_I_GAIN_HN1_CNST = pvproperty(
            value=0, dtype=IntegerRO
        )
        CAV_I_GAIN_HN2_CNST = pvproperty(
            value=0, dtype=IntegerRO
        )
        CAV_I_SHIFT = pvproperty(value=0, dtype=IntegerRO)
        CAV_PERIOD_IACC_SET = pvproperty(
            value=0, dtype=IntegerRO
        )

    @SubGroup(prefix="RB:")
    class RB(PVGroup):
        CAV_P_GAIN_HN1_FLOAT = pvproperty(value=0, dtype=Double)
        CAV_I_GAIN_HN1_FLOAT = pvproperty(value=0, dtype=Double)
        CAV_P_GAIN_HN2_FLOAT = pvproperty(value=0, dtype=Double)
        CAV_I_GAIN_HN2_FLOAT = pvproperty(value=0, dtype=Double)

    @SubGroup(prefix="SET:")
    class SET(PVGroup):
        CAV_P_GAIN_HN1_FLOAT = pvproperty(value=0, dtype=Double)
        CAV_I_GAIN_HN1_FLOAT = pvproperty(value=0, dtype=Double)
        CAV_P_GAIN_HN2_FLOAT = pvproperty(value=0, dtype=Double)
        CAV_I_GAIN_HN2_FLOAT = pvproperty(value=0, dtype=Double)


class SupportIOC(PVGroup):
    CAVFBGroup = SubGroup(CAVFBGroup, prefix="CAVFB:")
    BPMFBGroup = SubGroup(BPMFBGroup, prefix="BPMFB:")
    DelRPatternGroup = SubGroup(DelRPatternGroup, prefix="DR_PTN:")


if __name__ == "__main__":
    config_caproto_logging(level="INFO")
    ioc_options, run_options = ioc_arg_parser(
        default_prefix="SUPPORT:",
        desc="Run an IOC to reproduce issue 797 for the test suite.",
        # supported_async_libs=("asyncio",),
    )
    ioc = SupportIOC(**ioc_options)
    run_options["log_pv_names"] = True
    run(ioc.pvdb, **run_options)
