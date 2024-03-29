'''
Contains PVGroups representing all fields of EPICS base records.

This file contains implementation functionality on top of the record instances
found in :mod:`caproto.server.records.base` - a module auto-generated from
a reference EPICS DBD file.

Any customizations required for fields should be done in this file.
'''
import logging
from typing import ClassVar

from ..._data import ChannelData
from ..server import PvpropertyStringRO, pvproperty
from . import base
from .utils import link_enum_strings, link_parent_attribute, register_record

logger = logging.getLogger(__name__)


class RecordFieldGroup(base.RecordFieldGroup):
    _base = base.RecordFieldGroup
    _record_type: ClassVar[str]
    parent: ChannelData

    # Add some handling onto the autogenerated code above:
    record_type = pvproperty(
        name='RTYP',
        dtype=PvpropertyStringRO,
        read_only=True,
        doc='Record type'
    )

    def __init__(self, prefix, **kw):
        super().__init__(prefix, **kw)

        parent = self.parent
        # set .NAME
        self.record_name._data['value'] = parent.pvname
        # set .RTYP
        self.record_type._data['value'] = self._record_type

        # automatic alarm handling
        self._alarm = parent.alarm
        self._alarm.connect(self)

    async def publish(self, flags):
        # if SubscriptionType.DBE_ALARM in flags:
        # TODO this needs tweaking - proof of concept at the moment
        await self.alarm_acknowledge_transient.write(
            self._alarm.must_acknowledge_transient)
        await self.alarm_acknowledge_severity.write(
            self._alarm.severity_to_acknowledge)
        await self.alarm_status.write(self._alarm.status)
        await self.current_alarm_severity.write(self._alarm.severity)

    @_base.scan_rate.putter
    async def scan_rate(self, instance, value):
        scan_string = (self.scan_rate.enum_strings[value] if isinstance(
            value, int) else value)

        if scan_string in ('I/O Intr', 'Passive', 'Event'):
            self._scan_rate_sec = 0
        else:
            self._scan_rate_sec = float(scan_string.split(' ')[0])

        if hasattr(self.parent, 'scan_rate'):
            self.parent.scan_rate = self._scan_rate_sec

    @property
    def scan_rate_sec(self):
        'Record scan rate, in seconds (read-only)'
        return self._scan_rate_sec

    @_base.process_record.putter
    async def process_record(self, instance, value):
        await self.parent.write(self.parent.value)

    link_parent_attribute(_base.description, '__doc__', use_setattr=True)

    async def value_write_hook(self, instance, value):
        """An overridable hook for the parent value having been updated."""
        ...


@register_record
class AiFields(base.AiFields, RecordFieldGroup):
    _base = base.AiFields
    link_parent_attribute(
        _base.display_precision,
        'precision',
    )
    link_parent_attribute(_base.archive_deadband, 'log_atol', use_setattr=True)
    link_parent_attribute(_base.monitor_deadband, 'value_atol', use_setattr=True)


@register_record
class AsubFields(base.AsubFields, RecordFieldGroup):
    _base = base.AsubFields
    link_parent_attribute(
        _base.display_precision, "precision",
    )


@register_record
class AaiFields(base.AaiFields, RecordFieldGroup):
    _base = base.AaiFields
    link_parent_attribute(
        _base.display_precision, "precision",
    )
    link_parent_attribute(
        _base.high_operating_range, "upper_ctrl_limit",
    )
    link_parent_attribute(
        _base.low_operating_range, "lower_ctrl_limit",
    )
    link_parent_attribute(
        _base.number_of_elements, "max_length", use_setattr=True, read_only=True
    )


@register_record
class AaoFields(base.AaoFields, RecordFieldGroup):
    _base = base.AaoFields
    link_parent_attribute(
        _base.display_precision, "precision",
    )
    link_parent_attribute(
        _base.high_operating_range, "upper_ctrl_limit",
    )
    link_parent_attribute(
        _base.low_operating_range, "lower_ctrl_limit",
    )
    link_parent_attribute(
        _base.number_of_elements, "max_length", use_setattr=True, read_only=True
    )


@register_record
class AoFields(base.AoFields, RecordFieldGroup):
    _base = base.AoFields
    link_parent_attribute(
        _base.display_precision, "precision",
    )
    link_parent_attribute(_base.archive_deadband, "log_atol", use_setattr=True)
    link_parent_attribute(_base.monitor_deadband, "value_atol", use_setattr=True)


@register_record
class AsynFields(base.AsynFields, RecordFieldGroup):
    _base = base.AsynFields


@register_record
class BiFields(base.BiFields, RecordFieldGroup):
    _base = base.BiFields
    link_enum_strings(_base.zero_name, index=0)
    link_enum_strings(_base.one_name, index=1)

    @_base.raw_value.putter
    async def raw_value(self, instance, value):
        await self.parent.write(
            value=value
        )

    async def value_write_hook(self, instance, value):
        raw_value = self.parent.get_raw_value(value)
        if raw_value is not None:
            await self.raw_value.write(raw_value, verify_value=False)


