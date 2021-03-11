from ..._data import AlarmSeverity, ChannelType
from .. import menus
from ..server import PVGroup, pvproperty
from .utils import link_parent_attribute


class _Limits(PVGroup):
    high_alarm_limit = pvproperty(
        name="HIGH", dtype=ChannelType.DOUBLE, doc="High Alarm Limit"
    )
    high_severity = pvproperty(
        name="HSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="High Severity",
        value=menus.menuAlarmSevr.get_string_tuple()[AlarmSeverity.MINOR_ALARM],
    )
    hihi_alarm_limit = pvproperty(
        name="HIHI", dtype=ChannelType.DOUBLE, doc="Hihi Alarm Limit"
    )
    hihi_severity = pvproperty(
        name="HHSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Hihi Severity",
        value=menus.menuAlarmSevr.get_string_tuple()[AlarmSeverity.MAJOR_ALARM],
    )
    lolo_alarm_limit = pvproperty(
        name="LOLO", dtype=ChannelType.DOUBLE, doc="Lolo Alarm Limit"
    )
    lolo_severity = pvproperty(
        name="LLSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Lolo Severity",
        value=menus.menuAlarmSevr.get_string_tuple()[AlarmSeverity.MAJOR_ALARM],
    )
    low_alarm_limit = pvproperty(
        name="LOW", dtype=ChannelType.DOUBLE, doc="Low Alarm Limit"
    )
    low_severity = pvproperty(
        name="LSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Low Severity",
        value=menus.menuAlarmSevr.get_string_tuple()[AlarmSeverity.MINOR_ALARM],
    )
    high_operating_range = pvproperty(
        name="HOPR", dtype=ChannelType.DOUBLE, doc="High Operating Range"
    )
    low_operating_range = pvproperty(
        name="LOPR", dtype=ChannelType.DOUBLE, doc="Low Operating Range"
    )

    link_parent_attribute(hihi_alarm_limit, "upper_alarm_limit")
    link_parent_attribute(lolo_alarm_limit, "lower_alarm_limit")

    link_parent_attribute(high_alarm_limit, "upper_warning_limit")
    link_parent_attribute(low_alarm_limit, "lower_warning_limit")

    link_parent_attribute(high_operating_range, "upper_ctrl_limit")
    link_parent_attribute(low_operating_range, "lower_ctrl_limit")


class _LimitsLong(PVGroup):
    high_alarm_limit = pvproperty(
        name="HIGH", dtype=ChannelType.LONG, doc="High Alarm Limit"
    )
    high_severity = pvproperty(
        name="HSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="High Severity",
        value=menus.menuAlarmSevr.get_string_tuple()[AlarmSeverity.MINOR_ALARM],
    )
    hihi_alarm_limit = pvproperty(
        name="HIHI", dtype=ChannelType.LONG, doc="Hihi Alarm Limit"
    )
    hihi_severity = pvproperty(
        name="HHSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Hihi Severity",
        value=menus.menuAlarmSevr.get_string_tuple()[AlarmSeverity.MAJOR_ALARM],
    )
    lolo_alarm_limit = pvproperty(
        name="LOLO", dtype=ChannelType.LONG, doc="Lolo Alarm Limit"
    )
    lolo_severity = pvproperty(
        name="LLSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Lolo Severity",
        value=menus.menuAlarmSevr.get_string_tuple()[AlarmSeverity.MAJOR_ALARM],
    )
    low_alarm_limit = pvproperty(
        name="LOW", dtype=ChannelType.LONG, doc="Low Alarm Limit"
    )
    low_severity = pvproperty(
        name="LSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Low Severity",
        value=menus.menuAlarmSevr.get_string_tuple()[AlarmSeverity.MINOR_ALARM],
    )
    high_operating_range = pvproperty(
        name="HOPR", dtype=ChannelType.LONG, doc="High Operating Range"
    )
    low_operating_range = pvproperty(
        name="LOPR", dtype=ChannelType.LONG, doc="Low Operating Range"
    )

    link_parent_attribute(hihi_alarm_limit, "upper_alarm_limit")
    link_parent_attribute(lolo_alarm_limit, "lower_alarm_limit")

    link_parent_attribute(high_alarm_limit, "upper_warning_limit")
    link_parent_attribute(low_alarm_limit, "lower_warning_limit")

    link_parent_attribute(high_operating_range, "upper_ctrl_limit")
    link_parent_attribute(low_operating_range, "lower_ctrl_limit")


__all__ = ["_Limits", "_LimitsLong"]
