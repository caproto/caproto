'''
Contains PVGroups representing all fields of EPICS base records (minus .VAL)
'''

import inspect

from .high_level_server import PVGroup, pvproperty
from .._data import ChannelType


class RecordFieldGroup(PVGroup):
    alarm_acknowledge_severity = pvproperty(
        name='ACKS',
        dtype=ChannelType.ENUM,
        enum_strings=(b'NO_ALARM', b'MINOR', b'MAJOR', b'INVALID'),
        doc='Alarm Ack Severity')

    alarm_acknowledge_transient = pvproperty(
        name='ACKT',
        dtype=ChannelType.ENUM,
        enum_strings=(b'NO', b'YES'),
        doc='Alarm Ack Transient')

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
        enum_strings=(b'NO_ALARM', b'MINOR', b'MAJOR', b'INVALID'),
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
        name='LCNT', dtype=ChannelType.CHAR, doc='Lock Count')

    record_name = pvproperty(
        name='NAME', dtype=ChannelType.CHAR, max_length=61, doc='Record Name')

    new_alarm_severity = pvproperty(
        name='NSEV',
        dtype=ChannelType.ENUM,
        enum_strings=(b'NO_ALARM', b'MINOR', b'MAJOR', b'INVALID'),
        doc='New Alarm Severity')

    new_alarm_status = pvproperty(
        name='NSTA',
        dtype=ChannelType.ENUM,
        enum_strings=(b'NO_ALARM', b'READ', b'WRITE', b'HIHI', b'HIGH',
                      b'LOLO', b'LOW', b'STATE', b'COS', b'COMM', b'TIMEOUT',
                      b'HWLIMIT', b'CALC', b'SCAN', b'LINK', b'SOFT',
                      b'BAD_SUB', b'UDF', b'DISABLE', b'SIMM', b'READ_ACCESS',
                      b'WRITE_ACCESS'),
        doc='New Alarm Status')

    processing_active = pvproperty(
        name='PACT', dtype=ChannelType.CHAR, doc='Record active')

    scan_phase_number = pvproperty(
        name='PHAS', dtype=ChannelType.LONG, doc='Scan Phase')

    process_at_initialization = pvproperty(
        name='PINI',
        dtype=ChannelType.ENUM,
        enum_strings=(b'NO', b'YES', b'RUN', b'RUNNING', b'PAUSE', b'PAUSED'),
        doc='Process at iocInit')

    priority = pvproperty(
        name='PRIO',
        dtype=ChannelType.ENUM,
        enum_strings=(b'LOW', b'MEDIUM', b'HIGH'),
        doc='Scheduling Priority')

    process_record = pvproperty(
        name='PROC', dtype=ChannelType.CHAR, doc='Force Processing')

    dbputfield_process = pvproperty(
        name='PUTF', dtype=ChannelType.CHAR, doc='dbPutField process')

    reprocess = pvproperty(
        name='RPRO', dtype=ChannelType.CHAR, doc='Reprocess')

    scanning_rate = pvproperty(
        name='SCAN',
        dtype=ChannelType.ENUM,
        enum_strings=(b'Passive', b'Event', b'I/O Intr', b'10 second',
                      b'5 second', b'2 second', b'1 second', b'.5 second',
                      b'.2 second', b'.1 second'),
        doc='Scan Mechanism')

    scan_disable_input_link = pvproperty(
        name='SDIS', dtype=ChannelType.STRING, doc='Scanning Disable')

    current_alarm_severity = pvproperty(
        name='SEVR',
        dtype=ChannelType.ENUM,
        enum_strings=(b'NO_ALARM', b'MINOR', b'MAJOR', b'INVALID'),
        doc='Alarm Severity')

    trace_processing = pvproperty(
        name='TPRO', dtype=ChannelType.CHAR, doc='Trace Processing')

    time_stamp_event = pvproperty(
        name='TSE', dtype=ChannelType.LONG, doc='Time Stamp Event')

    time_stamp_event_link = pvproperty(
        name='TSEL', dtype=ChannelType.STRING, doc='Time Stamp Link')

    val_undefined = pvproperty(
        name='UDF', dtype=ChannelType.CHAR, doc='Undefined')