@register_record
class BoFields(base.BoFields, RecordFieldGroup):
    _base = base.BoFields
    link_enum_strings(_base.zero_name, index=0)
    link_enum_strings(_base.one_name, index=1)

    @_base.raw_value.putter
    async def raw_value(self, instance, value):
        await self.parent.write(
            value=value
        )

    async def value_write_hook(self, instance, value):
        raw_value = self.parent.get_raw_value(value)
        if raw_value is not None:
            await self.raw_value.write(raw_value, verify_value=False)


@register_record
class CalcFields(base.CalcFields, RecordFieldGroup):
    _base = base.CalcFields
    link_parent_attribute(
        _base.display_precision, "precision",
    )
    link_parent_attribute(_base.archive_deadband, "log_atol", use_setattr=True)
    link_parent_attribute(_base.monitor_deadband, "value_atol", use_setattr=True)


@register_record
class CalcoutFields(base.CalcoutFields, RecordFieldGroup):
    _base = base.CalcoutFields
    link_parent_attribute(
        _base.display_precision, "precision",
    )
    link_parent_attribute(_base.archive_deadband, "log_atol", use_setattr=True)
    link_parent_attribute(_base.monitor_deadband, "value_atol", use_setattr=True)


@register_record
class CompressFields(base.CompressFields, RecordFieldGroup):
    _base = base.CompressFields
    link_parent_attribute(
        _base.high_operating_range, "upper_ctrl_limit",
    )
    link_parent_attribute(
        _base.low_operating_range, "lower_ctrl_limit",
    )
    link_parent_attribute(
        _base.display_precision, "precision",
    )


@register_record
class DfanoutFields(base.DfanoutFields, RecordFieldGroup):
    _base = base.DfanoutFields
    link_parent_attribute(
        _base.display_precision, "precision",
    )
    link_parent_attribute(_base.archive_deadband, "log_atol", use_setattr=True)
    link_parent_attribute(_base.monitor_deadband, "value_atol", use_setattr=True)


@register_record
class EventFields(base.EventFields, RecordFieldGroup):
    _base = base.EventFields


@register_record
class FanoutFields(base.FanoutFields, RecordFieldGroup):
    _base = base.FanoutFields


@register_record
class HistogramFields(base.HistogramFields, RecordFieldGroup):
    _base = base.HistogramFields
    link_parent_attribute(
        _base.display_precision, "precision",
    )
    link_parent_attribute(
        _base.high_operating_range, "upper_ctrl_limit",
    )
    link_parent_attribute(
        _base.low_operating_range, "lower_ctrl_limit",
    )


@register_record
class Int64inFields(base.Int64inFields, RecordFieldGroup):
    _base = base.Int64inFields
    link_parent_attribute(_base.archive_deadband, "log_atol", use_setattr=True)
    link_parent_attribute(_base.monitor_deadband, "value_atol", use_setattr=True)


@register_record
class Int64outFields(base.Int64outFields, RecordFieldGroup):
    _base = base.Int64outFields
    link_parent_attribute(_base.archive_deadband, "log_atol", use_setattr=True)
    link_parent_attribute(_base.monitor_deadband, "value_atol", use_setattr=True)


@register_record
class LonginFields(base.LonginFields, RecordFieldGroup):
    _base = base.LonginFields
    link_parent_attribute(_base.archive_deadband, "log_atol", use_setattr=True)
    link_parent_attribute(_base.monitor_deadband, "value_atol", use_setattr=True)


@register_record
class LongoutFields(base.LongoutFields, RecordFieldGroup):
    _base = base.LongoutFields
    link_parent_attribute(_base.archive_deadband, "log_atol", use_setattr=True)
    link_parent_attribute(_base.monitor_deadband, "value_atol", use_setattr=True)


@register_record
class LsiFields(base.LsiFields, RecordFieldGroup):
    _base = base.LsiFields


@register_record
class LsoFields(base.LsoFields, RecordFieldGroup):
    _base = base.LsoFields


@register_record
class MbbiFields(base.MbbiFields, RecordFieldGroup):
    _base = base.MbbiFields
    link_enum_strings(_base.zero_string, index=0)
    link_enum_strings(_base.one_string, index=1)
    link_enum_strings(_base.two_string, index=2)
    link_enum_strings(_base.three_string, index=3)
    link_enum_strings(_base.four_string, index=4)
    link_enum_strings(_base.five_string, index=5)
    link_enum_strings(_base.six_string, index=6)
    link_enum_strings(_base.seven_string, index=7)
    link_enum_strings(_base.eight_string, index=8)
    link_enum_strings(_base.nine_string, index=9)
    link_enum_strings(_base.ten_string, index=10)
    link_enum_strings(_base.eleven_string, index=11)
    link_enum_strings(_base.twelve_string, index=12)
    link_enum_strings(_base.thirteen_string, index=13)
    link_enum_strings(_base.fourteen_string, index=14)
    link_enum_strings(_base.fifteen_string, index=15)

    @_base.raw_value.putter
    async def raw_value(self, instance, value):
        await self.parent.write(
            value=value
        )

    async def value_write_hook(self, instance, value):
        raw_value = self.parent.get_raw_value(value)
        if raw_value is not None:
            await self.raw_value.write(raw_value, verify_value=False)


