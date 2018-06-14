'''
Contains PVGroups representing all fields of EPICS base records (minus .VAL)
'''

import inspect

from .server import PVGroup, pvproperty
from .._data import ChannelType
from . import menus


def _link_parent_attribute(pvprop, parent_attr_name, *, read_only=False,
                           use_setattr=False, default=0):
    'Take a pvproperty and link its getter/putter to a parent attribute'

    @pvprop.getter
    async def getter(self, instance):
        return getattr(self.parent, parent_attr_name, default)

    if not read_only:
        if use_setattr:
            @pvprop.putter
            async def putter(self, instance, value):
                if hasattr(self.parent, parent_attr_name):
                    setattr(self.parent, parent_attr_name, value)

        else:
            @pvprop.putter
            async def putter(self, instance, value):
                kw = {parent_attr_name: value}
                await self.parent.write_metadata(**kw)

    return pvprop


class RecordFieldGroup(PVGroup):
    alarm_acknowledge_severity = pvproperty(
        name='ACKS',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Alarm Ack Severity',
        read_only=True)
    alarm_acknowledge_transient = pvproperty(
        name='ACKT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuYesNo.get_string_tuple(),
        doc='Alarm Ack Transient',
        read_only=True)
    access_security_group = pvproperty(
        name='ASG',
        dtype=ChannelType.CHAR,
        max_length=29,
        doc='Access Security Group')
    description = pvproperty(
        name='DESC', dtype=ChannelType.CHAR, max_length=41, doc='Descriptor')
    scan_disable_input_link_value = pvproperty(
        name='DISA', dtype=ChannelType.LONG, doc='Disable')
    disable_putfields = pvproperty(
        name='DISP', dtype=ChannelType.CHAR, doc='Disable putField')
    disable_alarm_severity = pvproperty(
        name='DISS',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Disable Alarm Sevrty')
    disable_value = pvproperty(
        name='DISV', dtype=ChannelType.LONG, doc='Disable Value')
    device_type = pvproperty(
        name='DTYP', dtype=ChannelType.STRING, doc='Device Type')
    event_number = pvproperty(
        name='EVNT', dtype=ChannelType.LONG, doc='Event Number')
    forward_link = pvproperty(
        name='FLNK', dtype=ChannelType.STRING, doc='Forward Process Link')
    lock_count = pvproperty(
        name='LCNT', dtype=ChannelType.CHAR, doc='Lock Count', read_only=True)
    record_name = pvproperty(
        name='NAME',
        dtype=ChannelType.CHAR,
        max_length=61,
        doc='Record Name',
        read_only=True)
    new_alarm_severity = pvproperty(
        name='NSEV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='New Alarm Severity',
        read_only=True)
    new_alarm_status = pvproperty(
        name='NSTA',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='New Alarm Status',
        read_only=True)
    processing_active = pvproperty(
        name='PACT',
        dtype=ChannelType.CHAR,
        doc='Record active',
        read_only=True)
    scan_phase_number = pvproperty(
        name='PHAS', dtype=ChannelType.LONG, doc='Scan Phase')
    process_at_initialization = pvproperty(
        name='PINI',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuPini.get_string_tuple(),
        doc='Process at iocInit')
    priority = pvproperty(
        name='PRIO',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuPriority.get_string_tuple(),
        doc='Scheduling Priority')
    process_record = pvproperty(
        name='PROC', dtype=ChannelType.CHAR, doc='Force Processing')
    dbputfield_process = pvproperty(
        name='PUTF',
        dtype=ChannelType.CHAR,
        doc='dbPutField process',
        read_only=True)
    reprocess = pvproperty(
        name='RPRO', dtype=ChannelType.CHAR, doc='Reprocess', read_only=True)
    scanning_rate = pvproperty(
        name='SCAN',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuScan.get_string_tuple(),
        doc='Scan Mechanism')
    scan_disable_input_link = pvproperty(
        name='SDIS', dtype=ChannelType.STRING, doc='Scanning Disable')
    current_alarm_severity = pvproperty(
        name='SEVR',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Alarm Severity',
        read_only=True)
    trace_processing = pvproperty(
        name='TPRO', dtype=ChannelType.CHAR, doc='Trace Processing')
    time_stamp_event = pvproperty(
        name='TSE', dtype=ChannelType.LONG, doc='Time Stamp Event')
    time_stamp_event_link = pvproperty(
        name='TSEL', dtype=ChannelType.STRING, doc='Time Stamp Link')
    val_undefined = pvproperty(
        name='UDF', dtype=ChannelType.CHAR, doc='Undefined')

    # -- Above is auto-generated --

    # Add some handling onto the autogenerated code above:
    record_type = pvproperty(
        name='RTYP', dtype=ChannelType.CHAR, read_only=True,
        max_length=40,
        doc='Record type')

    def __init__(self, prefix, **kw):
        super().__init__(prefix, **kw)

        parent = self.parent
        self.record_name._data['value'] = parent.pvname
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

    # TODO: server single-char issue with caget?

    @process_record.putter
    async def process_record(self, instance, value):
        await self.parent.write(self.parent.value)


class AiFields(RecordFieldGroup):
    _record_type = 'ai'
    # value = pvproperty(
    #     name='VAL', dtype=ChannelType.DOUBLE, doc='Current EGU Value')
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    current_raw_value = pvproperty(
        name='RVAL', dtype=ChannelType.LONG, doc='Current Raw Value')
    initialized = pvproperty(
        name='INIT',
        dtype=ChannelType.LONG,
        doc='Initialized?',
        read_only=True)
    last_val_monitored = pvproperty(
        name='MLST',
        dtype=ChannelType.DOUBLE,
        doc='Last Val Monitored',
        read_only=True)
    last_value_alarmed = pvproperty(
        name='LALM',
        dtype=ChannelType.DOUBLE,
        doc='Last Value Alarmed',
        read_only=True)
    last_value_archived = pvproperty(
        name='ALST',
        dtype=ChannelType.DOUBLE,
        doc='Last Value Archived',
        read_only=True)
    lastbreak_point = pvproperty(
        name='LBRK',
        dtype=ChannelType.LONG,
        doc='LastBreak Point',
        read_only=True)
    previous_raw_value = pvproperty(
        name='ORAW',
        dtype=ChannelType.LONG,
        doc='Previous Raw Value',
        read_only=True)
    raw_offset_obsolete = pvproperty(
        name='ROFF', dtype=ChannelType.LONG, doc='Raw Offset, obsolete')
    simulation_mode = pvproperty(
        name='SIMM',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuSimm.get_string_tuple(),
        doc='Simulation Mode')
    simulation_value = pvproperty(
        name='SVAL', dtype=ChannelType.DOUBLE, doc='Simulation Value')
    alarm_deadband = pvproperty(
        name='HYST', dtype=ChannelType.DOUBLE, doc='Alarm Deadband')
    high_alarm_limit = pvproperty(
        name='HIGH', dtype=ChannelType.DOUBLE, doc='High Alarm Limit')
    high_severity = pvproperty(
        name='HSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='High Severity')
    hihi_alarm_limit = pvproperty(
        name='HIHI', dtype=ChannelType.DOUBLE, doc='Hihi Alarm Limit')
    hihi_severity = pvproperty(
        name='HHSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Hihi Severity')
    lolo_alarm_limit = pvproperty(
        name='LOLO', dtype=ChannelType.DOUBLE, doc='Lolo Alarm Limit')
    lolo_severity = pvproperty(
        name='LLSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Lolo Severity')
    low_alarm_limit = pvproperty(
        name='LOW', dtype=ChannelType.DOUBLE, doc='Low Alarm Limit')
    low_severity = pvproperty(
        name='LSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Low Severity')
    adjustment_offset = pvproperty(
        name='AOFF', dtype=ChannelType.DOUBLE, doc='Adjustment Offset')
    adjustment_slope = pvproperty(
        name='ASLO', dtype=ChannelType.DOUBLE, doc='Adjustment Slope')
    engineer_units_full = pvproperty(
        name='EGUF', dtype=ChannelType.DOUBLE, doc='Engineer Units Full')
    engineer_units_low = pvproperty(
        name='EGUL', dtype=ChannelType.DOUBLE, doc='Engineer Units Low')
    linearization = pvproperty(
        name='LINR',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuConvert.get_string_tuple(),
        doc='Linearization')
    raw_to_egu_offset = pvproperty(
        name='EOFF', dtype=ChannelType.DOUBLE, doc='Raw to EGU Offset')
    raw_to_egu_slope = pvproperty(
        name='ESLO', dtype=ChannelType.DOUBLE, doc='Raw to EGU Slope')
    smoothing = pvproperty(
        name='SMOO', dtype=ChannelType.DOUBLE, doc='Smoothing')
    archive_deadband = pvproperty(
        name='ADEL', dtype=ChannelType.DOUBLE, doc='Archive Deadband')
    display_precision = pvproperty(
        name='PREC', dtype=ChannelType.LONG, doc='Display Precision')
    engineering_units = pvproperty(
        name='EGU',
        dtype=ChannelType.CHAR,
        max_length=16,
        doc='Engineering Units')
    high_operating_range = pvproperty(
        name='HOPR', dtype=ChannelType.DOUBLE, doc='High Operating Range')
    low_operating_range = pvproperty(
        name='LOPR', dtype=ChannelType.DOUBLE, doc='Low Operating Range')
    monitor_deadband = pvproperty(
        name='MDEL', dtype=ChannelType.DOUBLE, doc='Monitor Deadband')
    input_specification = pvproperty(
        name='INP', dtype=ChannelType.STRING, doc='Input Specification')
    sim_input_specifctn = pvproperty(
        name='SIOL', dtype=ChannelType.STRING, doc='Sim Input Specifctn')
    sim_mode_location = pvproperty(
        name='SIML', dtype=ChannelType.STRING, doc='Sim Mode Location')
    sim_mode_alarm_svrty = pvproperty(
        name='SIMS',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Sim mode Alarm Svrty')

    # -- end autogenerated code --

    # With this brief line:
    _link_parent_attribute(display_precision, 'precision')

    # we have the equivalent of:

    # @display_precision.getter
    # async def display_precision(self, instance):
    #     return getattr(self.parent, 'precision', 0)

    # @display_precision.putter
    # async def display_precision(self, instance, value):
    #     await self.parent.write_metadata(precision=value)

    _link_parent_attribute(hihi_alarm_limit, 'upper_alarm_limit')
    _link_parent_attribute(high_alarm_limit, 'upper_warning_limit')
    _link_parent_attribute(low_alarm_limit, 'lower_warning_limit')
    _link_parent_attribute(lolo_alarm_limit, 'lower_alarm_limit')
    _link_parent_attribute(high_operating_range, 'upper_ctrl_limit')
    _link_parent_attribute(low_operating_range, 'lower_ctrl_limit')


records = {record._record_type: record
           for name, record in globals().items()
           if inspect.isclass(record) and
           issubclass(record, PVGroup) and
           record not in (PVGroup, RecordFieldGroup)
           }
__all__ = ['records', 'RecordFieldGroup'] + list(records.keys())