class AiFields(RecordFieldGroup):
    _record_type = 'ai'
    value = pvproperty(
        name='VAL', dtype=ChannelType.DOUBLE, doc='Current EGU Value')

    alarm_status = pvproperty(
        name='STAT',
        dtype=ChannelType.ENUM,
        enum_strings=(b'NO_ALARM', b'READ', b'WRITE', b'HIHI', b'HIGH',
                      b'LOLO', b'LOW', b'STATE', b'COS', b'COMM', b'TIMEOUT',
                      b'HWLIMIT', b'CALC', b'SCAN', b'LINK', b'SOFT',
                      b'BAD_SUB', b'UDF', b'DISABLE', b'SIMM', b'READ_ACCESS',
                      b'WRITE_ACCESS'),
        doc='Alarm Status')

    current_raw_value = pvproperty(
        name='RVAL', dtype=ChannelType.LONG, doc='Current Raw Value')

    initialized = pvproperty(
        name='INIT', dtype=ChannelType.LONG, doc='Initialized?')

    last_val_monitored = pvproperty(
        name='MLST', dtype=ChannelType.DOUBLE, doc='Last Val Monitored')

    last_value_alarmed = pvproperty(
        name='LALM', dtype=ChannelType.DOUBLE, doc='Last Value Alarmed')

    last_value_archived = pvproperty(
        name='ALST', dtype=ChannelType.DOUBLE, doc='Last Value Archived')

    lastbreak_point = pvproperty(
        name='LBRK', dtype=ChannelType.LONG, doc='LastBreak Point')

    previous_raw_value = pvproperty(
        name='ORAW', dtype=ChannelType.LONG, doc='Previous Raw Value')

    raw_offset_obsolete = pvproperty(
        name='ROFF', dtype=ChannelType.LONG, doc='Raw Offset, obsolete')

    simulation_mode = pvproperty(
        name='SIMM',
        dtype=ChannelType.ENUM,
        enum_strings=(b'NO', b'YES', b'RAW'),
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
        enum_strings=(b'NO_ALARM', b'MINOR', b'MAJOR', b'INVALID'),
        doc='High Severity')

    hihi_alarm_limit = pvproperty(
        name='HIHI', dtype=ChannelType.DOUBLE, doc='Hihi Alarm Limit')

    hihi_severity = pvproperty(
        name='HHSV',
        dtype=ChannelType.ENUM,
        enum_strings=(b'NO_ALARM', b'MINOR', b'MAJOR', b'INVALID'),
        doc='Hihi Severity')

    lolo_alarm_limit = pvproperty(
        name='LOLO', dtype=ChannelType.DOUBLE, doc='Lolo Alarm Limit')

    lolo_severity = pvproperty(
        name='LLSV',
        dtype=ChannelType.ENUM,
        enum_strings=(b'NO_ALARM', b'MINOR', b'MAJOR', b'INVALID'),
        doc='Lolo Severity')

    low_alarm_limit = pvproperty(
        name='LOW', dtype=ChannelType.DOUBLE, doc='Low Alarm Limit')

    low_severity = pvproperty(
        name='LSV',
        dtype=ChannelType.ENUM,
        enum_strings=(b'NO_ALARM', b'MINOR', b'MAJOR', b'INVALID'),
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
        enum_strings=(b'NO CONVERSION', b'SLOPE', b'LINEAR', b'typeKdegF',
                      b'typeKdegC', b'typeJdegF', b'typeJdegC',
                      b'typeEdegF(ixe only)', b'typeEdegC(ixe only)',
                      b'typeTdegF', b'typeTdegC', b'typeRdegF', b'typeRdegC',
                      b'typeSdegF', b'typeSdegC'),
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
        enum_strings=(b'NO_ALARM', b'MINOR', b'MAJOR', b'INVALID'),
        doc='Sim mode Alarm Svrty')


records = {record._record_type: record
           for name, record in globals().items()
           if inspect.isclass(record) and
           issubclass(record, PVGroup) and
           record is not PVGroup
           }
__all__ = ['records'] + list(records.keys())
