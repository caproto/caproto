'''
Contains PVGroups representing all fields of EPICS base records (minus .VAL)
'''

import logging

from .server import PVGroup, pvproperty
from .._data import ChannelType
from .._dbr import AlarmSeverity
from . import menus


logger = logging.getLogger(__name__)
records = {}


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


def register_record(cls):
    'Register a record type to be used with pvproperty mock_record'
    assert issubclass(cls, PVGroup)
    records[cls._record_type] = cls
    logger.debug('Registered record type %r', cls._record_type)
    return cls


class RecordFieldGroup(PVGroup):
    _scan_rate_sec = None
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
    scan_rate = pvproperty(
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

    # TODO: server single-char issue with caget?

    @scan_rate.putter
    async def scan_rate(self, instance, value):
        idx = value
        scan_string = self.scan_rate.enum_strings[idx]
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

    @process_record.putter
    async def process_record(self, instance, value):
        await self.parent.write(self.parent.value)


class _Limits(PVGroup):
    high_alarm_limit = pvproperty(
        name='HIGH', dtype=ChannelType.DOUBLE, doc='High Alarm Limit')
    high_severity = pvproperty(
        name='HSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='High Severity',
        value=menus.menuAlarmSevr.get_string_tuple()[
            AlarmSeverity.MINOR_ALARM])
    hihi_alarm_limit = pvproperty(
        name='HIHI', dtype=ChannelType.DOUBLE, doc='Hihi Alarm Limit')
    hihi_severity = pvproperty(
        name='HHSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Hihi Severity',
        value=menus.menuAlarmSevr.get_string_tuple()[
            AlarmSeverity.MAJOR_ALARM])
    lolo_alarm_limit = pvproperty(
        name='LOLO', dtype=ChannelType.DOUBLE, doc='Lolo Alarm Limit')
    lolo_severity = pvproperty(
        name='LLSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Lolo Severity',
        value=menus.menuAlarmSevr.get_string_tuple()[
            AlarmSeverity.MAJOR_ALARM])
    low_alarm_limit = pvproperty(
        name='LOW', dtype=ChannelType.DOUBLE, doc='Low Alarm Limit')
    low_severity = pvproperty(
        name='LSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Low Severity',
        value=menus.menuAlarmSevr.get_string_tuple()[
            AlarmSeverity.MINOR_ALARM])
    high_operating_range = pvproperty(
        name='HOPR', dtype=ChannelType.DOUBLE, doc='High Operating Range')
    low_operating_range = pvproperty(
        name='LOPR', dtype=ChannelType.DOUBLE, doc='Low Operating Range')

    _link_parent_attribute(hihi_alarm_limit, 'upper_alarm_limit')
    _link_parent_attribute(lolo_alarm_limit, 'lower_alarm_limit')

    _link_parent_attribute(high_alarm_limit, 'upper_warning_limit')
    _link_parent_attribute(low_alarm_limit, 'lower_warning_limit')

    _link_parent_attribute(high_operating_range, 'upper_ctrl_limit')
    _link_parent_attribute(low_operating_range, 'lower_ctrl_limit')


class _LimitsLong(PVGroup):
    high_alarm_limit = pvproperty(
        name='HIGH', dtype=ChannelType.LONG, doc='High Alarm Limit')
    high_severity = pvproperty(
        name='HSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='High Severity',
        value=menus.menuAlarmSevr.get_string_tuple()[
            AlarmSeverity.MINOR_ALARM])
    hihi_alarm_limit = pvproperty(
        name='HIHI', dtype=ChannelType.LONG, doc='Hihi Alarm Limit')
    hihi_severity = pvproperty(
        name='HHSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Hihi Severity',
        value=menus.menuAlarmSevr.get_string_tuple()[
            AlarmSeverity.MAJOR_ALARM])
    lolo_alarm_limit = pvproperty(
        name='LOLO', dtype=ChannelType.LONG, doc='Lolo Alarm Limit')
    lolo_severity = pvproperty(
        name='LLSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Lolo Severity',
        value=menus.menuAlarmSevr.get_string_tuple()[
            AlarmSeverity.MAJOR_ALARM])
    low_alarm_limit = pvproperty(
        name='LOW', dtype=ChannelType.LONG, doc='Low Alarm Limit')
    low_severity = pvproperty(
        name='LSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Low Severity',
        value=menus.menuAlarmSevr.get_string_tuple()[
            AlarmSeverity.MINOR_ALARM])
    high_operating_range = pvproperty(
        name='HOPR', dtype=ChannelType.LONG, doc='High Operating Range')
    low_operating_range = pvproperty(
        name='LOPR', dtype=ChannelType.LONG, doc='Low Operating Range')

    _link_parent_attribute(hihi_alarm_limit, 'upper_alarm_limit')
    _link_parent_attribute(lolo_alarm_limit, 'lower_alarm_limit')

    _link_parent_attribute(high_alarm_limit, 'upper_warning_limit')
    _link_parent_attribute(low_alarm_limit, 'lower_warning_limit')

    _link_parent_attribute(high_operating_range, 'upper_ctrl_limit')
    _link_parent_attribute(low_operating_range, 'lower_ctrl_limit')


@register_record
class AiFields(RecordFieldGroup, _Limits):
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

    _link_parent_attribute(archive_deadband, 'log_atol')
    _link_parent_attribute(monitor_deadband, 'value_atol')

    # With this brief line:
    _link_parent_attribute(display_precision, 'precision')

    # we have the equivalent of:

    # @display_precision.getter
    # async def display_precision(self, instance):
    #     return getattr(self.parent, 'precision', 0)

    # @display_precision.putter
    # async def display_precision(self, instance, value):
    #     await self.parent.write_metadata(precision=value)


@register_record
class AsubFields(RecordFieldGroup):
    _record_type = 'aSub'
    # value = pvproperty(
    #     name='VAL', dtype=ChannelType.LONG, doc='Subr. return value')
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    old_return_value = pvproperty(
        name='OVAL',
        dtype=ChannelType.LONG,
        doc='Old return value',
        read_only=True)
    display_precision = pvproperty(
        name='PREC', dtype=ChannelType.LONG, doc='Display Precision')
    output_event_flag = pvproperty(
        name='EFLG',
        dtype=ChannelType.ENUM,
        enum_strings=menus.aSubEFLG.get_string_tuple(),
        doc='Output Event Flag')
    bad_return_severity = pvproperty(
        name='BRSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Bad Return Severity')
    initialize_subroutine_name = pvproperty(
        name='INAM',
        dtype=ChannelType.CHAR,
        max_length=41,
        doc='Initialize Subr. Name',
        read_only=True)
    old_subroutine_name = pvproperty(
        name='ONAM',
        dtype=ChannelType.CHAR,
        max_length=41,
        doc='Old Subr. Name',
        read_only=True)
    process_subroutine_name = pvproperty(
        name='SNAM',
        dtype=ChannelType.CHAR,
        max_length=41,
        doc='Process Subr. Name')
    subroutine_input_enable = pvproperty(
        name='LFLG',
        dtype=ChannelType.ENUM,
        enum_strings=menus.aSubLFLG.get_string_tuple(),
        doc='Subr. Input Enable')
    subroutine_name_link = pvproperty(
        name='SUBL',
        dtype=ChannelType.STRING,
        doc='Subroutine Name Link',
        read_only=True)
    _link_parent_attribute(display_precision, 'precision')


@register_record
class AaiFields(RecordFieldGroup):
    _record_type = 'aai'
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    hash_of_onchange_data = pvproperty(
        name='HASH', dtype=ChannelType.LONG, doc='Hash of OnChange data.')
    number_elements_read = pvproperty(
        name='NORD',
        dtype=ChannelType.LONG,
        doc='Number elements read',
        read_only=True)
    simulation_mode = pvproperty(
        name='SIMM',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuYesNo.get_string_tuple(),
        doc='Simulation Mode')
    display_precision = pvproperty(
        name='PREC', dtype=ChannelType.LONG, doc='Display Precision')
    input_specification = pvproperty(
        name='INP', dtype=ChannelType.STRING, doc='Input Specification')
    engineering_units_name = pvproperty(
        name='EGU',
        dtype=ChannelType.CHAR,
        max_length=16,
        doc='Engineering Units Name')
    high_operating_range = pvproperty(
        name='HOPR', dtype=ChannelType.DOUBLE, doc='High Operating Range')
    low_operating_range = pvproperty(
        name='LOPR', dtype=ChannelType.DOUBLE, doc='Low Operating Range')
    number_of_elements = pvproperty(
        name='NELM',
        dtype=ChannelType.LONG,
        doc='Number of Elements',
        read_only=True)
    field_type_of_value = pvproperty(
        name='FTVL',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Field Type of Value',
        read_only=True)
    post_archive_monitors = pvproperty(
        name='APST',
        dtype=ChannelType.ENUM,
        enum_strings=menus.aaiPOST.get_string_tuple(),
        doc='Post Archive Monitors')
    post_value_monitors = pvproperty(
        name='MPST',
        dtype=ChannelType.ENUM,
        enum_strings=menus.aaiPOST.get_string_tuple(),
        doc='Post Value Monitors')
    sim_mode_location = pvproperty(
        name='SIML', dtype=ChannelType.STRING, doc='Sim Mode Location')
    sim_input_specifctn = pvproperty(
        name='SIOL', dtype=ChannelType.STRING, doc='Sim Input Specifctn')
    sim_mode_alarm_svrty = pvproperty(
        name='SIMS',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Sim mode Alarm Svrty')
    _link_parent_attribute(display_precision, 'precision')
    _link_parent_attribute(high_operating_range, 'upper_ctrl_limit')
    _link_parent_attribute(low_operating_range, 'lower_ctrl_limit')
    _link_parent_attribute(number_of_elements, 'max_length')
    _link_parent_attribute(number_elements_read, 'length')


@register_record
class AaoFields(RecordFieldGroup):
    _record_type = 'aao'
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    hash_of_onchange_data = pvproperty(
        name='HASH', dtype=ChannelType.LONG, doc='Hash of OnChange data.')
    number_elements_read = pvproperty(
        name='NORD',
        dtype=ChannelType.LONG,
        doc='Number elements read',
        read_only=True)
    simulation_mode = pvproperty(
        name='SIMM',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuYesNo.get_string_tuple(),
        doc='Simulation Mode')
    display_precision = pvproperty(
        name='PREC', dtype=ChannelType.LONG, doc='Display Precision')
    output_specification = pvproperty(
        name='OUT', dtype=ChannelType.STRING, doc='Output Specification')
    engineering_units_name = pvproperty(
        name='EGU',
        dtype=ChannelType.CHAR,
        max_length=16,
        doc='Engineering Units Name')
    high_operating_range = pvproperty(
        name='HOPR', dtype=ChannelType.DOUBLE, doc='High Operating Range')
    low_operating_range = pvproperty(
        name='LOPR', dtype=ChannelType.DOUBLE, doc='Low Operating Range')
    number_of_elements = pvproperty(
        name='NELM',
        dtype=ChannelType.LONG,
        doc='Number of Elements',
        read_only=True)
    field_type_of_value = pvproperty(
        name='FTVL',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Field Type of Value',
        read_only=True)
    post_archive_monitors = pvproperty(
        name='APST',
        dtype=ChannelType.ENUM,
        enum_strings=menus.aaoPOST.get_string_tuple(),
        doc='Post Archive Monitors')
    post_value_monitors = pvproperty(
        name='MPST',
        dtype=ChannelType.ENUM,
        enum_strings=menus.aaoPOST.get_string_tuple(),
        doc='Post Value Monitors')
    sim_mode_location = pvproperty(
        name='SIML', dtype=ChannelType.STRING, doc='Sim Mode Location')
    sim_output_specifctn = pvproperty(
        name='SIOL', dtype=ChannelType.STRING, doc='Sim Output Specifctn')
    sim_mode_alarm_svrty = pvproperty(
        name='SIMS',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Sim mode Alarm Svrty')
    _link_parent_attribute(display_precision, 'precision')
    _link_parent_attribute(high_operating_range, 'upper_ctrl_limit')
    _link_parent_attribute(low_operating_range, 'lower_ctrl_limit')
    _link_parent_attribute(number_of_elements, 'max_length')
    _link_parent_attribute(number_elements_read, 'length')


@register_record
class AcalcoutFields(RecordFieldGroup, _Limits):
    _record_type = 'acalcout'
    # value = pvproperty(name='VAL', dtype=ChannelType.DOUBLE, doc='Result')
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    array_mod = pvproperty(
        name='AMASK', dtype=ChannelType.LONG, doc='Array mod', read_only=True)
    array_size_reported_to_clients = pvproperty(
        name='SIZE',
        dtype=ChannelType.ENUM,
        enum_strings=menus.acalcoutSIZE.get_string_tuple(),
        doc='Array size reported to clients')
    calc_valid = pvproperty(
        name='CLCV', dtype=ChannelType.LONG, doc='CALC Valid')
    calc_active = pvproperty(
        name='CACT', dtype=ChannelType.CHAR, doc='Calc active', read_only=True)
    calc_status = pvproperty(
        name='CSTAT',
        dtype=ChannelType.LONG,
        doc='Calc status',
        read_only=True)
    code_version = pvproperty(
        name='VERS',
        dtype=ChannelType.DOUBLE,
        doc='Code Version',
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
    ocal_valid = pvproperty(
        name='OCLV', dtype=ChannelType.LONG, doc='OCAL Valid')
    out_pv_status = pvproperty(
        name='OUTV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.acalcoutINAV.get_string_tuple(),
        doc='OUT PV Status',
        read_only=True)
    output_delay_active = pvproperty(
        name='DLYA',
        dtype=ChannelType.LONG,
        doc='Output Delay Active',
        read_only=True)
    output_value = pvproperty(
        name='OVAL', dtype=ChannelType.DOUBLE, doc='Output Value')
    prev_value_of_oval = pvproperty(
        name='POVL', dtype=ChannelType.DOUBLE, doc='Prev Value of OVAL')
    previous_value = pvproperty(
        name='PVAL', dtype=ChannelType.DOUBLE, doc='Previous Value')
    wait_for_completion = pvproperty(
        name='WAIT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.acalcoutWAIT.get_string_tuple(),
        doc='Wait for completion?')
    new_array_value_mask = pvproperty(
        name='NEWM',
        dtype=ChannelType.LONG,
        doc='new array value mask',
        read_only=True)
    alarm_deadband = pvproperty(
        name='HYST', dtype=ChannelType.DOUBLE, doc='Alarm Deadband')
    output_execute_delay = pvproperty(
        name='ODLY', dtype=ChannelType.DOUBLE, doc='Output Execute Delay')
    calculation = pvproperty(
        name='CALC', dtype=ChannelType.CHAR, max_length=80, doc='Calculation')
    output_calculation = pvproperty(
        name='OCAL',
        dtype=ChannelType.CHAR,
        max_length=80,
        doc='Output Calculation')
    output_data_opt = pvproperty(
        name='DOPT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.acalcoutDOPT.get_string_tuple(),
        doc='Output Data Opt')
    output_execute_opt = pvproperty(
        name='OOPT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.acalcoutOOPT.get_string_tuple(),
        doc='Output Execute Opt')
    event_to_issue = pvproperty(
        name='OEVT', dtype=ChannelType.LONG, doc='Event To Issue')
    archive_deadband = pvproperty(
        name='ADEL', dtype=ChannelType.DOUBLE, doc='Archive Deadband')
    display_precision = pvproperty(
        name='PREC', dtype=ChannelType.LONG, doc='Display Precision')
    monitor_deadband = pvproperty(
        name='MDEL', dtype=ChannelType.DOUBLE, doc='Monitor Deadband')
    units_name = pvproperty(
        name='EGU', dtype=ChannelType.CHAR, max_length=16, doc='Units Name')
    invalid_output_action = pvproperty(
        name='IVOA',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuIvoa.get_string_tuple(),
        doc='INVALID output action')
    invalid_output_value = pvproperty(
        name='IVOV', dtype=ChannelType.DOUBLE, doc='INVALID output value')
    output_link = pvproperty(
        name='OUT', dtype=ChannelType.STRING, doc='Output Link')
    elem_s_in_use = pvproperty(
        name='NUSE', dtype=ChannelType.LONG, doc="# elem's in use")
    number_of_elements = pvproperty(
        name='NELM',
        dtype=ChannelType.LONG,
        doc='Number of Elements',
        read_only=True)
    _link_parent_attribute(display_precision, 'precision')
    _link_parent_attribute(archive_deadband, 'log_atol')
    _link_parent_attribute(monitor_deadband, 'value_atol')
    _link_parent_attribute(number_of_elements, 'max_length')


@register_record
class AoFields(RecordFieldGroup, _Limits):
    _record_type = 'ao'
    # value = pvproperty(
    #     name='VAL', dtype=ChannelType.DOUBLE, doc='Desired Output')
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
    output_value = pvproperty(
        name='OVAL', dtype=ChannelType.DOUBLE, doc='Output Value')
    prev_readback_value = pvproperty(
        name='ORBV',
        dtype=ChannelType.LONG,
        doc='Prev Readback Value',
        read_only=True)
    previous_raw_value = pvproperty(
        name='ORAW',
        dtype=ChannelType.LONG,
        doc='Previous Raw Value',
        read_only=True)
    previous_value = pvproperty(
        name='PVAL',
        dtype=ChannelType.DOUBLE,
        doc='Previous value',
        read_only=True)
    raw_offset_obsolete = pvproperty(
        name='ROFF', dtype=ChannelType.LONG, doc='Raw Offset, obsolete')
    readback_value = pvproperty(
        name='RBV',
        dtype=ChannelType.LONG,
        doc='Readback Value',
        read_only=True)
    simulation_mode = pvproperty(
        name='SIMM',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuYesNo.get_string_tuple(),
        doc='Simulation Mode')
    was_oval_modified = pvproperty(
        name='OMOD',
        dtype=ChannelType.CHAR,
        doc='Was OVAL modified?',
        read_only=True)
    alarm_deadband = pvproperty(
        name='HYST', dtype=ChannelType.DOUBLE, doc='Alarm Deadband')
    adjustment_offset = pvproperty(
        name='AOFF', dtype=ChannelType.DOUBLE, doc='Adjustment Offset')
    adjustment_slope = pvproperty(
        name='ASLO', dtype=ChannelType.DOUBLE, doc='Adjustment Slope')
    egu_to_raw_offset = pvproperty(
        name='EOFF', dtype=ChannelType.DOUBLE, doc='EGU to Raw Offset')
    egu_to_raw_slope = pvproperty(
        name='ESLO', dtype=ChannelType.DOUBLE, doc='EGU to Raw Slope')
    eng_units_full = pvproperty(
        name='EGUF', dtype=ChannelType.DOUBLE, doc='Eng Units Full')
    eng_units_low = pvproperty(
        name='EGUL', dtype=ChannelType.DOUBLE, doc='Eng Units Low')
    linearization = pvproperty(
        name='LINR',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuConvert.get_string_tuple(),
        doc='Linearization')
    archive_deadband = pvproperty(
        name='ADEL', dtype=ChannelType.DOUBLE, doc='Archive Deadband')
    display_precision = pvproperty(
        name='PREC', dtype=ChannelType.LONG, doc='Display Precision')
    engineering_units = pvproperty(
        name='EGU',
        dtype=ChannelType.CHAR,
        max_length=16,
        doc='Engineering Units')
    monitor_deadband = pvproperty(
        name='MDEL', dtype=ChannelType.DOUBLE, doc='Monitor Deadband')
    sim_mode_location = pvproperty(
        name='SIML', dtype=ChannelType.STRING, doc='Sim Mode Location')
    sim_output_specifctn = pvproperty(
        name='SIOL', dtype=ChannelType.STRING, doc='Sim Output Specifctn')
    sim_mode_alarm_svrty = pvproperty(
        name='SIMS',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Sim mode Alarm Svrty')
    desired_output_loc = pvproperty(
        name='DOL', dtype=ChannelType.STRING, doc='Desired Output Loc')
    drive_high_limit = pvproperty(
        name='DRVH', dtype=ChannelType.DOUBLE, doc='Drive High Limit')
    drive_low_limit = pvproperty(
        name='DRVL', dtype=ChannelType.DOUBLE, doc='Drive Low Limit')
    invalid_output_action = pvproperty(
        name='IVOA',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuIvoa.get_string_tuple(),
        doc='INVALID output action')
    invalid_output_value = pvproperty(
        name='IVOV', dtype=ChannelType.DOUBLE, doc='INVALID output value')
    out_full_incremental = pvproperty(
        name='OIF',
        dtype=ChannelType.ENUM,
        enum_strings=menus.aoOIF.get_string_tuple(),
        doc='Out Full/Incremental')
    output_mode_select = pvproperty(
        name='OMSL',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuOmsl.get_string_tuple(),
        doc='Output Mode Select')
    output_rate_of_chang = pvproperty(
        name='OROC', dtype=ChannelType.DOUBLE, doc='Output Rate of Chang')
    output_specification = pvproperty(
        name='OUT', dtype=ChannelType.STRING, doc='Output Specification')
    _link_parent_attribute(display_precision, 'precision')
    _link_parent_attribute(archive_deadband, 'log_atol')
    _link_parent_attribute(monitor_deadband, 'value_atol')


@register_record
class AsynFields(RecordFieldGroup):
    _record_type = 'asyn'
    # value = pvproperty(
    #     name='VAL', dtype=ChannelType.LONG, doc='Value field (unused)')
    abort_queuerequest = pvproperty(
        name='AQR', dtype=ChannelType.CHAR, doc='Abort queueRequest')
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    eom_reason = pvproperty(
        name='EOMR',
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynEOMREASON.get_string_tuple(),
        doc='EOM reason',
        read_only=True)
    input_response_string = pvproperty(
        name='AINP',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Input (response) string',
        read_only=True)
    input_binary_data = pvproperty(
        name='BINP', dtype=ChannelType.CHAR, doc='Input binary data')
    number_of_bytes_actually_written = pvproperty(
        name='NAWT',
        dtype=ChannelType.LONG,
        doc='Number of bytes actually written')
    number_of_bytes_read = pvproperty(
        name='NORD',
        dtype=ChannelType.LONG,
        doc='Number of bytes read',
        read_only=True)
    output_binary_data = pvproperty(
        name='BOUT', dtype=ChannelType.CHAR, doc='Output binary data')
    port_connect_disconnect = pvproperty(
        name='PCNCT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynCONNECT.get_string_tuple(),
        doc='Port Connect/Disconnect')
    serial_poll_response = pvproperty(
        name='SPR',
        dtype=ChannelType.CHAR,
        doc='Serial poll response',
        read_only=True)
    translated_input_string = pvproperty(
        name='TINP',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Translated input string',
        read_only=True)
    asynfloat64_input = pvproperty(
        name='F64INP',
        dtype=ChannelType.DOUBLE,
        doc='asynFloat64 input',
        read_only=True)
    asynfloat64_is_valid = pvproperty(
        name='F64IV', dtype=ChannelType.LONG, doc='asynFloat64 is valid')
    asyngpib_is_valid = pvproperty(
        name='GPIBIV', dtype=ChannelType.LONG, doc='asynGPIB is valid')
    asynint32_input = pvproperty(
        name='I32INP',
        dtype=ChannelType.LONG,
        doc='asynInt32 input',
        read_only=True)
    asynint32_is_valid = pvproperty(
        name='I32IV', dtype=ChannelType.LONG, doc='asynInt32 is valid')
    asynoctet_is_valid = pvproperty(
        name='OCTETIV', dtype=ChannelType.LONG, doc='asynOctet is valid')
    asynoption_is_valid = pvproperty(
        name='OPTIONIV', dtype=ChannelType.LONG, doc='asynOption is valid')
    asynuint32digital_input = pvproperty(
        name='UI32INP',
        dtype=ChannelType.LONG,
        doc='asynUInt32Digital input',
        read_only=True)
    asynuint32digital_is_valid = pvproperty(
        name='UI32IV',
        dtype=ChannelType.LONG,
        doc='asynUInt32Digital is valid')
    asynuser_reason = pvproperty(
        name='REASON', dtype=ChannelType.LONG, doc='asynUser->reason')
    trace_io_mask = pvproperty(
        name='TIOM', dtype=ChannelType.LONG, doc='Trace I/O mask')
    trace_io_ascii = pvproperty(
        name='TIB0',
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynTRACE.get_string_tuple(),
        doc='Trace IO ASCII')
    trace_io_device = pvproperty(
        name='TB1',
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynTRACE.get_string_tuple(),
        doc='Trace IO device')
    trace_io_driver = pvproperty(
        name='TB3',
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynTRACE.get_string_tuple(),
        doc='Trace IO driver')
    trace_io_escape = pvproperty(
        name='TIB1',
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynTRACE.get_string_tuple(),
        doc='Trace IO escape')
    trace_io_file = pvproperty(
        name='TFIL',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Trace IO file')
    trace_io_filter = pvproperty(
        name='TB2',
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynTRACE.get_string_tuple(),
        doc='Trace IO filter')
    trace_io_hex = pvproperty(
        name='TIB2',
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynTRACE.get_string_tuple(),
        doc='Trace IO hex')
    trace_io_truncate_size = pvproperty(
        name='TSIZ', dtype=ChannelType.LONG, doc='Trace IO truncate size')
    trace_info_port = pvproperty(
        name='TINB1',
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynTRACE.get_string_tuple(),
        doc='Trace Info Port')
    trace_info_source = pvproperty(
        name='TINB2',
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynTRACE.get_string_tuple(),
        doc='Trace Info Source')
    trace_info_thread = pvproperty(
        name='TINB3',
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynTRACE.get_string_tuple(),
        doc='Trace Info Thread')
    trace_info_time = pvproperty(
        name='TINB0',
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynTRACE.get_string_tuple(),
        doc='Trace Info Time')
    trace_info_mask = pvproperty(
        name='TINM', dtype=ChannelType.LONG, doc='Trace Info mask')
    trace_error = pvproperty(
        name='TB0',
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynTRACE.get_string_tuple(),
        doc='Trace error')
    trace_flow = pvproperty(
        name='TB4',
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynTRACE.get_string_tuple(),
        doc='Trace flow')
    trace_mask = pvproperty(
        name='TMSK', dtype=ChannelType.LONG, doc='Trace mask')
    trace_warning = pvproperty(
        name='TB5',
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynTRACE.get_string_tuple(),
        doc='Trace warning')
    autoconnect = pvproperty(
        name='AUCT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynAUTOCONNECT.get_string_tuple(),
        doc='Autoconnect')
    baud_rate = pvproperty(
        name='BAUD',
        dtype=ChannelType.ENUM,
        enum_strings=menus.serialBAUD.get_string_tuple(),
        doc='Baud rate')
    baud_rate_lbaud = pvproperty(
        name='LBAUD', dtype=ChannelType.LONG, doc='Baud rate')
    connect_disconnect = pvproperty(
        name='CNCT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynCONNECT.get_string_tuple(),
        doc='Connect/Disconnect')
    data_bits = pvproperty(
        name='DBIT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.serialDBIT.get_string_tuple(),
        doc='Data bits')
    driver_info_string = pvproperty(
        name='DRVINFO',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Driver info string')
    enable_disable = pvproperty(
        name='ENBL',
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynENABLE.get_string_tuple(),
        doc='Enable/Disable')
    flow_control = pvproperty(
        name='FCTL',
        dtype=ChannelType.ENUM,
        enum_strings=menus.serialFCTL.get_string_tuple(),
        doc='Flow control')
    input_delimiter = pvproperty(
        name='IEOS',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Input Delimiter')
    input_xon_xoff = pvproperty(
        name='IXOFF',
        dtype=ChannelType.ENUM,
        enum_strings=menus.serialIX.get_string_tuple(),
        doc='Input XON/XOFF')
    input_format = pvproperty(
        name='IFMT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynFMT.get_string_tuple(),
        doc='Input format')
    interface = pvproperty(
        name='IFACE',
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynINTERFACE.get_string_tuple(),
        doc='Interface')
    max_size_of_input_array = pvproperty(
        name='IMAX',
        dtype=ChannelType.LONG,
        doc='Max. size of input array',
        read_only=True)
    modem_control = pvproperty(
        name='MCTL',
        dtype=ChannelType.ENUM,
        enum_strings=menus.serialMCTL.get_string_tuple(),
        doc='Modem control')
    number_of_bytes_to_read = pvproperty(
        name='NRRD', dtype=ChannelType.LONG, doc='Number of bytes to read')
    output_xon_xoff = pvproperty(
        name='IXON',
        dtype=ChannelType.ENUM,
        enum_strings=menus.serialIX.get_string_tuple(),
        doc='Output XON/XOFF')
    parity = pvproperty(
        name='PRTY',
        dtype=ChannelType.ENUM,
        enum_strings=menus.serialPRTY.get_string_tuple(),
        doc='Parity')
    stop_bits = pvproperty(
        name='SBIT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.serialSBIT.get_string_tuple(),
        doc='Stop bits')
    timeout_sec = pvproperty(
        name='TMOT', dtype=ChannelType.DOUBLE, doc='Timeout (sec)')
    transaction_mode = pvproperty(
        name='TMOD',
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynTMOD.get_string_tuple(),
        doc='Transaction mode')
    xon_any_character = pvproperty(
        name='IXANY',
        dtype=ChannelType.ENUM,
        enum_strings=menus.serialIX.get_string_tuple(),
        doc='XON=any character')
    asyn_address = pvproperty(
        name='ADDR', dtype=ChannelType.LONG, doc='asyn address')
    asyn_port = pvproperty(
        name='PORT', dtype=ChannelType.CHAR, max_length=40, doc='asyn port')
    addressed_command = pvproperty(
        name='ACMD',
        dtype=ChannelType.ENUM,
        enum_strings=menus.gpibACMD.get_string_tuple(),
        doc='Addressed command')
    max_size_of_output_array = pvproperty(
        name='OMAX',
        dtype=ChannelType.LONG,
        doc='Max. size of output array',
        read_only=True)
    number_of_bytes_to_write = pvproperty(
        name='NOWT', dtype=ChannelType.LONG, doc='Number of bytes to write')
    output_command_string = pvproperty(
        name='AOUT',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Output (command) string')
    output_delimiter = pvproperty(
        name='OEOS',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Output delimiter')
    output_format = pvproperty(
        name='OFMT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynFMT.get_string_tuple(),
        doc='Output format')
    universal_command = pvproperty(
        name='UCMD',
        dtype=ChannelType.ENUM,
        enum_strings=menus.gpibUCMD.get_string_tuple(),
        doc='Universal command')
    asynfloat64_output = pvproperty(
        name='F64OUT', dtype=ChannelType.DOUBLE, doc='asynFloat64 output')
    asynint32_output = pvproperty(
        name='I32OUT', dtype=ChannelType.LONG, doc='asynInt32 output')
    asynuint32digital_mask = pvproperty(
        name='UI32MASK', dtype=ChannelType.LONG, doc='asynUInt32Digital mask')
    asynuint32digital_output = pvproperty(
        name='UI32OUT', dtype=ChannelType.LONG, doc='asynUInt32Digital output')


@register_record
class BiFields(RecordFieldGroup):
    _record_type = 'bi'
    # value = pvproperty(name='VAL', dtype=ChannelType.ENUM, doc='Current Value')
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    hardware_mask = pvproperty(
        name='MASK',
        dtype=ChannelType.LONG,
        doc='Hardware Mask',
        read_only=True)
    last_value_alarmed = pvproperty(
        name='LALM',
        dtype=ChannelType.LONG,
        doc='Last Value Alarmed',
        read_only=True)
    last_value_monitored = pvproperty(
        name='MLST',
        dtype=ChannelType.LONG,
        doc='Last Value Monitored',
        read_only=True)
    raw_value = pvproperty(
        name='RVAL', dtype=ChannelType.LONG, doc='Raw Value')
    simulation_mode = pvproperty(
        name='SIMM',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuSimm.get_string_tuple(),
        doc='Simulation Mode')
    simulation_value = pvproperty(
        name='SVAL', dtype=ChannelType.LONG, doc='Simulation Value')
    prev_raw_value = pvproperty(
        name='ORAW',
        dtype=ChannelType.LONG,
        doc='prev Raw Value',
        read_only=True)
    zero_error_severity = pvproperty(
        name='ZSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Zero Error Severity')
    one_error_severity = pvproperty(
        name='OSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='One Error Severity')
    change_of_state_svr = pvproperty(
        name='COSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Change of State Svr')
    zero_name = pvproperty(
        name='ZNAM', dtype=ChannelType.CHAR, max_length=26, doc='Zero Name')
    one_name = pvproperty(
        name='ONAM', dtype=ChannelType.CHAR, max_length=26, doc='One Name')
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


@register_record
class BoFields(RecordFieldGroup):
    _record_type = 'bo'
    # value = pvproperty(name='VAL', dtype=ChannelType.ENUM, doc='Current Value')
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    hardware_mask = pvproperty(
        name='MASK',
        dtype=ChannelType.LONG,
        doc='Hardware Mask',
        read_only=True)
    last_value_alarmed = pvproperty(
        name='LALM',
        dtype=ChannelType.LONG,
        doc='Last Value Alarmed',
        read_only=True)
    last_value_monitored = pvproperty(
        name='MLST',
        dtype=ChannelType.LONG,
        doc='Last Value Monitored',
        read_only=True)
    prev_readback_value = pvproperty(
        name='ORBV',
        dtype=ChannelType.LONG,
        doc='Prev Readback Value',
        read_only=True)
    raw_value = pvproperty(
        name='RVAL', dtype=ChannelType.LONG, doc='Raw Value')
    readback_value = pvproperty(
        name='RBV',
        dtype=ChannelType.LONG,
        doc='Readback Value',
        read_only=True)
    simulation_mode = pvproperty(
        name='SIMM',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuYesNo.get_string_tuple(),
        doc='Simulation Mode')
    prev_raw_value = pvproperty(
        name='ORAW',
        dtype=ChannelType.LONG,
        doc='prev Raw Value',
        read_only=True)
    change_of_state_sevr = pvproperty(
        name='COSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Change of State Sevr')
    one_error_severity = pvproperty(
        name='OSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='One Error Severity')
    zero_error_severity = pvproperty(
        name='ZSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Zero Error Severity')
    one_name = pvproperty(
        name='ONAM', dtype=ChannelType.CHAR, max_length=26, doc='One Name')
    zero_name = pvproperty(
        name='ZNAM', dtype=ChannelType.CHAR, max_length=26, doc='Zero Name')
    sim_mode_location = pvproperty(
        name='SIML', dtype=ChannelType.STRING, doc='Sim Mode Location')
    sim_output_specifctn = pvproperty(
        name='SIOL', dtype=ChannelType.STRING, doc='Sim Output Specifctn')
    sim_mode_alarm_svrty = pvproperty(
        name='SIMS',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Sim mode Alarm Svrty')
    desired_output_loc = pvproperty(
        name='DOL', dtype=ChannelType.STRING, doc='Desired Output Loc')
    invalid_outpt_action = pvproperty(
        name='IVOA',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuIvoa.get_string_tuple(),
        doc='INVALID outpt action')
    invalid_output_value = pvproperty(
        name='IVOV', dtype=ChannelType.LONG, doc='INVALID output value')
    output_mode_select = pvproperty(
        name='OMSL',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuOmsl.get_string_tuple(),
        doc='Output Mode Select')
    output_specification = pvproperty(
        name='OUT', dtype=ChannelType.STRING, doc='Output Specification')
    seconds_to_hold_high = pvproperty(
        name='HIGH', dtype=ChannelType.DOUBLE, doc='Seconds to Hold High')


@register_record
class BusyFields(RecordFieldGroup):
    _record_type = 'busy'
    # value = pvproperty(name='VAL', dtype=ChannelType.ENUM, doc='Current Value')
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    last_value_alarmed = pvproperty(
        name='LALM',
        dtype=ChannelType.LONG,
        doc='Last Value Alarmed',
        read_only=True)
    last_value_monitored = pvproperty(
        name='MLST',
        dtype=ChannelType.LONG,
        doc='Last Value Monitored',
        read_only=True)
    prev_readback_value = pvproperty(
        name='ORBV',
        dtype=ChannelType.LONG,
        doc='Prev Readback Value',
        read_only=True)
    raw_value = pvproperty(
        name='RVAL', dtype=ChannelType.LONG, doc='Raw Value')
    readback_value = pvproperty(
        name='RBV',
        dtype=ChannelType.LONG,
        doc='Readback Value',
        read_only=True)
    simulation_mode = pvproperty(
        name='SIMM',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuYesNo.get_string_tuple(),
        doc='Simulation Mode')
    prev_raw_value = pvproperty(
        name='ORAW',
        dtype=ChannelType.LONG,
        doc='prev Raw Value',
        read_only=True)
    prev_value = pvproperty(
        name='OVAL', dtype=ChannelType.LONG, doc='prev Value', read_only=True)
    change_of_state_sevr = pvproperty(
        name='COSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Change of State Sevr')
    one_error_severity = pvproperty(
        name='OSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='One Error Severity')
    zero_error_severity = pvproperty(
        name='ZSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Zero Error Severity')
    one_name = pvproperty(
        name='ONAM', dtype=ChannelType.CHAR, max_length=26, doc='One Name')
    zero_name = pvproperty(
        name='ZNAM', dtype=ChannelType.CHAR, max_length=26, doc='Zero Name')
    sim_mode_location = pvproperty(
        name='SIML', dtype=ChannelType.STRING, doc='Sim Mode Location')
    sim_output_specifctn = pvproperty(
        name='SIOL', dtype=ChannelType.STRING, doc='Sim Output Specifctn')
    sim_mode_alarm_svrty = pvproperty(
        name='SIMS',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Sim mode Alarm Svrty')
    desired_output_loc = pvproperty(
        name='DOL', dtype=ChannelType.STRING, doc='Desired Output Loc')
    hardware_mask = pvproperty(
        name='MASK',
        dtype=ChannelType.LONG,
        doc='Hardware Mask',
        read_only=True)
    invalid_outpt_action = pvproperty(
        name='IVOA',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuIvoa.get_string_tuple(),
        doc='INVALID outpt action')
    invalid_output_value = pvproperty(
        name='IVOV', dtype=ChannelType.LONG, doc='INVALID output value')
    output_mode_select = pvproperty(
        name='OMSL',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuOmsl.get_string_tuple(),
        doc='Output Mode Select')
    output_specification = pvproperty(
        name='OUT', dtype=ChannelType.STRING, doc='Output Specification')
    seconds_to_hold_high = pvproperty(
        name='HIGH', dtype=ChannelType.DOUBLE, doc='Seconds to Hold High')


@register_record
class CalcFields(RecordFieldGroup, _Limits):
    _record_type = 'calc'
    # value = pvproperty(name='VAL', dtype=ChannelType.DOUBLE, doc='Result')
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
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
    alarm_deadband = pvproperty(
        name='HYST', dtype=ChannelType.DOUBLE, doc='Alarm Deadband')
    calculation = pvproperty(
        name='CALC', dtype=ChannelType.CHAR, max_length=80, doc='Calculation')
    archive_deadband = pvproperty(
        name='ADEL', dtype=ChannelType.DOUBLE, doc='Archive Deadband')
    display_precision = pvproperty(
        name='PREC', dtype=ChannelType.LONG, doc='Display Precision')
    monitor_deadband = pvproperty(
        name='MDEL', dtype=ChannelType.DOUBLE, doc='Monitor Deadband')
    units_name = pvproperty(
        name='EGU', dtype=ChannelType.CHAR, max_length=16, doc='Units Name')
    _link_parent_attribute(display_precision, 'precision')
    _link_parent_attribute(archive_deadband, 'log_atol')
    _link_parent_attribute(monitor_deadband, 'value_atol')


@register_record
class CalcoutFields(RecordFieldGroup, _Limits):
    _record_type = 'calcout'
    # value = pvproperty(name='VAL', dtype=ChannelType.DOUBLE, doc='Result')
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    calc_valid = pvproperty(
        name='CLCV', dtype=ChannelType.LONG, doc='CALC Valid')
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
    ocal_valid = pvproperty(
        name='OCLV', dtype=ChannelType.LONG, doc='OCAL Valid')
    out_pv_status = pvproperty(
        name='OUTV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.calcoutINAV.get_string_tuple(),
        doc='OUT PV Status',
        read_only=True)
    output_delay_active = pvproperty(
        name='DLYA',
        dtype=ChannelType.LONG,
        doc='Output Delay Active',
        read_only=True)
    output_value = pvproperty(
        name='OVAL', dtype=ChannelType.DOUBLE, doc='Output Value')
    prev_value_of_oval = pvproperty(
        name='POVL', dtype=ChannelType.DOUBLE, doc='Prev Value of OVAL')
    previous_value = pvproperty(
        name='PVAL', dtype=ChannelType.DOUBLE, doc='Previous Value')
    alarm_deadband = pvproperty(
        name='HYST', dtype=ChannelType.DOUBLE, doc='Alarm Deadband')
    output_execute_delay = pvproperty(
        name='ODLY', dtype=ChannelType.DOUBLE, doc='Output Execute Delay')
    calculation = pvproperty(
        name='CALC', dtype=ChannelType.CHAR, max_length=80, doc='Calculation')
    output_calculation = pvproperty(
        name='OCAL',
        dtype=ChannelType.CHAR,
        max_length=80,
        doc='Output Calculation')
    output_data_opt = pvproperty(
        name='DOPT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.calcoutDOPT.get_string_tuple(),
        doc='Output Data Opt')
    output_execute_opt = pvproperty(
        name='OOPT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.calcoutOOPT.get_string_tuple(),
        doc='Output Execute Opt')
    event_to_issue = pvproperty(
        name='OEVT', dtype=ChannelType.LONG, doc='Event To Issue')
    archive_deadband = pvproperty(
        name='ADEL', dtype=ChannelType.DOUBLE, doc='Archive Deadband')
    display_precision = pvproperty(
        name='PREC', dtype=ChannelType.LONG, doc='Display Precision')
    monitor_deadband = pvproperty(
        name='MDEL', dtype=ChannelType.DOUBLE, doc='Monitor Deadband')
    units_name = pvproperty(
        name='EGU', dtype=ChannelType.CHAR, max_length=16, doc='Units Name')
    invalid_output_action = pvproperty(
        name='IVOA',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuIvoa.get_string_tuple(),
        doc='INVALID output action')
    invalid_output_value = pvproperty(
        name='IVOV', dtype=ChannelType.DOUBLE, doc='INVALID output value')
    output_specification = pvproperty(
        name='OUT', dtype=ChannelType.STRING, doc='Output Specification')
    _link_parent_attribute(display_precision, 'precision')
    _link_parent_attribute(archive_deadband, 'log_atol')
    _link_parent_attribute(monitor_deadband, 'value_atol')


@register_record
class CompressFields(RecordFieldGroup):
    _record_type = 'compress'
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    compress_value_buffer = pvproperty(
        name='CVB',
        dtype=ChannelType.DOUBLE,
        doc='Compress Value Buffer',
        read_only=True)
    compressed_array_inx = pvproperty(
        name='INX',
        dtype=ChannelType.LONG,
        doc='Compressed Array Inx',
        read_only=True)
    number_used = pvproperty(
        name='NUSE', dtype=ChannelType.LONG, doc='Number Used', read_only=True)
    number_of_elements_in_working_buffer = pvproperty(
        name='INPN',
        dtype=ChannelType.LONG,
        doc='Number of elements in Working Buffer',
        read_only=True)
    old_number_used = pvproperty(
        name='OUSE',
        dtype=ChannelType.LONG,
        doc='Old Number Used',
        read_only=True)
    reset = pvproperty(name='RES', dtype=ChannelType.LONG, doc='Reset')
    compression_algorithm = pvproperty(
        name='ALG',
        dtype=ChannelType.ENUM,
        enum_strings=menus.compressALG.get_string_tuple(),
        doc='Compression Algorithm')
    init_high_interest_lim = pvproperty(
        name='IHIL', dtype=ChannelType.DOUBLE, doc='Init High Interest Lim')
    init_low_interest_lim = pvproperty(
        name='ILIL', dtype=ChannelType.DOUBLE, doc='Init Low Interest Lim')
    input_specification = pvproperty(
        name='INP', dtype=ChannelType.STRING, doc='Input Specification')
    n_to_1_compression = pvproperty(
        name='N', dtype=ChannelType.LONG, doc='N to 1 Compression')
    number_of_values = pvproperty(
        name='NSAM',
        dtype=ChannelType.LONG,
        doc='Number of Values',
        read_only=True)
    display_precision = pvproperty(
        name='PREC', dtype=ChannelType.LONG, doc='Display Precision')
    engineeringunits = pvproperty(
        name='EGU',
        dtype=ChannelType.CHAR,
        max_length=16,
        doc='EngineeringUnits')
    high_operating_range = pvproperty(
        name='HOPR', dtype=ChannelType.DOUBLE, doc='High Operating Range')
    low_operating_range = pvproperty(
        name='LOPR', dtype=ChannelType.DOUBLE, doc='Low Operating Range')
    _link_parent_attribute(display_precision, 'precision')
    _link_parent_attribute(high_operating_range, 'upper_ctrl_limit')
    _link_parent_attribute(low_operating_range, 'lower_ctrl_limit')


@register_record
class DfanoutFields(RecordFieldGroup, _Limits):
    _record_type = 'dfanout'
    # value = pvproperty(
    #     name='VAL', dtype=ChannelType.DOUBLE, doc='Desired Output')
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
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
    link_selection = pvproperty(
        name='SELN', dtype=ChannelType.LONG, doc='Link Selection')
    alarm_deadband = pvproperty(
        name='HYST', dtype=ChannelType.DOUBLE, doc='Alarm Deadband')
    archive_deadband = pvproperty(
        name='ADEL', dtype=ChannelType.DOUBLE, doc='Archive Deadband')
    display_precision = pvproperty(
        name='PREC', dtype=ChannelType.LONG, doc='Display Precision')
    monitor_deadband = pvproperty(
        name='MDEL', dtype=ChannelType.DOUBLE, doc='Monitor Deadband')
    units_name = pvproperty(
        name='EGU', dtype=ChannelType.CHAR, max_length=16, doc='Units name')
    desired_output_loc = pvproperty(
        name='DOL', dtype=ChannelType.STRING, doc='Desired Output Loc')
    link_selection_loc = pvproperty(
        name='SELL', dtype=ChannelType.STRING, doc='Link Selection Loc')
    select_mechanism = pvproperty(
        name='SELM',
        dtype=ChannelType.ENUM,
        enum_strings=menus.dfanoutSELM.get_string_tuple(),
        doc='Select Mechanism')
    output_mode_select = pvproperty(
        name='OMSL',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuOmsl.get_string_tuple(),
        doc='Output Mode Select')
    output_spec_a = pvproperty(
        name='OUTA', dtype=ChannelType.STRING, doc='Output Spec A')
    output_spec_b = pvproperty(
        name='OUTB', dtype=ChannelType.STRING, doc='Output Spec B')
    output_spec_c = pvproperty(
        name='OUTC', dtype=ChannelType.STRING, doc='Output Spec C')
    output_spec_d = pvproperty(
        name='OUTD', dtype=ChannelType.STRING, doc='Output Spec D')
    output_spec_e = pvproperty(
        name='OUTE', dtype=ChannelType.STRING, doc='Output Spec E')
    output_spec_f = pvproperty(
        name='OUTF', dtype=ChannelType.STRING, doc='Output Spec F')
    output_spec_g = pvproperty(
        name='OUTG', dtype=ChannelType.STRING, doc='Output Spec G')
    output_spec_h = pvproperty(
        name='OUTH', dtype=ChannelType.STRING, doc='Output Spec H')
    _link_parent_attribute(display_precision, 'precision')
    _link_parent_attribute(archive_deadband, 'log_atol')
    _link_parent_attribute(monitor_deadband, 'value_atol')


@register_record
class DigitelFields(RecordFieldGroup):
    _record_type = 'digitel'
    # value = pvproperty(
    #     name='VAL', dtype=ChannelType.DOUBLE, doc='Pressure', read_only=True)
    acc_current = pvproperty(
        name='ACCI',
        dtype=ChannelType.DOUBLE,
        doc='Acc Current',
        read_only=True)
    acc_power = pvproperty(
        name='ACCW', dtype=ChannelType.DOUBLE, doc='Acc Power', read_only=True)
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    bake_installed = pvproperty(
        name='BKIN',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelBKIN.get_string_tuple(),
        doc='Bake Installed',
        read_only=True)
    bake_readback = pvproperty(
        name='BAKR',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelBAKS.get_string_tuple(),
        doc='Bake Readback',
        read_only=True)
    bake_time_mode_read = pvproperty(
        name='S3BR',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelS3BS.get_string_tuple(),
        doc='Bake Time Mode Read',
        read_only=True)
    bake_time_read = pvproperty(
        name='S3TR',
        dtype=ChannelType.DOUBLE,
        doc='Bake Time Read',
        read_only=True)
    bake_time_set = pvproperty(
        name='S3TS', dtype=ChannelType.DOUBLE, doc='Bake Time Set')
    cooldown_mode = pvproperty(
        name='CMOR',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelCMOR.get_string_tuple(),
        doc='Cooldown Mode',
        read_only=True)
    cooldown_time = pvproperty(
        name='COOL',
        dtype=ChannelType.DOUBLE,
        doc='Cooldown Time',
        read_only=True)
    current = pvproperty(
        name='CRNT', dtype=ChannelType.DOUBLE, doc='Current', read_only=True)
    cycle_count = pvproperty(
        name='CYCL', dtype=ChannelType.LONG, doc='Cycle count', read_only=True)
    error_count = pvproperty(
        name='ERR', dtype=ChannelType.LONG, doc='Error Count', read_only=True)
    last_value_alarmed = pvproperty(
        name='LALM',
        dtype=ChannelType.DOUBLE,
        doc='Last Value Alarmed',
        read_only=True)
    mod_flags = pvproperty(
        name='FLGS', dtype=ChannelType.LONG, doc='Mod Flags', read_only=True)
    mode_readback = pvproperty(
        name='MODR',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelMODR.get_string_tuple(),
        doc='Mode Readback',
        read_only=True)
    pressure_log10_form = pvproperty(
        name='LVAL',
        dtype=ChannelType.DOUBLE,
        doc='Pressure (log10 form)',
        read_only=True)
    pump_type = pvproperty(
        name='PTYP',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelPTYP.get_string_tuple(),
        doc='Pump Type',
        read_only=True)
    sp1_hvi_readback = pvproperty(
        name='S1VR',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelS1VS.get_string_tuple(),
        doc='SP1 HVI Readback',
        read_only=True)
    sp1_hy_readback = pvproperty(
        name='S1HR',
        dtype=ChannelType.DOUBLE,
        doc='SP1 HY Readback',
        read_only=True)
    sp1_hysteresis = pvproperty(
        name='S1HS', dtype=ChannelType.DOUBLE, doc='SP1 Hysteresis')
    sp1_mode_readback = pvproperty(
        name='S1MR',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelS1MS.get_string_tuple(),
        doc='SP1 Mode Readback',
        read_only=True)
    sp1_sp_readback = pvproperty(
        name='SP1R',
        dtype=ChannelType.DOUBLE,
        doc='SP1 SP Readback',
        read_only=True)
    sp1_setpoint = pvproperty(
        name='SP1S', dtype=ChannelType.DOUBLE, doc='SP1 Setpoint')
    sp2_hvi_readback = pvproperty(
        name='S2VR',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelS1VS.get_string_tuple(),
        doc='SP2 HVI Readback',
        read_only=True)
    sp2_hy_readback = pvproperty(
        name='S2HR',
        dtype=ChannelType.DOUBLE,
        doc='SP2 HY Readback',
        read_only=True)
    sp2_hysteresis = pvproperty(
        name='S2HS', dtype=ChannelType.DOUBLE, doc='SP2 Hysteresis')
    sp2_mode_readback = pvproperty(
        name='S2MR',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelS1MS.get_string_tuple(),
        doc='SP2 Mode Readback',
        read_only=True)
    sp2_sp_readback = pvproperty(
        name='SP2R',
        dtype=ChannelType.DOUBLE,
        doc='SP2 SP Readback',
        read_only=True)
    sp2_setpoint = pvproperty(
        name='SP2S', dtype=ChannelType.DOUBLE, doc='SP2 Setpoint')
    sp3_hvi_readback = pvproperty(
        name='S3VR',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelS1VS.get_string_tuple(),
        doc='SP3 HVI Readback',
        read_only=True)
    sp3_hy_readback = pvproperty(
        name='S3HR',
        dtype=ChannelType.DOUBLE,
        doc='SP3 HY Readback',
        read_only=True)
    sp3_hysteresis = pvproperty(
        name='S3HS', dtype=ChannelType.DOUBLE, doc='SP3 Hysteresis')
    sp3_mode_readback = pvproperty(
        name='S3MR',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelS1MS.get_string_tuple(),
        doc='SP3 Mode Readback',
        read_only=True)
    sp3_sp_readback = pvproperty(
        name='SP3R',
        dtype=ChannelType.DOUBLE,
        doc='SP3 SP Readback',
        read_only=True)
    sp3_setpoint = pvproperty(
        name='SP3S', dtype=ChannelType.DOUBLE, doc='SP3 Setpoint')
    setpoint_1 = pvproperty(
        name='SET1',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelSET1.get_string_tuple(),
        doc='Setpoint 1',
        read_only=True)
    setpoint_2 = pvproperty(
        name='SET2',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelSET1.get_string_tuple(),
        doc='Setpoint 2',
        read_only=True)
    setpoint_3 = pvproperty(
        name='SET3',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelSET1.get_string_tuple(),
        doc='Setpoint 3',
        read_only=True)
    setpoint_flags = pvproperty(
        name='SPFG',
        dtype=ChannelType.LONG,
        doc='Setpoint Flags',
        read_only=True)
    sim_mode_value = pvproperty(
        name='SIMM',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuYesNo.get_string_tuple(),
        doc='Sim Mode Value')
    sim_value_current = pvproperty(
        name='SVCR', dtype=ChannelType.DOUBLE, doc='Sim Value Current')
    sim_value_mode = pvproperty(
        name='SVMO',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelMODS.get_string_tuple(),
        doc='Sim Value Mode')
    sim_value_sp1 = pvproperty(
        name='SVS1',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelSET1.get_string_tuple(),
        doc='Sim Value SP1')
    sim_value_sp2 = pvproperty(
        name='SVS2',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelSET1.get_string_tuple(),
        doc='Sim Value SP2')
    time_online = pvproperty(
        name='TONL', dtype=ChannelType.LONG, doc='Time Online', read_only=True)
    voltage = pvproperty(
        name='VOLT', dtype=ChannelType.DOUBLE, doc='Voltage', read_only=True)
    init_acc_current = pvproperty(
        name='IACI',
        dtype=ChannelType.DOUBLE,
        doc='init Acc current',
        read_only=True)
    init_acc_power = pvproperty(
        name='IACW',
        dtype=ChannelType.DOUBLE,
        doc='init Acc power',
        read_only=True)
    init_bake_installed = pvproperty(
        name='IBKN',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelBKIN.get_string_tuple(),
        doc='init Bake Installed',
        read_only=True)
    init_error_count = pvproperty(
        name='IERR',
        dtype=ChannelType.LONG,
        doc='init Error Count',
        read_only=True)
    init_bake = pvproperty(
        name='IBAK',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelBAKS.get_string_tuple(),
        doc='init bake',
        read_only=True)
    init_cooldown_time = pvproperty(
        name='ICOL',
        dtype=ChannelType.DOUBLE,
        doc='init cooldown time',
        read_only=True)
    init_current = pvproperty(
        name='ICRN',
        dtype=ChannelType.DOUBLE,
        doc='init current',
        read_only=True)
    init_mode = pvproperty(
        name='IMOD',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelMODS.get_string_tuple(),
        doc='init mode',
        read_only=True)
    init_pressure = pvproperty(
        name='IVAL',
        dtype=ChannelType.DOUBLE,
        doc='init pressure',
        read_only=True)
    init_pressure_log10 = pvproperty(
        name='ILVA',
        dtype=ChannelType.DOUBLE,
        doc='init pressure (log10)',
        read_only=True)
    init_pump_type = pvproperty(
        name='IPTY',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelPTYP.get_string_tuple(),
        doc='init pump type',
        read_only=True)
    init_set1 = pvproperty(
        name='ISP1',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelSET1.get_string_tuple(),
        doc='init set1',
        read_only=True)
    init_set2 = pvproperty(
        name='ISP2',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelSET1.get_string_tuple(),
        doc='init set2',
        read_only=True)
    init_set3 = pvproperty(
        name='ISP3',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelSET1.get_string_tuple(),
        doc='init set3',
        read_only=True)
    init_sp1 = pvproperty(
        name='IS1', dtype=ChannelType.DOUBLE, doc='init sp1', read_only=True)
    init_sp1_hvi = pvproperty(
        name='II1',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelS1VS.get_string_tuple(),
        doc='init sp1 HVI',
        read_only=True)
    init_sp1_hy = pvproperty(
        name='IH1',
        dtype=ChannelType.DOUBLE,
        doc='init sp1 HY',
        read_only=True)
    init_sp1_mode = pvproperty(
        name='IM1',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelS1MS.get_string_tuple(),
        doc='init sp1 mode',
        read_only=True)
    init_sp2 = pvproperty(
        name='IS2', dtype=ChannelType.DOUBLE, doc='init sp2', read_only=True)
    init_sp2_hvi = pvproperty(
        name='II2',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelS1VS.get_string_tuple(),
        doc='init sp2 HVI',
        read_only=True)
    init_sp2_hy = pvproperty(
        name='IH2',
        dtype=ChannelType.DOUBLE,
        doc='init sp2 HY',
        read_only=True)
    init_sp2_mode = pvproperty(
        name='IM2',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelS1MS.get_string_tuple(),
        doc='init sp2 mode',
        read_only=True)
    init_sp3 = pvproperty(
        name='IS3', dtype=ChannelType.DOUBLE, doc='init sp3', read_only=True)
    init_sp3_hvi = pvproperty(
        name='II3',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelS1VS.get_string_tuple(),
        doc='init sp3 HVI',
        read_only=True)
    init_sp3_hy = pvproperty(
        name='IH3',
        dtype=ChannelType.DOUBLE,
        doc='init sp3 HY',
        read_only=True)
    init_sp3_bake_time = pvproperty(
        name='IT3',
        dtype=ChannelType.DOUBLE,
        doc='init sp3 bake time',
        read_only=True)
    init_sp3_bake_time_md = pvproperty(
        name='IB3',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelS3BS.get_string_tuple(),
        doc='init sp3 bake time md',
        read_only=True)
    init_sp3_mode = pvproperty(
        name='IM3',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelS1MS.get_string_tuple(),
        doc='init sp3 mode',
        read_only=True)
    init_tonl = pvproperty(
        name='ITON', dtype=ChannelType.LONG, doc='init tonl', read_only=True)
    init_voltage = pvproperty(
        name='IVOL',
        dtype=ChannelType.DOUBLE,
        doc='init voltage',
        read_only=True)
    alarm_deadband = pvproperty(
        name='HYST', dtype=ChannelType.DOUBLE, doc='Alarm Deadband')
    display_mode = pvproperty(
        name='DSPL',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelDSPL.get_string_tuple(),
        doc='Display Mode')
    pressure_high_alarm = pvproperty(
        name='HIGH', dtype=ChannelType.DOUBLE, doc='Pressure High Alarm')
    pressure_high_severity = pvproperty(
        name='HSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Pressure High Severity')
    pressure_hihi_alarm = pvproperty(
        name='HIHI', dtype=ChannelType.DOUBLE, doc='Pressure Hihi Alarm')
    pressure_hihi_severity = pvproperty(
        name='HHSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Pressure Hihi Severity')
    pressure_lolo_alarm = pvproperty(
        name='LOLO', dtype=ChannelType.DOUBLE, doc='Pressure Lolo Alarm')
    pressure_lolo_severity = pvproperty(
        name='LLSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Pressure Lolo Severity')
    pressure_low_alarm = pvproperty(
        name='LOW', dtype=ChannelType.DOUBLE, doc='Pressure Low Alarm')
    pressure_low_severity = pvproperty(
        name='LSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Pressure Low Severity')
    keyboard_lock = pvproperty(
        name='KLCK',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelKLCK.get_string_tuple(),
        doc='Keyboard Lock')
    bake = pvproperty(
        name='BAKS',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelBAKS.get_string_tuple(),
        doc='Bake')
    controller_type = pvproperty(
        name='TYPE',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelTYPE.get_string_tuple(),
        doc='Controller Type')
    mode = pvproperty(
        name='MODS',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelMODS.get_string_tuple(),
        doc='Mode')
    device_specification = pvproperty(
        name='INP',
        dtype=ChannelType.STRING,
        doc='Device Specification',
        read_only=True)
    log_pres_display_hi = pvproperty(
        name='HLPR', dtype=ChannelType.DOUBLE, doc='Log Pres Display Hi')
    log_pres_display_lo = pvproperty(
        name='LLPR', dtype=ChannelType.DOUBLE, doc='Log Pres Display Lo')
    sim_location_current = pvproperty(
        name='SLCR',
        dtype=ChannelType.STRING,
        doc='Sim Location Current',
        read_only=True)
    sim_location_mode = pvproperty(
        name='SLMO',
        dtype=ChannelType.STRING,
        doc='Sim Location Mode',
        read_only=True)
    sim_location_sp1 = pvproperty(
        name='SLS1',
        dtype=ChannelType.STRING,
        doc='Sim Location SP1',
        read_only=True)
    sim_location_sp2 = pvproperty(
        name='SLS2',
        dtype=ChannelType.STRING,
        doc='Sim Location SP2',
        read_only=True)
    sim_mode_location = pvproperty(
        name='SIML',
        dtype=ChannelType.STRING,
        doc='Sim Mode Location',
        read_only=True)
    sp1_mode = pvproperty(
        name='S1MS',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelS1MS.get_string_tuple(),
        doc='SP1 Mode')
    sp1_hv_interlock = pvproperty(
        name='S1VS',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelS1VS.get_string_tuple(),
        doc='SP1 HV Interlock')
    sp2_mode = pvproperty(
        name='S2MS',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelS1MS.get_string_tuple(),
        doc='SP2 Mode')
    sp3_mode = pvproperty(
        name='S3MS',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelS1MS.get_string_tuple(),
        doc='SP3 Mode')
    sp2_hv_interlock = pvproperty(
        name='S2VS',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelS1VS.get_string_tuple(),
        doc='SP2 HV Interlock')
    sp3_hv_interlock = pvproperty(
        name='S3VS',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelS1VS.get_string_tuple(),
        doc='SP3 HV Interlock')
    bake_time_mode_set = pvproperty(
        name='S3BS',
        dtype=ChannelType.ENUM,
        enum_strings=menus.digitelS3BS.get_string_tuple(),
        doc='Bake Time Mode Set')
    voltage_display_lo = pvproperty(
        name='LVTR', dtype=ChannelType.DOUBLE, doc='Voltage Display Lo')
    pressure_display_hi = pvproperty(
        name='HOPR', dtype=ChannelType.DOUBLE, doc='Pressure Display Hi')
    pressure_display_lo = pvproperty(
        name='LOPR', dtype=ChannelType.DOUBLE, doc='Pressure Display Lo')
    current_display_hi = pvproperty(
        name='HCTR', dtype=ChannelType.DOUBLE, doc='Current Display Hi')
    current_display_lo = pvproperty(
        name='LCTR', dtype=ChannelType.DOUBLE, doc='Current Display Lo')
    voltage_display_hi = pvproperty(
        name='HVTR', dtype=ChannelType.DOUBLE, doc='Voltage Display Hi')


@register_record
class EpidFields(RecordFieldGroup):
    _record_type = 'epid'
    # value = pvproperty(name='VAL', dtype=ChannelType.DOUBLE, doc='Setpoint')
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    controlled_value = pvproperty(
        name='CVAL',
        dtype=ChannelType.DOUBLE,
        doc='Controlled Value',
        read_only=True)
    d_component = pvproperty(
        name='D', dtype=ChannelType.DOUBLE, doc='D component', read_only=True)
    delta_t = pvproperty(name='DT', dtype=ChannelType.DOUBLE, doc='Delta T')
    error = pvproperty(
        name='ERR', dtype=ChannelType.DOUBLE, doc='Error', read_only=True)
    i_component = pvproperty(
        name='I', dtype=ChannelType.DOUBLE, doc='I component')
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
    last_value_monitored = pvproperty(
        name='MLST',
        dtype=ChannelType.DOUBLE,
        doc='Last Value Monitored',
        read_only=True)
    output_value = pvproperty(
        name='OVAL',
        dtype=ChannelType.DOUBLE,
        doc='Output value',
        read_only=True)
    p_component = pvproperty(
        name='P', dtype=ChannelType.DOUBLE, doc='P component', read_only=True)
    prev_output = pvproperty(
        name='OVLP',
        dtype=ChannelType.DOUBLE,
        doc='Prev output',
        read_only=True)
    prev_controlled_value = pvproperty(
        name='CVLP',
        dtype=ChannelType.DOUBLE,
        doc='Prev. Controlled Value',
        read_only=True)
    prev_d_component = pvproperty(
        name='DP',
        dtype=ChannelType.DOUBLE,
        doc='Prev. D component',
        read_only=True)
    prev_delta_t = pvproperty(
        name='DTP', dtype=ChannelType.DOUBLE, doc='Prev. Delta T')
    prev_error = pvproperty(
        name='ERRP',
        dtype=ChannelType.DOUBLE,
        doc='Prev. Error',
        read_only=True)
    prev_i_component = pvproperty(
        name='IP', dtype=ChannelType.DOUBLE, doc='Prev. I component')
    prev_p_component = pvproperty(
        name='PP',
        dtype=ChannelType.DOUBLE,
        doc='Prev. P component',
        read_only=True)
    alarm_deadband = pvproperty(
        name='HYST', dtype=ChannelType.DOUBLE, doc='Alarm Deadband')
    high_deviation_limit = pvproperty(
        name='HIGH', dtype=ChannelType.DOUBLE, doc='High Deviation Limit')
    high_severity = pvproperty(
        name='HSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='High Severity')
    hihi_deviation_limit = pvproperty(
        name='HIHI', dtype=ChannelType.DOUBLE, doc='Hihi Deviation Limit')
    hihi_severity = pvproperty(
        name='HHSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Hihi Severity')
    lolo_deviation_limit = pvproperty(
        name='LOLO', dtype=ChannelType.DOUBLE, doc='Lolo Deviation Limit')
    lolo_severity = pvproperty(
        name='LLSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Lolo Severity')
    low_deviation_limit = pvproperty(
        name='LOW', dtype=ChannelType.DOUBLE, doc='Low Deviation Limit')
    low_severity = pvproperty(
        name='LSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Low Severity')
    archive_deadband = pvproperty(
        name='ADEL', dtype=ChannelType.DOUBLE, doc='Archive Deadband')
    display_precision = pvproperty(
        name='PREC', dtype=ChannelType.LONG, doc='Display Precision')
    engineering_units = pvproperty(
        name='EGU',
        dtype=ChannelType.CHAR,
        max_length=16,
        doc='Engineering Units')
    high_drive_limit = pvproperty(
        name='DRVH', dtype=ChannelType.DOUBLE, doc='High Drive Limit')
    high_operating_range = pvproperty(
        name='HOPR', dtype=ChannelType.DOUBLE, doc='High Operating Range')
    low_drive_limit = pvproperty(
        name='DRVL', dtype=ChannelType.DOUBLE, doc='Low Drive Limit')
    low_operating_range = pvproperty(
        name='LOPR', dtype=ChannelType.DOUBLE, doc='Low Operating Range')
    monitor_deadband = pvproperty(
        name='MDEL', dtype=ChannelType.DOUBLE, doc='Monitor Deadband')
    controlled_value_loc = pvproperty(
        name='INP', dtype=ChannelType.STRING, doc='Controlled Value Loc')
    derivative_gain = pvproperty(
        name='KD', dtype=ChannelType.DOUBLE, doc='Derivative Gain')
    feedback_mode = pvproperty(
        name='FMOD',
        dtype=ChannelType.ENUM,
        enum_strings=menus.epidFeedbackMode.get_string_tuple(),
        doc='Feedback Mode')
    feedback_on_off = pvproperty(
        name='FBON',
        dtype=ChannelType.ENUM,
        enum_strings=menus.epidFeedbackState.get_string_tuple(),
        doc='Feedback On/Off')
    intergral_gain = pvproperty(
        name='KI', dtype=ChannelType.DOUBLE, doc='Intergral Gain')
    min_delta_t = pvproperty(
        name='MDT', dtype=ChannelType.DOUBLE, doc='Min Delta T')
    output_deadband = pvproperty(
        name='ODEL', dtype=ChannelType.DOUBLE, doc='Output Deadband')
    output_location = pvproperty(
        name='OUTL', dtype=ChannelType.STRING, doc='Output Location')
    prev_feedback_on_off = pvproperty(
        name='FBOP',
        dtype=ChannelType.ENUM,
        enum_strings=menus.epidFeedbackState.get_string_tuple(),
        doc='Prev. feedback On/Off')
    proportional_gain = pvproperty(
        name='KP', dtype=ChannelType.DOUBLE, doc='Proportional Gain')
    readback_trigger = pvproperty(
        name='TRIG', dtype=ChannelType.STRING, doc='Readback Trigger')
    setpoint_location = pvproperty(
        name='STPL', dtype=ChannelType.STRING, doc='Setpoint Location')
    setpoint_mode_select = pvproperty(
        name='SMSL',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuOmsl.get_string_tuple(),
        doc='Setpoint Mode Select')
    trigger_value = pvproperty(
        name='TVAL', dtype=ChannelType.DOUBLE, doc='Trigger Value')
    _link_parent_attribute(display_precision, 'precision')
    _link_parent_attribute(high_operating_range, 'upper_ctrl_limit')
    _link_parent_attribute(low_operating_range, 'lower_ctrl_limit')
    _link_parent_attribute(archive_deadband, 'log_atol')
    _link_parent_attribute(monitor_deadband, 'value_atol')


@register_record
class EventFields(RecordFieldGroup):
    _record_type = 'event'
    # value = pvproperty(
    #     name='VAL', dtype=ChannelType.LONG, doc='Event Number To Post')
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    simulation_mode = pvproperty(
        name='SIMM',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuYesNo.get_string_tuple(),
        doc='Simulation Mode')
    simulation_value = pvproperty(
        name='SVAL', dtype=ChannelType.LONG, doc='Simulation Value')
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


@register_record
class FanoutFields(RecordFieldGroup):
    _record_type = 'fanout'
    # value = pvproperty(
    #     name='VAL', dtype=ChannelType.LONG, doc='Used to trigger')
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    link_selection = pvproperty(
        name='SELN', dtype=ChannelType.LONG, doc='Link Selection')
    forward_link_1 = pvproperty(
        name='LNK1', dtype=ChannelType.STRING, doc='Forward Link 1')
    forward_link_2 = pvproperty(
        name='LNK2', dtype=ChannelType.STRING, doc='Forward Link 2')
    forward_link_3 = pvproperty(
        name='LNK3', dtype=ChannelType.STRING, doc='Forward Link 3')
    forward_link_4 = pvproperty(
        name='LNK4', dtype=ChannelType.STRING, doc='Forward Link 4')
    forward_link_5 = pvproperty(
        name='LNK5', dtype=ChannelType.STRING, doc='Forward Link 5')
    forward_link_6 = pvproperty(
        name='LNK6', dtype=ChannelType.STRING, doc='Forward Link 6')
    link_selection_loc = pvproperty(
        name='SELL', dtype=ChannelType.STRING, doc='Link Selection Loc')
    select_mechanism = pvproperty(
        name='SELM',
        dtype=ChannelType.ENUM,
        enum_strings=menus.fanoutSELM.get_string_tuple(),
        doc='Select Mechanism')


@register_record
class GensubFields(RecordFieldGroup):
    _record_type = 'genSub'
    # value = pvproperty(
    #     name='VAL', dtype=ChannelType.LONG, doc='Subr. return value')
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    old_subr_address = pvproperty(
        name='OSAD',
        dtype=ChannelType.LONG,
        doc='Old Subr. Address',
        read_only=True)
    old_return_value = pvproperty(
        name='OVAL',
        dtype=ChannelType.LONG,
        doc='Old return value',
        read_only=True)
    subroutine_address = pvproperty(
        name='SADR',
        dtype=ChannelType.LONG,
        doc='Subroutine Address',
        read_only=True)
    display_precision = pvproperty(
        name='PREC', dtype=ChannelType.LONG, doc='Display Precision')
    version_number = pvproperty(
        name='VERS',
        dtype=ChannelType.DOUBLE,
        doc='Version Number',
        read_only=True)
    input_link_a = pvproperty(
        name='INPA',
        dtype=ChannelType.STRING,
        doc='Input Link A',
        read_only=True)
    input_link_b = pvproperty(
        name='INPB',
        dtype=ChannelType.STRING,
        doc='Input Link B',
        read_only=True)
    input_link_c = pvproperty(
        name='INPC',
        dtype=ChannelType.STRING,
        doc='Input Link C',
        read_only=True)
    input_link_d = pvproperty(
        name='INPD',
        dtype=ChannelType.STRING,
        doc='Input Link D',
        read_only=True)
    input_link_e = pvproperty(
        name='INPE',
        dtype=ChannelType.STRING,
        doc='Input Link E',
        read_only=True)
    input_link_f = pvproperty(
        name='INPF',
        dtype=ChannelType.STRING,
        doc='Input Link F',
        read_only=True)
    input_link_g = pvproperty(
        name='INPG',
        dtype=ChannelType.STRING,
        doc='Input Link G',
        read_only=True)
    input_link_h = pvproperty(
        name='INPH',
        dtype=ChannelType.STRING,
        doc='Input Link H',
        read_only=True)
    input_link_i = pvproperty(
        name='INPI',
        dtype=ChannelType.STRING,
        doc='Input Link I',
        read_only=True)
    input_link_j = pvproperty(
        name='INPJ',
        dtype=ChannelType.STRING,
        doc='Input Link J',
        read_only=True)
    input_link_k = pvproperty(
        name='INPK',
        dtype=ChannelType.STRING,
        doc='Input Link K',
        read_only=True)
    input_link_l = pvproperty(
        name='INPL',
        dtype=ChannelType.STRING,
        doc='Input Link L',
        read_only=True)
    input_link_m = pvproperty(
        name='INPM',
        dtype=ChannelType.STRING,
        doc='Input Link M',
        read_only=True)
    input_link_n = pvproperty(
        name='INPN',
        dtype=ChannelType.STRING,
        doc='Input Link N',
        read_only=True)
    input_link_o = pvproperty(
        name='INPO',
        dtype=ChannelType.STRING,
        doc='Input Link O',
        read_only=True)
    input_link_p = pvproperty(
        name='INPP',
        dtype=ChannelType.STRING,
        doc='Input Link P',
        read_only=True)
    input_link_q = pvproperty(
        name='INPQ',
        dtype=ChannelType.STRING,
        doc='Input Link Q',
        read_only=True)
    input_link_r = pvproperty(
        name='INPR',
        dtype=ChannelType.STRING,
        doc='Input Link R',
        read_only=True)
    input_link_s = pvproperty(
        name='INPS',
        dtype=ChannelType.STRING,
        doc='Input Link S',
        read_only=True)
    input_link_t = pvproperty(
        name='INPT',
        dtype=ChannelType.STRING,
        doc='Input Link T',
        read_only=True)
    input_link_u = pvproperty(
        name='INPU',
        dtype=ChannelType.STRING,
        doc='Input Link U',
        read_only=True)
    subroutine_input_link = pvproperty(
        name='SUBL',
        dtype=ChannelType.STRING,
        doc='Subroutine Input Link',
        read_only=True)
    event_flag = pvproperty(
        name='EFLG',
        dtype=ChannelType.ENUM,
        enum_strings=menus.genSubEFLG.get_string_tuple(),
        doc='Event Flag')
    link_flag = pvproperty(
        name='LFLG',
        dtype=ChannelType.ENUM,
        enum_strings=menus.genSubLFLG.get_string_tuple(),
        doc='Link Flag')
    output_link_a = pvproperty(
        name='OUTA',
        dtype=ChannelType.STRING,
        doc='Output Link A',
        read_only=True)
    output_link_b = pvproperty(
        name='OUTB',
        dtype=ChannelType.STRING,
        doc='Output Link B',
        read_only=True)
    output_link_c = pvproperty(
        name='OUTC',
        dtype=ChannelType.STRING,
        doc='Output Link C',
        read_only=True)
    output_link_d = pvproperty(
        name='OUTD',
        dtype=ChannelType.STRING,
        doc='Output Link D',
        read_only=True)
    output_link_e = pvproperty(
        name='OUTE',
        dtype=ChannelType.STRING,
        doc='Output Link E',
        read_only=True)
    output_link_f = pvproperty(
        name='OUTF',
        dtype=ChannelType.STRING,
        doc='Output Link F',
        read_only=True)
    output_link_g = pvproperty(
        name='OUTG',
        dtype=ChannelType.STRING,
        doc='Output Link G',
        read_only=True)
    output_link_h = pvproperty(
        name='OUTH',
        dtype=ChannelType.STRING,
        doc='Output Link H',
        read_only=True)
    output_link_i = pvproperty(
        name='OUTI',
        dtype=ChannelType.STRING,
        doc='Output Link I',
        read_only=True)
    output_link_j = pvproperty(
        name='OUTJ',
        dtype=ChannelType.STRING,
        doc='Output Link J',
        read_only=True)
    output_link_k = pvproperty(
        name='OUTK',
        dtype=ChannelType.STRING,
        doc='Output Link K',
        read_only=True)
    output_link_l = pvproperty(
        name='OUTL',
        dtype=ChannelType.STRING,
        doc='Output Link L',
        read_only=True)
    output_link_m = pvproperty(
        name='OUTM',
        dtype=ChannelType.STRING,
        doc='Output Link M',
        read_only=True)
    output_link_n = pvproperty(
        name='OUTN',
        dtype=ChannelType.STRING,
        doc='Output Link N',
        read_only=True)
    output_link_o = pvproperty(
        name='OUTO',
        dtype=ChannelType.STRING,
        doc='Output Link O',
        read_only=True)
    output_link_p = pvproperty(
        name='OUTP',
        dtype=ChannelType.STRING,
        doc='Output Link P',
        read_only=True)
    output_link_q = pvproperty(
        name='OUTQ',
        dtype=ChannelType.STRING,
        doc='Output Link Q',
        read_only=True)
    output_link_r = pvproperty(
        name='OUTR',
        dtype=ChannelType.STRING,
        doc='Output Link R',
        read_only=True)
    output_link_s = pvproperty(
        name='OUTS',
        dtype=ChannelType.STRING,
        doc='Output Link S',
        read_only=True)
    output_link_t = pvproperty(
        name='OUTT',
        dtype=ChannelType.STRING,
        doc='Output Link T',
        read_only=True)
    output_link_u = pvproperty(
        name='OUTU',
        dtype=ChannelType.STRING,
        doc='Output Link U',
        read_only=True)
    bad_return_severity = pvproperty(
        name='BRSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Bad Return Severity')
    init_routine_name = pvproperty(
        name='INAM',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Init Routine Name',
        read_only=True)
    input_structure_a = pvproperty(
        name='UFA',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Input Structure A',
        read_only=True)
    input_structure_b = pvproperty(
        name='UFB',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Input Structure B',
        read_only=True)
    input_structure_c = pvproperty(
        name='UFC',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Input Structure C',
        read_only=True)
    input_structure_d = pvproperty(
        name='UFD',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Input Structure D',
        read_only=True)
    input_structure_e = pvproperty(
        name='UFE',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Input Structure E',
        read_only=True)
    input_structure_f = pvproperty(
        name='UFF',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Input Structure F',
        read_only=True)
    input_structure_g = pvproperty(
        name='UFG',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Input Structure G',
        read_only=True)
    input_structure_h = pvproperty(
        name='UFH',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Input Structure H',
        read_only=True)
    input_structure_i = pvproperty(
        name='UFI',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Input Structure I',
        read_only=True)
    input_structure_j = pvproperty(
        name='UFJ',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Input Structure J',
        read_only=True)
    input_structure_k = pvproperty(
        name='UFK',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Input Structure K',
        read_only=True)
    input_structure_l = pvproperty(
        name='UFL',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Input Structure L',
        read_only=True)
    input_structure_m = pvproperty(
        name='UFM',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Input Structure M',
        read_only=True)
    input_structure_n = pvproperty(
        name='UFN',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Input Structure N',
        read_only=True)
    input_structure_o = pvproperty(
        name='UFO',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Input Structure O',
        read_only=True)
    input_structure_p = pvproperty(
        name='UFP',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Input Structure P',
        read_only=True)
    input_structure_q = pvproperty(
        name='UFQ',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Input Structure Q',
        read_only=True)
    input_structure_r = pvproperty(
        name='UFR',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Input Structure R',
        read_only=True)
    input_structure_s = pvproperty(
        name='UFS',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Input Structure S',
        read_only=True)
    input_structure_t = pvproperty(
        name='UFT',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Input Structure T',
        read_only=True)
    input_structure_u = pvproperty(
        name='UFU',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Input Structure U',
        read_only=True)
    old_subroutine_name = pvproperty(
        name='ONAM',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Old Subroutine Name',
        read_only=True)
    output_structure_a = pvproperty(
        name='UFVA',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Output Structure A',
        read_only=True)
    output_structure_b = pvproperty(
        name='UFVB',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Output Structure B',
        read_only=True)
    output_structure_c = pvproperty(
        name='UFVC',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Output Structure C',
        read_only=True)
    output_structure_d = pvproperty(
        name='UFVD',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Output Structure D',
        read_only=True)
    output_structure_e = pvproperty(
        name='UFVE',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Output Structure E',
        read_only=True)
    output_structure_f = pvproperty(
        name='UFVF',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Output Structure F',
        read_only=True)
    output_structure_g = pvproperty(
        name='UFVG',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Output Structure G',
        read_only=True)
    output_structure_h = pvproperty(
        name='UFVH',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Output Structure H',
        read_only=True)
    output_structure_i = pvproperty(
        name='UFVI',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Output Structure I',
        read_only=True)
    output_structure_j = pvproperty(
        name='UFVJ',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Output Structure J',
        read_only=True)
    output_structure_k = pvproperty(
        name='UFVK',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Output Structure K',
        read_only=True)
    output_structure_l = pvproperty(
        name='UFVL',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Output Structure L',
        read_only=True)
    output_structure_m = pvproperty(
        name='UFVM',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Output Structure M',
        read_only=True)
    output_structure_n = pvproperty(
        name='UFVN',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Output Structure N',
        read_only=True)
    output_structure_o = pvproperty(
        name='UFVO',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Output Structure O',
        read_only=True)
    output_structure_p = pvproperty(
        name='UFVP',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Output Structure P',
        read_only=True)
    output_structure_q = pvproperty(
        name='UFVQ',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Output Structure Q',
        read_only=True)
    output_structure_r = pvproperty(
        name='UFVR',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Output Structure R',
        read_only=True)
    output_structure_s = pvproperty(
        name='UFVS',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Output Structure S',
        read_only=True)
    output_structure_t = pvproperty(
        name='UFVT',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Output Structure T',
        read_only=True)
    output_structure_u = pvproperty(
        name='UFVU',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Output Structure U',
        read_only=True)
    process_subr_name = pvproperty(
        name='SNAM',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Process Subr. Name')
    no_in_a = pvproperty(
        name='NOA', dtype=ChannelType.LONG, doc='No. in A', read_only=True)
    no_in_b = pvproperty(
        name='NOB', dtype=ChannelType.LONG, doc='No. in B', read_only=True)
    no_in_c = pvproperty(
        name='NOC', dtype=ChannelType.LONG, doc='No. in C', read_only=True)
    no_in_d = pvproperty(
        name='NOD', dtype=ChannelType.LONG, doc='No. in D', read_only=True)
    no_in_e = pvproperty(
        name='NOE', dtype=ChannelType.LONG, doc='No. in E', read_only=True)
    no_in_f = pvproperty(
        name='NOF', dtype=ChannelType.LONG, doc='No. in F', read_only=True)
    no_in_g = pvproperty(
        name='NOG', dtype=ChannelType.LONG, doc='No. in G', read_only=True)
    no_in_h = pvproperty(
        name='NOH', dtype=ChannelType.LONG, doc='No. in H', read_only=True)
    no_in_i = pvproperty(
        name='NOI', dtype=ChannelType.LONG, doc='No. in I', read_only=True)
    no_in_j = pvproperty(
        name='NOJ', dtype=ChannelType.LONG, doc='No. in J', read_only=True)
    no_in_k = pvproperty(
        name='NOK', dtype=ChannelType.LONG, doc='No. in K', read_only=True)
    no_in_l = pvproperty(
        name='NOL', dtype=ChannelType.LONG, doc='No. in L', read_only=True)
    no_in_m = pvproperty(
        name='NOM', dtype=ChannelType.LONG, doc='No. in M', read_only=True)
    no_in_n = pvproperty(
        name='NON', dtype=ChannelType.LONG, doc='No. in N', read_only=True)
    no_in_o = pvproperty(
        name='NOO', dtype=ChannelType.LONG, doc='No. in O', read_only=True)
    no_in_p = pvproperty(
        name='NOP', dtype=ChannelType.LONG, doc='No. in P', read_only=True)
    no_in_q = pvproperty(
        name='NOQ', dtype=ChannelType.LONG, doc='No. in Q', read_only=True)
    no_in_r = pvproperty(
        name='NOR', dtype=ChannelType.LONG, doc='No. in R', read_only=True)
    no_in_s = pvproperty(
        name='NOS', dtype=ChannelType.LONG, doc='No. in S', read_only=True)
    no_in_t = pvproperty(
        name='NOT', dtype=ChannelType.LONG, doc='No. in T', read_only=True)
    no_in_u = pvproperty(
        name='NOU', dtype=ChannelType.LONG, doc='No. in U', read_only=True)
    no_in_vala = pvproperty(
        name='NOVA', dtype=ChannelType.LONG, doc='No. in VALA', read_only=True)
    no_in_valb = pvproperty(
        name='NOVB', dtype=ChannelType.LONG, doc='No. in VALB', read_only=True)
    no_in_valc = pvproperty(
        name='NOVC', dtype=ChannelType.LONG, doc='No. in VALC', read_only=True)
    no_in_vald = pvproperty(
        name='NOVD', dtype=ChannelType.LONG, doc='No. in VALD', read_only=True)
    no_in_vale = pvproperty(
        name='NOVE', dtype=ChannelType.LONG, doc='No. in VALE', read_only=True)
    no_in_valf = pvproperty(
        name='NOVF', dtype=ChannelType.LONG, doc='No. in VALF', read_only=True)
    no_in_valg = pvproperty(
        name='NOVG', dtype=ChannelType.LONG, doc='No. in VALG', read_only=True)
    no_in_vali = pvproperty(
        name='NOVI', dtype=ChannelType.LONG, doc='No. in VALI', read_only=True)
    no_in_valj = pvproperty(
        name='NOVJ', dtype=ChannelType.LONG, doc='No. in VALJ', read_only=True)
    no_in_valk = pvproperty(
        name='NOVK', dtype=ChannelType.LONG, doc='No. in VALK', read_only=True)
    no_in_vall = pvproperty(
        name='NOVL', dtype=ChannelType.LONG, doc='No. in VALL', read_only=True)
    no_in_valm = pvproperty(
        name='NOVM', dtype=ChannelType.LONG, doc='No. in VALM', read_only=True)
    no_in_valn = pvproperty(
        name='NOVN', dtype=ChannelType.LONG, doc='No. in VALN', read_only=True)
    no_in_valo = pvproperty(
        name='NOVO', dtype=ChannelType.LONG, doc='No. in VALO', read_only=True)
    no_in_valp = pvproperty(
        name='NOVP', dtype=ChannelType.LONG, doc='No. in VALP', read_only=True)
    no_in_valq = pvproperty(
        name='NOVQ', dtype=ChannelType.LONG, doc='No. in VALQ', read_only=True)
    no_in_valr = pvproperty(
        name='NOVR', dtype=ChannelType.LONG, doc='No. in VALR', read_only=True)
    no_in_vals = pvproperty(
        name='NOVS', dtype=ChannelType.LONG, doc='No. in VALS', read_only=True)
    no_in_valt = pvproperty(
        name='NOVT', dtype=ChannelType.LONG, doc='No. in VALT', read_only=True)
    no_in_valu = pvproperty(
        name='NOVU', dtype=ChannelType.LONG, doc='No. in VALU', read_only=True)
    no_in_valh = pvproperty(
        name='NOVH', dtype=ChannelType.LONG, doc='No. in VAlH', read_only=True)
    total_bytes_for_vala = pvproperty(
        name='TOVA',
        dtype=ChannelType.LONG,
        doc='Total bytes for VALA',
        read_only=True)
    total_bytes_for_valb = pvproperty(
        name='TOVB',
        dtype=ChannelType.LONG,
        doc='Total bytes for VALB',
        read_only=True)
    total_bytes_for_valc = pvproperty(
        name='TOVC',
        dtype=ChannelType.LONG,
        doc='Total bytes for VALC',
        read_only=True)
    total_bytes_for_vald = pvproperty(
        name='TOVD',
        dtype=ChannelType.LONG,
        doc='Total bytes for VALD',
        read_only=True)
    total_bytes_for_vale = pvproperty(
        name='TOVE',
        dtype=ChannelType.LONG,
        doc='Total bytes for VALE',
        read_only=True)
    total_bytes_for_valf = pvproperty(
        name='TOVF',
        dtype=ChannelType.LONG,
        doc='Total bytes for VALF',
        read_only=True)
    total_bytes_for_valg = pvproperty(
        name='TOVG',
        dtype=ChannelType.LONG,
        doc='Total bytes for VALG',
        read_only=True)
    total_bytes_for_vali = pvproperty(
        name='TOVI',
        dtype=ChannelType.LONG,
        doc='Total bytes for VALI',
        read_only=True)
    total_bytes_for_valj = pvproperty(
        name='TOVJ',
        dtype=ChannelType.LONG,
        doc='Total bytes for VALJ',
        read_only=True)
    total_bytes_for_valk = pvproperty(
        name='TOVK',
        dtype=ChannelType.LONG,
        doc='Total bytes for VALK',
        read_only=True)
    total_bytes_for_vall = pvproperty(
        name='TOVL',
        dtype=ChannelType.LONG,
        doc='Total bytes for VALL',
        read_only=True)
    total_bytes_for_valm = pvproperty(
        name='TOVM',
        dtype=ChannelType.LONG,
        doc='Total bytes for VALM',
        read_only=True)
    total_bytes_for_valn = pvproperty(
        name='TOVN',
        dtype=ChannelType.LONG,
        doc='Total bytes for VALN',
        read_only=True)
    total_bytes_for_valo = pvproperty(
        name='TOVO',
        dtype=ChannelType.LONG,
        doc='Total bytes for VALO',
        read_only=True)
    total_bytes_for_valp = pvproperty(
        name='TOVP',
        dtype=ChannelType.LONG,
        doc='Total bytes for VALP',
        read_only=True)
    total_bytes_for_valq = pvproperty(
        name='TOVQ',
        dtype=ChannelType.LONG,
        doc='Total bytes for VALQ',
        read_only=True)
    total_bytes_for_valr = pvproperty(
        name='TOVR',
        dtype=ChannelType.LONG,
        doc='Total bytes for VALR',
        read_only=True)
    total_bytes_for_vals = pvproperty(
        name='TOVS',
        dtype=ChannelType.LONG,
        doc='Total bytes for VALS',
        read_only=True)
    total_bytes_for_valt = pvproperty(
        name='TOVT',
        dtype=ChannelType.LONG,
        doc='Total bytes for VALT',
        read_only=True)
    total_bytes_for_valu = pvproperty(
        name='TOVU',
        dtype=ChannelType.LONG,
        doc='Total bytes for VALU',
        read_only=True)
    total_bytes_for_valh = pvproperty(
        name='TOVH',
        dtype=ChannelType.LONG,
        doc='Total bytes for VAlH',
        read_only=True)
    type_of_a = pvproperty(
        name='FTA',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of A',
        read_only=True)
    type_of_b = pvproperty(
        name='FTB',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of B',
        read_only=True)
    type_of_c = pvproperty(
        name='FTC',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of C',
        read_only=True)
    type_of_d = pvproperty(
        name='FTD',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of D',
        read_only=True)
    type_of_e = pvproperty(
        name='FTE',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of E',
        read_only=True)
    type_of_f = pvproperty(
        name='FTF',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of F',
        read_only=True)
    type_of_g = pvproperty(
        name='FTG',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of G',
        read_only=True)
    type_of_h = pvproperty(
        name='FTH',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of H',
        read_only=True)
    type_of_i = pvproperty(
        name='FTI',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of I',
        read_only=True)
    type_of_j = pvproperty(
        name='FTJ',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of J',
        read_only=True)
    type_of_k = pvproperty(
        name='FTK',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of K',
        read_only=True)
    type_of_l = pvproperty(
        name='FTL',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of L',
        read_only=True)
    type_of_m = pvproperty(
        name='FTM',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of M',
        read_only=True)
    type_of_n = pvproperty(
        name='FTN',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of N',
        read_only=True)
    type_of_o = pvproperty(
        name='FTO',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of O',
        read_only=True)
    type_of_p = pvproperty(
        name='FTP',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of P',
        read_only=True)
    type_of_q = pvproperty(
        name='FTQ',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of Q',
        read_only=True)
    type_of_r = pvproperty(
        name='FTR',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of R',
        read_only=True)
    type_of_s = pvproperty(
        name='FTS',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of S',
        read_only=True)
    type_of_t = pvproperty(
        name='FTT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of T',
        read_only=True)
    type_of_u = pvproperty(
        name='FTU',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of U',
        read_only=True)
    type_of_vala = pvproperty(
        name='FTVA',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of VALA',
        read_only=True)
    type_of_valb = pvproperty(
        name='FTVB',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of VALB',
        read_only=True)
    type_of_valc = pvproperty(
        name='FTVC',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of VALC',
        read_only=True)
    type_of_vald = pvproperty(
        name='FTVD',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of VALD',
        read_only=True)
    type_of_vale = pvproperty(
        name='FTVE',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of VALE',
        read_only=True)
    type_of_valf = pvproperty(
        name='FTVF',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of VALF',
        read_only=True)
    type_of_valg = pvproperty(
        name='FTVG',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of VALG',
        read_only=True)
    type_of_valh = pvproperty(
        name='FTVH',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of VALH',
        read_only=True)
    type_of_vali = pvproperty(
        name='FTVI',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of VALI',
        read_only=True)
    type_of_valj = pvproperty(
        name='FTVJ',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of VALJ',
        read_only=True)
    type_of_valk = pvproperty(
        name='FTVK',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of VALK',
        read_only=True)
    type_of_vall = pvproperty(
        name='FTVL',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of VALL',
        read_only=True)
    type_of_valm = pvproperty(
        name='FTVM',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of VALM',
        read_only=True)
    type_of_valn = pvproperty(
        name='FTVN',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of VALN',
        read_only=True)
    type_of_valo = pvproperty(
        name='FTVO',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of VALO',
        read_only=True)
    type_of_valp = pvproperty(
        name='FTVP',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of VALP',
        read_only=True)
    type_of_valq = pvproperty(
        name='FTVQ',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of VALQ',
        read_only=True)
    type_of_valr = pvproperty(
        name='FTVR',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of VALR',
        read_only=True)
    type_of_vals = pvproperty(
        name='FTVS',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of VALS',
        read_only=True)
    type_of_valt = pvproperty(
        name='FTVT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of VALT',
        read_only=True)
    type_of_valu = pvproperty(
        name='FTVU',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Type of VALU',
        read_only=True)
    _link_parent_attribute(display_precision, 'precision')


@register_record
class HistogramFields(RecordFieldGroup):
    _record_type = 'histogram'
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    collection_control = pvproperty(
        name='CMD',
        dtype=ChannelType.ENUM,
        enum_strings=menus.histogramCMD.get_string_tuple(),
        doc='Collection Control')
    collection_status = pvproperty(
        name='CSTA',
        dtype=ChannelType.LONG,
        doc='Collection Status',
        read_only=True)
    counts_since_monitor = pvproperty(
        name='MCNT',
        dtype=ChannelType.LONG,
        doc='Counts Since Monitor',
        read_only=True)
    element_width = pvproperty(
        name='WDTH',
        dtype=ChannelType.DOUBLE,
        doc='Element Width',
        read_only=True)
    signal_value = pvproperty(
        name='SGNL', dtype=ChannelType.DOUBLE, doc='Signal Value')
    simulation_mode = pvproperty(
        name='SIMM',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuYesNo.get_string_tuple(),
        doc='Simulation Mode')
    simulation_value = pvproperty(
        name='SVAL', dtype=ChannelType.DOUBLE, doc='Simulation Value')
    display_precision = pvproperty(
        name='PREC', dtype=ChannelType.LONG, doc='Display Precision')
    high_operating_range = pvproperty(
        name='HOPR', dtype=ChannelType.LONG, doc='High Operating Range')
    low_operating_range = pvproperty(
        name='LOPR', dtype=ChannelType.LONG, doc='Low Operating Range')
    lower_signal_limit = pvproperty(
        name='LLIM', dtype=ChannelType.DOUBLE, doc='Lower Signal Limit')
    monitor_count_deadband = pvproperty(
        name='MDEL', dtype=ChannelType.LONG, doc='Monitor Count Deadband')
    monitor_seconds_dband = pvproperty(
        name='SDEL', dtype=ChannelType.DOUBLE, doc='Monitor Seconds Dband')
    number_of_elements = pvproperty(
        name='NELM',
        dtype=ChannelType.LONG,
        doc='Num of Array Elements',
        read_only=True)
    upper_signal_limit = pvproperty(
        name='ULIM', dtype=ChannelType.DOUBLE, doc='Upper Signal Limit')
    signal_value_location = pvproperty(
        name='SVL', dtype=ChannelType.STRING, doc='Signal Value Location')
    sim_input_specifctn = pvproperty(
        name='SIOL', dtype=ChannelType.STRING, doc='Sim Input Specifctn')
    sim_mode_location = pvproperty(
        name='SIML', dtype=ChannelType.STRING, doc='Sim Mode Location')
    sim_mode_alarm_svrty = pvproperty(
        name='SIMS',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Sim mode Alarm Svrty')
    _link_parent_attribute(display_precision, 'precision')
    _link_parent_attribute(high_operating_range, 'upper_ctrl_limit')
    _link_parent_attribute(low_operating_range, 'lower_ctrl_limit')
    _link_parent_attribute(number_of_elements, 'max_length')


@register_record
class LonginFields(RecordFieldGroup, _LimitsLong):
    _record_type = 'longin'
    # value = pvproperty(name='VAL', dtype=ChannelType.LONG, doc='Current value')
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    last_val_monitored = pvproperty(
        name='MLST',
        dtype=ChannelType.LONG,
        doc='Last Val Monitored',
        read_only=True)
    last_value_alarmed = pvproperty(
        name='LALM',
        dtype=ChannelType.LONG,
        doc='Last Value Alarmed',
        read_only=True)
    last_value_archived = pvproperty(
        name='ALST',
        dtype=ChannelType.LONG,
        doc='Last Value Archived',
        read_only=True)
    simulation_mode = pvproperty(
        name='SIMM',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuYesNo.get_string_tuple(),
        doc='Simulation Mode')
    simulation_value = pvproperty(
        name='SVAL', dtype=ChannelType.LONG, doc='Simulation Value')
    alarm_deadband = pvproperty(
        name='HYST', dtype=ChannelType.LONG, doc='Alarm Deadband')
    archive_deadband = pvproperty(
        name='ADEL', dtype=ChannelType.LONG, doc='Archive Deadband')
    monitor_deadband = pvproperty(
        name='MDEL', dtype=ChannelType.LONG, doc='Monitor Deadband')
    units_name = pvproperty(
        name='EGU', dtype=ChannelType.CHAR, max_length=16, doc='Units name')
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
    _link_parent_attribute(archive_deadband, 'log_atol')
    _link_parent_attribute(monitor_deadband, 'value_atol')


@register_record
class LongoutFields(RecordFieldGroup, _LimitsLong):
    _record_type = 'longout'
    # value = pvproperty(
    #     name='VAL', dtype=ChannelType.LONG, doc='Desired Output')
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    last_val_monitored = pvproperty(
        name='MLST',
        dtype=ChannelType.LONG,
        doc='Last Val Monitored',
        read_only=True)
    last_value_alarmed = pvproperty(
        name='LALM',
        dtype=ChannelType.LONG,
        doc='Last Value Alarmed',
        read_only=True)
    last_value_archived = pvproperty(
        name='ALST',
        dtype=ChannelType.LONG,
        doc='Last Value Archived',
        read_only=True)
    simulation_mode = pvproperty(
        name='SIMM',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuYesNo.get_string_tuple(),
        doc='Simulation Mode')
    alarm_deadband = pvproperty(
        name='HYST', dtype=ChannelType.LONG, doc='Alarm Deadband')
    archive_deadband = pvproperty(
        name='ADEL', dtype=ChannelType.LONG, doc='Archive Deadband')
    monitor_deadband = pvproperty(
        name='MDEL', dtype=ChannelType.LONG, doc='Monitor Deadband')
    units_name = pvproperty(
        name='EGU', dtype=ChannelType.CHAR, max_length=16, doc='Units name')
    sim_mode_location = pvproperty(
        name='SIML', dtype=ChannelType.STRING, doc='Sim Mode Location')
    sim_output_specifctn = pvproperty(
        name='SIOL', dtype=ChannelType.STRING, doc='Sim Output Specifctn')
    sim_mode_alarm_svrty = pvproperty(
        name='SIMS',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Sim mode Alarm Svrty')
    desired_output_loc = pvproperty(
        name='DOL', dtype=ChannelType.STRING, doc='Desired Output Loc')
    drive_high_limit = pvproperty(
        name='DRVH', dtype=ChannelType.LONG, doc='Drive High Limit')
    drive_low_limit = pvproperty(
        name='DRVL', dtype=ChannelType.LONG, doc='Drive Low Limit')
    invalid_output_action = pvproperty(
        name='IVOA',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuIvoa.get_string_tuple(),
        doc='INVALID output action')
    invalid_output_value = pvproperty(
        name='IVOV', dtype=ChannelType.LONG, doc='INVALID output value')
    output_mode_select = pvproperty(
        name='OMSL',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuOmsl.get_string_tuple(),
        doc='Output Mode Select')
    output_specification = pvproperty(
        name='OUT', dtype=ChannelType.STRING, doc='Output Specification')
    _link_parent_attribute(archive_deadband, 'log_atol')
    _link_parent_attribute(monitor_deadband, 'value_atol')


@register_record
class MbbiFields(RecordFieldGroup):
    _record_type = 'mbbi'
    # value = pvproperty(name='VAL', dtype=ChannelType.ENUM, doc='Current Value')
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    hardware_mask = pvproperty(
        name='MASK',
        dtype=ChannelType.LONG,
        doc='Hardware Mask',
        read_only=True)
    last_value_alarmed = pvproperty(
        name='LALM',
        dtype=ChannelType.LONG,
        doc='Last Value Alarmed',
        read_only=True)
    last_value_monitored = pvproperty(
        name='MLST',
        dtype=ChannelType.LONG,
        doc='Last Value Monitored',
        read_only=True)
    prev_raw_value = pvproperty(
        name='ORAW',
        dtype=ChannelType.LONG,
        doc='Prev Raw Value',
        read_only=True)
    raw_value = pvproperty(
        name='RVAL', dtype=ChannelType.LONG, doc='Raw Value')
    simulation_mode = pvproperty(
        name='SIMM',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuSimm.get_string_tuple(),
        doc='Simulation Mode')
    states_defined = pvproperty(
        name='SDEF',
        dtype=ChannelType.LONG,
        doc='States Defined',
        read_only=True)
    change_of_state_severity = pvproperty(
        name='COSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Change of State Svr')
    number_of_bits = pvproperty(
        name='NOBT',
        dtype=ChannelType.LONG,
        doc='Number of Bits',
        read_only=True)
    shift = pvproperty(name='SHFT', dtype=ChannelType.LONG, doc='Shift')
    sim_mode_alarm_severity = pvproperty(
        name='SIMS',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Sim mode Alarm Svrty')
    unknown_state_severity = pvproperty(
        name='UNSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Unknown State Severity')
    input_specification = pvproperty(
        name='INP', dtype=ChannelType.STRING, doc='Input Specification')
    sim_input_specification = pvproperty(
        name='SIOL', dtype=ChannelType.STRING, doc='Sim Input Specifctn')
    simulation_value = pvproperty(
        name='SVAL', dtype=ChannelType.LONG, doc='Simulation Value')


@register_record
class MbbidirectFields(RecordFieldGroup):
    _record_type = 'mbbiDirect'
    # value = pvproperty(name='VAL', dtype=ChannelType.LONG, doc='Current Value')
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    bit_0 = pvproperty(name='B0', dtype=ChannelType.CHAR, doc='Bit 0')
    bit_1 = pvproperty(name='B1', dtype=ChannelType.CHAR, doc='Bit 1')
    bit_2 = pvproperty(name='B2', dtype=ChannelType.CHAR, doc='Bit 2')
    bit_3 = pvproperty(name='B3', dtype=ChannelType.CHAR, doc='Bit 3')
    bit_4 = pvproperty(name='B4', dtype=ChannelType.CHAR, doc='Bit 4')
    bit_5 = pvproperty(name='B5', dtype=ChannelType.CHAR, doc='Bit 5')
    bit_6 = pvproperty(name='B6', dtype=ChannelType.CHAR, doc='Bit 6')
    bit_7 = pvproperty(name='B7', dtype=ChannelType.CHAR, doc='Bit 7')
    bit_8 = pvproperty(name='B8', dtype=ChannelType.CHAR, doc='Bit 8')
    bit_9 = pvproperty(name='B9', dtype=ChannelType.CHAR, doc='Bit 9')
    bit_a = pvproperty(name='BA', dtype=ChannelType.CHAR, doc='Bit A')
    bit_b = pvproperty(name='BB', dtype=ChannelType.CHAR, doc='Bit B')
    bit_c = pvproperty(name='BC', dtype=ChannelType.CHAR, doc='Bit C')
    bit_d = pvproperty(name='BD', dtype=ChannelType.CHAR, doc='Bit D')
    bit_e = pvproperty(name='BE', dtype=ChannelType.CHAR, doc='Bit E')
    bit_f = pvproperty(name='BF', dtype=ChannelType.CHAR, doc='Bit F')
    hardware_mask = pvproperty(
        name='MASK',
        dtype=ChannelType.LONG,
        doc='Hardware Mask',
        read_only=True)
    last_value_alarmed = pvproperty(
        name='LALM',
        dtype=ChannelType.LONG,
        doc='Last Value Alarmed',
        read_only=True)
    last_value_monitored = pvproperty(
        name='MLST',
        dtype=ChannelType.LONG,
        doc='Last Value Monitored',
        read_only=True)
    prev_raw_value = pvproperty(
        name='ORAW',
        dtype=ChannelType.LONG,
        doc='Prev Raw Value',
        read_only=True)
    raw_value = pvproperty(
        name='RVAL', dtype=ChannelType.LONG, doc='Raw Value')
    simulation_mode = pvproperty(
        name='SIMM',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuSimm.get_string_tuple(),
        doc='Simulation Mode')
    simulation_value = pvproperty(
        name='SVAL', dtype=ChannelType.LONG, doc='Simulation Value')
    states_defined = pvproperty(
        name='SDEF',
        dtype=ChannelType.LONG,
        doc='States Defined',
        read_only=True)
    input_specification = pvproperty(
        name='INP', dtype=ChannelType.STRING, doc='Input Specification')
    number_of_bits = pvproperty(
        name='NOBT',
        dtype=ChannelType.LONG,
        doc='Number of Bits',
        read_only=True)
    shift = pvproperty(name='SHFT', dtype=ChannelType.LONG, doc='Shift')
    sim_input_specifctn = pvproperty(
        name='SIOL', dtype=ChannelType.STRING, doc='Sim Input Specifctn')
    sim_mode_location = pvproperty(
        name='SIML', dtype=ChannelType.STRING, doc='Sim Mode Location')
    sim_mode_alarm_svrty = pvproperty(
        name='SIMS',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Sim mode Alarm Svrty')


@register_record
class MbboFields(RecordFieldGroup):
    _record_type = 'mbbo'
    # value = pvproperty(name='VAL', dtype=ChannelType.ENUM, doc='Desired Value')
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    hardware_mask = pvproperty(
        name='MASK',
        dtype=ChannelType.LONG,
        doc='Hardware Mask',
        read_only=True)
    last_value_alarmed = pvproperty(
        name='LALM',
        dtype=ChannelType.LONG,
        doc='Last Value Alarmed',
        read_only=True)
    last_value_monitored = pvproperty(
        name='MLST',
        dtype=ChannelType.LONG,
        doc='Last Value Monitored',
        read_only=True)
    prev_raw_value = pvproperty(
        name='ORAW',
        dtype=ChannelType.LONG,
        doc='Prev Raw Value',
        read_only=True)
    raw_value = pvproperty(
        name='RVAL', dtype=ChannelType.LONG, doc='Raw Value')
    simulation_mode = pvproperty(
        name='SIMM',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuYesNo.get_string_tuple(),
        doc='Simulation Mode')
    states_defined = pvproperty(
        name='SDEF',
        dtype=ChannelType.LONG,
        doc='States Defined',
        read_only=True)
    change_of_state_severity = pvproperty(
        name='COSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Change of State Sevr')
    number_of_bits = pvproperty(
        name='NOBT',
        dtype=ChannelType.LONG,
        doc='Number of Bits',
        read_only=True)
    shift = pvproperty(name='SHFT', dtype=ChannelType.LONG, doc='Shift')
    sim_mode_alarm_severity = pvproperty(
        name='SIMS',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Sim mode Alarm Svrty')
    unknown_state_severity = pvproperty(
        name='UNSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Unknown State Sevr')
    prev_readback_value = pvproperty(
        name='ORBV',
        dtype=ChannelType.LONG,
        doc='Prev Readback Value',
        read_only=True)
    readback_value = pvproperty(
        name='RBV',
        dtype=ChannelType.LONG,
        doc='Readback Value',
        read_only=True)
    desired_output_location = pvproperty(
        name='DOL', dtype=ChannelType.STRING, doc='Desired Output Loc')
    invalid_outpt_action = pvproperty(
        name='IVOA',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuIvoa.get_string_tuple(),
        doc='INVALID outpt action')
    invalid_output_value = pvproperty(
        name='IVOV', dtype=ChannelType.LONG, doc='INVALID output value')
    output_mode_select = pvproperty(
        name='OMSL',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuOmsl.get_string_tuple(),
        doc='Output Mode Select')
    output_specification = pvproperty(
        name='OUT', dtype=ChannelType.STRING, doc='Output Specification')
    sim_output_specification = pvproperty(
        name='SIOL', dtype=ChannelType.STRING, doc='Sim Output Specifctn')


@register_record
class MbbodirectFields(RecordFieldGroup):
    _record_type = 'mbboDirect'
    # value = pvproperty(name='VAL', dtype=ChannelType.LONG, doc='Word')
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    hardware_mask = pvproperty(
        name='MASK',
        dtype=ChannelType.LONG,
        doc='Hardware Mask',
        read_only=True)
    last_value_alarmed = pvproperty(
        name='LALM',
        dtype=ChannelType.LONG,
        doc='Last Value Alarmed',
        read_only=True)
    last_value_monitored = pvproperty(
        name='MLST',
        dtype=ChannelType.LONG,
        doc='Last Value Monitored',
        read_only=True)
    prev_raw_value = pvproperty(
        name='ORAW',
        dtype=ChannelType.LONG,
        doc='Prev Raw Value',
        read_only=True)
    prev_readback_value = pvproperty(
        name='ORBV',
        dtype=ChannelType.LONG,
        doc='Prev Readback Value',
        read_only=True)
    raw_value = pvproperty(
        name='RVAL', dtype=ChannelType.LONG, doc='Raw Value', read_only=True)
    readback_value = pvproperty(
        name='RBV',
        dtype=ChannelType.LONG,
        doc='Readback Value',
        read_only=True)
    simulation_mode = pvproperty(
        name='SIMM',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuYesNo.get_string_tuple(),
        doc='Simulation Mode')
    bit_0 = pvproperty(name='B0', dtype=ChannelType.CHAR, doc='Bit 0')
    bit_1 = pvproperty(name='B1', dtype=ChannelType.CHAR, doc='Bit 1')
    bit_2 = pvproperty(name='B2', dtype=ChannelType.CHAR, doc='Bit 2')
    bit_3 = pvproperty(name='B3', dtype=ChannelType.CHAR, doc='Bit 3')
    bit_4 = pvproperty(name='B4', dtype=ChannelType.CHAR, doc='Bit 4')
    bit_5 = pvproperty(name='B5', dtype=ChannelType.CHAR, doc='Bit 5')
    bit_6 = pvproperty(name='B6', dtype=ChannelType.CHAR, doc='Bit 6')
    bit_7 = pvproperty(name='B7', dtype=ChannelType.CHAR, doc='Bit 7')
    bit_10 = pvproperty(name='BA', dtype=ChannelType.CHAR, doc='Bit 10')
    bit_11 = pvproperty(name='BB', dtype=ChannelType.CHAR, doc='Bit 11')
    bit_12 = pvproperty(name='BC', dtype=ChannelType.CHAR, doc='Bit 12')
    bit_13 = pvproperty(name='BD', dtype=ChannelType.CHAR, doc='Bit 13')
    bit_14 = pvproperty(name='BE', dtype=ChannelType.CHAR, doc='Bit 14')
    bit_15 = pvproperty(name='BF', dtype=ChannelType.CHAR, doc='Bit 15')
    bit_8 = pvproperty(name='B8', dtype=ChannelType.CHAR, doc='Bit 8')
    bit_9 = pvproperty(name='B9', dtype=ChannelType.CHAR, doc='Bit 9')
    desired_output_loc = pvproperty(
        name='DOL', dtype=ChannelType.STRING, doc='Desired Output Loc')
    invalid_outpt_action = pvproperty(
        name='IVOA',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuIvoa.get_string_tuple(),
        doc='INVALID outpt action')
    invalid_output_value = pvproperty(
        name='IVOV', dtype=ChannelType.LONG, doc='INVALID output value')
    number_of_bits = pvproperty(
        name='NOBT',
        dtype=ChannelType.LONG,
        doc='Number of Bits',
        read_only=True)
    output_mode_select = pvproperty(
        name='OMSL',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuOmsl.get_string_tuple(),
        doc='Output Mode Select')
    output_specification = pvproperty(
        name='OUT', dtype=ChannelType.STRING, doc='Output Specification')
    shift = pvproperty(name='SHFT', dtype=ChannelType.LONG, doc='Shift')
    sim_mode_location = pvproperty(
        name='SIML', dtype=ChannelType.STRING, doc='Sim Mode Location')
    sim_output_specifctn = pvproperty(
        name='SIOL', dtype=ChannelType.STRING, doc='Sim Output Specifctn')
    sim_mode_alarm_svrty = pvproperty(
        name='SIMS',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Sim mode Alarm Svrty')


@register_record
class MotorFields(RecordFieldGroup):
    _record_type = 'motor'
    # value = pvproperty(
    #     name='VAL', dtype=ChannelType.DOUBLE, doc='User Desired Value (EGU')
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    at_home = pvproperty(
        name='ATHM', dtype=ChannelType.LONG, doc='At HOME', read_only=True)
    card_number = pvproperty(
        name='CARD', dtype=ChannelType.LONG, doc='Card Number', read_only=True)
    code_version = pvproperty(
        name='VERS',
        dtype=ChannelType.DOUBLE,
        doc='Code Version',
        read_only=True)
    dial_desired_value_egu = pvproperty(
        name='DVAL', dtype=ChannelType.DOUBLE, doc='Dial Desired Value (EGU')
    dial_readback_value = pvproperty(
        name='DRBV',
        dtype=ChannelType.DOUBLE,
        doc='Dial Readback Value',
        read_only=True)
    difference_dval_drbv = pvproperty(
        name='DIFF',
        dtype=ChannelType.DOUBLE,
        doc='Difference dval-drbv',
        read_only=True)
    difference_rval_rrbv = pvproperty(
        name='RDIF',
        dtype=ChannelType.LONG,
        doc='Difference rval-rrbv',
        read_only=True)
    direction_of_travel = pvproperty(
        name='TDIR',
        dtype=ChannelType.LONG,
        doc='Direction of Travel',
        read_only=True)
    freeze_offset = pvproperty(
        name='FOF', dtype=ChannelType.LONG, doc='Freeze Offset')
    home_forward = pvproperty(
        name='HOMF', dtype=ChannelType.LONG, doc='Home Forward')
    home_reverse = pvproperty(
        name='HOMR', dtype=ChannelType.LONG, doc='Home Reverse')
    jog_motor_forward = pvproperty(
        name='JOGF', dtype=ChannelType.LONG, doc='Jog motor Forward')
    jog_motor_reverse = pvproperty(
        name='JOGR', dtype=ChannelType.LONG, doc='Jog motor Reverse')
    last_dial_des_val_egu = pvproperty(
        name='LDVL',
        dtype=ChannelType.DOUBLE,
        doc='Last Dial Des Val (EGU)',
        read_only=True)
    last_raw_des_val_steps = pvproperty(
        name='LRVL',
        dtype=ChannelType.LONG,
        doc='Last Raw Des Val (steps',
        read_only=True)
    last_rel_value_egu = pvproperty(
        name='LRLV',
        dtype=ChannelType.DOUBLE,
        doc='Last Rel Value (EGU)',
        read_only=True)
    last_spmg = pvproperty(
        name='LSPG',
        dtype=ChannelType.ENUM,
        enum_strings=menus.motorSPMG.get_string_tuple(),
        doc='Last SPMG',
        read_only=True)
    last_user_des_val_egu = pvproperty(
        name='LVAL',
        dtype=ChannelType.DOUBLE,
        doc='Last User Des Val (EGU)',
        read_only=True)
    last_val_monitored = pvproperty(
        name='MLST',
        dtype=ChannelType.DOUBLE,
        doc='Last Val Monitored',
        read_only=True)
    last_value_archived = pvproperty(
        name='ALST',
        dtype=ChannelType.DOUBLE,
        doc='Last Value Archived',
        read_only=True)
    limit_violation = pvproperty(
        name='LVIO',
        dtype=ChannelType.LONG,
        doc='Limit violation',
        read_only=True)
    monitor_mask = pvproperty(
        name='MMAP',
        dtype=ChannelType.LONG,
        doc='Monitor Mask',
        read_only=True)
    monitor_mask_more = pvproperty(
        name='NMAP',
        dtype=ChannelType.LONG,
        doc='Monitor Mask (more)',
        read_only=True)
    motion_in_progress = pvproperty(
        name='MIP',
        dtype=ChannelType.LONG,
        doc='Motion In Progress',
        read_only=True)
    motor_status = pvproperty(
        name='MSTA',
        dtype=ChannelType.LONG,
        doc='Motor Status',
        read_only=True)
    motor_is_moving = pvproperty(
        name='MOVN',
        dtype=ChannelType.LONG,
        doc='Motor is moving',
        read_only=True)
    post_process_command = pvproperty(
        name='PP',
        dtype=ChannelType.LONG,
        doc='Post process command',
        read_only=True)
    ran_out_of_retries = pvproperty(
        name='MISS',
        dtype=ChannelType.LONG,
        doc='Ran out of retries',
        read_only=True)
    raw_desired_value_step = pvproperty(
        name='RVAL', dtype=ChannelType.LONG, doc='Raw Desired Value (step')
    raw_encoder_position = pvproperty(
        name='REP',
        dtype=ChannelType.LONG,
        doc='Raw Encoder Position',
        read_only=True)
    raw_high_limit_switch = pvproperty(
        name='RHLS',
        dtype=ChannelType.LONG,
        doc='Raw High Limit Switch',
        read_only=True)
    raw_low_limit_switch = pvproperty(
        name='RLLS',
        dtype=ChannelType.LONG,
        doc='Raw Low Limit Switch',
        read_only=True)
    raw_motor_position = pvproperty(
        name='RMP',
        dtype=ChannelType.LONG,
        doc='Raw Motor Position',
        read_only=True)
    raw_readback_value = pvproperty(
        name='RRBV',
        dtype=ChannelType.LONG,
        doc='Raw Readback Value',
        read_only=True)
    raw_command_direction = pvproperty(
        name='CDIR',
        dtype=ChannelType.LONG,
        doc='Raw cmnd direction',
        read_only=True)
    relative_value_egu = pvproperty(
        name='RLV', dtype=ChannelType.DOUBLE, doc='Relative Value (EGU)')
    retry_count = pvproperty(
        name='RCNT', dtype=ChannelType.LONG, doc='Retry count', read_only=True)
    set_set_mode = pvproperty(
        name='SSET', dtype=ChannelType.LONG, doc='Set SET Mode')
    set_use_mode = pvproperty(
        name='SUSE', dtype=ChannelType.LONG, doc='Set USE Mode')
    set_use_switch = pvproperty(
        name='SET',
        dtype=ChannelType.ENUM,
        enum_strings=menus.motorSET.get_string_tuple(),
        doc='Set/Use Switch')
    motor_stop = pvproperty(name='STOP', dtype=ChannelType.LONG, doc='Stop')
    stop_pause_move_go = pvproperty(
        name='SPMG',
        dtype=ChannelType.ENUM,
        enum_strings=menus.motorSPMG.get_string_tuple(),
        doc='Stop/Pause/Move/Go')
    sync_position = pvproperty(
        name='SYNC', dtype=ChannelType.LONG, doc='Sync position')
    tweak_motor_forward = pvproperty(
        name='TWF', dtype=ChannelType.LONG, doc='Tweak motor Forward')
    tweak_motor_reverse = pvproperty(
        name='TWR', dtype=ChannelType.LONG, doc='Tweak motor Reverse')
    user_high_limit = pvproperty(
        name='HLM', dtype=ChannelType.DOUBLE, doc='User High Limit')
    user_high_limit_switch = pvproperty(
        name='HLS',
        dtype=ChannelType.LONG,
        doc='User High Limit Switch',
        read_only=True)
    user_low_limit = pvproperty(
        name='LLM', dtype=ChannelType.DOUBLE, doc='User Low Limit')
    user_low_limit_switch = pvproperty(
        name='LLS',
        dtype=ChannelType.LONG,
        doc='User Low Limit Switch',
        read_only=True)
    user_readback_value = pvproperty(
        name='RBV',
        dtype=ChannelType.DOUBLE,
        doc='User Readback Value',
        read_only=True)
    variable_offset = pvproperty(
        name='VOF', dtype=ChannelType.LONG, doc='Variable Offset')
    archive_deadband = pvproperty(
        name='ADEL', dtype=ChannelType.DOUBLE, doc='Archive Deadband')
    bl_distance_egu = pvproperty(
        name='BDST', dtype=ChannelType.DOUBLE, doc='BL Distance (EGU)')
    bl_seconds_to_velocity = pvproperty(
        name='BACC', dtype=ChannelType.DOUBLE, doc='BL Seconds to Velocity')
    bl_speed_rps = pvproperty(
        name='SBAK', dtype=ChannelType.DOUBLE, doc='BL Speed (RPS)')
    bl_velocity_egu_s = pvproperty(
        name='BVEL', dtype=ChannelType.DOUBLE, doc='BL Velocity (EGU/s)')
    base_speed_rps = pvproperty(
        name='SBAS', dtype=ChannelType.DOUBLE, doc='Base Speed (RPS)')
    base_velocity_egu_s = pvproperty(
        name='VBAS', dtype=ChannelType.DOUBLE, doc='Base Velocity (EGU/s)')
    dmov_input_link = pvproperty(
        name='DINP', dtype=ChannelType.STRING, doc='DMOV Input Link')
    derivative_gain = pvproperty(
        name='DCOF', dtype=ChannelType.DOUBLE, doc='Derivative Gain')
    desired_output_loc = pvproperty(
        name='DOL', dtype=ChannelType.STRING, doc='Desired Output Loc')
    dial_high_limit = pvproperty(
        name='DHLM', dtype=ChannelType.DOUBLE, doc='Dial High Limit')
    dial_low_limit = pvproperty(
        name='DLLM', dtype=ChannelType.DOUBLE, doc='Dial Low Limit')
    display_precision = pvproperty(
        name='PREC', dtype=ChannelType.LONG, doc='Display Precision')
    done_moving_to_value = pvproperty(
        name='DMOV',
        dtype=ChannelType.LONG,
        doc='Done moving to value',
        read_only=True)
    egu_s_per_revolution = pvproperty(
        name='UREV', dtype=ChannelType.DOUBLE, doc="EGU's per Revolution")
    enable_control = pvproperty(
        name='CNEN',
        dtype=ChannelType.ENUM,
        enum_strings=menus.motorTORQ.get_string_tuple(),
        doc='Enable control')
    encoder_step_size_egu = pvproperty(
        name='ERES', dtype=ChannelType.DOUBLE, doc='Encoder Step Size (EGU)')
    engineering_units = pvproperty(
        name='EGU',
        dtype=ChannelType.CHAR,
        max_length=16,
        doc='Engineering Units')
    hw_limit_violation_svr = pvproperty(
        name='HLSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='HW Limit Violation Svr')
    high_alarm_limit_egu = pvproperty(
        name='HIGH', dtype=ChannelType.DOUBLE, doc='High Alarm Limit (EGU)')
    high_operating_range = pvproperty(
        name='HOPR', dtype=ChannelType.DOUBLE, doc='High Operating Range')
    high_severity = pvproperty(
        name='HSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='High Severity')
    hihi_alarm_limit_egu = pvproperty(
        name='HIHI', dtype=ChannelType.DOUBLE, doc='Hihi Alarm Limit (EGU)')
    hihi_severity = pvproperty(
        name='HHSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Hihi Severity')
    home_velocity_egu_s = pvproperty(
        name='HVEL', dtype=ChannelType.DOUBLE, doc='Home Velocity (EGU/s)')
    integral_gain = pvproperty(
        name='ICOF', dtype=ChannelType.DOUBLE, doc='Integral Gain')
    jog_accel_egu_s_2 = pvproperty(
        name='JAR', dtype=ChannelType.DOUBLE, doc='Jog Accel. (EGU/s^2)')
    jog_velocity_egu_s = pvproperty(
        name='JVEL', dtype=ChannelType.DOUBLE, doc='Jog Velocity (EGU/s)')
    lolo_alarm_limit_egu = pvproperty(
        name='LOLO', dtype=ChannelType.DOUBLE, doc='Lolo Alarm Limit (EGU)')
    lolo_severity = pvproperty(
        name='LLSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Lolo Severity')
    low_alarm_limit_egu = pvproperty(
        name='LOW', dtype=ChannelType.DOUBLE, doc='Low Alarm Limit (EGU)')
    low_operating_range = pvproperty(
        name='LOPR', dtype=ChannelType.DOUBLE, doc='Low Operating Range')
    low_severity = pvproperty(
        name='LSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Low Severity')
    max_retry_count = pvproperty(
        name='RTRY', dtype=ChannelType.LONG, doc='Max retry count')
    max_speed_rps = pvproperty(
        name='SMAX', dtype=ChannelType.DOUBLE, doc='Max. Speed (RPS)')
    max_velocity_egu_s = pvproperty(
        name='VMAX', dtype=ChannelType.DOUBLE, doc='Max. Velocity (EGU/s)')
    monitor_deadband = pvproperty(
        name='MDEL', dtype=ChannelType.DOUBLE, doc='Monitor Deadband')
    motor_step_size_egu = pvproperty(
        name='MRES', dtype=ChannelType.DOUBLE, doc='Motor Step Size (EGU)')
    move_fraction = pvproperty(
        name='FRAC', dtype=ChannelType.DOUBLE, doc='Move Fraction')
    ntm_deadband_factor = pvproperty(
        name='NTMF', dtype=ChannelType.LONG, doc='NTM Deadband Factor')
    new_target_monitor = pvproperty(
        name='NTM',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuYesNo.get_string_tuple(),
        doc='New Target Monitor')
    offset_freeze_switch = pvproperty(
        name='FOFF',
        dtype=ChannelType.ENUM,
        enum_strings=menus.motorFOFF.get_string_tuple(),
        doc='Offset-Freeze Switch')
    output_mode_select = pvproperty(
        name='OMSL',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuOmsl.get_string_tuple(),
        doc='Output Mode Select')
    output_specification = pvproperty(
        name='OUT', dtype=ChannelType.STRING, doc='Output Specification')
    post_move_commands = pvproperty(
        name='POST',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Post-move commands')
    pre_move_commands = pvproperty(
        name='PREM',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Pre-move commands')
    proportional_gain = pvproperty(
        name='PCOF', dtype=ChannelType.DOUBLE, doc='Proportional Gain')
    rmp_input_link = pvproperty(
        name='RINP', dtype=ChannelType.STRING, doc='RMP Input Link')
    raw_velocity = pvproperty(
        name='RVEL',
        dtype=ChannelType.LONG,
        doc='Raw Velocity',
        read_only=True)
    readback_location = pvproperty(
        name='RDBL', dtype=ChannelType.STRING, doc='Readback Location')
    readback_outlink = pvproperty(
        name='RLNK', dtype=ChannelType.STRING, doc='Readback OutLink')
    readback_step_size_egu = pvproperty(
        name='RRES', dtype=ChannelType.DOUBLE, doc='Readback Step Size (EGU')
    readback_settle_time_s = pvproperty(
        name='DLY', dtype=ChannelType.DOUBLE, doc='Readback settle time (s)')
    retry_deadband_egu = pvproperty(
        name='RDBD', dtype=ChannelType.DOUBLE, doc='Retry Deadband (EGU)')
    retry_mode = pvproperty(
        name='RMOD',
        dtype=ChannelType.ENUM,
        enum_strings=menus.motorRMOD.get_string_tuple(),
        doc='Retry Mode')
    stop_outlink = pvproperty(
        name='STOO', dtype=ChannelType.STRING, doc='STOP OutLink')
    seconds_to_velocity = pvproperty(
        name='ACCL', dtype=ChannelType.DOUBLE, doc='Seconds to Velocity')
    soft_channel_position_lock = pvproperty(
        name='LOCK',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuYesNo.get_string_tuple(),
        doc='Soft Channel Position Lock')
    speed_revolutions_sec = pvproperty(
        name='S', dtype=ChannelType.DOUBLE, doc='Speed (revolutions/sec)')
    startup_commands = pvproperty(
        name='INIT',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Startup commands')
    status_update = pvproperty(
        name='STUP',
        dtype=ChannelType.ENUM,
        enum_strings=menus.motorSTUP.get_string_tuple(),
        doc='Status Update')
    steps_per_revolution = pvproperty(
        name='SREV', dtype=ChannelType.LONG, doc='Steps per Revolution')
    tweak_step_size_egu = pvproperty(
        name='TWV', dtype=ChannelType.DOUBLE, doc='Tweak Step Size (EGU)')
    use_encoder_if_present = pvproperty(
        name='UEIP',
        dtype=ChannelType.ENUM,
        enum_strings=menus.motorUEIP.get_string_tuple(),
        doc='Use Encoder If Present')
    use_rdbl_link_if_presen = pvproperty(
        name='URIP',
        dtype=ChannelType.ENUM,
        enum_strings=menus.motorUEIP.get_string_tuple(),
        doc='Use RDBL Link If Presen')
    user_direction = pvproperty(
        name='DIR',
        dtype=ChannelType.ENUM,
        enum_strings=menus.motorDIR.get_string_tuple(),
        doc='User Direction')
    velocity_egu_s = pvproperty(
        name='VELO', dtype=ChannelType.DOUBLE, doc='Velocity (EGU/s)')
    _link_parent_attribute(display_precision, 'precision')
    _link_parent_attribute(high_operating_range, 'upper_ctrl_limit')
    _link_parent_attribute(low_operating_range, 'lower_ctrl_limit')
    _link_parent_attribute(archive_deadband, 'log_atol')
    _link_parent_attribute(monitor_deadband, 'value_atol')


@register_record
class PermissiveFields(RecordFieldGroup):
    _record_type = 'permissive'
    # value = pvproperty(name='VAL', dtype=ChannelType.LONG, doc='Status')
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    old_flag = pvproperty(
        name='OFLG', dtype=ChannelType.LONG, doc='Old Flag', read_only=True)
    old_status = pvproperty(
        name='OVAL', dtype=ChannelType.LONG, doc='Old Status', read_only=True)
    wait_flag = pvproperty(
        name='WFLG', dtype=ChannelType.LONG, doc='Wait Flag')
    button_label = pvproperty(
        name='LABL', dtype=ChannelType.CHAR, max_length=20, doc='Button Label')


@register_record
class ScalcoutFields(RecordFieldGroup):
    _record_type = 'scalcout'
    # value = pvproperty(name='VAL', dtype=ChannelType.DOUBLE, doc='Result')
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    calc_valid = pvproperty(
        name='CLCV', dtype=ChannelType.LONG, doc='CALC Valid')
    code_version = pvproperty(
        name='VERS',
        dtype=ChannelType.DOUBLE,
        doc='Code Version',
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
    ocal_valid = pvproperty(
        name='OCLV', dtype=ChannelType.LONG, doc='OCAL Valid')
    out_pv_status = pvproperty(
        name='OUTV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.scalcoutINAV.get_string_tuple(),
        doc='OUT PV Status',
        read_only=True)
    output_delay_active = pvproperty(
        name='DLYA',
        dtype=ChannelType.LONG,
        doc='Output Delay Active',
        read_only=True)
    output_value = pvproperty(
        name='OVAL', dtype=ChannelType.DOUBLE, doc='Output Value')
    output_string_value = pvproperty(
        name='OSV',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Output string value')
    previous_ovalue = pvproperty(
        name='POVL', dtype=ChannelType.DOUBLE, doc='Prev Value of OVAL')
    previous_value = pvproperty(
        name='PVAL', dtype=ChannelType.DOUBLE, doc='Previous Value')
    previous_output_string_value = pvproperty(
        name='POSV',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Previous output string value',
        read_only=True)
    previous_string_result = pvproperty(
        name='PSVL',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Previous string result',
        read_only=True)
    string_result = pvproperty(
        name='SVAL',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='String result')
    wait_for_completion = pvproperty(
        name='WAIT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.scalcoutWAIT.get_string_tuple(),
        doc='Wait for completion?')
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
    output_execute_delay = pvproperty(
        name='ODLY', dtype=ChannelType.DOUBLE, doc='Output Execute Delay')
    calculation = pvproperty(
        name='CALC', dtype=ChannelType.CHAR, max_length=80, doc='Calculation')
    output_calculation = pvproperty(
        name='OCAL',
        dtype=ChannelType.CHAR,
        max_length=80,
        doc='Output Calculation')
    output_data_opt = pvproperty(
        name='DOPT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.scalcoutDOPT.get_string_tuple(),
        doc='Output Data Opt')
    output_execute_opt = pvproperty(
        name='OOPT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.scalcoutOOPT.get_string_tuple(),
        doc='Output Execute Opt')
    event_to_issue = pvproperty(
        name='OEVT', dtype=ChannelType.LONG, doc='Event To Issue')
    archive_deadband = pvproperty(
        name='ADEL', dtype=ChannelType.DOUBLE, doc='Archive Deadband')
    display_precision = pvproperty(
        name='PREC', dtype=ChannelType.LONG, doc='Display Precision')
    high_operating_rng = pvproperty(
        name='HOPR', dtype=ChannelType.DOUBLE, doc='High Operating Rng')
    low_operating_range = pvproperty(
        name='LOPR', dtype=ChannelType.DOUBLE, doc='Low Operating Range')
    monitor_deadband = pvproperty(
        name='MDEL', dtype=ChannelType.DOUBLE, doc='Monitor Deadband')
    units_name = pvproperty(
        name='EGU', dtype=ChannelType.CHAR, max_length=16, doc='Units Name')
    invalid_output_action = pvproperty(
        name='IVOA',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuIvoa.get_string_tuple(),
        doc='INVALID output action')
    invalid_output_value = pvproperty(
        name='IVOV', dtype=ChannelType.DOUBLE, doc='INVALID output value')
    output_link = pvproperty(
        name='OUT', dtype=ChannelType.STRING, doc='Output Link')
    _link_parent_attribute(display_precision, 'precision')
    _link_parent_attribute(hihi_alarm_limit, 'upper_alarm_limit')
    _link_parent_attribute(high_alarm_limit, 'upper_warning_limit')
    _link_parent_attribute(low_alarm_limit, 'lower_warning_limit')
    _link_parent_attribute(lolo_alarm_limit, 'lower_alarm_limit')
    _link_parent_attribute(low_operating_range, 'lower_ctrl_limit')
    _link_parent_attribute(archive_deadband, 'log_atol')
    _link_parent_attribute(monitor_deadband, 'value_atol')


@register_record
class ScanparmFields(RecordFieldGroup):
    _record_type = 'scanparm'
    # value = pvproperty(name='VAL', dtype=ChannelType.DOUBLE, doc='Result')
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    code_version = pvproperty(
        name='VERS',
        dtype=ChannelType.DOUBLE,
        doc='Code Version',
        read_only=True)
    last_stepsize = pvproperty(
        name='LSTP',
        dtype=ChannelType.DOUBLE,
        doc='Last stepSize',
        read_only=True)
    maxpts = pvproperty(
        name='MP', dtype=ChannelType.LONG, doc='MaxPts', read_only=True)
    scanactive = pvproperty(
        name='ACT', dtype=ChannelType.LONG, doc='ScanActive', read_only=True)
    stepsize = pvproperty(
        name='STEP', dtype=ChannelType.DOUBLE, doc='StepSize', read_only=True)
    after_outlink = pvproperty(
        name='OAFT',
        dtype=ChannelType.STRING,
        doc='AFT OutLink',
        read_only=True)
    acquire_time_outlink = pvproperty(
        name='OAQT',
        dtype=ChannelType.STRING,
        doc='AQT OutLink',
        read_only=True)
    ar_outlink = pvproperty(
        name='OAR', dtype=ChannelType.STRING, doc='AR OutLink', read_only=True)
    after = pvproperty(
        name='AFT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sscanPASM.get_string_tuple(),
        doc='After')
    d1pv_outlink = pvproperty(
        name='ODPV',
        dtype=ChannelType.STRING,
        doc='D1PV OutLink',
        read_only=True)
    detpvname = pvproperty(
        name='DPV', dtype=ChannelType.CHAR, max_length=40, doc='DetPVName')
    ep_outlink = pvproperty(
        name='OEP', dtype=ChannelType.STRING, doc='EP OutLink', read_only=True)
    go_outlink = pvproperty(
        name='OGO', dtype=ChannelType.STRING, doc='GO OutLink', read_only=True)
    inlink = pvproperty(
        name='IACT', dtype=ChannelType.STRING, doc='InLink', read_only=True)
    load_outlink = pvproperty(
        name='OLOAD',
        dtype=ChannelType.STRING,
        doc='LOAD OutLink',
        read_only=True)
    mp_inlink = pvproperty(
        name='IMP', dtype=ChannelType.STRING, doc='MP InLink', read_only=True)
    np_outlink = pvproperty(
        name='ONP', dtype=ChannelType.STRING, doc='NP OutLink', read_only=True)
    p1pv_outlink = pvproperty(
        name='OPPV',
        dtype=ChannelType.STRING,
        doc='P1PV OutLink',
        read_only=True)
    pre_write_outlink = pvproperty(
        name='OPRE',
        dtype=ChannelType.STRING,
        doc='PRE-write OutLink',
        read_only=True)
    positionerpvname = pvproperty(
        name='PPV',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='PositionerPVName')
    r1pv_outlink = pvproperty(
        name='ORPV',
        dtype=ChannelType.STRING,
        doc='R1PV OutLink',
        read_only=True)
    readbackpvname = pvproperty(
        name='RPV',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='ReadbackPVName')
    sc_outlink = pvproperty(
        name='OSC', dtype=ChannelType.STRING, doc='SC OutLink', read_only=True)
    sm_outlink = pvproperty(
        name='OSM', dtype=ChannelType.STRING, doc='SM OutLink', read_only=True)
    sp_outlink = pvproperty(
        name='OSP', dtype=ChannelType.STRING, doc='SP OutLink', read_only=True)
    stepmode = pvproperty(
        name='SM',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sscanP1SM.get_string_tuple(),
        doc='StepMode')
    t1pv_outlink = pvproperty(
        name='OTPV',
        dtype=ChannelType.STRING,
        doc='T1PV OutLink',
        read_only=True)
    trigpvname = pvproperty(
        name='TPV', dtype=ChannelType.CHAR, max_length=40, doc='TrigPVName')
    absrel = pvproperty(
        name='AR',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sscanP1AR.get_string_tuple(),
        doc='absRel')
    acquire_time = pvproperty(
        name='AQT', dtype=ChannelType.DOUBLE, doc='Acquire time')
    display_precision = pvproperty(
        name='PREC', dtype=ChannelType.LONG, doc='Display Precision')
    endpos = pvproperty(name='EP', dtype=ChannelType.DOUBLE, doc='EndPos')
    go = pvproperty(name='GO', dtype=ChannelType.LONG, doc='Go')
    load = pvproperty(name='LOAD', dtype=ChannelType.LONG, doc='Load')
    pre_write_command = pvproperty(
        name='PRE', dtype=ChannelType.LONG, doc='PRE-write command')
    startcmd = pvproperty(name='SC', dtype=ChannelType.LONG, doc='StartCmd')
    startpos = pvproperty(name='SP', dtype=ChannelType.DOUBLE, doc='StartPos')
    npts = pvproperty(name='NP', dtype=ChannelType.LONG, doc='nPts')
    _link_parent_attribute(display_precision, 'precision')


@register_record
class SelFields(RecordFieldGroup):
    _record_type = 'sel'
    # value = pvproperty(
    #     name='VAL', dtype=ChannelType.DOUBLE, doc='Result', read_only=True)
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    index_value = pvproperty(
        name='SELN', dtype=ChannelType.LONG, doc='Index value')
    last_index_monitored = pvproperty(
        name='NLST',
        dtype=ChannelType.LONG,
        doc='Last Index Monitored',
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
    archive_deadband = pvproperty(
        name='ADEL', dtype=ChannelType.DOUBLE, doc='Archive Deadband')
    display_precision = pvproperty(
        name='PREC', dtype=ChannelType.LONG, doc='Display Precision')
    high_operating_rng = pvproperty(
        name='HOPR', dtype=ChannelType.DOUBLE, doc='High Operating Rng')
    low_operating_range = pvproperty(
        name='LOPR', dtype=ChannelType.DOUBLE, doc='Low Operating Range')
    monitor_deadband = pvproperty(
        name='MDEL', dtype=ChannelType.DOUBLE, doc='Monitor Deadband')
    units_name = pvproperty(
        name='EGU', dtype=ChannelType.CHAR, max_length=16, doc='Units Name')
    index_value_location = pvproperty(
        name='NVL', dtype=ChannelType.STRING, doc='Index Value Location')
    select_mechanism = pvproperty(
        name='SELM',
        dtype=ChannelType.ENUM,
        enum_strings=menus.selSELM.get_string_tuple(),
        doc='Select Mechanism')
    _link_parent_attribute(display_precision, 'precision')
    _link_parent_attribute(hihi_alarm_limit, 'upper_alarm_limit')
    _link_parent_attribute(high_alarm_limit, 'upper_warning_limit')
    _link_parent_attribute(low_alarm_limit, 'lower_warning_limit')
    _link_parent_attribute(lolo_alarm_limit, 'lower_alarm_limit')
    _link_parent_attribute(low_operating_range, 'lower_ctrl_limit')
    _link_parent_attribute(archive_deadband, 'log_atol')
    _link_parent_attribute(monitor_deadband, 'value_atol')


@register_record
class SeqFields(RecordFieldGroup):
    _record_type = 'seq'
    # value = pvproperty(
    #     name='VAL', dtype=ChannelType.LONG, doc='Used to trigger')
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    constant_input_1 = pvproperty(
        name='DO1', dtype=ChannelType.DOUBLE, doc='Constant input 1')
    constant_input_10 = pvproperty(
        name='DOA', dtype=ChannelType.DOUBLE, doc='Constant input 10')
    constant_input_2 = pvproperty(
        name='DO2', dtype=ChannelType.DOUBLE, doc='Constant input 2')
    constant_input_3 = pvproperty(
        name='DO3', dtype=ChannelType.DOUBLE, doc='Constant input 3')
    constant_input_4 = pvproperty(
        name='DO4', dtype=ChannelType.DOUBLE, doc='Constant input 4')
    constant_input_5 = pvproperty(
        name='DO5', dtype=ChannelType.DOUBLE, doc='Constant input 5')
    constant_input_6 = pvproperty(
        name='DO6', dtype=ChannelType.DOUBLE, doc='Constant input 6')
    constant_input_7 = pvproperty(
        name='DO7', dtype=ChannelType.DOUBLE, doc='Constant input 7')
    constant_input_8 = pvproperty(
        name='DO8', dtype=ChannelType.DOUBLE, doc='Constant input 8')
    constant_input_9 = pvproperty(
        name='DO9', dtype=ChannelType.DOUBLE, doc='Constant input 9')
    link_selection = pvproperty(
        name='SELN', dtype=ChannelType.LONG, doc='Link Selection')
    display_precision = pvproperty(
        name='PREC', dtype=ChannelType.LONG, doc='Display Precision')
    link_selection_loc = pvproperty(
        name='SELL', dtype=ChannelType.STRING, doc='Link Selection Loc')
    select_mechanism = pvproperty(
        name='SELM',
        dtype=ChannelType.ENUM,
        enum_strings=menus.seqSELM.get_string_tuple(),
        doc='Select Mechanism')
    delay_1 = pvproperty(name='DLY1', dtype=ChannelType.DOUBLE, doc='Delay 1')
    delay_2 = pvproperty(name='DLY2', dtype=ChannelType.DOUBLE, doc='Delay 2')
    delay_3 = pvproperty(name='DLY3', dtype=ChannelType.DOUBLE, doc='Delay 3')
    input_link_2 = pvproperty(
        name='DOL2', dtype=ChannelType.STRING, doc='Input link 2')
    input_link_3 = pvproperty(
        name='DOL3', dtype=ChannelType.STRING, doc='Input link 3')
    input_link1 = pvproperty(
        name='DOL1', dtype=ChannelType.STRING, doc='Input link1')
    output_link_1 = pvproperty(
        name='LNK1', dtype=ChannelType.STRING, doc='Output Link 1')
    output_link_2 = pvproperty(
        name='LNK2', dtype=ChannelType.STRING, doc='Output Link 2')
    output_link_3 = pvproperty(
        name='LNK3', dtype=ChannelType.STRING, doc='Output Link 3')
    delay_4 = pvproperty(name='DLY4', dtype=ChannelType.DOUBLE, doc='Delay 4')
    delay_5 = pvproperty(name='DLY5', dtype=ChannelType.DOUBLE, doc='Delay 5')
    delay_6 = pvproperty(name='DLY6', dtype=ChannelType.DOUBLE, doc='Delay 6')
    input_link_4 = pvproperty(
        name='DOL4', dtype=ChannelType.STRING, doc='Input link 4')
    input_link_5 = pvproperty(
        name='DOL5', dtype=ChannelType.STRING, doc='Input link 5')
    input_link_6 = pvproperty(
        name='DOL6', dtype=ChannelType.STRING, doc='Input link 6')
    output_link_4 = pvproperty(
        name='LNK4', dtype=ChannelType.STRING, doc='Output Link 4')
    output_link_5 = pvproperty(
        name='LNK5', dtype=ChannelType.STRING, doc='Output Link 5')
    output_link_6 = pvproperty(
        name='LNK6', dtype=ChannelType.STRING, doc='Output Link 6')
    delay_10 = pvproperty(
        name='DLYA', dtype=ChannelType.DOUBLE, doc='Delay 10')
    delay_7 = pvproperty(name='DLY7', dtype=ChannelType.DOUBLE, doc='Delay 7')
    delay_8 = pvproperty(name='DLY8', dtype=ChannelType.DOUBLE, doc='Delay 8')
    delay_9 = pvproperty(name='DLY9', dtype=ChannelType.DOUBLE, doc='Delay 9')
    input_link_10 = pvproperty(
        name='DOLA', dtype=ChannelType.STRING, doc='Input link 10')
    input_link_7 = pvproperty(
        name='DOL7', dtype=ChannelType.STRING, doc='Input link 7')
    input_link_8 = pvproperty(
        name='DOL8', dtype=ChannelType.STRING, doc='Input link 8')
    input_link_9 = pvproperty(
        name='DOL9', dtype=ChannelType.STRING, doc='Input link 9')
    output_link_10 = pvproperty(
        name='LNKA', dtype=ChannelType.STRING, doc='Output Link 10')
    output_link_7 = pvproperty(
        name='LNK7', dtype=ChannelType.STRING, doc='Output Link 7')
    output_link_8 = pvproperty(
        name='LNK8', dtype=ChannelType.STRING, doc='Output Link 8')
    output_link_9 = pvproperty(
        name='LNK9', dtype=ChannelType.STRING, doc='Output Link 9')
    _link_parent_attribute(display_precision, 'precision')


@register_record
class SscanFields(RecordFieldGroup):
    _record_type = 'sscan'
    # value = pvproperty(name='VAL', dtype=ChannelType.DOUBLE, doc='Value Field')
    a1_pv_status = pvproperty(
        name='A1NV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sscanP1NV.get_string_tuple(),
        doc='A1  PV Status',
        read_only=True)
    abort_right_now = pvproperty(
        name='KILL',
        dtype=ChannelType.CHAR,
        doc='Abort right now',
        read_only=True)
    after_scan_pv_status = pvproperty(
        name='ASNV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sscanP1NV.get_string_tuple(),
        doc='After Scan PV Status',
        read_only=True)
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    auto_wait_count = pvproperty(
        name='AWCT', dtype=ChannelType.LONG, doc='Auto WCNT')
    beforescan_pv_status = pvproperty(
        name='BSNV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sscanP1NV.get_string_tuple(),
        doc='BeforeScan PV Status',
        read_only=True)
    buffered_current_point = pvproperty(
        name='BCPT',
        dtype=ChannelType.LONG,
        doc='Bufferred Current Point',
        read_only=True)
    code_version = pvproperty(
        name='VERS',
        dtype=ChannelType.DOUBLE,
        doc='Code Version',
        read_only=True)
    command_field = pvproperty(
        name='CMND',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sscanCMND.get_string_tuple(),
        doc='Command Field')
    current_point = pvproperty(
        name='CPT',
        dtype=ChannelType.LONG,
        doc='Current Point',
        read_only=True)
    desired_point = pvproperty(
        name='DPT', dtype=ChannelType.LONG, doc='Desired Point')
    execute_scan = pvproperty(
        name='EXSC', dtype=ChannelType.LONG, doc='Execute Scan')
    go_pause_control = pvproperty(
        name='PAUS',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sscanPAUS.get_string_tuple(),
        doc='Go/Pause control')
    internal_execscan = pvproperty(
        name='XSC',
        dtype=ChannelType.LONG,
        doc='Internal execScan',
        read_only=True)
    last_value_of_go_pause = pvproperty(
        name='LPAU',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sscanPAUS.get_string_tuple(),
        doc='Last value of Go/Pause',
        read_only=True)
    operator_alert = pvproperty(
        name='ALRT',
        dtype=ChannelType.CHAR,
        doc='Operator Alert',
        read_only=True)
    point_oflast_posting = pvproperty(
        name='PCPT',
        dtype=ChannelType.LONG,
        doc='Point ofLast Posting',
        read_only=True)
    previous_xscan = pvproperty(
        name='PXSC',
        dtype=ChannelType.CHAR,
        doc='Previous XScan',
        read_only=True)
    record_state_msg = pvproperty(
        name='SMSG',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Record State Msg')
    reference_detector = pvproperty(
        name='REFD', dtype=ChannelType.LONG, doc='Reference detector')
    scan_data_ready = pvproperty(
        name='DATA',
        dtype=ChannelType.LONG,
        doc='Scan data ready',
        read_only=True)
    scan_in_progress = pvproperty(
        name='BUSY',
        dtype=ChannelType.CHAR,
        doc='Scan in progress',
        read_only=True)
    scan_phase = pvproperty(
        name='FAZE',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sscanFAZE.get_string_tuple(),
        doc='Scan phase',
        read_only=True)
    wait_count = pvproperty(
        name='WCNT', dtype=ChannelType.LONG, doc='Wait count)', read_only=True)
    wait_for_client_s = pvproperty(
        name='WAIT', dtype=ChannelType.LONG, doc='Wait for client(s)')
    waiting_for_client_s = pvproperty(
        name='WTNG',
        dtype=ChannelType.LONG,
        doc='Waiting for client(s)',
        read_only=True)
    waiting_for_data_storage_client = pvproperty(
        name='AWAIT',
        dtype=ChannelType.LONG,
        doc='Waiting for data-storage client')
    after_scan_pv_name = pvproperty(
        name='ASPV',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='After Scan   PV Name')
    array_read_trigger_1_pv_name = pvproperty(
        name='A1PV',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Array-read trigger 1 PV Name')
    before_scan_pv_name = pvproperty(
        name='BSPV',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Before Scan  PV Name')
    acquisition_mode = pvproperty(
        name='ACQM',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sscanACQM.get_string_tuple(),
        doc='Acquisition mode')
    acquisition_type = pvproperty(
        name='ACQT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sscanACQT.get_string_tuple(),
        doc='Acquisition type')
    copy_last_pt_thru = pvproperty(
        name='COPYTO', dtype=ChannelType.LONG, doc='Copy Last Pt Thru')
    data_state = pvproperty(
        name='DSTATE',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sscanDSTATE.get_string_tuple(),
        doc='Data state',
        read_only=True)
    a1_command = pvproperty(
        name='A1CD', dtype=ChannelType.DOUBLE, doc='A1 Cmnd')
    after_scan_command = pvproperty(
        name='ASCD', dtype=ChannelType.DOUBLE, doc='After Scan Cmnd')
    array_post_time_period = pvproperty(
        name='ATIME', dtype=ChannelType.DOUBLE, doc='Array post time period')
    autowait_for_data_storage_client = pvproperty(
        name='AAWAIT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sscanNOYES.get_string_tuple(),
        doc='AutoWait for data-storage client')
    before_scan_command = pvproperty(
        name='BSCD', dtype=ChannelType.DOUBLE, doc='Before Scan Cmnd')
    detector_settling_delay = pvproperty(
        name='DDLY', dtype=ChannelType.DOUBLE, doc='Detector-settling delay')
    pause_resume_delay = pvproperty(
        name='RDLY', dtype=ChannelType.DOUBLE, doc='Pause resume delay')
    positioner_settling_delay = pvproperty(
        name='PDLY', dtype=ChannelType.DOUBLE, doc='Positioner-settling delay')
    wait_for_completion = pvproperty(
        name='ASWAIT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sscanLINKWAIT.get_string_tuple(),
        doc='Wait for completion?')
    wait_for_completion_bswait = pvproperty(
        name='BSWAIT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sscanLINKWAIT.get_string_tuple(),
        doc='Wait for completion?')
    max_of_points = pvproperty(
        name='MPTS',
        dtype=ChannelType.LONG,
        doc='Max # of Points',
        read_only=True)
    number_of_points = pvproperty(
        name='NPTS', dtype=ChannelType.LONG, doc='Number of Points')
    after_scan_mode = pvproperty(
        name='PASM',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sscanPASM.get_string_tuple(),
        doc='After Scan Mode')
    freeze_flag_override = pvproperty(
        name='FFO',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sscanFFO.get_string_tuple(),
        doc='Freeze Flag Override')
    freeze_num_of_points = pvproperty(
        name='FPTS',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sscanFPTS.get_string_tuple(),
        doc='Freeze Num of Points')


@register_record
class SseqFields(RecordFieldGroup):
    _record_type = 'sseq'
    # value = pvproperty(
    #     name='VAL', dtype=ChannelType.LONG, doc='Used to trigger')
    ix1 = pvproperty(name='IX1', dtype=ChannelType.LONG, read_only=True)
    ix2 = pvproperty(name='IX2', dtype=ChannelType.LONG, read_only=True)
    ix3 = pvproperty(name='IX3', dtype=ChannelType.LONG, read_only=True)
    ix4 = pvproperty(name='IX4', dtype=ChannelType.LONG, read_only=True)
    ix5 = pvproperty(name='IX5', dtype=ChannelType.LONG, read_only=True)
    ix6 = pvproperty(name='IX6', dtype=ChannelType.LONG, read_only=True)
    ix7 = pvproperty(name='IX7', dtype=ChannelType.LONG, read_only=True)
    ix8 = pvproperty(name='IX8', dtype=ChannelType.LONG, read_only=True)
    ix9 = pvproperty(name='IX9', dtype=ChannelType.LONG, read_only=True)
    ixa = pvproperty(
        name='IXA',
        dtype=ChannelType.LONG,
    )
    werr1 = pvproperty(name='WERR1', dtype=ChannelType.LONG, read_only=True)
    werr2 = pvproperty(name='WERR2', dtype=ChannelType.LONG, read_only=True)
    werr3 = pvproperty(name='WERR3', dtype=ChannelType.LONG, read_only=True)
    werr4 = pvproperty(name='WERR4', dtype=ChannelType.LONG, read_only=True)
    werr5 = pvproperty(name='WERR5', dtype=ChannelType.LONG, read_only=True)
    werr6 = pvproperty(name='WERR6', dtype=ChannelType.LONG, read_only=True)
    werr7 = pvproperty(name='WERR7', dtype=ChannelType.LONG, read_only=True)
    werr8 = pvproperty(name='WERR8', dtype=ChannelType.LONG, read_only=True)
    werr9 = pvproperty(name='WERR9', dtype=ChannelType.LONG, read_only=True)
    werra = pvproperty(name='WERRA', dtype=ChannelType.LONG, read_only=True)
    wtg1 = pvproperty(name='WTG1', dtype=ChannelType.LONG, read_only=True)
    wtg2 = pvproperty(name='WTG2', dtype=ChannelType.LONG, read_only=True)
    wtg3 = pvproperty(name='WTG3', dtype=ChannelType.LONG, read_only=True)
    wtg4 = pvproperty(name='WTG4', dtype=ChannelType.LONG, read_only=True)
    wtg5 = pvproperty(name='WTG5', dtype=ChannelType.LONG, read_only=True)
    wtg6 = pvproperty(name='WTG6', dtype=ChannelType.LONG, read_only=True)
    wtg7 = pvproperty(name='WTG7', dtype=ChannelType.LONG, read_only=True)
    wtg8 = pvproperty(name='WTG8', dtype=ChannelType.LONG, read_only=True)
    wtg9 = pvproperty(name='WTG9', dtype=ChannelType.LONG, read_only=True)
    wtga = pvproperty(
        name='WTGA',
        dtype=ChannelType.LONG,
    )
    abort_sequence = pvproperty(
        name='ABORT', dtype=ChannelType.LONG, doc='Abort sequence')
    aborting = pvproperty(
        name='ABORTING', dtype=ChannelType.LONG, doc='Aborting')
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    dol_link_status = pvproperty(
        name='DOL1V',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sseqLNKV.get_string_tuple(),
        doc='DOL LINK Status',
        read_only=True)
    dol_link_status_dol2v = pvproperty(
        name='DOL2V',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sseqLNKV.get_string_tuple(),
        doc='DOL LINK Status',
        read_only=True)
    dol_link_status_dol3v = pvproperty(
        name='DOL3V',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sseqLNKV.get_string_tuple(),
        doc='DOL LINK Status',
        read_only=True)
    dol_link_status_dol4v = pvproperty(
        name='DOL4V',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sseqLNKV.get_string_tuple(),
        doc='DOL LINK Status',
        read_only=True)
    dol_link_status_dol5v = pvproperty(
        name='DOL5V',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sseqLNKV.get_string_tuple(),
        doc='DOL LINK Status',
        read_only=True)
    dol_link_status_dol6v = pvproperty(
        name='DOL6V',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sseqLNKV.get_string_tuple(),
        doc='DOL LINK Status',
        read_only=True)
    dol_link_status_dol7v = pvproperty(
        name='DOL7V',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sseqLNKV.get_string_tuple(),
        doc='DOL LINK Status',
        read_only=True)
    dol_link_status_dol8v = pvproperty(
        name='DOL8V',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sseqLNKV.get_string_tuple(),
        doc='DOL LINK Status',
        read_only=True)
    dol_link_status_dol9v = pvproperty(
        name='DOL9V',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sseqLNKV.get_string_tuple(),
        doc='DOL LINK Status',
        read_only=True)
    dol_link_status_dolav = pvproperty(
        name='DOLAV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sseqLNKV.get_string_tuple(),
        doc='DOL LINK Status',
        read_only=True)
    dol_link_type = pvproperty(
        name='DT1',
        dtype=ChannelType.LONG,
        doc='DOL link type',
        read_only=True)
    dol_link_type_dt2 = pvproperty(
        name='DT2',
        dtype=ChannelType.LONG,
        doc='DOL link type',
        read_only=True)
    dol_link_type_dt3 = pvproperty(
        name='DT3',
        dtype=ChannelType.LONG,
        doc='DOL link type',
        read_only=True)
    dol_link_type_dt4 = pvproperty(
        name='DT4',
        dtype=ChannelType.LONG,
        doc='DOL link type',
        read_only=True)
    dol_link_type_dt5 = pvproperty(
        name='DT5',
        dtype=ChannelType.LONG,
        doc='DOL link type',
        read_only=True)
    dol_link_type_dt6 = pvproperty(
        name='DT6',
        dtype=ChannelType.LONG,
        doc='DOL link type',
        read_only=True)
    dol_link_type_dt7 = pvproperty(
        name='DT7',
        dtype=ChannelType.LONG,
        doc='DOL link type',
        read_only=True)
    dol_link_type_dt8 = pvproperty(
        name='DT8',
        dtype=ChannelType.LONG,
        doc='DOL link type',
        read_only=True)
    dol_link_type_dt9 = pvproperty(
        name='DT9',
        dtype=ChannelType.LONG,
        doc='DOL link type',
        read_only=True)
    dol_link_type_dta = pvproperty(
        name='DTA',
        dtype=ChannelType.LONG,
        doc='DOL link type',
        read_only=True)
    lnk_link_status = pvproperty(
        name='LNK1V',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sseqLNKV.get_string_tuple(),
        doc='LNK LINK Status',
        read_only=True)
    lnk_link_status_lnk2v = pvproperty(
        name='LNK2V',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sseqLNKV.get_string_tuple(),
        doc='LNK LINK Status',
        read_only=True)
    lnk_link_status_lnk3v = pvproperty(
        name='LNK3V',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sseqLNKV.get_string_tuple(),
        doc='LNK LINK Status',
        read_only=True)
    lnk_link_status_lnk4v = pvproperty(
        name='LNK4V',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sseqLNKV.get_string_tuple(),
        doc='LNK LINK Status',
        read_only=True)
    lnk_link_status_lnk5v = pvproperty(
        name='LNK5V',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sseqLNKV.get_string_tuple(),
        doc='LNK LINK Status',
        read_only=True)
    lnk_link_status_lnk6v = pvproperty(
        name='LNK6V',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sseqLNKV.get_string_tuple(),
        doc='LNK LINK Status',
        read_only=True)
    lnk_link_status_lnk7v = pvproperty(
        name='LNK7V',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sseqLNKV.get_string_tuple(),
        doc='LNK LINK Status',
        read_only=True)
    lnk_link_status_lnk8v = pvproperty(
        name='LNK8V',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sseqLNKV.get_string_tuple(),
        doc='LNK LINK Status',
        read_only=True)
    lnk_link_status_lnk9v = pvproperty(
        name='LNK9V',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sseqLNKV.get_string_tuple(),
        doc='LNK LINK Status',
        read_only=True)
    lnk_link_status_lnkav = pvproperty(
        name='LNKAV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sseqLNKV.get_string_tuple(),
        doc='LNK LINK Status',
        read_only=True)
    lnk_link_type = pvproperty(
        name='LT1',
        dtype=ChannelType.LONG,
        doc='LNK link type',
        read_only=True)
    lnk_link_type_lt2 = pvproperty(
        name='LT2',
        dtype=ChannelType.LONG,
        doc='LNK link type',
        read_only=True)
    lnk_link_type_lt3 = pvproperty(
        name='LT3',
        dtype=ChannelType.LONG,
        doc='LNK link type',
        read_only=True)
    lnk_link_type_lt4 = pvproperty(
        name='LT4',
        dtype=ChannelType.LONG,
        doc='LNK link type',
        read_only=True)
    lnk_link_type_lt5 = pvproperty(
        name='LT5',
        dtype=ChannelType.LONG,
        doc='LNK link type',
        read_only=True)
    lnk_link_type_lt6 = pvproperty(
        name='LT6',
        dtype=ChannelType.LONG,
        doc='LNK link type',
        read_only=True)
    lnk_link_type_lt7 = pvproperty(
        name='LT7',
        dtype=ChannelType.LONG,
        doc='LNK link type',
        read_only=True)
    lnk_link_type_lt8 = pvproperty(
        name='LT8',
        dtype=ChannelType.LONG,
        doc='LNK link type',
        read_only=True)
    lnk_link_type_lt9 = pvproperty(
        name='LT9',
        dtype=ChannelType.LONG,
        doc='LNK link type',
        read_only=True)
    lnk_link_type_lta = pvproperty(
        name='LTA',
        dtype=ChannelType.LONG,
        doc='LNK link type',
        read_only=True)
    link_selection = pvproperty(
        name='SELN', dtype=ChannelType.LONG, doc='Link Selection')
    sequence_active = pvproperty(
        name='BUSY',
        dtype=ChannelType.LONG,
        doc='Sequence active',
        read_only=True)
    display_precision = pvproperty(
        name='PREC', dtype=ChannelType.LONG, doc='Display Precision')
    link_selection_loc = pvproperty(
        name='SELL', dtype=ChannelType.STRING, doc='Link Selection Loc')
    select_mechanism = pvproperty(
        name='SELM',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sseqSELM.get_string_tuple(),
        doc='Select Mechanism')
    constant_input_1 = pvproperty(
        name='DO1', dtype=ChannelType.DOUBLE, doc='Constant input 1')
    constant_input_10 = pvproperty(
        name='DOA', dtype=ChannelType.DOUBLE, doc='Constant input 10')
    constant_input_2 = pvproperty(
        name='DO2', dtype=ChannelType.DOUBLE, doc='Constant input 2')
    constant_input_3 = pvproperty(
        name='DO3', dtype=ChannelType.DOUBLE, doc='Constant input 3')
    constant_input_4 = pvproperty(
        name='DO4', dtype=ChannelType.DOUBLE, doc='Constant input 4')
    constant_input_5 = pvproperty(
        name='DO5', dtype=ChannelType.DOUBLE, doc='Constant input 5')
    constant_input_6 = pvproperty(
        name='DO6', dtype=ChannelType.DOUBLE, doc='Constant input 6')
    constant_input_7 = pvproperty(
        name='DO7', dtype=ChannelType.DOUBLE, doc='Constant input 7')
    constant_input_8 = pvproperty(
        name='DO8', dtype=ChannelType.DOUBLE, doc='Constant input 8')
    constant_input_9 = pvproperty(
        name='DO9', dtype=ChannelType.DOUBLE, doc='Constant input 9')
    delay_1 = pvproperty(name='DLY1', dtype=ChannelType.DOUBLE, doc='Delay 1')
    delay_2 = pvproperty(name='DLY2', dtype=ChannelType.DOUBLE, doc='Delay 2')
    delay_3 = pvproperty(name='DLY3', dtype=ChannelType.DOUBLE, doc='Delay 3')
    input_link_2 = pvproperty(
        name='DOL2', dtype=ChannelType.STRING, doc='Input link 2')
    input_link_3 = pvproperty(
        name='DOL3', dtype=ChannelType.STRING, doc='Input link 3')
    input_link1 = pvproperty(
        name='DOL1', dtype=ChannelType.STRING, doc='Input link1')
    output_link_1 = pvproperty(
        name='LNK1', dtype=ChannelType.STRING, doc='Output Link 1')
    output_link_2 = pvproperty(
        name='LNK2', dtype=ChannelType.STRING, doc='Output Link 2')
    output_link_3 = pvproperty(
        name='LNK3', dtype=ChannelType.STRING, doc='Output Link 3')
    string_value_1 = pvproperty(
        name='STR1',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='String value 1')
    string_value_2 = pvproperty(
        name='STR2',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='String value 2')
    string_value_3 = pvproperty(
        name='STR3',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='String value 3')
    string_value_4 = pvproperty(
        name='STR4',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='String value 4')
    string_value_5 = pvproperty(
        name='STR5',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='String value 5')
    string_value_6 = pvproperty(
        name='STR6',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='String value 6')
    string_value_7 = pvproperty(
        name='STR7',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='String value 7')
    string_value_8 = pvproperty(
        name='STR8',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='String value 8')
    string_value_9 = pvproperty(
        name='STR9',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='String value 9')
    string_value_a = pvproperty(
        name='STRA',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='String value A')
    wait_for_completion = pvproperty(
        name='WAIT1',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sseqWAIT.get_string_tuple(),
        doc='Wait for completion?')
    wait_for_completion_wait2 = pvproperty(
        name='WAIT2',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sseqWAIT.get_string_tuple(),
        doc='Wait for completion?')
    wait_for_completion_wait3 = pvproperty(
        name='WAIT3',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sseqWAIT.get_string_tuple(),
        doc='Wait for completion?')
    wait_for_completion_wait4 = pvproperty(
        name='WAIT4',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sseqWAIT.get_string_tuple(),
        doc='Wait for completion?')
    wait_for_completion_wait5 = pvproperty(
        name='WAIT5',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sseqWAIT.get_string_tuple(),
        doc='Wait for completion?')
    wait_for_completion_wait6 = pvproperty(
        name='WAIT6',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sseqWAIT.get_string_tuple(),
        doc='Wait for completion?')
    wait_for_completion_wait7 = pvproperty(
        name='WAIT7',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sseqWAIT.get_string_tuple(),
        doc='Wait for completion?')
    wait_for_completion_wait8 = pvproperty(
        name='WAIT8',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sseqWAIT.get_string_tuple(),
        doc='Wait for completion?')
    wait_for_completion_wait9 = pvproperty(
        name='WAIT9',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sseqWAIT.get_string_tuple(),
        doc='Wait for completion?')
    wait_for_completion_waita = pvproperty(
        name='WAITA',
        dtype=ChannelType.ENUM,
        enum_strings=menus.sseqWAIT.get_string_tuple(),
        doc='Wait for completion?')
    delay_4 = pvproperty(name='DLY4', dtype=ChannelType.DOUBLE, doc='Delay 4')
    delay_5 = pvproperty(name='DLY5', dtype=ChannelType.DOUBLE, doc='Delay 5')
    delay_6 = pvproperty(name='DLY6', dtype=ChannelType.DOUBLE, doc='Delay 6')
    input_link_4 = pvproperty(
        name='DOL4', dtype=ChannelType.STRING, doc='Input link 4')
    input_link_5 = pvproperty(
        name='DOL5', dtype=ChannelType.STRING, doc='Input link 5')
    input_link_6 = pvproperty(
        name='DOL6', dtype=ChannelType.STRING, doc='Input link 6')
    output_link_4 = pvproperty(
        name='LNK4', dtype=ChannelType.STRING, doc='Output Link 4')
    output_link_5 = pvproperty(
        name='LNK5', dtype=ChannelType.STRING, doc='Output Link 5')
    output_link_6 = pvproperty(
        name='LNK6', dtype=ChannelType.STRING, doc='Output Link 6')
    delay_10 = pvproperty(
        name='DLYA', dtype=ChannelType.DOUBLE, doc='Delay 10')
    delay_7 = pvproperty(name='DLY7', dtype=ChannelType.DOUBLE, doc='Delay 7')
    delay_8 = pvproperty(name='DLY8', dtype=ChannelType.DOUBLE, doc='Delay 8')
    delay_9 = pvproperty(name='DLY9', dtype=ChannelType.DOUBLE, doc='Delay 9')
    input_link_10 = pvproperty(
        name='DOLA', dtype=ChannelType.STRING, doc='Input link 10')
    input_link_7 = pvproperty(
        name='DOL7', dtype=ChannelType.STRING, doc='Input link 7')
    input_link_8 = pvproperty(
        name='DOL8', dtype=ChannelType.STRING, doc='Input link 8')
    input_link_9 = pvproperty(
        name='DOL9', dtype=ChannelType.STRING, doc='Input link 9')
    output_link_10 = pvproperty(
        name='LNKA', dtype=ChannelType.STRING, doc='Output Link 10')
    output_link_7 = pvproperty(
        name='LNK7', dtype=ChannelType.STRING, doc='Output Link 7')
    output_link_8 = pvproperty(
        name='LNK8', dtype=ChannelType.STRING, doc='Output Link 8')
    output_link_9 = pvproperty(
        name='LNK9', dtype=ChannelType.STRING, doc='Output Link 9')
    _link_parent_attribute(display_precision, 'precision')


@register_record
class StateFields(RecordFieldGroup):
    _record_type = 'state'
    # value = pvproperty(
    #     name='VAL', dtype=ChannelType.CHAR, max_length=20, doc='Value')
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    prev_value = pvproperty(
        name='OVAL',
        dtype=ChannelType.CHAR,
        max_length=20,
        doc='Prev Value',
        read_only=True)


@register_record
class StringinFields(RecordFieldGroup):
    _record_type = 'stringin'
    # value = pvproperty(
    #     name='VAL', dtype=ChannelType.CHAR, max_length=40, doc='Current Value')
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    previous_value = pvproperty(
        name='OVAL',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Previous Value',
        read_only=True)
    simulation_mode = pvproperty(
        name='SIMM',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuYesNo.get_string_tuple(),
        doc='Simulation Mode')
    simulation_value = pvproperty(
        name='SVAL',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Simulation Value')
    post_archive_monitors = pvproperty(
        name='APST',
        dtype=ChannelType.ENUM,
        enum_strings=menus.stringinPOST.get_string_tuple(),
        doc='Post Archive Monitors')
    post_value_monitors = pvproperty(
        name='MPST',
        dtype=ChannelType.ENUM,
        enum_strings=menus.stringinPOST.get_string_tuple(),
        doc='Post Value Monitors')
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


@register_record
class StringoutFields(RecordFieldGroup):
    _record_type = 'stringout'
    # value = pvproperty(
    #     name='VAL', dtype=ChannelType.CHAR, max_length=40, doc='Current Value')
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    previous_value = pvproperty(
        name='OVAL',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Previous Value',
        read_only=True)
    simulation_mode = pvproperty(
        name='SIMM',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuYesNo.get_string_tuple(),
        doc='Simulation Mode')
    post_archive_monitors = pvproperty(
        name='APST',
        dtype=ChannelType.ENUM,
        enum_strings=menus.stringoutPOST.get_string_tuple(),
        doc='Post Archive Monitors')
    post_value_monitors = pvproperty(
        name='MPST',
        dtype=ChannelType.ENUM,
        enum_strings=menus.stringoutPOST.get_string_tuple(),
        doc='Post Value Monitors')
    sim_mode_location = pvproperty(
        name='SIML', dtype=ChannelType.STRING, doc='Sim Mode Location')
    sim_output_specifctn = pvproperty(
        name='SIOL', dtype=ChannelType.STRING, doc='Sim Output Specifctn')
    sim_mode_alarm_svrty = pvproperty(
        name='SIMS',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Sim mode Alarm Svrty')
    desired_output_loc = pvproperty(
        name='DOL', dtype=ChannelType.STRING, doc='Desired Output Loc')
    invalid_output_action = pvproperty(
        name='IVOA',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuIvoa.get_string_tuple(),
        doc='INVALID output action')
    invalid_output_value = pvproperty(
        name='IVOV',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='INVALID output value')
    output_mode_select = pvproperty(
        name='OMSL',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuOmsl.get_string_tuple(),
        doc='Output Mode Select')
    output_specification = pvproperty(
        name='OUT', dtype=ChannelType.STRING, doc='Output Specification')


@register_record
class SubFields(RecordFieldGroup):
    _record_type = 'sub'
    # value = pvproperty(name='VAL', dtype=ChannelType.DOUBLE, doc='Result')
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
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
    last_value_monitored = pvproperty(
        name='MLST',
        dtype=ChannelType.DOUBLE,
        doc='Last Value Monitored',
        read_only=True)
    prev_value_of_a = pvproperty(
        name='LA',
        dtype=ChannelType.DOUBLE,
        doc='Prev Value of A',
        read_only=True)
    prev_value_of_b = pvproperty(
        name='LB',
        dtype=ChannelType.DOUBLE,
        doc='Prev Value of B',
        read_only=True)
    prev_value_of_c = pvproperty(
        name='LC',
        dtype=ChannelType.DOUBLE,
        doc='Prev Value of C',
        read_only=True)
    prev_value_of_d = pvproperty(
        name='LD',
        dtype=ChannelType.DOUBLE,
        doc='Prev Value of D',
        read_only=True)
    prev_value_of_e = pvproperty(
        name='LE',
        dtype=ChannelType.DOUBLE,
        doc='Prev Value of E',
        read_only=True)
    prev_value_of_f = pvproperty(
        name='LF',
        dtype=ChannelType.DOUBLE,
        doc='Prev Value of F',
        read_only=True)
    prev_value_of_g = pvproperty(
        name='LG',
        dtype=ChannelType.DOUBLE,
        doc='Prev Value of G',
        read_only=True)
    prev_value_of_h = pvproperty(
        name='LH',
        dtype=ChannelType.DOUBLE,
        doc='Prev Value of H',
        read_only=True)
    prev_value_of_i = pvproperty(
        name='LI',
        dtype=ChannelType.DOUBLE,
        doc='Prev Value of I',
        read_only=True)
    prev_value_of_j = pvproperty(
        name='LJ',
        dtype=ChannelType.DOUBLE,
        doc='Prev Value of J',
        read_only=True)
    prev_value_of_k = pvproperty(
        name='LK',
        dtype=ChannelType.DOUBLE,
        doc='Prev Value of K',
        read_only=True)
    prev_value_of_l = pvproperty(
        name='LL',
        dtype=ChannelType.DOUBLE,
        doc='Prev Value of L',
        read_only=True)
    value_of_input_a = pvproperty(
        name='A', dtype=ChannelType.DOUBLE, doc='Value of Input A')
    value_of_input_b = pvproperty(
        name='B', dtype=ChannelType.DOUBLE, doc='Value of Input B')
    value_of_input_c = pvproperty(
        name='C', dtype=ChannelType.DOUBLE, doc='Value of Input C')
    value_of_input_d = pvproperty(
        name='D', dtype=ChannelType.DOUBLE, doc='Value of Input D')
    value_of_input_e = pvproperty(
        name='E', dtype=ChannelType.DOUBLE, doc='Value of Input E')
    value_of_input_f = pvproperty(
        name='F', dtype=ChannelType.DOUBLE, doc='Value of Input F')
    value_of_input_g = pvproperty(
        name='G', dtype=ChannelType.DOUBLE, doc='Value of Input G')
    value_of_input_h = pvproperty(
        name='H', dtype=ChannelType.DOUBLE, doc='Value of Input H')
    value_of_input_i = pvproperty(
        name='I', dtype=ChannelType.DOUBLE, doc='Value of Input I')
    value_of_input_j = pvproperty(
        name='J', dtype=ChannelType.DOUBLE, doc='Value of Input J')
    value_of_input_k = pvproperty(
        name='K', dtype=ChannelType.DOUBLE, doc='Value of Input K')
    value_of_input_l = pvproperty(
        name='L', dtype=ChannelType.DOUBLE, doc='Value of Input L')
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
    archive_deadband = pvproperty(
        name='ADEL', dtype=ChannelType.DOUBLE, doc='Archive Deadband')
    display_precision = pvproperty(
        name='PREC', dtype=ChannelType.LONG, doc='Display Precision')
    high_operating_rng = pvproperty(
        name='HOPR', dtype=ChannelType.DOUBLE, doc='High Operating Rng')
    low_operating_range = pvproperty(
        name='LOPR', dtype=ChannelType.DOUBLE, doc='Low Operating Range')
    monitor_deadband = pvproperty(
        name='MDEL', dtype=ChannelType.DOUBLE, doc='Monitor Deadband')
    units_name = pvproperty(
        name='EGU', dtype=ChannelType.CHAR, max_length=16, doc='Units Name')
    input_a = pvproperty(name='INPA', dtype=ChannelType.STRING, doc='Input A')
    input_b = pvproperty(name='INPB', dtype=ChannelType.STRING, doc='Input B')
    input_c = pvproperty(name='INPC', dtype=ChannelType.STRING, doc='Input C')
    input_d = pvproperty(name='INPD', dtype=ChannelType.STRING, doc='Input D')
    input_e = pvproperty(name='INPE', dtype=ChannelType.STRING, doc='Input E')
    input_f = pvproperty(name='INPF', dtype=ChannelType.STRING, doc='Input F')
    input_g = pvproperty(name='INPG', dtype=ChannelType.STRING, doc='Input G')
    input_h = pvproperty(name='INPH', dtype=ChannelType.STRING, doc='Input H')
    input_i = pvproperty(name='INPI', dtype=ChannelType.STRING, doc='Input I')
    input_j = pvproperty(name='INPJ', dtype=ChannelType.STRING, doc='Input J')
    input_k = pvproperty(name='INPK', dtype=ChannelType.STRING, doc='Input K')
    input_l = pvproperty(name='INPL', dtype=ChannelType.STRING, doc='Input L')
    bad_return_severity = pvproperty(
        name='BRSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Bad Return Severity')
    init_routine_name = pvproperty(
        name='INAM',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Init Routine Name',
        read_only=True)
    subroutine_name = pvproperty(
        name='SNAM',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Subroutine Name')
    _link_parent_attribute(display_precision, 'precision')
    _link_parent_attribute(hihi_alarm_limit, 'upper_alarm_limit')
    _link_parent_attribute(high_alarm_limit, 'upper_warning_limit')
    _link_parent_attribute(low_alarm_limit, 'lower_warning_limit')
    _link_parent_attribute(lolo_alarm_limit, 'lower_alarm_limit')
    _link_parent_attribute(low_operating_range, 'lower_ctrl_limit')
    _link_parent_attribute(archive_deadband, 'log_atol')
    _link_parent_attribute(monitor_deadband, 'value_atol')


@register_record
class SubarrayFields(RecordFieldGroup):
    _record_type = 'subArray'
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    busy_indicator = pvproperty(
        name='BUSY',
        dtype=ChannelType.LONG,
        doc='Busy Indicator',
        read_only=True)
    number_elements_read = pvproperty(
        name='NORD',
        dtype=ChannelType.LONG,
        doc='Number elements read',
        read_only=True)
    field_type_of_value = pvproperty(
        name='FTVL',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Field Type of Value',
        read_only=True)
    input_specification = pvproperty(
        name='INP', dtype=ChannelType.STRING, doc='Input Specification')
    engineering_units_name = pvproperty(
        name='EGU',
        dtype=ChannelType.CHAR,
        max_length=16,
        doc='Engineering Units Name')
    high_operating_range = pvproperty(
        name='HOPR', dtype=ChannelType.DOUBLE, doc='High Operating Range')
    low_operating_range = pvproperty(
        name='LOPR', dtype=ChannelType.DOUBLE, doc='Low Operating Range')
    maximum_elements = pvproperty(
        name='MALM',
        dtype=ChannelType.LONG,
        doc='Maximum Elements',
        read_only=True)
    display_precision = pvproperty(
        name='PREC', dtype=ChannelType.LONG, doc='Display Precision')
    number_of_elements = pvproperty(
        name='NELM', dtype=ChannelType.LONG, doc='Number of Elements')
    substring_index = pvproperty(
        name='INDX', dtype=ChannelType.LONG, doc='Substring Index')
    _link_parent_attribute(display_precision, 'precision')
    _link_parent_attribute(high_operating_range, 'upper_ctrl_limit')
    _link_parent_attribute(low_operating_range, 'lower_ctrl_limit')
    _link_parent_attribute(maximum_elements, 'max_length')
    _link_parent_attribute(number_of_elements, 'length')


@register_record
class SwaitFields(RecordFieldGroup):
    _record_type = 'swait'
    # value = pvproperty(name='VAL', dtype=ChannelType.DOUBLE, doc='Value Field')
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    calc_valid = pvproperty(
        name='CLCV', dtype=ChannelType.LONG, doc='CALC Valid')
    code_version = pvproperty(
        name='VERS',
        dtype=ChannelType.DOUBLE,
        doc='Code Version',
        read_only=True)
    dol_pv_status = pvproperty(
        name='DOLV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.swaitINAV.get_string_tuple(),
        doc='DOL  PV Status',
        read_only=True)
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
    last_value_archived = pvproperty(
        name='ALST',
        dtype=ChannelType.DOUBLE,
        doc='Last Value Archived',
        read_only=True)
    out_pv_status = pvproperty(
        name='OUTV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.swaitINAV.get_string_tuple(),
        doc='OUT  PV Status',
        read_only=True)
    old_value = pvproperty(
        name='OVAL', dtype=ChannelType.DOUBLE, doc='Old Value')
    simulation_mode = pvproperty(
        name='SIMM',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuYesNo.get_string_tuple(),
        doc='Simulation Mode')
    simulation_value = pvproperty(
        name='SVAL', dtype=ChannelType.DOUBLE, doc='Simulation Value')
    high_operating_range = pvproperty(
        name='HOPR', dtype=ChannelType.DOUBLE, doc='High Operating Range')
    output_execute_delay = pvproperty(
        name='ODLY', dtype=ChannelType.DOUBLE, doc='Output Execute Delay')
    low_operating_range = pvproperty(
        name='LOPR', dtype=ChannelType.DOUBLE, doc='Low Operating Range')
    dol_pv_name = pvproperty(
        name='DOLN', dtype=ChannelType.CHAR, max_length=40, doc='DOL  PV Name')
    out_pv_name = pvproperty(
        name='OUTN', dtype=ChannelType.CHAR, max_length=40, doc='OUT  PV Name')
    output_data_option = pvproperty(
        name='DOPT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.swaitDOPT.get_string_tuple(),
        doc='Output Data Option')
    output_execute_opt = pvproperty(
        name='OOPT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.swaitOOPT.get_string_tuple(),
        doc='Output Execute Opt')
    archive_deadband = pvproperty(
        name='ADEL', dtype=ChannelType.DOUBLE, doc='Archive Deadband')
    calculation = pvproperty(
        name='CALC', dtype=ChannelType.CHAR, max_length=36, doc='Calculation')
    desired_output_data = pvproperty(
        name='DOLD', dtype=ChannelType.DOUBLE, doc='Desired Output Data')
    event_to_issue = pvproperty(
        name='OEVT', dtype=ChannelType.LONG, doc='Event To Issue')
    monitor_deadband = pvproperty(
        name='MDEL', dtype=ChannelType.DOUBLE, doc='Monitor Deadband')
    display_precision = pvproperty(
        name='PREC', dtype=ChannelType.LONG, doc='Display Precision')
    sim_input_specifctn = pvproperty(
        name='SIOL', dtype=ChannelType.STRING, doc='Sim Input Specifctn')
    sim_mode_location = pvproperty(
        name='SIML', dtype=ChannelType.STRING, doc='Sim Mode Location')
    sim_mode_alarm_svrty = pvproperty(
        name='SIMS',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='Sim mode Alarm Svrty')
    _link_parent_attribute(display_precision, 'precision')
    _link_parent_attribute(high_operating_range, 'upper_ctrl_limit')
    _link_parent_attribute(low_operating_range, 'lower_ctrl_limit')
    _link_parent_attribute(archive_deadband, 'log_atol')
    _link_parent_attribute(monitor_deadband, 'value_atol')


@register_record
class TableFields(RecordFieldGroup):
    _record_type = 'table'
    # value = pvproperty(name='VAL', dtype=ChannelType.DOUBLE, doc='Result')
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    code_version = pvproperty(
        name='VERS',
        dtype=ChannelType.DOUBLE,
        doc='Code Version',
        read_only=True)
    monitor_mask = pvproperty(
        name='MMAP',
        dtype=ChannelType.LONG,
        doc='Monitor Mask',
        read_only=True)
    set_set_mode = pvproperty(
        name='SSET', dtype=ChannelType.LONG, doc='Set SET Mode')
    set_use_mode = pvproperty(
        name='SUSE', dtype=ChannelType.LONG, doc='Set USE Mode')
    encoder_0x_val = pvproperty(
        name='E0X',
        dtype=ChannelType.DOUBLE,
        doc='encoder 0X val',
        read_only=True)
    encoder_0y_val = pvproperty(
        name='E0Y',
        dtype=ChannelType.DOUBLE,
        doc='encoder 0Y val',
        read_only=True)
    encoder_1y_val = pvproperty(
        name='E1Y',
        dtype=ChannelType.DOUBLE,
        doc='encoder 1Y val',
        read_only=True)
    encoder_2x_val = pvproperty(
        name='E2X',
        dtype=ChannelType.DOUBLE,
        doc='encoder 2X val',
        read_only=True)
    encoder_2y_val = pvproperty(
        name='E2Y',
        dtype=ChannelType.DOUBLE,
        doc='encoder 2Y val',
        read_only=True)
    encoder_2z_val = pvproperty(
        name='E2Z',
        dtype=ChannelType.DOUBLE,
        doc='encoder 2Z val',
        read_only=True)
    encoder_x = pvproperty(
        name='EX', dtype=ChannelType.DOUBLE, doc='encoder x', read_only=True)
    encoder_x_angle = pvproperty(
        name='EAX',
        dtype=ChannelType.DOUBLE,
        doc='encoder x angle',
        read_only=True)
    encoder_y = pvproperty(
        name='EY', dtype=ChannelType.DOUBLE, doc='encoder y', read_only=True)
    encoder_y_angle = pvproperty(
        name='EAY',
        dtype=ChannelType.DOUBLE,
        doc='encoder y angle',
        read_only=True)
    encoder_z = pvproperty(
        name='EZ', dtype=ChannelType.DOUBLE, doc='encoder z', read_only=True)
    encoder_z_angle = pvproperty(
        name='EAZ',
        dtype=ChannelType.DOUBLE,
        doc='encoder z angle',
        read_only=True)
    init_table = pvproperty(
        name='INIT', dtype=ChannelType.LONG, doc='init table')
    limit_violation = pvproperty(
        name='LVIO',
        dtype=ChannelType.LONG,
        doc='limit violation',
        read_only=True)
    motor_0x_hi_limit = pvproperty(
        name='H0X',
        dtype=ChannelType.DOUBLE,
        doc='motor 0X hi limit',
        read_only=True)
    motor_0x_lo_limit = pvproperty(
        name='L0X',
        dtype=ChannelType.DOUBLE,
        doc='motor 0X lo limit',
        read_only=True)
    motor_0x_readback = pvproperty(
        name='R0X',
        dtype=ChannelType.DOUBLE,
        doc='motor 0X readback',
        read_only=True)
    motor_0x_val = pvproperty(
        name='M0X',
        dtype=ChannelType.DOUBLE,
        doc='motor 0X val',
        read_only=True)
    motor_0y_hi_limit = pvproperty(
        name='H0Y',
        dtype=ChannelType.DOUBLE,
        doc='motor 0Y hi limit',
        read_only=True)
    motor_0y_lo_limit = pvproperty(
        name='L0Y',
        dtype=ChannelType.DOUBLE,
        doc='motor 0Y lo limit',
        read_only=True)
    motor_0y_readback = pvproperty(
        name='R0Y',
        dtype=ChannelType.DOUBLE,
        doc='motor 0Y readback',
        read_only=True)
    motor_0y_val = pvproperty(
        name='M0Y',
        dtype=ChannelType.DOUBLE,
        doc='motor 0Y val',
        read_only=True)
    motor_1y_hi_limit = pvproperty(
        name='H1Y',
        dtype=ChannelType.DOUBLE,
        doc='motor 1Y hi limit',
        read_only=True)
    motor_1y_lo_limit = pvproperty(
        name='L1Y',
        dtype=ChannelType.DOUBLE,
        doc='motor 1Y lo limit',
        read_only=True)
    motor_1y_readback = pvproperty(
        name='R1Y',
        dtype=ChannelType.DOUBLE,
        doc='motor 1Y readback',
        read_only=True)
    motor_1y_val = pvproperty(
        name='M1Y',
        dtype=ChannelType.DOUBLE,
        doc='motor 1Y val',
        read_only=True)
    motor_2x_hi_limit = pvproperty(
        name='H2X',
        dtype=ChannelType.DOUBLE,
        doc='motor 2X hi limit',
        read_only=True)
    motor_2x_lo_limit = pvproperty(
        name='L2X',
        dtype=ChannelType.DOUBLE,
        doc='motor 2X lo limit',
        read_only=True)
    motor_2x_readback = pvproperty(
        name='R2X',
        dtype=ChannelType.DOUBLE,
        doc='motor 2X readback',
        read_only=True)
    motor_2x_val = pvproperty(
        name='M2X',
        dtype=ChannelType.DOUBLE,
        doc='motor 2X val',
        read_only=True)
    motor_2y_hi_limit = pvproperty(
        name='H2Y',
        dtype=ChannelType.DOUBLE,
        doc='motor 2Y hi limit',
        read_only=True)
    motor_2y_lo_limit = pvproperty(
        name='L2Y',
        dtype=ChannelType.DOUBLE,
        doc='motor 2Y lo limit',
        read_only=True)
    motor_2y_readback = pvproperty(
        name='R2Y',
        dtype=ChannelType.DOUBLE,
        doc='motor 2Y readback',
        read_only=True)
    motor_2y_val = pvproperty(
        name='M2Y',
        dtype=ChannelType.DOUBLE,
        doc='motor 2Y val',
        read_only=True)
    motor_2z_hi_limit = pvproperty(
        name='H2Z',
        dtype=ChannelType.DOUBLE,
        doc='motor 2Z hi limit',
        read_only=True)
    motor_2z_lo_limit = pvproperty(
        name='L2Z',
        dtype=ChannelType.DOUBLE,
        doc='motor 2Z lo limit',
        read_only=True)
    motor_2z_readback = pvproperty(
        name='R2Z',
        dtype=ChannelType.DOUBLE,
        doc='motor 2Z readback',
        read_only=True)
    motor_2z_val = pvproperty(
        name='M2Z',
        dtype=ChannelType.DOUBLE,
        doc='motor 2Z val',
        read_only=True)
    readback_motors = pvproperty(
        name='READ', dtype=ChannelType.LONG, doc='readback motors')
    set_table = pvproperty(
        name='SET',
        dtype=ChannelType.ENUM,
        enum_strings=menus.tableSET.get_string_tuple(),
        doc='set table')
    speed_0x_val = pvproperty(
        name='V0X',
        dtype=ChannelType.DOUBLE,
        doc='speed 0X val',
        read_only=True)
    speed_0y_val = pvproperty(
        name='V0Y',
        dtype=ChannelType.DOUBLE,
        doc='speed 0Y val',
        read_only=True)
    speed_1y_val = pvproperty(
        name='V1Y',
        dtype=ChannelType.DOUBLE,
        doc='speed 1Y val',
        read_only=True)
    speed_2x_val = pvproperty(
        name='V2X',
        dtype=ChannelType.DOUBLE,
        doc='speed 2X val',
        read_only=True)
    speed_2y_val = pvproperty(
        name='V2Y',
        dtype=ChannelType.DOUBLE,
        doc='speed 2Y val',
        read_only=True)
    speed_2z_val = pvproperty(
        name='V2Z',
        dtype=ChannelType.DOUBLE,
        doc='speed 2Z val',
        read_only=True)
    sync_with_motors = pvproperty(
        name='SYNC', dtype=ChannelType.LONG, doc='sync with motors')
    x_angle = pvproperty(name='AX', dtype=ChannelType.DOUBLE, doc='x angle')
    x_angle_hi_limit = pvproperty(
        name='HLAX',
        dtype=ChannelType.DOUBLE,
        doc='x angle hi limit',
        read_only=True)
    x_angle_lo_limit = pvproperty(
        name='LLAX',
        dtype=ChannelType.DOUBLE,
        doc='x angle lo limit',
        read_only=True)
    x_angle_readback = pvproperty(
        name='AXRB',
        dtype=ChannelType.DOUBLE,
        doc='x angle readback',
        read_only=True)
    x_angle_true_value = pvproperty(
        name='AXL',
        dtype=ChannelType.DOUBLE,
        doc='x angle true value',
        read_only=True)
    x_hi_limit = pvproperty(
        name='HLX', dtype=ChannelType.DOUBLE, doc='x hi limit', read_only=True)
    x_lo_limit = pvproperty(
        name='LLX', dtype=ChannelType.DOUBLE, doc='x lo limit', read_only=True)
    x_offset = pvproperty(name='X0', dtype=ChannelType.DOUBLE, doc='x offset')
    x_readback_value = pvproperty(
        name='XRB',
        dtype=ChannelType.DOUBLE,
        doc='x readback value',
        read_only=True)
    x_translation = pvproperty(
        name='X', dtype=ChannelType.DOUBLE, doc='x translation')
    x_true_value = pvproperty(
        name='XL',
        dtype=ChannelType.DOUBLE,
        doc='x true value',
        read_only=True)
    x_angle_offset = pvproperty(
        name='AX0', dtype=ChannelType.DOUBLE, doc='x-angle offset')
    y_angle = pvproperty(name='AY', dtype=ChannelType.DOUBLE, doc='y angle')
    y_angle_hi_limit = pvproperty(
        name='HLAY',
        dtype=ChannelType.DOUBLE,
        doc='y angle hi limit',
        read_only=True)
    y_angle_lo_limit = pvproperty(
        name='LLAY',
        dtype=ChannelType.DOUBLE,
        doc='y angle lo limit',
        read_only=True)
    y_angle_readback = pvproperty(
        name='AYRB',
        dtype=ChannelType.DOUBLE,
        doc='y angle readback',
        read_only=True)
    y_angle_true_value = pvproperty(
        name='AYL',
        dtype=ChannelType.DOUBLE,
        doc='y angle true value',
        read_only=True)
    y_hi_limit = pvproperty(
        name='HLY', dtype=ChannelType.DOUBLE, doc='y hi limit', read_only=True)
    y_lo_limit = pvproperty(
        name='LLY', dtype=ChannelType.DOUBLE, doc='y lo limit', read_only=True)
    y_offset = pvproperty(name='Y0', dtype=ChannelType.DOUBLE, doc='y offset')
    y_readback_value = pvproperty(
        name='YRB',
        dtype=ChannelType.DOUBLE,
        doc='y readback value',
        read_only=True)
    y_translation = pvproperty(
        name='Y', dtype=ChannelType.DOUBLE, doc='y translation')
    y_true_value = pvproperty(
        name='YL',
        dtype=ChannelType.DOUBLE,
        doc='y true value',
        read_only=True)
    y_angle_offset = pvproperty(
        name='AY0', dtype=ChannelType.DOUBLE, doc='y-angle offset')
    z_angle = pvproperty(name='AZ', dtype=ChannelType.DOUBLE, doc='z angle')
    z_angle_hi_limit = pvproperty(
        name='HLAZ',
        dtype=ChannelType.DOUBLE,
        doc='z angle hi limit',
        read_only=True)
    z_angle_lo_limit = pvproperty(
        name='LLAZ',
        dtype=ChannelType.DOUBLE,
        doc='z angle lo limit',
        read_only=True)
    z_angle_readback = pvproperty(
        name='AZRB',
        dtype=ChannelType.DOUBLE,
        doc='z angle readback',
        read_only=True)
    z_angle_true_value = pvproperty(
        name='AZL',
        dtype=ChannelType.DOUBLE,
        doc='z angle true value',
        read_only=True)
    z_hi_limit = pvproperty(
        name='HLZ', dtype=ChannelType.DOUBLE, doc='z hi limit', read_only=True)
    z_lo_limit = pvproperty(
        name='LLZ', dtype=ChannelType.DOUBLE, doc='z lo limit', read_only=True)
    z_offset = pvproperty(name='Z0', dtype=ChannelType.DOUBLE, doc='z offset')
    z_readback_value = pvproperty(
        name='ZRB',
        dtype=ChannelType.DOUBLE,
        doc='z readback value',
        read_only=True)
    z_translation = pvproperty(
        name='Z', dtype=ChannelType.DOUBLE, doc='z translation')
    z_true_value = pvproperty(
        name='ZL',
        dtype=ChannelType.DOUBLE,
        doc='z true value',
        read_only=True)
    z_angle_offset = pvproperty(
        name='AZ0', dtype=ChannelType.DOUBLE, doc='z-angle offset')
    zero_table = pvproperty(
        name='ZERO', dtype=ChannelType.LONG, doc='zero table')
    angular_units_name = pvproperty(
        name='AEGU',
        dtype=ChannelType.CHAR,
        max_length=16,
        doc='Angular Units Name')
    display_precision = pvproperty(
        name='PREC', dtype=ChannelType.LONG, doc='Display Precision')
    geometry = pvproperty(
        name='GEOM',
        dtype=ChannelType.ENUM,
        enum_strings=menus.tableGEOM.get_string_tuple(),
        doc='Geometry')
    linear_units_name = pvproperty(
        name='LEGU',
        dtype=ChannelType.CHAR,
        max_length=16,
        doc='Linear Units Name')
    orientation_angle = pvproperty(
        name='YANG', dtype=ChannelType.DOUBLE, doc='Orientation angle')
    encoder_0x_inlink = pvproperty(
        name='E0XI',
        dtype=ChannelType.STRING,
        doc='encoder 0X inlink',
        read_only=True)
    encoder_0y_inlink = pvproperty(
        name='E0YI',
        dtype=ChannelType.STRING,
        doc='encoder 0Y inlink',
        read_only=True)
    encoder_1y_inlink = pvproperty(
        name='E1YI',
        dtype=ChannelType.STRING,
        doc='encoder 1Y inlink',
        read_only=True)
    encoder_2x_inlink = pvproperty(
        name='E2XI',
        dtype=ChannelType.STRING,
        doc='encoder 2X inlink',
        read_only=True)
    encoder_2y_inlink = pvproperty(
        name='E2YI',
        dtype=ChannelType.STRING,
        doc='encoder 2Y inlink',
        read_only=True)
    encoder_2z_inlink = pvproperty(
        name='E2ZI',
        dtype=ChannelType.STRING,
        doc='encoder 2Z inlink',
        read_only=True)
    motor_0x_hlm_link = pvproperty(
        name='H0XL',
        dtype=ChannelType.STRING,
        doc='motor 0X HLM link',
        read_only=True)
    motor_0x_llm_link = pvproperty(
        name='L0XL',
        dtype=ChannelType.STRING,
        doc='motor 0X LLM link',
        read_only=True)
    motor_0x_rbv_link = pvproperty(
        name='R0XI',
        dtype=ChannelType.STRING,
        doc='motor 0X RBV link',
        read_only=True)
    motor_0x_outlink = pvproperty(
        name='M0XL',
        dtype=ChannelType.STRING,
        doc='motor 0X outlink',
        read_only=True)
    motor_0y_hlm_link = pvproperty(
        name='H0YL',
        dtype=ChannelType.STRING,
        doc='motor 0Y HLM link',
        read_only=True)
    motor_0y_llm_link = pvproperty(
        name='L0YL',
        dtype=ChannelType.STRING,
        doc='motor 0Y LLM link',
        read_only=True)
    motor_0y_rbv_link = pvproperty(
        name='R0YI',
        dtype=ChannelType.STRING,
        doc='motor 0Y RBV link',
        read_only=True)
    motor_0y_outlink = pvproperty(
        name='M0YL',
        dtype=ChannelType.STRING,
        doc='motor 0Y outlink',
        read_only=True)
    motor_1y_hlm_link = pvproperty(
        name='H1YL',
        dtype=ChannelType.STRING,
        doc='motor 1Y HLM link',
        read_only=True)
    motor_1y_llm_link = pvproperty(
        name='L1YL',
        dtype=ChannelType.STRING,
        doc='motor 1Y LLM link',
        read_only=True)
    motor_1y_rbv_link = pvproperty(
        name='R1YI',
        dtype=ChannelType.STRING,
        doc='motor 1Y RBV link',
        read_only=True)
    motor_1y_outlink = pvproperty(
        name='M1YL',
        dtype=ChannelType.STRING,
        doc='motor 1Y outlink',
        read_only=True)
    motor_2x_hlm_link = pvproperty(
        name='H2XL',
        dtype=ChannelType.STRING,
        doc='motor 2X HLM link',
        read_only=True)
    motor_2x_llm_link = pvproperty(
        name='L2XL',
        dtype=ChannelType.STRING,
        doc='motor 2X LLM link',
        read_only=True)
    motor_2x_rbv_link = pvproperty(
        name='R2XI',
        dtype=ChannelType.STRING,
        doc='motor 2X RBV link',
        read_only=True)
    motor_2x_outlink = pvproperty(
        name='M2XL',
        dtype=ChannelType.STRING,
        doc='motor 2X outlink',
        read_only=True)
    motor_2y_hlm_link = pvproperty(
        name='H2YL',
        dtype=ChannelType.STRING,
        doc='motor 2Y HLM link',
        read_only=True)
    motor_2y_llm_link = pvproperty(
        name='L2YL',
        dtype=ChannelType.STRING,
        doc='motor 2Y LLM link',
        read_only=True)
    motor_2y_rbv_link = pvproperty(
        name='R2YI',
        dtype=ChannelType.STRING,
        doc='motor 2Y RBV link',
        read_only=True)
    motor_2y_outlink = pvproperty(
        name='M2YL',
        dtype=ChannelType.STRING,
        doc='motor 2Y outlink',
        read_only=True)
    motor_2z_hlm_link = pvproperty(
        name='H2ZL',
        dtype=ChannelType.STRING,
        doc='motor 2Z HLM link',
        read_only=True)
    motor_2z_llm_link = pvproperty(
        name='L2ZL',
        dtype=ChannelType.STRING,
        doc='motor 2Z LLM link',
        read_only=True)
    motor_2z_rbv_link = pvproperty(
        name='R2ZI',
        dtype=ChannelType.STRING,
        doc='motor 2Z RBV link',
        read_only=True)
    motor_2z_outlink = pvproperty(
        name='M2ZL',
        dtype=ChannelType.STRING,
        doc='motor 2Z outlink',
        read_only=True)
    speed_0x_inlink = pvproperty(
        name='V0XI',
        dtype=ChannelType.STRING,
        doc='speed 0X inlink',
        read_only=True)
    speed_0x_outlink = pvproperty(
        name='V0XL',
        dtype=ChannelType.STRING,
        doc='speed 0X outlink',
        read_only=True)
    speed_0y_inlink = pvproperty(
        name='V0YI',
        dtype=ChannelType.STRING,
        doc='speed 0Y inlink',
        read_only=True)
    speed_0y_outlink = pvproperty(
        name='V0YL',
        dtype=ChannelType.STRING,
        doc='speed 0Y outlink',
        read_only=True)
    speed_1y_inlink = pvproperty(
        name='V1YI',
        dtype=ChannelType.STRING,
        doc='speed 1Y inlink',
        read_only=True)
    speed_1y_outlink = pvproperty(
        name='V1YL',
        dtype=ChannelType.STRING,
        doc='speed 1Y outlink',
        read_only=True)
    speed_2x_inlink = pvproperty(
        name='V2XI',
        dtype=ChannelType.STRING,
        doc='speed 2X inlink',
        read_only=True)
    speed_2x_outlink = pvproperty(
        name='V2XL',
        dtype=ChannelType.STRING,
        doc='speed 2X outlink',
        read_only=True)
    speed_2y_inlink = pvproperty(
        name='V2YI',
        dtype=ChannelType.STRING,
        doc='speed 2Y inlink',
        read_only=True)
    speed_2y_outlink = pvproperty(
        name='V2YL',
        dtype=ChannelType.STRING,
        doc='speed 2Y outlink',
        read_only=True)
    speed_2z_inlink = pvproperty(
        name='V2ZI',
        dtype=ChannelType.STRING,
        doc='speed 2Z inlink',
        read_only=True)
    speed_2z_outlink = pvproperty(
        name='V2ZL',
        dtype=ChannelType.STRING,
        doc='speed 2Z outlink',
        read_only=True)
    wheelbase_x = pvproperty(
        name='LX', dtype=ChannelType.DOUBLE, doc='wheelbase x')
    wheelbase_z = pvproperty(
        name='LZ', dtype=ChannelType.DOUBLE, doc='wheelbase z')
    x_angle_user_hi_limit = pvproperty(
        name='UHAX', dtype=ChannelType.DOUBLE, doc='x angle user hi limit')
    x_angle_user_lo_limit = pvproperty(
        name='ULAX', dtype=ChannelType.DOUBLE, doc='x angle user lo limit')
    x_of_fixed_point = pvproperty(
        name='SX', dtype=ChannelType.DOUBLE, doc='x of fixed point')
    x_of_ref_point = pvproperty(
        name='RX', dtype=ChannelType.DOUBLE, doc='x of ref point')
    x_user_hi_limit = pvproperty(
        name='UHX', dtype=ChannelType.DOUBLE, doc='x user hi limit')
    x_user_lo_limit = pvproperty(
        name='ULX', dtype=ChannelType.DOUBLE, doc='x user lo limit')
    y_angle_user_hi_limit = pvproperty(
        name='UHAY', dtype=ChannelType.DOUBLE, doc='y angle user hi limit')
    y_angle_user_lo_limit = pvproperty(
        name='ULAY', dtype=ChannelType.DOUBLE, doc='y angle user lo limit')
    y_of_fixed_point = pvproperty(
        name='SY', dtype=ChannelType.DOUBLE, doc='y of fixed point')
    y_of_ref_point = pvproperty(
        name='RY', dtype=ChannelType.DOUBLE, doc='y of ref point')
    y_user_hi_limit = pvproperty(
        name='UHY', dtype=ChannelType.DOUBLE, doc='y user hi limit')
    y_user_lo_limit = pvproperty(
        name='ULY', dtype=ChannelType.DOUBLE, doc='y user lo limit')
    z_angle_user_hi_limit = pvproperty(
        name='UHAZ', dtype=ChannelType.DOUBLE, doc='z angle user hi limit')
    z_angle_user_lo_limit = pvproperty(
        name='ULAZ', dtype=ChannelType.DOUBLE, doc='z angle user lo limit')
    z_of_fixed_point = pvproperty(
        name='SZ', dtype=ChannelType.DOUBLE, doc='z of fixed point')
    z_of_ref_point = pvproperty(
        name='RZ', dtype=ChannelType.DOUBLE, doc='z of ref point')
    z_user_hi_limit = pvproperty(
        name='UHZ', dtype=ChannelType.DOUBLE, doc='z user hi limit')
    z_user_lo_limit = pvproperty(
        name='ULZ', dtype=ChannelType.DOUBLE, doc='z user lo limit')
    _link_parent_attribute(display_precision, 'precision')


@register_record
class TimestampFields(RecordFieldGroup):
    _record_type = 'timestamp'
    # value = pvproperty(
    #     name='VAL', dtype=ChannelType.CHAR, max_length=40, doc='Current Value')
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    current_raw_value = pvproperty(
        name='RVAL', dtype=ChannelType.LONG, doc='Current Raw Value')
    previous_value = pvproperty(
        name='OVAL',
        dtype=ChannelType.CHAR,
        max_length=40,
        doc='Previous Value',
        read_only=True)
    time_stamp_type = pvproperty(
        name='TST',
        dtype=ChannelType.ENUM,
        enum_strings=menus.timestampTST.get_string_tuple(),
        doc='Time Stamp Type')


@register_record
class TransformFields(RecordFieldGroup):
    _record_type = 'transform'
    # value = pvproperty(name='VAL', dtype=ChannelType.DOUBLE, doc='Result')
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    code_version = pvproperty(
        name='VERS',
        dtype=ChannelType.DOUBLE,
        doc='Code Version',
        read_only=True)
    calc_option = pvproperty(
        name='COPT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.transformCOPT.get_string_tuple(),
        doc='Calc option')
    display_precision = pvproperty(
        name='PREC', dtype=ChannelType.LONG, doc='Display Precision')
    input_bitmap = pvproperty(
        name='MAP', dtype=ChannelType.LONG, doc='Input bitmap')
    invalid_link_action = pvproperty(
        name='IVLA',
        dtype=ChannelType.ENUM,
        enum_strings=menus.transformIVLA.get_string_tuple(),
        doc='Invalid link action')
    units_name = pvproperty(
        name='EGU', dtype=ChannelType.CHAR, max_length=16, doc='Units Name')
    _link_parent_attribute(display_precision, 'precision')


@register_record
class VmeFields(RecordFieldGroup):
    _record_type = 'vme'
    # value = pvproperty(name='VAL', dtype=ChannelType.LONG, doc='Current value')
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    status_array = pvproperty(
        name='SARR', dtype=ChannelType.CHAR, doc='Status array')
    read_write = pvproperty(
        name='RDWT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.vmeRDWT.get_string_tuple(),
        doc='Read/write')
    vme_address_mode = pvproperty(
        name='AMOD',
        dtype=ChannelType.ENUM,
        enum_strings=menus.vmeAMOD.get_string_tuple(),
        doc='VME address mode')
    vme_data_size = pvproperty(
        name='DSIZ',
        dtype=ChannelType.ENUM,
        enum_strings=menus.vmeDSIZ.get_string_tuple(),
        doc='VME data size')
    address_increment_1_4 = pvproperty(
        name='AINC', dtype=ChannelType.LONG, doc='Address increment (1-4)')
    max_number_of_values = pvproperty(
        name='NMAX', dtype=ChannelType.LONG, doc='Max. number of values')
    number_of_values_to_r_w = pvproperty(
        name='NUSE', dtype=ChannelType.LONG, doc='Number of values to R/W')
    vme_address_hex = pvproperty(
        name='ADDR', dtype=ChannelType.LONG, doc='VME address (hex)')


@register_record
class VsFields(RecordFieldGroup):
    _record_type = 'vs'
    # value = pvproperty(
    #     name='VAL',
    #     dtype=ChannelType.DOUBLE,
    #     doc='Gauge Pressure',
    #     read_only=True)
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    changed_control = pvproperty(
        name='CHGC',
        dtype=ChannelType.LONG,
        doc='Changed Control',
        read_only=True)
    controller_err_cnt = pvproperty(
        name='ERR', dtype=ChannelType.LONG, doc='Controller Err Cnt')
    controller_type = pvproperty(
        name='TYPE',
        dtype=ChannelType.ENUM,
        enum_strings=menus.vsTYPE.get_string_tuple(),
        doc='Controller Type')
    conv_a_log10_pressure = pvproperty(
        name='LCAP',
        dtype=ChannelType.DOUBLE,
        doc='Conv-A Log10 Pressure',
        read_only=True)
    conv_b_log10_pressure = pvproperty(
        name='LCBP',
        dtype=ChannelType.DOUBLE,
        doc='Conv-B Log10 Pressure',
        read_only=True)
    convectron_a_pressure = pvproperty(
        name='CGAP',
        dtype=ChannelType.DOUBLE,
        doc='Convectron-A Pressure',
        read_only=True)
    convectron_b_pressure = pvproperty(
        name='CGBP',
        dtype=ChannelType.DOUBLE,
        doc='Convectron-B Pressure',
        read_only=True)
    degas_read = pvproperty(
        name='DGSR',
        dtype=ChannelType.ENUM,
        enum_strings=menus.vsOFFON.get_string_tuple(),
        doc='Degas Read',
        read_only=True)
    fault_read = pvproperty(
        name='FLTR',
        dtype=ChannelType.ENUM,
        enum_strings=menus.vsOFFON.get_string_tuple(),
        doc='Fault Read',
        read_only=True)
    gauge_pressure = pvproperty(
        name='PRES',
        dtype=ChannelType.DOUBLE,
        doc='Gauge Pressure',
        read_only=True)
    ig_last_value_alarmed = pvproperty(
        name='LALM',
        dtype=ChannelType.DOUBLE,
        doc='IG Last Value Alarmed',
        read_only=True)
    ig_log10_pressure = pvproperty(
        name='LPRS',
        dtype=ChannelType.DOUBLE,
        doc='IG Log10 Pressure',
        read_only=True)
    ion_gauge_1_read = pvproperty(
        name='IG1R',
        dtype=ChannelType.ENUM,
        enum_strings=menus.vsOFFON.get_string_tuple(),
        doc='Ion Gauge 1 Read',
        read_only=True)
    ion_gauge_2_read = pvproperty(
        name='IG2R',
        dtype=ChannelType.ENUM,
        enum_strings=menus.vsOFFON.get_string_tuple(),
        doc='Ion Gauge 2 Read',
        read_only=True)
    sp_1_readback = pvproperty(
        name='SP1R',
        dtype=ChannelType.DOUBLE,
        doc='SP 1 Readback',
        read_only=True)
    sp_1_setpoint_set = pvproperty(
        name='SP1S', dtype=ChannelType.DOUBLE, doc='SP 1 Setpoint Set')
    sp_2_readback = pvproperty(
        name='SP2R',
        dtype=ChannelType.DOUBLE,
        doc='SP 2 Readback',
        read_only=True)
    sp_2_setpoint_set = pvproperty(
        name='SP2S', dtype=ChannelType.DOUBLE, doc='SP 2 Setpoint Set')
    sp_3_readback = pvproperty(
        name='SP3R',
        dtype=ChannelType.DOUBLE,
        doc='SP 3 Readback',
        read_only=True)
    sp_3_setpoint_set = pvproperty(
        name='SP3S', dtype=ChannelType.DOUBLE, doc='SP 3 Setpoint Set')
    sp_4_readback = pvproperty(
        name='SP4R',
        dtype=ChannelType.DOUBLE,
        doc='SP 4 Readback',
        read_only=True)
    sp_4_setpoint_set = pvproperty(
        name='SP4S', dtype=ChannelType.DOUBLE, doc='SP 4 Setpoint Set')
    set_point_1 = pvproperty(
        name='SP1',
        dtype=ChannelType.ENUM,
        enum_strings=menus.vsOFFON.get_string_tuple(),
        doc='Set Point 1',
        read_only=True)
    set_point_2 = pvproperty(
        name='SP2',
        dtype=ChannelType.ENUM,
        enum_strings=menus.vsOFFON.get_string_tuple(),
        doc='Set Point 2',
        read_only=True)
    set_point_3 = pvproperty(
        name='SP3',
        dtype=ChannelType.ENUM,
        enum_strings=menus.vsOFFON.get_string_tuple(),
        doc='Set Point 3',
        read_only=True)
    set_point_4 = pvproperty(
        name='SP4',
        dtype=ChannelType.ENUM,
        enum_strings=menus.vsOFFON.get_string_tuple(),
        doc='Set Point 4',
        read_only=True)
    set_point_5 = pvproperty(
        name='SP5',
        dtype=ChannelType.ENUM,
        enum_strings=menus.vsOFFON.get_string_tuple(),
        doc='Set Point 5',
        read_only=True)
    set_point_6 = pvproperty(
        name='SP6',
        dtype=ChannelType.ENUM,
        enum_strings=menus.vsOFFON.get_string_tuple(),
        doc='Set Point 6',
        read_only=True)
    prev_conv_a_log10_pres = pvproperty(
        name='PLCA',
        dtype=ChannelType.DOUBLE,
        doc='prev Conv-A Log10 Pres',
        read_only=True)
    prev_conv_a_pres = pvproperty(
        name='PCGA',
        dtype=ChannelType.DOUBLE,
        doc='prev Conv-A Pres',
        read_only=True)
    prev_conv_b_log10_pres = pvproperty(
        name='PLCB',
        dtype=ChannelType.DOUBLE,
        doc='prev Conv-B Log10 Pres',
        read_only=True)
    prev_conv_b_pres = pvproperty(
        name='PCGB',
        dtype=ChannelType.DOUBLE,
        doc='prev Conv-B Pres',
        read_only=True)
    prev_degas = pvproperty(
        name='PDGS',
        dtype=ChannelType.ENUM,
        enum_strings=menus.vsOFFON.get_string_tuple(),
        doc='prev Degas',
        read_only=True)
    prev_degas_pdss = pvproperty(
        name='PDSS',
        dtype=ChannelType.ENUM,
        enum_strings=menus.vsOFFON.get_string_tuple(),
        doc='prev Degas',
        read_only=True)
    prev_fault = pvproperty(
        name='PFLT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.vsOFFON.get_string_tuple(),
        doc='prev Fault',
        read_only=True)
    prev_gauge_pres = pvproperty(
        name='PPRE',
        dtype=ChannelType.DOUBLE,
        doc='prev Gauge Pres',
        read_only=True)
    prev_gauge_pres_pval = pvproperty(
        name='PVAL',
        dtype=ChannelType.DOUBLE,
        doc='prev Gauge Pres',
        read_only=True)
    prev_ig_log10_pres = pvproperty(
        name='PLPE',
        dtype=ChannelType.DOUBLE,
        doc='prev IG Log10 Pres',
        read_only=True)
    prev_ion_gauge_1 = pvproperty(
        name='PI1S',
        dtype=ChannelType.ENUM,
        enum_strings=menus.vsOFFON.get_string_tuple(),
        doc='prev Ion Gauge 1',
        read_only=True)
    prev_ion_gauge_1_pig1 = pvproperty(
        name='PIG1',
        dtype=ChannelType.ENUM,
        enum_strings=menus.vsOFFON.get_string_tuple(),
        doc='prev Ion Gauge 1',
        read_only=True)
    prev_ion_gauge_2 = pvproperty(
        name='PI2S',
        dtype=ChannelType.ENUM,
        enum_strings=menus.vsOFFON.get_string_tuple(),
        doc='prev Ion Gauge 2',
        read_only=True)
    prev_ion_gauge_2_pig2 = pvproperty(
        name='PIG2',
        dtype=ChannelType.ENUM,
        enum_strings=menus.vsOFFON.get_string_tuple(),
        doc='prev Ion Gauge 2',
        read_only=True)
    prev_sp1_readback = pvproperty(
        name='PS1R',
        dtype=ChannelType.DOUBLE,
        doc='prev SP1 Readback',
        read_only=True)
    prev_sp1_set = pvproperty(
        name='PS1S',
        dtype=ChannelType.DOUBLE,
        doc='prev SP1 Set',
        read_only=True)
    prev_sp2_readback = pvproperty(
        name='PS2R',
        dtype=ChannelType.DOUBLE,
        doc='prev SP2 Readback',
        read_only=True)
    prev_sp2_set = pvproperty(
        name='PS2S',
        dtype=ChannelType.DOUBLE,
        doc='prev SP2 Set',
        read_only=True)
    prev_sp3_readback = pvproperty(
        name='PS3R',
        dtype=ChannelType.DOUBLE,
        doc='prev SP3 Readback',
        read_only=True)
    prev_sp3_set = pvproperty(
        name='PS3S',
        dtype=ChannelType.DOUBLE,
        doc='prev SP3 Set',
        read_only=True)
    prev_sp4_readback = pvproperty(
        name='PS4R',
        dtype=ChannelType.DOUBLE,
        doc='prev SP4 Readback',
        read_only=True)
    prev_sp4_set = pvproperty(
        name='PS4S',
        dtype=ChannelType.DOUBLE,
        doc='prev SP4 Set',
        read_only=True)
    prev_set_point_1 = pvproperty(
        name='PSP1',
        dtype=ChannelType.ENUM,
        enum_strings=menus.vsOFFON.get_string_tuple(),
        doc='prev Set Point 1',
        read_only=True)
    prev_set_point_2 = pvproperty(
        name='PSP2',
        dtype=ChannelType.ENUM,
        enum_strings=menus.vsOFFON.get_string_tuple(),
        doc='prev Set Point 2',
        read_only=True)
    prev_set_point_3 = pvproperty(
        name='PSP3',
        dtype=ChannelType.ENUM,
        enum_strings=menus.vsOFFON.get_string_tuple(),
        doc='prev Set Point 3',
        read_only=True)
    prev_set_point_4 = pvproperty(
        name='PSP4',
        dtype=ChannelType.ENUM,
        enum_strings=menus.vsOFFON.get_string_tuple(),
        doc='prev Set Point 4',
        read_only=True)
    prev_set_point_5 = pvproperty(
        name='PSP5',
        dtype=ChannelType.ENUM,
        enum_strings=menus.vsOFFON.get_string_tuple(),
        doc='prev Set Point 5',
        read_only=True)
    prev_set_point_6 = pvproperty(
        name='PSP6',
        dtype=ChannelType.ENUM,
        enum_strings=menus.vsOFFON.get_string_tuple(),
        doc='prev Set Point 6',
        read_only=True)
    ion_gauge_1_set = pvproperty(
        name='IG1S',
        dtype=ChannelType.ENUM,
        enum_strings=menus.vsOFFON.get_string_tuple(),
        doc='Ion Gauge 1 Set')
    ion_gauge_2_set = pvproperty(
        name='IG2S',
        dtype=ChannelType.ENUM,
        enum_strings=menus.vsOFFON.get_string_tuple(),
        doc='Ion Gauge 2 Set')
    degas_set = pvproperty(
        name='DGSS',
        dtype=ChannelType.ENUM,
        enum_strings=menus.vsOFFON.get_string_tuple(),
        doc='Degas Set')
    device_specification = pvproperty(
        name='INP',
        dtype=ChannelType.STRING,
        doc='Device Specification',
        read_only=True)
    ig_alarm_deadband = pvproperty(
        name='HYST', dtype=ChannelType.DOUBLE, doc='IG Alarm Deadband')
    ig_high_alarm = pvproperty(
        name='HIGH', dtype=ChannelType.DOUBLE, doc='IG High Alarm')
    ig_high_severity = pvproperty(
        name='HSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='IG High Severity')
    ig_hihi_alarm = pvproperty(
        name='HIHI', dtype=ChannelType.DOUBLE, doc='IG Hihi Alarm')
    ig_hihi_severity = pvproperty(
        name='HHSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='IG Hihi Severity')
    ig_lolo_alarm = pvproperty(
        name='LOLO', dtype=ChannelType.DOUBLE, doc='IG Lolo Alarm')
    ig_lolo_severity = pvproperty(
        name='LLSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='IG Lolo Severity')
    ig_low_alarm = pvproperty(
        name='LOW', dtype=ChannelType.DOUBLE, doc='IG Low Alarm')
    ig_low_severity = pvproperty(
        name='LSV',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc='IG Low Severity')
    ig_pres_high_display = pvproperty(
        name='HOPR', dtype=ChannelType.DOUBLE, doc='IG Pres High Display')
    ig_pres_low_display = pvproperty(
        name='LOPR', dtype=ChannelType.DOUBLE, doc='IG Pres Low Display')
    ig_log10_high_display = pvproperty(
        name='HLPR', dtype=ChannelType.DOUBLE, doc='IG Log10 High Display')
    ig_log10_low_display = pvproperty(
        name='LLPR', dtype=ChannelType.DOUBLE, doc='IG Log10 Low Display')
    cga_pres_high_display = pvproperty(
        name='HAPR', dtype=ChannelType.DOUBLE, doc='CGA Pres High Display')
    cga_pres_low_display = pvproperty(
        name='LAPR', dtype=ChannelType.DOUBLE, doc='CGA Pres Low Display')
    cga_log10_high_display = pvproperty(
        name='HALR', dtype=ChannelType.DOUBLE, doc='CGA Log10 High Display')
    cga_log10_low_display = pvproperty(
        name='LALR', dtype=ChannelType.DOUBLE, doc='CGA Log10 Low Display')
    cgb_pres_high_display = pvproperty(
        name='HBPR', dtype=ChannelType.DOUBLE, doc='CGB Pres High Display')
    cgb_pres_low_display = pvproperty(
        name='LBPR', dtype=ChannelType.DOUBLE, doc='CGB Pres Low Display')
    cgb_log10_high_display = pvproperty(
        name='HBLR', dtype=ChannelType.DOUBLE, doc='CGB Log10 High Display')
    cgb_log10_low_display = pvproperty(
        name='LBLR', dtype=ChannelType.DOUBLE, doc='CGB Log10 Low Display')


@register_record
class WaveformFields(RecordFieldGroup):
    _record_type = 'waveform'
    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc='Alarm Status',
        read_only=True)
    busy_indicator = pvproperty(
        name='BUSY',
        dtype=ChannelType.LONG,
        doc='Busy Indicator',
        read_only=True)
    hash_of_onchange_data = pvproperty(
        name='HASH', dtype=ChannelType.LONG, doc='Hash of OnChange data.')
    number_elements_read = pvproperty(
        name='NORD',
        dtype=ChannelType.LONG,
        doc='Number elements read',
        read_only=True)
    simulation_mode = pvproperty(
        name='SIMM',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuYesNo.get_string_tuple(),
        doc='Simulation Mode')
    display_precision = pvproperty(
        name='PREC', dtype=ChannelType.LONG, doc='Display Precision')
    engineering_units_name = pvproperty(
        name='EGU',
        dtype=ChannelType.CHAR,
        max_length=16,
        doc='Engineering Units Name')
    high_operating_range = pvproperty(
        name='HOPR', dtype=ChannelType.DOUBLE, doc='High Operating Range')
    low_operating_range = pvproperty(
        name='LOPR', dtype=ChannelType.DOUBLE, doc='Low Operating Range')
    post_archive_monitors = pvproperty(
        name='APST',
        dtype=ChannelType.ENUM,
        enum_strings=menus.waveformPOST.get_string_tuple(),
        doc='Post Archive Monitors')
    post_value_monitors = pvproperty(
        name='MPST',
        dtype=ChannelType.ENUM,
        enum_strings=menus.waveformPOST.get_string_tuple(),
        doc='Post Value Monitors')
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
    field_type_of_value = pvproperty(
        name='FTVL',
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc='Field Type of Value',
        read_only=True)
    number_of_elements = pvproperty(
        name='NELM',
        dtype=ChannelType.LONG,
        doc='Number of Elements',
        read_only=True)
    rearm_the_waveform = pvproperty(
        name='RARM', dtype=ChannelType.LONG, doc='Rearm the waveform')
    _link_parent_attribute(display_precision, 'precision')
    _link_parent_attribute(high_operating_range, 'upper_ctrl_limit')
    _link_parent_attribute(low_operating_range, 'lower_ctrl_limit')
    _link_parent_attribute(number_of_elements, 'max_length')


__all__ = ['records', 'RecordFieldGroup'] + list(records.keys())