@register_record
class MbbidirectFields(base.MbbidirectFields, RecordFieldGroup):
    _base = base.MbbidirectFields


@register_record
class MbboFields(base.MbboFields, RecordFieldGroup):
    _base = base.MbboFields
    link_enum_strings(_base.one_string, index=1)
    link_enum_strings(_base.two_string, index=2)
    link_enum_strings(_base.three_string, index=3)
    link_enum_strings(_base.four_string, index=4)
    link_enum_strings(_base.five_string, index=5)
    link_enum_strings(_base.six_string, index=6)
    link_enum_strings(_base.seven_string, index=7)
    link_enum_strings(_base.eight_string, index=8)
    link_enum_strings(_base.nine_string, index=9)
    link_enum_strings(_base.ten_string, index=10)
    link_enum_strings(_base.eleven_string, index=11)
    link_enum_strings(_base.twelve_string, index=12)
    link_enum_strings(_base.thirteen_string, index=13)
    link_enum_strings(_base.fourteen_string, index=14)
    link_enum_strings(_base.fifteen_string, index=15)

    @_base.raw_value.putter
    async def raw_value(self, instance, value):
        await self.parent.write(
            value=value
        )

    async def value_write_hook(self, instance, value):
        raw_value = self.parent.get_raw_value(value)
        if raw_value is not None:
            await self.raw_value.write(raw_value, verify_value=False)


@register_record
class MbbodirectFields(base.MbbodirectFields, RecordFieldGroup):
    _base = base.MbbodirectFields


@register_record
class MotorFields(base.MotorFields, RecordFieldGroup):
    _base = base.MotorFields
    link_parent_attribute(
        _base.display_precision, "precision",
    )
    link_parent_attribute(_base.archive_deadband, "log_atol", use_setattr=True)
    link_parent_attribute(_base.monitor_deadband, "value_atol", use_setattr=True)


@register_record
class PermissiveFields(base.PermissiveFields, RecordFieldGroup):
    _base = base.PermissiveFields


@register_record
class PrintfFields(base.PrintfFields, RecordFieldGroup):
    _base = base.PrintfFields


@register_record
class SelFields(base.SelFields, RecordFieldGroup):
    _base = base.SelFields
    link_parent_attribute(
        _base.display_precision, "precision",
    )
    link_parent_attribute(_base.archive_deadband, "log_atol", use_setattr=True)
    link_parent_attribute(_base.monitor_deadband, "value_atol", use_setattr=True)


@register_record
class SeqFields(base.SeqFields, RecordFieldGroup):
    _base = base.SeqFields
    link_parent_attribute(
        _base.display_precision, "precision",
    )


@register_record
class StateFields(base.StateFields, RecordFieldGroup):
    _base = base.StateFields


@register_record
class StringinFields(base.StringinFields, RecordFieldGroup):
    _base = base.StringinFields


@register_record
class StringoutFields(base.StringoutFields, RecordFieldGroup):
    _base = base.StringoutFields


@register_record
class SubFields(base.SubFields, RecordFieldGroup):
    _base = base.SubFields
    link_parent_attribute(
        _base.display_precision, "precision",
    )
    link_parent_attribute(_base.archive_deadband, "log_atol", use_setattr=True)
    link_parent_attribute(_base.monitor_deadband, "value_atol", use_setattr=True)


@register_record
class SubarrayFields(base.SubarrayFields, RecordFieldGroup):
    _base = base.SubarrayFields
    link_parent_attribute(
        _base.display_precision, "precision",
    )
    link_parent_attribute(
        _base.high_operating_range, "upper_ctrl_limit",
    )
    link_parent_attribute(
        _base.low_operating_range, "lower_ctrl_limit",
    )
    link_parent_attribute(
        _base.maximum_elements, "length", use_setattr=True, read_only=True
    )
    link_parent_attribute(
        _base.number_of_elements, "max_length", use_setattr=True, read_only=True
    )


@register_record
class WaveformFields(base.WaveformFields, RecordFieldGroup):
    _base = base.WaveformFields
    link_parent_attribute(
        _base.display_precision, "precision",
    )
    link_parent_attribute(
        _base.high_operating_range, "upper_ctrl_limit",
    )
    link_parent_attribute(
        _base.low_operating_range, "lower_ctrl_limit",
    )
    link_parent_attribute(
        _base.number_of_elements, "max_length", use_setattr=True, read_only=True
    )
