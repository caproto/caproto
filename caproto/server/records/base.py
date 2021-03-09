"""
Contains the base field representation for EPICS base records.

This file is auto-generated.  Do not modify it.

If you need to add or modify fields to correct something, please use the
``reference-dbd`` project to regenerate this file.

If you need to add functionality to any record, see the module
:mod:`caproto.server.records.records`.
"""
# **NOTE** **NOTE**
# This file is auto-generated.  Please see the module docstring for details.
# **NOTE** **NOTE**
from ..._data import ChannelType
from .. import menus
from ..server import PVGroup, pvproperty
from .mixins import _Limits, _LimitsLong
from .utils import copy_pvproperties, link_parent_attribute


class RecordFieldGroup(PVGroup):
    _scan_rate_sec = None
    _dtype = None  # to be set by subclasses
    has_val_field = True

    alarm_acknowledge_severity = pvproperty(
        name="ACKS",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Alarm Ack Severity",
        read_only=True,
    )
    alarm_acknowledge_transient = pvproperty(
        name="ACKT",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuYesNo.get_string_tuple(),
        doc="Alarm Ack Transient",
        read_only=True,
        value="YES",
    )
    access_security_group = pvproperty(
        name="ASG",
        dtype=ChannelType.CHAR,
        max_length=29,
        report_as_string=True,
        doc="Access Security Group",
    )
    description = pvproperty(
        name="DESC",
        dtype=ChannelType.CHAR,
        max_length=41,
        report_as_string=True,
        doc="Descriptor",
    )
    disable = pvproperty(name="DISA", dtype=ChannelType.INT, doc="Disable")
    disable_putfield = pvproperty(
        name="DISP", dtype=ChannelType.CHAR, doc="Disable putField"
    )
    disable_alarm_severity = pvproperty(
        name="DISS",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Disable Alarm Sevrty",
    )
    disable_value = pvproperty(
        name="DISV", dtype=ChannelType.INT, doc="Disable Value", value=1
    )
    device_type = pvproperty(
        name="DTYP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.dtyp_base.get_string_tuple(),
        doc="Device Type",
    )
    event_name = pvproperty(
        name="EVNT",
        dtype=ChannelType.CHAR,
        max_length=40,
        report_as_string=True,
        doc="Event Name",
    )
    forward_link = pvproperty(
        name="FLNK", dtype=ChannelType.STRING, doc="Forward Process Link"
    )
    lock_count = pvproperty(
        name="LCNT", dtype=ChannelType.CHAR, doc="Lock Count", read_only=True
    )
    record_name = pvproperty(
        name="NAME",
        dtype=ChannelType.CHAR,
        max_length=61,
        report_as_string=True,
        doc="Record Name",
        read_only=True,
    )
    new_alarm_severity = pvproperty(
        name="NSEV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="New Alarm Severity",
        read_only=True,
    )
    new_alarm_status = pvproperty(
        name="NSTA",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc="New Alarm Status",
        read_only=True,
    )
    record_active = pvproperty(
        name="PACT", dtype=ChannelType.CHAR, doc="Record active", read_only=True
    )
    scan_phase = pvproperty(
        name="PHAS", dtype=ChannelType.INT, doc="Scan Phase"
    )
    process_at_iocinit = pvproperty(
        name="PINI",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuPini.get_string_tuple(),
        doc="Process at iocInit",
    )
    scheduling_priority = pvproperty(
        name="PRIO",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuPriority.get_string_tuple(),
        doc="Scheduling Priority",
    )
    process_record = pvproperty(
        name="PROC", dtype=ChannelType.CHAR, doc="Force Processing"
    )
    dbputfield_process = pvproperty(
        name="PUTF",
        dtype=ChannelType.CHAR,
        doc="dbPutField process",
        read_only=True,
    )
    reprocess = pvproperty(
        name="RPRO", dtype=ChannelType.CHAR, doc="Reprocess ", read_only=True
    )
    scan_rate = pvproperty(
        name="SCAN",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuScan.get_string_tuple(),
        doc="Scan Mechanism",
    )
    scanning_disable = pvproperty(
        name="SDIS", dtype=ChannelType.STRING, doc="Scanning Disable"
    )
    current_alarm_severity = pvproperty(
        name="SEVR",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Alarm Severity",
        read_only=True,
    )
    trace_processing = pvproperty(
        name="TPRO", dtype=ChannelType.CHAR, doc="Trace Processing"
    )
    time_stamp_event = pvproperty(
        name="TSE", dtype=ChannelType.INT, doc="Time Stamp Event"
    )
    time_stamp_link = pvproperty(
        name="TSEL", dtype=ChannelType.STRING, doc="Time Stamp Link"
    )
    undefined = pvproperty(
        name="UDF", dtype=ChannelType.CHAR, doc="Undefined", value=chr(1)
    )
    alarm_status = pvproperty(
        name="STAT",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmStat.get_string_tuple(),
        doc="Alarm Status",
        read_only=True,
        value="NO_ALARM",
    )
    undefined_alarm_severity = pvproperty(
        name="UDFS",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Undefined Alarm Sevrty",
        value="INVALID",
    )


class AiFields(RecordFieldGroup, _Limits):
    _record_type = "ai"
    _dtype = ChannelType.DOUBLE  # DTYP of .VAL
    has_val_field = True
    copy_pvproperties(locals(), RecordFieldGroup, _Limits)
    device_type = pvproperty(
        name="DTYP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.dtyp_ai.get_string_tuple(),
        doc="Device Type",
    )
    current_raw_value = pvproperty(
        name="RVAL", dtype=ChannelType.LONG, doc="Current Raw Value"
    )
    initialized = pvproperty(
        name="INIT", dtype=ChannelType.INT, doc="Initialized?", read_only=True
    )
    last_val_monitored = pvproperty(
        name="MLST",
        dtype=ChannelType.DOUBLE,
        doc="Last Val Monitored",
        read_only=True,
    )
    last_value_alarmed = pvproperty(
        name="LALM",
        dtype=ChannelType.DOUBLE,
        doc="Last Value Alarmed",
        read_only=True,
    )
    last_value_archived = pvproperty(
        name="ALST",
        dtype=ChannelType.DOUBLE,
        doc="Last Value Archived",
        read_only=True,
    )
    lastbreak_point = pvproperty(
        name="LBRK",
        dtype=ChannelType.INT,
        doc="LastBreak Point",
        read_only=True,
    )
    previous_raw_value = pvproperty(
        name="ORAW",
        dtype=ChannelType.LONG,
        doc="Previous Raw Value",
        read_only=True,
    )
    raw_offset = pvproperty(
        name="ROFF", dtype=ChannelType.LONG, doc="Raw Offset"
    )
    simulation_mode = pvproperty(
        name="SIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuSimm.get_string_tuple(),
        doc="Simulation Mode",
    )
    simulation_value = pvproperty(
        name="SVAL", dtype=ChannelType.DOUBLE, doc="Simulation Value"
    )
    alarm_deadband = pvproperty(
        name="HYST", dtype=ChannelType.DOUBLE, doc="Alarm Deadband"
    )
    adjustment_offset = pvproperty(
        name="AOFF", dtype=ChannelType.DOUBLE, doc="Adjustment Offset"
    )
    adjustment_slope = pvproperty(
        name="ASLO", dtype=ChannelType.DOUBLE, doc="Adjustment Slope", value=1
    )
    engineer_units_full = pvproperty(
        name="EGUF", dtype=ChannelType.DOUBLE, doc="Engineer Units Full"
    )
    engineer_units_low = pvproperty(
        name="EGUL", dtype=ChannelType.DOUBLE, doc="Engineer Units Low"
    )
    linearization = pvproperty(
        name="LINR",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuConvert.get_string_tuple(),
        doc="Linearization",
    )
    raw_to_egu_offset = pvproperty(
        name="EOFF", dtype=ChannelType.DOUBLE, doc="Raw to EGU Offset"
    )
    raw_to_egu_slope = pvproperty(
        name="ESLO", dtype=ChannelType.DOUBLE, doc="Raw to EGU Slope", value=1
    )
    smoothing = pvproperty(
        name="SMOO", dtype=ChannelType.DOUBLE, doc="Smoothing"
    )
    archive_deadband = pvproperty(
        name="ADEL", dtype=ChannelType.DOUBLE, doc="Archive Deadband"
    )
    display_precision = pvproperty(
        name="PREC", dtype=ChannelType.INT, doc="Display Precision"
    )
    engineering_units = pvproperty(
        name="EGU",
        dtype=ChannelType.CHAR,
        max_length=16,
        report_as_string=True,
        doc="Engineering Units",
    )
    monitor_deadband = pvproperty(
        name="MDEL", dtype=ChannelType.DOUBLE, doc="Monitor Deadband"
    )
    input_specification = pvproperty(
        name="INP", dtype=ChannelType.STRING, doc="Input Specification"
    )
    simulation_input_link = pvproperty(
        name="SIOL", dtype=ChannelType.STRING, doc="Simulation Input Link"
    )
    simulation_mode_link = pvproperty(
        name="SIML", dtype=ChannelType.STRING, doc="Simulation Mode Link"
    )
    simulation_mode_severity = pvproperty(
        name="SIMS",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Simulation Mode Severity",
    )
    alarm_filter_time_constant = pvproperty(
        name="AFTC", dtype=ChannelType.DOUBLE, doc="Alarm Filter Time Constant"
    )
    alarm_filter_value = pvproperty(
        name="AFVL",
        dtype=ChannelType.DOUBLE,
        doc="Alarm Filter Value",
        read_only=True,
    )
    prev_simulation_mode = pvproperty(
        name="OLDSIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuSimm.get_string_tuple(),
        doc="Prev. Simulation Mode",
        read_only=True,
    )
    sim_mode_async_delay = pvproperty(
        name="SDLY",
        dtype=ChannelType.DOUBLE,
        doc="Sim. Mode Async Delay",
        value=-1.0,
    )
    sim_mode_scan = pvproperty(
        name="SSCN",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuScan.get_string_tuple(),
        doc="Sim. Mode Scan",
        value=0,
    )
    # current_egu_value = pvproperty(name='VAL',
    #      dtype=ChannelType.DOUBLE,
    # doc='Current EGU Value')
    link_parent_attribute(
        display_precision, "precision",
    )
    link_parent_attribute(archive_deadband, "log_atol", use_setattr=True)
    link_parent_attribute(monitor_deadband, "value_atol", use_setattr=True)


class AsubFields(RecordFieldGroup):
    _record_type = "aSub"
    _dtype = ChannelType.LONG  # DTYP of .VAL
    has_val_field = True
    copy_pvproperties(locals(), RecordFieldGroup)
    device_type = pvproperty(
        name="DTYP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.dtyp_aSub.get_string_tuple(),
        doc="Device Type",
    )
    bad_return_severity = pvproperty(
        name="BRSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Bad Return Severity",
    )
    output_event_flag = pvproperty(
        name="EFLG",
        dtype=ChannelType.ENUM,
        enum_strings=menus.aSubEFLG.get_string_tuple(),
        doc="Output Event Flag",
        value=1,
    )
    type_of_a = pvproperty(
        name="FTA",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of A",
        read_only=True,
        value="DOUBLE",
    )
    type_of_b = pvproperty(
        name="FTB",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of B",
        read_only=True,
        value="DOUBLE",
    )
    type_of_c = pvproperty(
        name="FTC",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of C",
        read_only=True,
        value="DOUBLE",
    )
    type_of_d = pvproperty(
        name="FTD",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of D",
        read_only=True,
        value="DOUBLE",
    )
    type_of_e = pvproperty(
        name="FTE",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of E",
        read_only=True,
        value="DOUBLE",
    )
    type_of_f = pvproperty(
        name="FTF",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of F",
        read_only=True,
        value="DOUBLE",
    )
    type_of_g = pvproperty(
        name="FTG",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of G",
        read_only=True,
        value="DOUBLE",
    )
    type_of_h = pvproperty(
        name="FTH",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of H",
        read_only=True,
        value="DOUBLE",
    )
    type_of_i = pvproperty(
        name="FTI",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of I",
        read_only=True,
        value="DOUBLE",
    )
    type_of_j = pvproperty(
        name="FTJ",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of J",
        read_only=True,
        value="DOUBLE",
    )
    type_of_k = pvproperty(
        name="FTK",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of K",
        read_only=True,
        value="DOUBLE",
    )
    type_of_l = pvproperty(
        name="FTL",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of L",
        read_only=True,
        value="DOUBLE",
    )
    type_of_m = pvproperty(
        name="FTM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of M",
        read_only=True,
        value="DOUBLE",
    )
    type_of_n = pvproperty(
        name="FTN",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of N",
        read_only=True,
        value="DOUBLE",
    )
    type_of_o = pvproperty(
        name="FTO",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of O",
        read_only=True,
        value="DOUBLE",
    )
    type_of_p = pvproperty(
        name="FTP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of P",
        read_only=True,
        value="DOUBLE",
    )
    type_of_q = pvproperty(
        name="FTQ",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of Q",
        read_only=True,
        value="DOUBLE",
    )
    type_of_r = pvproperty(
        name="FTR",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of R",
        read_only=True,
        value="DOUBLE",
    )
    type_of_s = pvproperty(
        name="FTS",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of S",
        read_only=True,
        value="DOUBLE",
    )
    type_of_t = pvproperty(
        name="FTT",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of T",
        read_only=True,
        value="DOUBLE",
    )
    type_of_u = pvproperty(
        name="FTU",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of U",
        read_only=True,
        value="DOUBLE",
    )
    type_of_vala = pvproperty(
        name="FTVA",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of VALA",
        read_only=True,
        value="DOUBLE",
    )
    type_of_valb = pvproperty(
        name="FTVB",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of VALB",
        read_only=True,
        value="DOUBLE",
    )
    type_of_valc = pvproperty(
        name="FTVC",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of VALC",
        read_only=True,
        value="DOUBLE",
    )
    type_of_vald = pvproperty(
        name="FTVD",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of VALD",
        read_only=True,
        value="DOUBLE",
    )
    type_of_vale = pvproperty(
        name="FTVE",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of VALE",
        read_only=True,
        value="DOUBLE",
    )
    type_of_valf = pvproperty(
        name="FTVF",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of VALF",
        read_only=True,
        value="DOUBLE",
    )
    type_of_valg = pvproperty(
        name="FTVG",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of VALG",
        read_only=True,
        value="DOUBLE",
    )
    type_of_valh = pvproperty(
        name="FTVH",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of VALH",
        read_only=True,
        value="DOUBLE",
    )
    type_of_vali = pvproperty(
        name="FTVI",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of VALI",
        read_only=True,
        value="DOUBLE",
    )
    type_of_valj = pvproperty(
        name="FTVJ",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of VALJ",
        read_only=True,
        value="DOUBLE",
    )
    type_of_valk = pvproperty(
        name="FTVK",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of VALK",
        read_only=True,
        value="DOUBLE",
    )
    type_of_vall = pvproperty(
        name="FTVL",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of VALL",
        read_only=True,
        value="DOUBLE",
    )
    type_of_valm = pvproperty(
        name="FTVM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of VALM",
        read_only=True,
        value="DOUBLE",
    )
    type_of_valn = pvproperty(
        name="FTVN",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of VALN",
        read_only=True,
        value="DOUBLE",
    )
    type_of_valo = pvproperty(
        name="FTVO",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of VALO",
        read_only=True,
        value="DOUBLE",
    )
    type_of_valp = pvproperty(
        name="FTVP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of VALP",
        read_only=True,
        value="DOUBLE",
    )
    type_of_valq = pvproperty(
        name="FTVQ",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of VALQ",
        read_only=True,
        value="DOUBLE",
    )
    type_of_valr = pvproperty(
        name="FTVR",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of VALR",
        read_only=True,
        value="DOUBLE",
    )
    type_of_vals = pvproperty(
        name="FTVS",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of VALS",
        read_only=True,
        value="DOUBLE",
    )
    type_of_valt = pvproperty(
        name="FTVT",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of VALT",
        read_only=True,
        value="DOUBLE",
    )
    type_of_valu = pvproperty(
        name="FTVU",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Type of VALU",
        read_only=True,
        value="DOUBLE",
    )
    initialize_subr_name = pvproperty(
        name="INAM",
        dtype=ChannelType.CHAR,
        max_length=41,
        report_as_string=True,
        doc="Initialize Subr. Name",
        read_only=True,
    )
    input_link_a = pvproperty(
        name="INPA", dtype=ChannelType.STRING, doc="Input Link A"
    )
    input_link_b = pvproperty(
        name="INPB", dtype=ChannelType.STRING, doc="Input Link B"
    )
    input_link_c = pvproperty(
        name="INPC", dtype=ChannelType.STRING, doc="Input Link C"
    )
    input_link_d = pvproperty(
        name="INPD", dtype=ChannelType.STRING, doc="Input Link D"
    )
    input_link_e = pvproperty(
        name="INPE", dtype=ChannelType.STRING, doc="Input Link E"
    )
    input_link_f = pvproperty(
        name="INPF", dtype=ChannelType.STRING, doc="Input Link F"
    )
    input_link_g = pvproperty(
        name="INPG", dtype=ChannelType.STRING, doc="Input Link G"
    )
    input_link_h = pvproperty(
        name="INPH", dtype=ChannelType.STRING, doc="Input Link H"
    )
    input_link_i = pvproperty(
        name="INPI", dtype=ChannelType.STRING, doc="Input Link I"
    )
    input_link_j = pvproperty(
        name="INPJ", dtype=ChannelType.STRING, doc="Input Link J"
    )
    input_link_k = pvproperty(
        name="INPK", dtype=ChannelType.STRING, doc="Input Link K"
    )
    input_link_l = pvproperty(
        name="INPL", dtype=ChannelType.STRING, doc="Input Link L"
    )
    input_link_m = pvproperty(
        name="INPM", dtype=ChannelType.STRING, doc="Input Link M"
    )
    input_link_n = pvproperty(
        name="INPN", dtype=ChannelType.STRING, doc="Input Link N"
    )
    input_link_o = pvproperty(
        name="INPO", dtype=ChannelType.STRING, doc="Input Link O"
    )
    input_link_p = pvproperty(
        name="INPP", dtype=ChannelType.STRING, doc="Input Link P"
    )
    input_link_q = pvproperty(
        name="INPQ", dtype=ChannelType.STRING, doc="Input Link Q"
    )
    input_link_r = pvproperty(
        name="INPR", dtype=ChannelType.STRING, doc="Input Link R"
    )
    input_link_s = pvproperty(
        name="INPS", dtype=ChannelType.STRING, doc="Input Link S"
    )
    input_link_t = pvproperty(
        name="INPT", dtype=ChannelType.STRING, doc="Input Link T"
    )
    input_link_u = pvproperty(
        name="INPU", dtype=ChannelType.STRING, doc="Input Link U"
    )
    subr_input_enable = pvproperty(
        name="LFLG",
        dtype=ChannelType.ENUM,
        enum_strings=menus.aSubLFLG.get_string_tuple(),
        doc="Subr. Input Enable",
    )
    num_elements_in_a = pvproperty(
        name="NEA",
        dtype=ChannelType.LONG,
        doc="Num. elements in A",
        read_only=True,
        value=1,
    )
    num_elements_in_b = pvproperty(
        name="NEB",
        dtype=ChannelType.LONG,
        doc="Num. elements in B",
        read_only=True,
        value=1,
    )
    num_elements_in_c = pvproperty(
        name="NEC",
        dtype=ChannelType.LONG,
        doc="Num. elements in C",
        read_only=True,
        value=1,
    )
    num_elements_in_d = pvproperty(
        name="NED",
        dtype=ChannelType.LONG,
        doc="Num. elements in D",
        read_only=True,
        value=1,
    )
    num_elements_in_e = pvproperty(
        name="NEE",
        dtype=ChannelType.LONG,
        doc="Num. elements in E",
        read_only=True,
        value=1,
    )
    num_elements_in_f = pvproperty(
        name="NEF",
        dtype=ChannelType.LONG,
        doc="Num. elements in F",
        read_only=True,
        value=1,
    )
    num_elements_in_g = pvproperty(
        name="NEG",
        dtype=ChannelType.LONG,
        doc="Num. elements in G",
        read_only=True,
        value=1,
    )
    num_elements_in_h = pvproperty(
        name="NEH",
        dtype=ChannelType.LONG,
        doc="Num. elements in H",
        read_only=True,
        value=1,
    )
    num_elements_in_i = pvproperty(
        name="NEI",
        dtype=ChannelType.LONG,
        doc="Num. elements in I",
        read_only=True,
        value=1,
    )
    num_elements_in_j = pvproperty(
        name="NEJ",
        dtype=ChannelType.LONG,
        doc="Num. elements in J",
        read_only=True,
        value=1,
    )
    num_elements_in_k = pvproperty(
        name="NEK",
        dtype=ChannelType.LONG,
        doc="Num. elements in K",
        read_only=True,
        value=1,
    )
    num_elements_in_l = pvproperty(
        name="NEL",
        dtype=ChannelType.LONG,
        doc="Num. elements in L",
        read_only=True,
        value=1,
    )
    num_elements_in_m = pvproperty(
        name="NEM",
        dtype=ChannelType.LONG,
        doc="Num. elements in M",
        read_only=True,
        value=1,
    )
    num_elements_in_n = pvproperty(
        name="NEN",
        dtype=ChannelType.LONG,
        doc="Num. elements in N",
        read_only=True,
        value=1,
    )
    num_elements_in_o = pvproperty(
        name="NEO",
        dtype=ChannelType.LONG,
        doc="Num. elements in O",
        read_only=True,
        value=1,
    )
    num_elements_in_p = pvproperty(
        name="NEP",
        dtype=ChannelType.LONG,
        doc="Num. elements in P",
        read_only=True,
        value=1,
    )
    num_elements_in_q = pvproperty(
        name="NEQ",
        dtype=ChannelType.LONG,
        doc="Num. elements in Q",
        read_only=True,
        value=1,
    )
    num_elements_in_r = pvproperty(
        name="NER",
        dtype=ChannelType.LONG,
        doc="Num. elements in R",
        read_only=True,
        value=1,
    )
    num_elements_in_s = pvproperty(
        name="NES",
        dtype=ChannelType.LONG,
        doc="Num. elements in S",
        read_only=True,
        value=1,
    )
    num_elements_in_t = pvproperty(
        name="NET",
        dtype=ChannelType.LONG,
        doc="Num. elements in T",
        read_only=True,
        value=1,
    )
    num_elements_in_u = pvproperty(
        name="NEU",
        dtype=ChannelType.LONG,
        doc="Num. elements in U",
        read_only=True,
        value=1,
    )
    num_elements_in_vala = pvproperty(
        name="NEVA",
        dtype=ChannelType.LONG,
        doc="Num. elements in VALA",
        read_only=True,
        value=1,
    )
    num_elements_in_valb = pvproperty(
        name="NEVB",
        dtype=ChannelType.LONG,
        doc="Num. elements in VALB",
        read_only=True,
        value=1,
    )
    num_elements_in_valc = pvproperty(
        name="NEVC",
        dtype=ChannelType.LONG,
        doc="Num. elements in VALC",
        read_only=True,
        value=1,
    )
    num_elements_in_vald = pvproperty(
        name="NEVD",
        dtype=ChannelType.LONG,
        doc="Num. elements in VALD",
        read_only=True,
        value=1,
    )
    num_elements_in_vale = pvproperty(
        name="NEVE",
        dtype=ChannelType.LONG,
        doc="Num. elements in VALE",
        read_only=True,
        value=1,
    )
    num_elements_in_valf = pvproperty(
        name="NEVF",
        dtype=ChannelType.LONG,
        doc="Num. elements in VALF",
        read_only=True,
        value=1,
    )
    num_elements_in_valg = pvproperty(
        name="NEVG",
        dtype=ChannelType.LONG,
        doc="Num. elements in VALG",
        read_only=True,
        value=1,
    )
    num_elements_in_valh = pvproperty(
        name="NEVH",
        dtype=ChannelType.LONG,
        doc="Num. elements in VAlH",
        read_only=True,
        value=1,
    )
    num_elements_in_vali = pvproperty(
        name="NEVI",
        dtype=ChannelType.LONG,
        doc="Num. elements in VALI",
        read_only=True,
        value=1,
    )
    num_elements_in_valj = pvproperty(
        name="NEVJ",
        dtype=ChannelType.LONG,
        doc="Num. elements in VALJ",
        read_only=True,
        value=1,
    )
    num_elements_in_valk = pvproperty(
        name="NEVK",
        dtype=ChannelType.LONG,
        doc="Num. elements in VALK",
        read_only=True,
        value=1,
    )
    num_elements_in_vall = pvproperty(
        name="NEVL",
        dtype=ChannelType.LONG,
        doc="Num. elements in VALL",
        read_only=True,
        value=1,
    )
    num_elements_in_valm = pvproperty(
        name="NEVM",
        dtype=ChannelType.LONG,
        doc="Num. elements in VALM",
        read_only=True,
        value=1,
    )
    num_elements_in_valn = pvproperty(
        name="NEVN",
        dtype=ChannelType.LONG,
        doc="Num. elements in VALN",
        read_only=True,
        value=1,
    )
    num_elements_in_valo = pvproperty(
        name="NEVO",
        dtype=ChannelType.LONG,
        doc="Num. elements in VALO",
        read_only=True,
        value=1,
    )
    num_elements_in_valp = pvproperty(
        name="NEVP",
        dtype=ChannelType.LONG,
        doc="Num. elements in VALP",
        read_only=True,
        value=1,
    )
    num_elements_in_valq = pvproperty(
        name="NEVQ",
        dtype=ChannelType.LONG,
        doc="Num. elements in VALQ",
        read_only=True,
        value=1,
    )
    num_elements_in_valr = pvproperty(
        name="NEVR",
        dtype=ChannelType.LONG,
        doc="Num. elements in VALR",
        read_only=True,
        value=1,
    )
    num_elements_in_vals = pvproperty(
        name="NEVS",
        dtype=ChannelType.LONG,
        doc="Num. elements in VALS",
        read_only=True,
        value=1,
    )
    num_elements_in_valt = pvproperty(
        name="NEVT",
        dtype=ChannelType.LONG,
        doc="Num. elements in VALT",
        read_only=True,
        value=1,
    )
    num_elements_in_valu = pvproperty(
        name="NEVU",
        dtype=ChannelType.LONG,
        doc="Num. elements in VALU",
        read_only=True,
        value=1,
    )
    max_elements_in_a = pvproperty(
        name="NOA",
        dtype=ChannelType.LONG,
        doc="Max. elements in A",
        read_only=True,
        value=1,
    )
    max_elements_in_b = pvproperty(
        name="NOB",
        dtype=ChannelType.LONG,
        doc="Max. elements in B",
        read_only=True,
        value=1,
    )
    max_elements_in_c = pvproperty(
        name="NOC",
        dtype=ChannelType.LONG,
        doc="Max. elements in C",
        read_only=True,
        value=1,
    )
    max_elements_in_d = pvproperty(
        name="NOD",
        dtype=ChannelType.LONG,
        doc="Max. elements in D",
        read_only=True,
        value=1,
    )
    max_elements_in_e = pvproperty(
        name="NOE",
        dtype=ChannelType.LONG,
        doc="Max. elements in E",
        read_only=True,
        value=1,
    )
    max_elements_in_f = pvproperty(
        name="NOF",
        dtype=ChannelType.LONG,
        doc="Max. elements in F",
        read_only=True,
        value=1,
    )
    max_elements_in_g = pvproperty(
        name="NOG",
        dtype=ChannelType.LONG,
        doc="Max. elements in G",
        read_only=True,
        value=1,
    )
    max_elements_in_h = pvproperty(
        name="NOH",
        dtype=ChannelType.LONG,
        doc="Max. elements in H",
        read_only=True,
        value=1,
    )
    max_elements_in_i = pvproperty(
        name="NOI",
        dtype=ChannelType.LONG,
        doc="Max. elements in I",
        read_only=True,
        value=1,
    )
    max_elements_in_j = pvproperty(
        name="NOJ",
        dtype=ChannelType.LONG,
        doc="Max. elements in J",
        read_only=True,
        value=1,
    )
    max_elements_in_k = pvproperty(
        name="NOK",
        dtype=ChannelType.LONG,
        doc="Max. elements in K",
        read_only=True,
        value=1,
    )
    max_elements_in_l = pvproperty(
        name="NOL",
        dtype=ChannelType.LONG,
        doc="Max. elements in L",
        read_only=True,
        value=1,
    )
    max_elements_in_m = pvproperty(
        name="NOM",
        dtype=ChannelType.LONG,
        doc="Max. elements in M",
        read_only=True,
        value=1,
    )
    max_elements_in_n = pvproperty(
        name="NON",
        dtype=ChannelType.LONG,
        doc="Max. elements in N",
        read_only=True,
        value=1,
    )
    max_elements_in_o = pvproperty(
        name="NOO",
        dtype=ChannelType.LONG,
        doc="Max. elements in O",
        read_only=True,
        value=1,
    )
    max_elements_in_p = pvproperty(
        name="NOP",
        dtype=ChannelType.LONG,
        doc="Max. elements in P",
        read_only=True,
        value=1,
    )
    max_elements_in_q = pvproperty(
        name="NOQ",
        dtype=ChannelType.LONG,
        doc="Max. elements in Q",
        read_only=True,
        value=1,
    )
    max_elements_in_r = pvproperty(
        name="NOR",
        dtype=ChannelType.LONG,
        doc="Max. elements in R",
        read_only=True,
        value=1,
    )
    max_elements_in_s = pvproperty(
        name="NOS",
        dtype=ChannelType.LONG,
        doc="Max. elements in S",
        read_only=True,
        value=1,
    )
    max_elements_in_t = pvproperty(
        name="NOT",
        dtype=ChannelType.LONG,
        doc="Max. elements in T",
        read_only=True,
        value=1,
    )
    max_elements_in_u = pvproperty(
        name="NOU",
        dtype=ChannelType.LONG,
        doc="Max. elements in U",
        read_only=True,
        value=1,
    )
    max_elements_in_vala = pvproperty(
        name="NOVA",
        dtype=ChannelType.LONG,
        doc="Max. elements in VALA",
        read_only=True,
        value=1,
    )
    max_elements_in_valb = pvproperty(
        name="NOVB",
        dtype=ChannelType.LONG,
        doc="Max. elements in VALB",
        read_only=True,
        value=1,
    )
    max_elements_in_valc = pvproperty(
        name="NOVC",
        dtype=ChannelType.LONG,
        doc="Max. elements in VALC",
        read_only=True,
        value=1,
    )
    max_elements_in_vald = pvproperty(
        name="NOVD",
        dtype=ChannelType.LONG,
        doc="Max. elements in VALD",
        read_only=True,
        value=1,
    )
    max_elements_in_vale = pvproperty(
        name="NOVE",
        dtype=ChannelType.LONG,
        doc="Max. elements in VALE",
        read_only=True,
        value=1,
    )
    max_elements_in_valf = pvproperty(
        name="NOVF",
        dtype=ChannelType.LONG,
        doc="Max. elements in VALF",
        read_only=True,
        value=1,
    )
    max_elements_in_valg = pvproperty(
        name="NOVG",
        dtype=ChannelType.LONG,
        doc="Max. elements in VALG",
        read_only=True,
        value=1,
    )
    max_elements_in_valh = pvproperty(
        name="NOVH",
        dtype=ChannelType.LONG,
        doc="Max. elements in VAlH",
        read_only=True,
        value=1,
    )
    max_elements_in_vali = pvproperty(
        name="NOVI",
        dtype=ChannelType.LONG,
        doc="Max. elements in VALI",
        read_only=True,
        value=1,
    )
    max_elements_in_valj = pvproperty(
        name="NOVJ",
        dtype=ChannelType.LONG,
        doc="Max. elements in VALJ",
        read_only=True,
        value=1,
    )
    max_elements_in_valk = pvproperty(
        name="NOVK",
        dtype=ChannelType.LONG,
        doc="Max. elements in VALK",
        read_only=True,
        value=1,
    )
    max_elements_in_vall = pvproperty(
        name="NOVL",
        dtype=ChannelType.LONG,
        doc="Max. elements in VALL",
        read_only=True,
        value=1,
    )
    max_elements_in_valm = pvproperty(
        name="NOVM",
        dtype=ChannelType.LONG,
        doc="Max. elements in VALM",
        read_only=True,
        value=1,
    )
    max_elements_in_valn = pvproperty(
        name="NOVN",
        dtype=ChannelType.LONG,
        doc="Max. elements in VALN",
        read_only=True,
        value=1,
    )
    max_elements_in_valo = pvproperty(
        name="NOVO",
        dtype=ChannelType.LONG,
        doc="Max. elements in VALO",
        read_only=True,
        value=1,
    )
    max_elements_in_valp = pvproperty(
        name="NOVP",
        dtype=ChannelType.LONG,
        doc="Max. elements in VALP",
        read_only=True,
        value=1,
    )
    max_elements_in_valq = pvproperty(
        name="NOVQ",
        dtype=ChannelType.LONG,
        doc="Max. elements in VALQ",
        read_only=True,
        value=1,
    )
    max_elements_in_valr = pvproperty(
        name="NOVR",
        dtype=ChannelType.LONG,
        doc="Max. elements in VALR",
        read_only=True,
        value=1,
    )
    max_elements_in_vals = pvproperty(
        name="NOVS",
        dtype=ChannelType.LONG,
        doc="Max. elements in VALS",
        read_only=True,
        value=1,
    )
    max_elements_in_valt = pvproperty(
        name="NOVT",
        dtype=ChannelType.LONG,
        doc="Max. elements in VALT",
        read_only=True,
        value=1,
    )
    max_elements_in_valu = pvproperty(
        name="NOVU",
        dtype=ChannelType.LONG,
        doc="Max. elements in VALU",
        read_only=True,
        value=1,
    )
    old_subr_name = pvproperty(
        name="ONAM",
        dtype=ChannelType.CHAR,
        max_length=41,
        report_as_string=True,
        doc="Old Subr. Name",
        read_only=True,
    )
    num_elements_in_ovla = pvproperty(
        name="ONVA",
        dtype=ChannelType.LONG,
        doc="Num. elements in OVLA",
        read_only=True,
        value=1,
    )
    num_elements_in_ovlb = pvproperty(
        name="ONVB",
        dtype=ChannelType.LONG,
        doc="Num. elements in OVLB",
        read_only=True,
        value=1,
    )
    num_elements_in_ovlc = pvproperty(
        name="ONVC",
        dtype=ChannelType.LONG,
        doc="Num. elements in OVLC",
        read_only=True,
        value=1,
    )
    num_elements_in_ovld = pvproperty(
        name="ONVD",
        dtype=ChannelType.LONG,
        doc="Num. elements in OVLD",
        read_only=True,
        value=1,
    )
    num_elements_in_ovle = pvproperty(
        name="ONVE",
        dtype=ChannelType.LONG,
        doc="Num. elements in OVLE",
        read_only=True,
        value=1,
    )
    num_elements_in_ovlf = pvproperty(
        name="ONVF",
        dtype=ChannelType.LONG,
        doc="Num. elements in OVLF",
        read_only=True,
        value=1,
    )
    num_elements_in_ovlg = pvproperty(
        name="ONVG",
        dtype=ChannelType.LONG,
        doc="Num. elements in OVLG",
        read_only=True,
        value=1,
    )
    num_elements_in_ovlh = pvproperty(
        name="ONVH",
        dtype=ChannelType.LONG,
        doc="Num. elements in VAlH",
        read_only=True,
        value=1,
    )
    num_elements_in_ovli = pvproperty(
        name="ONVI",
        dtype=ChannelType.LONG,
        doc="Num. elements in OVLI",
        read_only=True,
        value=1,
    )
    num_elements_in_ovlj = pvproperty(
        name="ONVJ",
        dtype=ChannelType.LONG,
        doc="Num. elements in OVLJ",
        read_only=True,
        value=1,
    )
    num_elements_in_ovlk = pvproperty(
        name="ONVK",
        dtype=ChannelType.LONG,
        doc="Num. elements in OVLK",
        read_only=True,
        value=1,
    )
    num_elements_in_ovll = pvproperty(
        name="ONVL",
        dtype=ChannelType.LONG,
        doc="Num. elements in OVLL",
        read_only=True,
        value=1,
    )
    num_elements_in_ovlm = pvproperty(
        name="ONVM",
        dtype=ChannelType.LONG,
        doc="Num. elements in OVLM",
        read_only=True,
        value=1,
    )
    num_elements_in_ovln = pvproperty(
        name="ONVN",
        dtype=ChannelType.LONG,
        doc="Num. elements in OVLN",
        read_only=True,
        value=1,
    )
    num_elements_in_ovlo = pvproperty(
        name="ONVO",
        dtype=ChannelType.LONG,
        doc="Num. elements in OVLO",
        read_only=True,
        value=1,
    )
    num_elements_in_ovlp = pvproperty(
        name="ONVP",
        dtype=ChannelType.LONG,
        doc="Num. elements in OVLP",
        read_only=True,
        value=1,
    )
    num_elements_in_ovlq = pvproperty(
        name="ONVQ",
        dtype=ChannelType.LONG,
        doc="Num. elements in OVLQ",
        read_only=True,
        value=1,
    )
    num_elements_in_ovlr = pvproperty(
        name="ONVR",
        dtype=ChannelType.LONG,
        doc="Num. elements in OVLR",
        read_only=True,
        value=1,
    )
    num_elements_in_ovls = pvproperty(
        name="ONVS",
        dtype=ChannelType.LONG,
        doc="Num. elements in OVLS",
        read_only=True,
        value=1,
    )
    num_elements_in_ovlt = pvproperty(
        name="ONVT",
        dtype=ChannelType.LONG,
        doc="Num. elements in OVLT",
        read_only=True,
        value=1,
    )
    num_elements_in_ovlu = pvproperty(
        name="ONVU",
        dtype=ChannelType.LONG,
        doc="Num. elements in OVLU",
        read_only=True,
        value=1,
    )
    output_link_a = pvproperty(
        name="OUTA", dtype=ChannelType.STRING, doc="Output Link A"
    )
    output_link_b = pvproperty(
        name="OUTB", dtype=ChannelType.STRING, doc="Output Link B"
    )
    output_link_c = pvproperty(
        name="OUTC", dtype=ChannelType.STRING, doc="Output Link C"
    )
    output_link_d = pvproperty(
        name="OUTD", dtype=ChannelType.STRING, doc="Output Link D"
    )
    output_link_e = pvproperty(
        name="OUTE", dtype=ChannelType.STRING, doc="Output Link E"
    )
    output_link_f = pvproperty(
        name="OUTF", dtype=ChannelType.STRING, doc="Output Link F"
    )
    output_link_g = pvproperty(
        name="OUTG", dtype=ChannelType.STRING, doc="Output Link G"
    )
    output_link_h = pvproperty(
        name="OUTH", dtype=ChannelType.STRING, doc="Output Link H"
    )
    output_link_i = pvproperty(
        name="OUTI", dtype=ChannelType.STRING, doc="Output Link I"
    )
    output_link_j = pvproperty(
        name="OUTJ", dtype=ChannelType.STRING, doc="Output Link J"
    )
    output_link_k = pvproperty(
        name="OUTK", dtype=ChannelType.STRING, doc="Output Link K"
    )
    output_link_l = pvproperty(
        name="OUTL", dtype=ChannelType.STRING, doc="Output Link L"
    )
    output_link_m = pvproperty(
        name="OUTM", dtype=ChannelType.STRING, doc="Output Link M"
    )
    output_link_n = pvproperty(
        name="OUTN", dtype=ChannelType.STRING, doc="Output Link N"
    )
    output_link_o = pvproperty(
        name="OUTO", dtype=ChannelType.STRING, doc="Output Link O"
    )
    output_link_p = pvproperty(
        name="OUTP", dtype=ChannelType.STRING, doc="Output Link P"
    )
    output_link_q = pvproperty(
        name="OUTQ", dtype=ChannelType.STRING, doc="Output Link Q"
    )
    output_link_r = pvproperty(
        name="OUTR", dtype=ChannelType.STRING, doc="Output Link R"
    )
    output_link_s = pvproperty(
        name="OUTS", dtype=ChannelType.STRING, doc="Output Link S"
    )
    output_link_t = pvproperty(
        name="OUTT", dtype=ChannelType.STRING, doc="Output Link T"
    )
    output_link_u = pvproperty(
        name="OUTU", dtype=ChannelType.STRING, doc="Output Link U"
    )
    old_return_value = pvproperty(
        name="OVAL",
        dtype=ChannelType.LONG,
        doc="Old return value",
        read_only=True,
    )
    display_precision = pvproperty(
        name="PREC", dtype=ChannelType.INT, doc="Display Precision"
    )
    process_subr_name = pvproperty(
        name="SNAM",
        dtype=ChannelType.CHAR,
        max_length=41,
        report_as_string=True,
        doc="Process Subr. Name",
    )
    subroutine_name_link = pvproperty(
        name="SUBL",
        dtype=ChannelType.STRING,
        doc="Subroutine Name Link",
        read_only=True,
    )
    # subr_return_value = pvproperty(name='VAL',
    #      dtype=ChannelType.LONG,
    # doc='Subr. return value')
    link_parent_attribute(
        display_precision, "precision",
    )


class AaiFields(RecordFieldGroup):
    _record_type = "aai"
    _dtype = None  # DTYP of .VAL
    has_val_field = False
    copy_pvproperties(locals(), RecordFieldGroup)
    device_type = pvproperty(
        name="DTYP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.dtyp_aai.get_string_tuple(),
        doc="Device Type",
    )
    post_archive_monitors = pvproperty(
        name="APST",
        dtype=ChannelType.ENUM,
        enum_strings=menus.aaiPOST.get_string_tuple(),
        doc="Post Archive Monitors",
    )
    engineering_units = pvproperty(
        name="EGU",
        dtype=ChannelType.CHAR,
        max_length=16,
        report_as_string=True,
        doc="Engineering Units",
    )
    field_type_of_value = pvproperty(
        name="FTVL",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Field Type of Value",
        read_only=True,
    )
    hash_of_onchange_data = pvproperty(
        name="HASH", dtype=ChannelType.LONG, doc="Hash of OnChange data."
    )
    high_operating_range = pvproperty(
        name="HOPR", dtype=ChannelType.DOUBLE, doc="High Operating Range"
    )
    input_specification = pvproperty(
        name="INP", dtype=ChannelType.STRING, doc="Input Specification"
    )
    low_operating_range = pvproperty(
        name="LOPR", dtype=ChannelType.DOUBLE, doc="Low Operating Range"
    )
    post_value_monitors = pvproperty(
        name="MPST",
        dtype=ChannelType.ENUM,
        enum_strings=menus.aaiPOST.get_string_tuple(),
        doc="Post Value Monitors",
    )
    number_of_elements = pvproperty(
        name="NELM",
        dtype=ChannelType.LONG,
        doc="Number of Elements",
        read_only=True,
        value=1,
    )
    number_elements_read = pvproperty(
        name="NORD",
        dtype=ChannelType.LONG,
        doc="Number elements read",
        read_only=True,
    )
    prev_simulation_mode = pvproperty(
        name="OLDSIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuSimm.get_string_tuple(),
        doc="Prev. Simulation Mode",
        read_only=True,
    )
    display_precision = pvproperty(
        name="PREC", dtype=ChannelType.INT, doc="Display Precision"
    )
    sim_mode_async_delay = pvproperty(
        name="SDLY",
        dtype=ChannelType.DOUBLE,
        doc="Sim. Mode Async Delay",
        value=-1.0,
    )
    simulation_mode_link = pvproperty(
        name="SIML", dtype=ChannelType.STRING, doc="Simulation Mode Link"
    )
    simulation_mode = pvproperty(
        name="SIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuYesNo.get_string_tuple(),
        doc="Simulation Mode",
    )
    simulation_mode_severity = pvproperty(
        name="SIMS",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Simulation Mode Severity",
    )
    simulation_input_link = pvproperty(
        name="SIOL", dtype=ChannelType.STRING, doc="Simulation Input Link"
    )
    sim_mode_scan = pvproperty(
        name="SSCN",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuScan.get_string_tuple(),
        doc="Sim. Mode Scan",
        value=0,
    )
    link_parent_attribute(
        display_precision, "precision",
    )
    link_parent_attribute(
        high_operating_range, "upper_ctrl_limit",
    )
    link_parent_attribute(
        low_operating_range, "lower_ctrl_limit",
    )
    link_parent_attribute(
        number_of_elements, "max_length", use_setattr=True, read_only=True
    )


class AaoFields(RecordFieldGroup):
    _record_type = "aao"
    _dtype = None  # DTYP of .VAL
    has_val_field = False
    copy_pvproperties(locals(), RecordFieldGroup)
    device_type = pvproperty(
        name="DTYP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.dtyp_aao.get_string_tuple(),
        doc="Device Type",
    )
    post_archive_monitors = pvproperty(
        name="APST",
        dtype=ChannelType.ENUM,
        enum_strings=menus.aaoPOST.get_string_tuple(),
        doc="Post Archive Monitors",
    )
    engineering_units = pvproperty(
        name="EGU",
        dtype=ChannelType.CHAR,
        max_length=16,
        report_as_string=True,
        doc="Engineering Units",
    )
    field_type_of_value = pvproperty(
        name="FTVL",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Field Type of Value",
        read_only=True,
    )
    hash_of_onchange_data = pvproperty(
        name="HASH", dtype=ChannelType.LONG, doc="Hash of OnChange data."
    )
    high_operating_range = pvproperty(
        name="HOPR", dtype=ChannelType.DOUBLE, doc="High Operating Range"
    )
    low_operating_range = pvproperty(
        name="LOPR", dtype=ChannelType.DOUBLE, doc="Low Operating Range"
    )
    post_value_monitors = pvproperty(
        name="MPST",
        dtype=ChannelType.ENUM,
        enum_strings=menus.aaoPOST.get_string_tuple(),
        doc="Post Value Monitors",
    )
    number_of_elements = pvproperty(
        name="NELM",
        dtype=ChannelType.LONG,
        doc="Number of Elements",
        read_only=True,
        value=1,
    )
    number_elements_read = pvproperty(
        name="NORD",
        dtype=ChannelType.LONG,
        doc="Number elements read",
        read_only=True,
    )
    prev_simulation_mode = pvproperty(
        name="OLDSIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuSimm.get_string_tuple(),
        doc="Prev. Simulation Mode",
        read_only=True,
    )
    output_specification = pvproperty(
        name="OUT", dtype=ChannelType.STRING, doc="Output Specification"
    )
    display_precision = pvproperty(
        name="PREC", dtype=ChannelType.INT, doc="Display Precision"
    )
    sim_mode_async_delay = pvproperty(
        name="SDLY",
        dtype=ChannelType.DOUBLE,
        doc="Sim. Mode Async Delay",
        value=-1.0,
    )
    simulation_mode_link = pvproperty(
        name="SIML", dtype=ChannelType.STRING, doc="Simulation Mode Link"
    )
    simulation_mode = pvproperty(
        name="SIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuYesNo.get_string_tuple(),
        doc="Simulation Mode",
    )
    simulation_mode_severity = pvproperty(
        name="SIMS",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Simulation Mode Severity",
    )
    simulation_output_link = pvproperty(
        name="SIOL", dtype=ChannelType.STRING, doc="Simulation Output Link"
    )
    sim_mode_scan = pvproperty(
        name="SSCN",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuScan.get_string_tuple(),
        doc="Sim. Mode Scan",
        value=0,
    )
    link_parent_attribute(
        display_precision, "precision",
    )
    link_parent_attribute(
        high_operating_range, "upper_ctrl_limit",
    )
    link_parent_attribute(
        low_operating_range, "lower_ctrl_limit",
    )
    link_parent_attribute(
        number_of_elements, "max_length", use_setattr=True, read_only=True
    )


class AoFields(RecordFieldGroup, _Limits):
    _record_type = "ao"
    _dtype = ChannelType.DOUBLE  # DTYP of .VAL
    has_val_field = True
    copy_pvproperties(locals(), RecordFieldGroup, _Limits)
    device_type = pvproperty(
        name="DTYP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.dtyp_ao.get_string_tuple(),
        doc="Device Type",
    )
    archive_deadband = pvproperty(
        name="ADEL", dtype=ChannelType.DOUBLE, doc="Archive Deadband"
    )
    last_value_archived = pvproperty(
        name="ALST",
        dtype=ChannelType.DOUBLE,
        doc="Last Value Archived",
        read_only=True,
    )
    adjustment_offset = pvproperty(
        name="AOFF", dtype=ChannelType.DOUBLE, doc="Adjustment Offset"
    )
    adjustment_slope = pvproperty(
        name="ASLO", dtype=ChannelType.DOUBLE, doc="Adjustment Slope"
    )
    desired_output_loc = pvproperty(
        name="DOL", dtype=ChannelType.STRING, doc="Desired Output Loc"
    )
    drive_high_limit = pvproperty(
        name="DRVH", dtype=ChannelType.DOUBLE, doc="Drive High Limit"
    )
    drive_low_limit = pvproperty(
        name="DRVL", dtype=ChannelType.DOUBLE, doc="Drive Low Limit"
    )
    engineering_units = pvproperty(
        name="EGU",
        dtype=ChannelType.CHAR,
        max_length=16,
        report_as_string=True,
        doc="Engineering Units",
    )
    eng_units_full = pvproperty(
        name="EGUF", dtype=ChannelType.DOUBLE, doc="Eng Units Full"
    )
    eng_units_low = pvproperty(
        name="EGUL", dtype=ChannelType.DOUBLE, doc="Eng Units Low"
    )
    egu_to_raw_offset = pvproperty(
        name="EOFF", dtype=ChannelType.DOUBLE, doc="EGU to Raw Offset"
    )
    egu_to_raw_slope = pvproperty(
        name="ESLO", dtype=ChannelType.DOUBLE, doc="EGU to Raw Slope", value=1
    )
    alarm_deadband = pvproperty(
        name="HYST", dtype=ChannelType.DOUBLE, doc="Alarm Deadband"
    )
    initialized = pvproperty(
        name="INIT", dtype=ChannelType.INT, doc="Initialized?", read_only=True
    )
    invalid_output_action = pvproperty(
        name="IVOA",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuIvoa.get_string_tuple(),
        doc="INVALID output action",
    )
    invalid_output_value = pvproperty(
        name="IVOV", dtype=ChannelType.DOUBLE, doc="INVALID output value"
    )
    last_value_alarmed = pvproperty(
        name="LALM",
        dtype=ChannelType.DOUBLE,
        doc="Last Value Alarmed",
        read_only=True,
    )
    lastbreak_point = pvproperty(
        name="LBRK",
        dtype=ChannelType.INT,
        doc="LastBreak Point",
        read_only=True,
    )
    linearization = pvproperty(
        name="LINR",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuConvert.get_string_tuple(),
        doc="Linearization",
    )
    monitor_deadband = pvproperty(
        name="MDEL", dtype=ChannelType.DOUBLE, doc="Monitor Deadband"
    )
    last_val_monitored = pvproperty(
        name="MLST",
        dtype=ChannelType.DOUBLE,
        doc="Last Val Monitored",
        read_only=True,
    )
    out_full_incremental = pvproperty(
        name="OIF",
        dtype=ChannelType.ENUM,
        enum_strings=menus.aoOIF.get_string_tuple(),
        doc="Out Full/Incremental",
    )
    prev_simulation_mode = pvproperty(
        name="OLDSIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuSimm.get_string_tuple(),
        doc="Prev. Simulation Mode",
        read_only=True,
    )
    was_oval_modified = pvproperty(
        name="OMOD",
        dtype=ChannelType.CHAR,
        doc="Was OVAL modified?",
        read_only=True,
    )
    output_mode_select = pvproperty(
        name="OMSL",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuOmsl.get_string_tuple(),
        doc="Output Mode Select",
    )
    previous_raw_value = pvproperty(
        name="ORAW",
        dtype=ChannelType.LONG,
        doc="Previous Raw Value",
        read_only=True,
    )
    prev_readback_value = pvproperty(
        name="ORBV",
        dtype=ChannelType.LONG,
        doc="Prev Readback Value",
        read_only=True,
    )
    output_rate_of_change = pvproperty(
        name="OROC", dtype=ChannelType.DOUBLE, doc="Output Rate of Change"
    )
    output_specification = pvproperty(
        name="OUT", dtype=ChannelType.STRING, doc="Output Specification"
    )
    output_value = pvproperty(
        name="OVAL", dtype=ChannelType.DOUBLE, doc="Output Value"
    )
    display_precision = pvproperty(
        name="PREC", dtype=ChannelType.INT, doc="Display Precision"
    )
    previous_value = pvproperty(
        name="PVAL",
        dtype=ChannelType.DOUBLE,
        doc="Previous value",
        read_only=True,
    )
    readback_value = pvproperty(
        name="RBV", dtype=ChannelType.LONG, doc="Readback Value", read_only=True
    )
    raw_offset = pvproperty(
        name="ROFF", dtype=ChannelType.LONG, doc="Raw Offset"
    )
    current_raw_value = pvproperty(
        name="RVAL", dtype=ChannelType.LONG, doc="Current Raw Value"
    )
    sim_mode_async_delay = pvproperty(
        name="SDLY",
        dtype=ChannelType.DOUBLE,
        doc="Sim. Mode Async Delay",
        value=-1.0,
    )
    simulation_mode_link = pvproperty(
        name="SIML", dtype=ChannelType.STRING, doc="Simulation Mode Link"
    )
    simulation_mode = pvproperty(
        name="SIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuYesNo.get_string_tuple(),
        doc="Simulation Mode",
    )
    simulation_mode_severity = pvproperty(
        name="SIMS",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Simulation Mode Severity",
    )
    simulation_output_link = pvproperty(
        name="SIOL", dtype=ChannelType.STRING, doc="Simulation Output Link"
    )
    sim_mode_scan = pvproperty(
        name="SSCN",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuScan.get_string_tuple(),
        doc="Sim. Mode Scan",
        value=0,
    )
    # desired_output = pvproperty(name='VAL',
    #      dtype=ChannelType.DOUBLE,
    # doc='Desired Output')
    link_parent_attribute(
        display_precision, "precision",
    )
    link_parent_attribute(archive_deadband, "log_atol", use_setattr=True)
    link_parent_attribute(monitor_deadband, "value_atol", use_setattr=True)


class AsynFields(RecordFieldGroup):
    _record_type = "asyn"
    _dtype = ChannelType.LONG  # DTYP of .VAL
    has_val_field = True
    copy_pvproperties(locals(), RecordFieldGroup)
    device_type = pvproperty(
        name="DTYP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.dtyp_asyn.get_string_tuple(),
        doc="Device Type",
    )
    addressed_command = pvproperty(
        name="ACMD",
        dtype=ChannelType.ENUM,
        enum_strings=menus.gpibACMD.get_string_tuple(),
        doc="Addressed command",
    )
    asyn_address = pvproperty(
        name="ADDR", dtype=ChannelType.LONG, doc="asyn address", value=0
    )
    input = pvproperty(
        name="AINP",
        dtype=ChannelType.CHAR,
        max_length=40,
        report_as_string=True,
        doc="Input (response) string",
        read_only=True,
    )
    output = pvproperty(
        name="AOUT",
        dtype=ChannelType.CHAR,
        max_length=40,
        report_as_string=True,
        doc="Output (command) string",
    )
    abort_queuerequest = pvproperty(
        name="AQR", dtype=ChannelType.CHAR, doc="Abort queueRequest"
    )
    autoconnect = pvproperty(
        name="AUCT",
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynAUTOCONNECT.get_string_tuple(),
        doc="Autoconnect",
    )
    baud_rate = pvproperty(
        name="BAUD",
        dtype=ChannelType.ENUM,
        enum_strings=menus.serialBAUD.get_string_tuple(),
        doc="Baud rate",
    )
    input_binary_data = pvproperty(
        name="BINP", dtype=ChannelType.CHAR, doc="Input binary data"
    )
    output_binary_data = pvproperty(
        name="BOUT", dtype=ChannelType.CHAR, doc="Output binary data"
    )
    connect_disconnect = pvproperty(
        name="CNCT",
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynCONNECT.get_string_tuple(),
        doc="Connect/Disconnect",
    )
    data_bits = pvproperty(
        name="DBIT",
        dtype=ChannelType.ENUM,
        enum_strings=menus.serialDBIT.get_string_tuple(),
        doc="Data bits",
    )
    disconnect_on_timeout = pvproperty(
        name="DRTO",
        dtype=ChannelType.ENUM,
        enum_strings=menus.ipDRTO.get_string_tuple(),
        doc="Disconnect on timeout",
    )
    driver_info_string = pvproperty(
        name="DRVINFO",
        dtype=ChannelType.CHAR,
        max_length=40,
        report_as_string=True,
        doc="Driver info string",
        value="",
    )
    enable_disable = pvproperty(
        name="ENBL",
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynENABLE.get_string_tuple(),
        doc="Enable/Disable",
    )
    eom_reason = pvproperty(
        name="EOMR",
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynEOMREASON.get_string_tuple(),
        doc="EOM reason",
        read_only=True,
    )
    asynfloat64_input = pvproperty(
        name="F64INP",
        dtype=ChannelType.DOUBLE,
        doc="asynFloat64 input",
        read_only=True,
    )
    asynfloat64_is_valid = pvproperty(
        name="F64IV", dtype=ChannelType.LONG, doc="asynFloat64 is valid"
    )
    asynfloat64_output = pvproperty(
        name="F64OUT", dtype=ChannelType.DOUBLE, doc="asynFloat64 output"
    )
    flow_control = pvproperty(
        name="FCTL",
        dtype=ChannelType.ENUM,
        enum_strings=menus.serialFCTL.get_string_tuple(),
        doc="Flow control",
    )
    asyngpib_is_valid = pvproperty(
        name="GPIBIV", dtype=ChannelType.LONG, doc="asynGPIB is valid"
    )
    host_info = pvproperty(
        name="HOSTINFO",
        dtype=ChannelType.CHAR,
        max_length=40,
        report_as_string=True,
        doc="host info",
        value="",
    )
    asynint32_input = pvproperty(
        name="I32INP",
        dtype=ChannelType.LONG,
        doc="asynInt32 input",
        read_only=True,
    )
    asynint32_is_valid = pvproperty(
        name="I32IV", dtype=ChannelType.LONG, doc="asynInt32 is valid"
    )
    asynint32_output = pvproperty(
        name="I32OUT", dtype=ChannelType.LONG, doc="asynInt32 output"
    )
    input_delimiter = pvproperty(
        name="IEOS",
        dtype=ChannelType.CHAR,
        max_length=40,
        report_as_string=True,
        doc="Input Delimiter",
    )
    interface = pvproperty(
        name="IFACE",
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynINTERFACE.get_string_tuple(),
        doc="Interface",
    )
    input_format = pvproperty(
        name="IFMT",
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynFMT.get_string_tuple(),
        doc="Input format",
    )
    max_size_of_input_array = pvproperty(
        name="IMAX",
        dtype=ChannelType.LONG,
        doc="Max. size of input array",
        read_only=True,
        value=80,
    )
    xon_any_character = pvproperty(
        name="IXANY",
        dtype=ChannelType.ENUM,
        enum_strings=menus.serialIX.get_string_tuple(),
        doc="XON=any character",
    )
    input_xon_xoff = pvproperty(
        name="IXOFF",
        dtype=ChannelType.ENUM,
        enum_strings=menus.serialIX.get_string_tuple(),
        doc="Input XON/XOFF",
    )
    output_xon_xoff = pvproperty(
        name="IXON",
        dtype=ChannelType.ENUM,
        enum_strings=menus.serialIX.get_string_tuple(),
        doc="Output XON/XOFF",
    )
    long_baud_rate = pvproperty(
        name="LBAUD", dtype=ChannelType.LONG, doc="Baud rate"
    )
    modem_control = pvproperty(
        name="MCTL",
        dtype=ChannelType.ENUM,
        enum_strings=menus.serialMCTL.get_string_tuple(),
        doc="Modem control",
    )
    number_of_bytes_actually_written = pvproperty(
        name="NAWT",
        dtype=ChannelType.LONG,
        doc="Number of bytes actually written",
    )
    number_of_bytes_read = pvproperty(
        name="NORD",
        dtype=ChannelType.LONG,
        doc="Number of bytes read",
        read_only=True,
    )
    number_of_bytes_to_write = pvproperty(
        name="NOWT",
        dtype=ChannelType.LONG,
        doc="Number of bytes to write",
        value=80,
    )
    number_of_bytes_to_read = pvproperty(
        name="NRRD", dtype=ChannelType.LONG, doc="Number of bytes to read"
    )
    asynoctet_is_valid = pvproperty(
        name="OCTETIV", dtype=ChannelType.LONG, doc="asynOctet is valid"
    )
    output_delimiter = pvproperty(
        name="OEOS",
        dtype=ChannelType.CHAR,
        max_length=40,
        report_as_string=True,
        doc="Output delimiter",
    )
    output_format = pvproperty(
        name="OFMT",
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynFMT.get_string_tuple(),
        doc="Output format",
    )
    max_size_of_output_array = pvproperty(
        name="OMAX",
        dtype=ChannelType.LONG,
        doc="Max. size of output array",
        read_only=True,
        value=80,
    )
    asynoption_is_valid = pvproperty(
        name="OPTIONIV", dtype=ChannelType.LONG, doc="asynOption is valid"
    )
    port_connect_disconnect = pvproperty(
        name="PCNCT",
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynCONNECT.get_string_tuple(),
        doc="Port Connect/Disconnect",
    )
    asyn_port = pvproperty(
        name="PORT",
        dtype=ChannelType.CHAR,
        max_length=40,
        report_as_string=True,
        doc="asyn port",
        value="",
    )
    parity = pvproperty(
        name="PRTY",
        dtype=ChannelType.ENUM,
        enum_strings=menus.serialPRTY.get_string_tuple(),
        doc="Parity",
    )
    asynuser_reason = pvproperty(
        name="REASON", dtype=ChannelType.LONG, doc="asynUser->reason"
    )
    stop_bits = pvproperty(
        name="SBIT",
        dtype=ChannelType.ENUM,
        enum_strings=menus.serialSBIT.get_string_tuple(),
        doc="Stop bits",
    )
    serial_poll_response = pvproperty(
        name="SPR",
        dtype=ChannelType.CHAR,
        doc="Serial poll response",
        read_only=True,
    )
    trace_error = pvproperty(
        name="TB0",
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynTRACE.get_string_tuple(),
        doc="Trace error",
    )
    trace_io_device = pvproperty(
        name="TB1",
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynTRACE.get_string_tuple(),
        doc="Trace IO device",
    )
    trace_io_filter = pvproperty(
        name="TB2",
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynTRACE.get_string_tuple(),
        doc="Trace IO filter",
    )
    trace_io_driver = pvproperty(
        name="TB3",
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynTRACE.get_string_tuple(),
        doc="Trace IO driver",
    )
    trace_flow = pvproperty(
        name="TB4",
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynTRACE.get_string_tuple(),
        doc="Trace flow",
    )
    trace_warning = pvproperty(
        name="TB5",
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynTRACE.get_string_tuple(),
        doc="Trace warning",
    )
    trace_io_file = pvproperty(
        name="TFIL",
        dtype=ChannelType.CHAR,
        max_length=40,
        report_as_string=True,
        doc="Trace IO file",
    )
    trace_io_ascii = pvproperty(
        name="TIB0",
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynTRACE.get_string_tuple(),
        doc="Trace IO ASCII",
    )
    trace_io_escape = pvproperty(
        name="TIB1",
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynTRACE.get_string_tuple(),
        doc="Trace IO escape",
    )
    trace_io_hex = pvproperty(
        name="TIB2",
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynTRACE.get_string_tuple(),
        doc="Trace IO hex",
    )
    trace_info_time = pvproperty(
        name="TINB0",
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynTRACE.get_string_tuple(),
        doc="Trace Info Time",
    )
    trace_info_port = pvproperty(
        name="TINB1",
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynTRACE.get_string_tuple(),
        doc="Trace Info Port",
    )
    trace_info_source = pvproperty(
        name="TINB2",
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynTRACE.get_string_tuple(),
        doc="Trace Info Source",
    )
    trace_info_thread = pvproperty(
        name="TINB3",
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynTRACE.get_string_tuple(),
        doc="Trace Info Thread",
    )
    trace_info_mask = pvproperty(
        name="TINM", dtype=ChannelType.LONG, doc="Trace Info mask"
    )
    translated_input_string = pvproperty(
        name="TINP",
        dtype=ChannelType.CHAR,
        max_length=40,
        report_as_string=True,
        doc="Translated input string",
        read_only=True,
    )
    trace_i_o_mask = pvproperty(
        name="TIOM", dtype=ChannelType.LONG, doc="Trace I/O mask"
    )
    transaction_mode = pvproperty(
        name="TMOD",
        dtype=ChannelType.ENUM,
        enum_strings=menus.asynTMOD.get_string_tuple(),
        doc="Transaction mode",
    )
    timeout = pvproperty(
        name="TMOT", dtype=ChannelType.DOUBLE, doc="Timeout (sec)", value=1.0
    )
    trace_mask = pvproperty(
        name="TMSK", dtype=ChannelType.LONG, doc="Trace mask"
    )
    trace_io_truncate_size = pvproperty(
        name="TSIZ", dtype=ChannelType.LONG, doc="Trace IO truncate size"
    )
    universal_command = pvproperty(
        name="UCMD",
        dtype=ChannelType.ENUM,
        enum_strings=menus.gpibUCMD.get_string_tuple(),
        doc="Universal command",
    )
    asynuint32digital_input = pvproperty(
        name="UI32INP",
        dtype=ChannelType.LONG,
        doc="asynUInt32Digital input",
        read_only=True,
    )
    asynuint32digital_is_valid = pvproperty(
        name="UI32IV", dtype=ChannelType.LONG, doc="asynUInt32Digital is valid"
    )
    asynuint32digital_mask = pvproperty(
        name="UI32MASK",
        dtype=ChannelType.LONG,
        doc="asynUInt32Digital mask",
        value=4294967295,
    )
    asynuint32digital_output = pvproperty(
        name="UI32OUT", dtype=ChannelType.LONG, doc="asynUInt32Digital output"
    )
    # value_field = pvproperty(name='VAL',
    #      dtype=ChannelType.LONG,
    # doc='Value field (unused)')


class BiFields(RecordFieldGroup):
    _record_type = "bi"
    _dtype = ChannelType.ENUM  # DTYP of .VAL
    has_val_field = True
    copy_pvproperties(locals(), RecordFieldGroup)
    device_type = pvproperty(
        name="DTYP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.dtyp_bi.get_string_tuple(),
        doc="Device Type",
    )
    change_of_state_svr = pvproperty(
        name="COSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Change of State Svr",
    )
    input_specification = pvproperty(
        name="INP", dtype=ChannelType.STRING, doc="Input Specification"
    )
    last_value_alarmed = pvproperty(
        name="LALM",
        dtype=ChannelType.INT,
        doc="Last Value Alarmed",
        read_only=True,
    )
    hardware_mask = pvproperty(
        name="MASK", dtype=ChannelType.LONG, doc="Hardware Mask", read_only=True
    )
    last_value_monitored = pvproperty(
        name="MLST",
        dtype=ChannelType.INT,
        doc="Last Value Monitored",
        read_only=True,
    )
    prev_simulation_mode = pvproperty(
        name="OLDSIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuSimm.get_string_tuple(),
        doc="Prev. Simulation Mode",
        read_only=True,
    )
    one_name = pvproperty(
        name="ONAM",
        dtype=ChannelType.CHAR,
        max_length=26,
        report_as_string=True,
        doc="One Name",
    )
    prev_raw_value = pvproperty(
        name="ORAW",
        dtype=ChannelType.LONG,
        doc="prev Raw Value",
        read_only=True,
    )
    one_error_severity = pvproperty(
        name="OSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="One Error Severity",
    )
    raw_value = pvproperty(name="RVAL", dtype=ChannelType.LONG, doc="Raw Value")
    sim_mode_async_delay = pvproperty(
        name="SDLY",
        dtype=ChannelType.DOUBLE,
        doc="Sim. Mode Async Delay",
        value=-1.0,
    )
    simulation_mode_link = pvproperty(
        name="SIML", dtype=ChannelType.STRING, doc="Simulation Mode Link"
    )
    simulation_mode = pvproperty(
        name="SIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuSimm.get_string_tuple(),
        doc="Simulation Mode",
    )
    simulation_mode_severity = pvproperty(
        name="SIMS",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Simulation Mode Severity",
    )
    simulation_input_link = pvproperty(
        name="SIOL", dtype=ChannelType.STRING, doc="Simulation Input Link"
    )
    sim_mode_scan = pvproperty(
        name="SSCN",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuScan.get_string_tuple(),
        doc="Sim. Mode Scan",
        value=0,
    )
    simulation_value = pvproperty(
        name="SVAL", dtype=ChannelType.LONG, doc="Simulation Value"
    )
    zero_name = pvproperty(
        name="ZNAM",
        dtype=ChannelType.CHAR,
        max_length=26,
        report_as_string=True,
        doc="Zero Name",
    )
    zero_error_severity = pvproperty(
        name="ZSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Zero Error Severity",
    )
    # current_value = pvproperty(name='VAL',
    #      dtype=ChannelType.ENUM,
    # doc='Current Value')


class BoFields(RecordFieldGroup):
    _record_type = "bo"
    _dtype = ChannelType.ENUM  # DTYP of .VAL
    has_val_field = True
    copy_pvproperties(locals(), RecordFieldGroup)
    device_type = pvproperty(
        name="DTYP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.dtyp_bo.get_string_tuple(),
        doc="Device Type",
    )
    change_of_state_sevr = pvproperty(
        name="COSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Change of State Sevr",
    )
    desired_output_loc = pvproperty(
        name="DOL", dtype=ChannelType.STRING, doc="Desired Output Loc"
    )
    seconds_to_hold_high = pvproperty(
        name="HIGH", dtype=ChannelType.DOUBLE, doc="Seconds to Hold High"
    )
    invalid_outpt_action = pvproperty(
        name="IVOA",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuIvoa.get_string_tuple(),
        doc="INVALID outpt action",
    )
    invalid_output_value = pvproperty(
        name="IVOV", dtype=ChannelType.INT, doc="INVALID output value"
    )
    last_value_alarmed = pvproperty(
        name="LALM",
        dtype=ChannelType.INT,
        doc="Last Value Alarmed",
        read_only=True,
    )
    hardware_mask = pvproperty(
        name="MASK", dtype=ChannelType.LONG, doc="Hardware Mask", read_only=True
    )
    last_value_monitored = pvproperty(
        name="MLST",
        dtype=ChannelType.INT,
        doc="Last Value Monitored",
        read_only=True,
    )
    prev_simulation_mode = pvproperty(
        name="OLDSIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuSimm.get_string_tuple(),
        doc="Prev. Simulation Mode",
        read_only=True,
    )
    output_mode_select = pvproperty(
        name="OMSL",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuOmsl.get_string_tuple(),
        doc="Output Mode Select",
    )
    one_name = pvproperty(
        name="ONAM",
        dtype=ChannelType.CHAR,
        max_length=26,
        report_as_string=True,
        doc="One Name",
    )
    prev_raw_value = pvproperty(
        name="ORAW",
        dtype=ChannelType.LONG,
        doc="prev Raw Value",
        read_only=True,
    )
    prev_readback_value = pvproperty(
        name="ORBV",
        dtype=ChannelType.LONG,
        doc="Prev Readback Value",
        read_only=True,
    )
    one_error_severity = pvproperty(
        name="OSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="One Error Severity",
    )
    output_specification = pvproperty(
        name="OUT", dtype=ChannelType.STRING, doc="Output Specification"
    )
    readback_value = pvproperty(
        name="RBV", dtype=ChannelType.LONG, doc="Readback Value", read_only=True
    )
    raw_value = pvproperty(name="RVAL", dtype=ChannelType.LONG, doc="Raw Value")
    sim_mode_async_delay = pvproperty(
        name="SDLY",
        dtype=ChannelType.DOUBLE,
        doc="Sim. Mode Async Delay",
        value=-1.0,
    )
    simulation_mode_link = pvproperty(
        name="SIML", dtype=ChannelType.STRING, doc="Simulation Mode Link"
    )
    simulation_mode = pvproperty(
        name="SIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuYesNo.get_string_tuple(),
        doc="Simulation Mode",
    )
    simulation_mode_severity = pvproperty(
        name="SIMS",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Simulation Mode Severity",
    )
    simulation_output_link = pvproperty(
        name="SIOL", dtype=ChannelType.STRING, doc="Simulation Output Link"
    )
    sim_mode_scan = pvproperty(
        name="SSCN",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuScan.get_string_tuple(),
        doc="Sim. Mode Scan",
        value=0,
    )
    zero_name = pvproperty(
        name="ZNAM",
        dtype=ChannelType.CHAR,
        max_length=26,
        report_as_string=True,
        doc="Zero Name",
    )
    zero_error_severity = pvproperty(
        name="ZSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Zero Error Severity",
    )
    # current_value = pvproperty(name='VAL',
    #      dtype=ChannelType.ENUM,
    # doc='Current Value')


class CalcFields(RecordFieldGroup, _Limits):
    _record_type = "calc"
    _dtype = ChannelType.DOUBLE  # DTYP of .VAL
    has_val_field = True
    copy_pvproperties(locals(), RecordFieldGroup, _Limits)
    device_type = pvproperty(
        name="DTYP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.dtyp_calc.get_string_tuple(),
        doc="Device Type",
    )
    value_of_input_a = pvproperty(
        name="A", dtype=ChannelType.DOUBLE, doc="Value of Input A"
    )
    archive_deadband = pvproperty(
        name="ADEL", dtype=ChannelType.DOUBLE, doc="Archive Deadband"
    )
    alarm_filter_time_constant = pvproperty(
        name="AFTC", dtype=ChannelType.DOUBLE, doc="Alarm Filter Time Constant"
    )
    alarm_filter_value = pvproperty(
        name="AFVL",
        dtype=ChannelType.DOUBLE,
        doc="Alarm Filter Value",
        read_only=True,
    )
    last_value_archived = pvproperty(
        name="ALST",
        dtype=ChannelType.DOUBLE,
        doc="Last Value Archived",
        read_only=True,
    )
    value_of_input_b = pvproperty(
        name="B", dtype=ChannelType.DOUBLE, doc="Value of Input B"
    )
    value_of_input_c = pvproperty(
        name="C", dtype=ChannelType.DOUBLE, doc="Value of Input C"
    )
    calculation = pvproperty(
        name="CALC",
        dtype=ChannelType.CHAR,
        max_length=80,
        report_as_string=True,
        doc="Calculation",
        value=chr(0),
    )
    value_of_input_d = pvproperty(
        name="D", dtype=ChannelType.DOUBLE, doc="Value of Input D"
    )
    value_of_input_e = pvproperty(
        name="E", dtype=ChannelType.DOUBLE, doc="Value of Input E"
    )
    engineering_units = pvproperty(
        name="EGU",
        dtype=ChannelType.CHAR,
        max_length=16,
        report_as_string=True,
        doc="Engineering Units",
    )
    value_of_input_f = pvproperty(
        name="F", dtype=ChannelType.DOUBLE, doc="Value of Input F"
    )
    value_of_input_g = pvproperty(
        name="G", dtype=ChannelType.DOUBLE, doc="Value of Input G"
    )
    value_of_input_h = pvproperty(
        name="H", dtype=ChannelType.DOUBLE, doc="Value of Input H"
    )
    alarm_deadband = pvproperty(
        name="HYST", dtype=ChannelType.DOUBLE, doc="Alarm Deadband"
    )
    value_of_input_i = pvproperty(
        name="I", dtype=ChannelType.DOUBLE, doc="Value of Input I"
    )
    input_a = pvproperty(name="INPA", dtype=ChannelType.STRING, doc="Input A")
    input_b = pvproperty(name="INPB", dtype=ChannelType.STRING, doc="Input B")
    input_c = pvproperty(name="INPC", dtype=ChannelType.STRING, doc="Input C")
    input_d = pvproperty(name="INPD", dtype=ChannelType.STRING, doc="Input D")
    input_e = pvproperty(name="INPE", dtype=ChannelType.STRING, doc="Input E")
    input_f = pvproperty(name="INPF", dtype=ChannelType.STRING, doc="Input F")
    input_g = pvproperty(name="INPG", dtype=ChannelType.STRING, doc="Input G")
    input_h = pvproperty(name="INPH", dtype=ChannelType.STRING, doc="Input H")
    input_i = pvproperty(name="INPI", dtype=ChannelType.STRING, doc="Input I")
    input_j = pvproperty(name="INPJ", dtype=ChannelType.STRING, doc="Input J")
    input_k = pvproperty(name="INPK", dtype=ChannelType.STRING, doc="Input K")
    input_l = pvproperty(name="INPL", dtype=ChannelType.STRING, doc="Input L")
    value_of_input_j = pvproperty(
        name="J", dtype=ChannelType.DOUBLE, doc="Value of Input J"
    )
    value_of_input_k = pvproperty(
        name="K", dtype=ChannelType.DOUBLE, doc="Value of Input K"
    )
    value_of_input_l = pvproperty(
        name="L", dtype=ChannelType.DOUBLE, doc="Value of Input L"
    )
    prev_value_of_a = pvproperty(
        name="LA",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of A",
        read_only=True,
    )
    last_value_alarmed = pvproperty(
        name="LALM",
        dtype=ChannelType.DOUBLE,
        doc="Last Value Alarmed",
        read_only=True,
    )
    prev_value_of_b = pvproperty(
        name="LB",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of B",
        read_only=True,
    )
    prev_value_of_c = pvproperty(
        name="LC",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of C",
        read_only=True,
    )
    prev_value_of_d = pvproperty(
        name="LD",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of D",
        read_only=True,
    )
    prev_value_of_e = pvproperty(
        name="LE",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of E",
        read_only=True,
    )
    prev_value_of_f = pvproperty(
        name="LF",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of F",
        read_only=True,
    )
    prev_value_of_g = pvproperty(
        name="LG",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of G",
        read_only=True,
    )
    prev_value_of_h = pvproperty(
        name="LH",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of H",
        read_only=True,
    )
    prev_value_of_i = pvproperty(
        name="LI",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of I",
        read_only=True,
    )
    prev_value_of_j = pvproperty(
        name="LJ",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of J",
        read_only=True,
    )
    prev_value_of_k = pvproperty(
        name="LK",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of K",
        read_only=True,
    )
    prev_value_of_l = pvproperty(
        name="LL",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of L",
        read_only=True,
    )
    monitor_deadband = pvproperty(
        name="MDEL", dtype=ChannelType.DOUBLE, doc="Monitor Deadband"
    )
    last_val_monitored = pvproperty(
        name="MLST",
        dtype=ChannelType.DOUBLE,
        doc="Last Val Monitored",
        read_only=True,
    )
    display_precision = pvproperty(
        name="PREC", dtype=ChannelType.INT, doc="Display Precision"
    )
    # result = pvproperty(name='VAL',
    #      dtype=ChannelType.DOUBLE,
    # doc='Result')
    link_parent_attribute(
        display_precision, "precision",
    )
    link_parent_attribute(archive_deadband, "log_atol", use_setattr=True)
    link_parent_attribute(monitor_deadband, "value_atol", use_setattr=True)


class CalcoutFields(RecordFieldGroup, _Limits):
    _record_type = "calcout"
    _dtype = ChannelType.DOUBLE  # DTYP of .VAL
    has_val_field = True
    copy_pvproperties(locals(), RecordFieldGroup, _Limits)
    device_type = pvproperty(
        name="DTYP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.dtyp_calcout.get_string_tuple(),
        doc="Device Type",
    )
    value_of_input_a = pvproperty(
        name="A", dtype=ChannelType.DOUBLE, doc="Value of Input A"
    )
    archive_deadband = pvproperty(
        name="ADEL", dtype=ChannelType.DOUBLE, doc="Archive Deadband"
    )
    last_value_archived = pvproperty(
        name="ALST",
        dtype=ChannelType.DOUBLE,
        doc="Last Value Archived",
        read_only=True,
    )
    value_of_input_b = pvproperty(
        name="B", dtype=ChannelType.DOUBLE, doc="Value of Input B"
    )
    value_of_input_c = pvproperty(
        name="C", dtype=ChannelType.DOUBLE, doc="Value of Input C"
    )
    calculation = pvproperty(
        name="CALC",
        dtype=ChannelType.CHAR,
        max_length=80,
        report_as_string=True,
        doc="Calculation",
        value=chr(0),
    )
    calc_valid = pvproperty(
        name="CLCV", dtype=ChannelType.LONG, doc="CALC Valid"
    )
    value_of_input_d = pvproperty(
        name="D", dtype=ChannelType.DOUBLE, doc="Value of Input D"
    )
    output_delay_active = pvproperty(
        name="DLYA",
        dtype=ChannelType.INT,
        doc="Output Delay Active",
        read_only=True,
    )
    output_data_opt = pvproperty(
        name="DOPT",
        dtype=ChannelType.ENUM,
        enum_strings=menus.calcoutDOPT.get_string_tuple(),
        doc="Output Data Opt",
    )
    value_of_input_e = pvproperty(
        name="E", dtype=ChannelType.DOUBLE, doc="Value of Input E"
    )
    engineering_units = pvproperty(
        name="EGU",
        dtype=ChannelType.CHAR,
        max_length=16,
        report_as_string=True,
        doc="Engineering Units",
    )
    value_of_input_f = pvproperty(
        name="F", dtype=ChannelType.DOUBLE, doc="Value of Input F"
    )
    value_of_input_g = pvproperty(
        name="G", dtype=ChannelType.DOUBLE, doc="Value of Input G"
    )
    value_of_input_h = pvproperty(
        name="H", dtype=ChannelType.DOUBLE, doc="Value of Input H"
    )
    alarm_deadband = pvproperty(
        name="HYST", dtype=ChannelType.DOUBLE, doc="Alarm Deadband"
    )
    value_of_input_i = pvproperty(
        name="I", dtype=ChannelType.DOUBLE, doc="Value of Input I"
    )
    inpa_pv_status = pvproperty(
        name="INAV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.calcoutINAV.get_string_tuple(),
        doc="INPA PV Status",
        read_only=True,
        value=1,
    )
    inpb_pv_status = pvproperty(
        name="INBV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.calcoutINAV.get_string_tuple(),
        doc="INPB PV Status",
        read_only=True,
        value=1,
    )
    inpc_pv_status = pvproperty(
        name="INCV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.calcoutINAV.get_string_tuple(),
        doc="INPC PV Status",
        read_only=True,
        value=1,
    )
    inpd_pv_status = pvproperty(
        name="INDV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.calcoutINAV.get_string_tuple(),
        doc="INPD PV Status",
        read_only=True,
        value=1,
    )
    inpe_pv_status = pvproperty(
        name="INEV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.calcoutINAV.get_string_tuple(),
        doc="INPE PV Status",
        read_only=True,
        value=1,
    )
    inpf_pv_status = pvproperty(
        name="INFV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.calcoutINAV.get_string_tuple(),
        doc="INPF PV Status",
        read_only=True,
        value=1,
    )
    inpg_pv_status = pvproperty(
        name="INGV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.calcoutINAV.get_string_tuple(),
        doc="INPG PV Status",
        read_only=True,
        value=1,
    )
    inph_pv_status = pvproperty(
        name="INHV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.calcoutINAV.get_string_tuple(),
        doc="INPH PV Status",
        read_only=True,
        value=1,
    )
    inpi_pv_status = pvproperty(
        name="INIV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.calcoutINAV.get_string_tuple(),
        doc="INPI PV Status",
        read_only=True,
        value=1,
    )
    inpj_pv_status = pvproperty(
        name="INJV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.calcoutINAV.get_string_tuple(),
        doc="INPJ PV Status",
        read_only=True,
        value=1,
    )
    inpk_pv_status = pvproperty(
        name="INKV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.calcoutINAV.get_string_tuple(),
        doc="INPK PV Status",
        read_only=True,
        value=1,
    )
    inpl_pv_status = pvproperty(
        name="INLV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.calcoutINAV.get_string_tuple(),
        doc="INPL PV Status",
        read_only=True,
        value=1,
    )
    input_a = pvproperty(name="INPA", dtype=ChannelType.STRING, doc="Input A")
    input_b = pvproperty(name="INPB", dtype=ChannelType.STRING, doc="Input B")
    input_c = pvproperty(name="INPC", dtype=ChannelType.STRING, doc="Input C")
    input_d = pvproperty(name="INPD", dtype=ChannelType.STRING, doc="Input D")
    input_e = pvproperty(name="INPE", dtype=ChannelType.STRING, doc="Input E")
    input_f = pvproperty(name="INPF", dtype=ChannelType.STRING, doc="Input F")
    input_g = pvproperty(name="INPG", dtype=ChannelType.STRING, doc="Input G")
    input_h = pvproperty(name="INPH", dtype=ChannelType.STRING, doc="Input H")
    input_i = pvproperty(name="INPI", dtype=ChannelType.STRING, doc="Input I")
    input_j = pvproperty(name="INPJ", dtype=ChannelType.STRING, doc="Input J")
    input_k = pvproperty(name="INPK", dtype=ChannelType.STRING, doc="Input K")
    input_l = pvproperty(name="INPL", dtype=ChannelType.STRING, doc="Input L")
    invalid_output_action = pvproperty(
        name="IVOA",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuIvoa.get_string_tuple(),
        doc="INVALID output action",
    )
    invalid_output_value = pvproperty(
        name="IVOV", dtype=ChannelType.DOUBLE, doc="INVALID output value"
    )
    value_of_input_j = pvproperty(
        name="J", dtype=ChannelType.DOUBLE, doc="Value of Input J"
    )
    value_of_input_k = pvproperty(
        name="K", dtype=ChannelType.DOUBLE, doc="Value of Input K"
    )
    value_of_input_l = pvproperty(
        name="L", dtype=ChannelType.DOUBLE, doc="Value of Input L"
    )
    prev_value_of_a = pvproperty(
        name="LA",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of A",
        read_only=True,
    )
    last_value_alarmed = pvproperty(
        name="LALM",
        dtype=ChannelType.DOUBLE,
        doc="Last Value Alarmed",
        read_only=True,
    )
    prev_value_of_b = pvproperty(
        name="LB",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of B",
        read_only=True,
    )
    prev_value_of_c = pvproperty(
        name="LC",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of C",
        read_only=True,
    )
    prev_value_of_d = pvproperty(
        name="LD",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of D",
        read_only=True,
    )
    prev_value_of_e = pvproperty(
        name="LE",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of E",
        read_only=True,
    )
    prev_value_of_f = pvproperty(
        name="LF",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of F",
        read_only=True,
    )
    prev_value_of_g = pvproperty(
        name="LG",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of G",
        read_only=True,
    )
    prev_value_of_h = pvproperty(
        name="LH",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of H",
        read_only=True,
    )
    prev_value_of_i = pvproperty(
        name="LI",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of I",
        read_only=True,
    )
    prev_value_of_j = pvproperty(
        name="LJ",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of J",
        read_only=True,
    )
    prev_value_of_k = pvproperty(
        name="LK",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of K",
        read_only=True,
    )
    prev_value_of_l = pvproperty(
        name="LL",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of L",
        read_only=True,
    )
    monitor_deadband = pvproperty(
        name="MDEL", dtype=ChannelType.DOUBLE, doc="Monitor Deadband"
    )
    last_val_monitored = pvproperty(
        name="MLST",
        dtype=ChannelType.DOUBLE,
        doc="Last Val Monitored",
        read_only=True,
    )
    output_calculation = pvproperty(
        name="OCAL",
        dtype=ChannelType.CHAR,
        max_length=80,
        report_as_string=True,
        doc="Output Calculation",
        value=chr(0),
    )
    ocal_valid = pvproperty(
        name="OCLV", dtype=ChannelType.LONG, doc="OCAL Valid"
    )
    output_execute_delay = pvproperty(
        name="ODLY", dtype=ChannelType.DOUBLE, doc="Output Execute Delay"
    )
    event_to_issue = pvproperty(
        name="OEVT",
        dtype=ChannelType.CHAR,
        max_length=40,
        report_as_string=True,
        doc="Event To Issue",
    )
    output_execute_opt = pvproperty(
        name="OOPT",
        dtype=ChannelType.ENUM,
        enum_strings=menus.calcoutOOPT.get_string_tuple(),
        doc="Output Execute Opt",
    )
    output_specification = pvproperty(
        name="OUT", dtype=ChannelType.STRING, doc="Output Specification"
    )
    out_pv_status = pvproperty(
        name="OUTV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.calcoutINAV.get_string_tuple(),
        doc="OUT PV Status",
        read_only=True,
    )
    output_value = pvproperty(
        name="OVAL", dtype=ChannelType.DOUBLE, doc="Output Value"
    )
    prev_value_of_oval = pvproperty(
        name="POVL", dtype=ChannelType.DOUBLE, doc="Prev Value of OVAL"
    )
    display_precision = pvproperty(
        name="PREC", dtype=ChannelType.INT, doc="Display Precision"
    )
    previous_value = pvproperty(
        name="PVAL", dtype=ChannelType.DOUBLE, doc="Previous Value"
    )
    # result = pvproperty(name='VAL',
    #      dtype=ChannelType.DOUBLE,
    # doc='Result')
    link_parent_attribute(
        display_precision, "precision",
    )
    link_parent_attribute(archive_deadband, "log_atol", use_setattr=True)
    link_parent_attribute(monitor_deadband, "value_atol", use_setattr=True)


class CompressFields(RecordFieldGroup):
    _record_type = "compress"
    _dtype = None  # DTYP of .VAL
    has_val_field = False
    copy_pvproperties(locals(), RecordFieldGroup)
    device_type = pvproperty(
        name="DTYP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.dtyp_compress.get_string_tuple(),
        doc="Device Type",
    )
    compression_algorithm = pvproperty(
        name="ALG",
        dtype=ChannelType.ENUM,
        enum_strings=menus.compressALG.get_string_tuple(),
        doc="Compression Algorithm",
    )
    buffering_algorithm = pvproperty(
        name="BALG",
        dtype=ChannelType.ENUM,
        enum_strings=menus.bufferingALG.get_string_tuple(),
        doc="Buffering Algorithm",
    )
    compress_value_buffer = pvproperty(
        name="CVB",
        dtype=ChannelType.DOUBLE,
        doc="Compress Value Buffer",
        read_only=True,
    )
    engineering_units = pvproperty(
        name="EGU",
        dtype=ChannelType.CHAR,
        max_length=16,
        report_as_string=True,
        doc="Engineering Units",
    )
    high_operating_range = pvproperty(
        name="HOPR", dtype=ChannelType.DOUBLE, doc="High Operating Range"
    )
    init_high_interest_lim = pvproperty(
        name="IHIL", dtype=ChannelType.DOUBLE, doc="Init High Interest Lim"
    )
    init_low_interest_lim = pvproperty(
        name="ILIL", dtype=ChannelType.DOUBLE, doc="Init Low Interest Lim"
    )
    input_specification = pvproperty(
        name="INP", dtype=ChannelType.STRING, doc="Input Specification"
    )
    number_of_elements_in_working_buffer = pvproperty(
        name="INPN",
        dtype=ChannelType.LONG,
        doc="Number of elements in Working Buffer",
        read_only=True,
    )
    compressed_array_inx = pvproperty(
        name="INX",
        dtype=ChannelType.LONG,
        doc="Compressed Array Inx",
        read_only=True,
    )
    low_operating_range = pvproperty(
        name="LOPR", dtype=ChannelType.DOUBLE, doc="Low Operating Range"
    )
    n_to_1_compression = pvproperty(
        name="N", dtype=ChannelType.LONG, doc="N to 1 Compression", value=1
    )
    number_of_values = pvproperty(
        name="NSAM",
        dtype=ChannelType.LONG,
        doc="Number of Values",
        read_only=True,
        value=1,
    )
    number_used = pvproperty(
        name="NUSE", dtype=ChannelType.LONG, doc="Number Used", read_only=True
    )
    offset = pvproperty(
        name="OFF", dtype=ChannelType.LONG, doc="Offset", read_only=True
    )
    old_number_used = pvproperty(
        name="OUSE",
        dtype=ChannelType.LONG,
        doc="Old Number Used",
        read_only=True,
    )
    display_precision = pvproperty(
        name="PREC", dtype=ChannelType.INT, doc="Display Precision"
    )
    reset = pvproperty(name="RES", dtype=ChannelType.INT, doc="Reset")
    link_parent_attribute(
        high_operating_range, "upper_ctrl_limit",
    )
    link_parent_attribute(
        low_operating_range, "lower_ctrl_limit",
    )
    link_parent_attribute(
        display_precision, "precision",
    )


class DfanoutFields(RecordFieldGroup, _Limits):
    _record_type = "dfanout"
    _dtype = ChannelType.DOUBLE  # DTYP of .VAL
    has_val_field = True
    copy_pvproperties(locals(), RecordFieldGroup, _Limits)
    device_type = pvproperty(
        name="DTYP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.dtyp_dfanout.get_string_tuple(),
        doc="Device Type",
    )
    archive_deadband = pvproperty(
        name="ADEL", dtype=ChannelType.DOUBLE, doc="Archive Deadband"
    )
    last_value_archived = pvproperty(
        name="ALST",
        dtype=ChannelType.DOUBLE,
        doc="Last Value Archived",
        read_only=True,
    )
    desired_output_loc = pvproperty(
        name="DOL", dtype=ChannelType.STRING, doc="Desired Output Loc"
    )
    engineering_units = pvproperty(
        name="EGU",
        dtype=ChannelType.CHAR,
        max_length=16,
        report_as_string=True,
        doc="Engineering Units",
    )
    alarm_deadband = pvproperty(
        name="HYST", dtype=ChannelType.DOUBLE, doc="Alarm Deadband"
    )
    last_value_alarmed = pvproperty(
        name="LALM",
        dtype=ChannelType.DOUBLE,
        doc="Last Value Alarmed",
        read_only=True,
    )
    monitor_deadband = pvproperty(
        name="MDEL", dtype=ChannelType.DOUBLE, doc="Monitor Deadband"
    )
    last_val_monitored = pvproperty(
        name="MLST",
        dtype=ChannelType.DOUBLE,
        doc="Last Val Monitored",
        read_only=True,
    )
    output_mode_select = pvproperty(
        name="OMSL",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuOmsl.get_string_tuple(),
        doc="Output Mode Select",
    )
    output_spec_a = pvproperty(
        name="OUTA", dtype=ChannelType.STRING, doc="Output Spec A"
    )
    output_spec_b = pvproperty(
        name="OUTB", dtype=ChannelType.STRING, doc="Output Spec B"
    )
    output_spec_c = pvproperty(
        name="OUTC", dtype=ChannelType.STRING, doc="Output Spec C"
    )
    output_spec_d = pvproperty(
        name="OUTD", dtype=ChannelType.STRING, doc="Output Spec D"
    )
    output_spec_e = pvproperty(
        name="OUTE", dtype=ChannelType.STRING, doc="Output Spec E"
    )
    output_spec_f = pvproperty(
        name="OUTF", dtype=ChannelType.STRING, doc="Output Spec F"
    )
    output_spec_g = pvproperty(
        name="OUTG", dtype=ChannelType.STRING, doc="Output Spec G"
    )
    output_spec_h = pvproperty(
        name="OUTH", dtype=ChannelType.STRING, doc="Output Spec H"
    )
    display_precision = pvproperty(
        name="PREC", dtype=ChannelType.INT, doc="Display Precision"
    )
    link_selection_loc = pvproperty(
        name="SELL", dtype=ChannelType.STRING, doc="Link Selection Loc"
    )
    select_mechanism = pvproperty(
        name="SELM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.dfanoutSELM.get_string_tuple(),
        doc="Select Mechanism",
    )
    link_selection = pvproperty(
        name="SELN", dtype=ChannelType.INT, doc="Link Selection", value=1
    )
    # desired_output = pvproperty(name='VAL',
    #      dtype=ChannelType.DOUBLE,
    # doc='Desired Output')
    link_parent_attribute(
        display_precision, "precision",
    )
    link_parent_attribute(archive_deadband, "log_atol", use_setattr=True)
    link_parent_attribute(monitor_deadband, "value_atol", use_setattr=True)


class EventFields(RecordFieldGroup):
    _record_type = "event"
    _dtype = ChannelType.STRING  # DTYP of .VAL
    has_val_field = True
    copy_pvproperties(locals(), RecordFieldGroup)
    device_type = pvproperty(
        name="DTYP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.dtyp_event.get_string_tuple(),
        doc="Device Type",
    )
    input_specification = pvproperty(
        name="INP", dtype=ChannelType.STRING, doc="Input Specification"
    )
    prev_simulation_mode = pvproperty(
        name="OLDSIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuSimm.get_string_tuple(),
        doc="Prev. Simulation Mode",
        read_only=True,
    )
    sim_mode_async_delay = pvproperty(
        name="SDLY",
        dtype=ChannelType.DOUBLE,
        doc="Sim. Mode Async Delay",
        value=-1.0,
    )
    sim_mode_location = pvproperty(
        name="SIML", dtype=ChannelType.STRING, doc="Sim Mode Location"
    )
    simulation_mode = pvproperty(
        name="SIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuYesNo.get_string_tuple(),
        doc="Simulation Mode",
    )
    sim_mode_alarm_svrty = pvproperty(
        name="SIMS",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Sim mode Alarm Svrty",
    )
    sim_input_specifctn = pvproperty(
        name="SIOL", dtype=ChannelType.STRING, doc="Sim Input Specifctn"
    )
    sim_mode_scan = pvproperty(
        name="SSCN",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuScan.get_string_tuple(),
        doc="Sim. Mode Scan",
        value=0,
    )
    simulation_value = pvproperty(
        name="SVAL",
        dtype=ChannelType.CHAR,
        max_length=40,
        report_as_string=True,
        doc="Simulation Value",
    )
    # event_name_to_post = pvproperty(name='VAL',
    #      dtype=ChannelType.CHAR,
    # max_length=40,report_as_string=True,doc='Event Name To Post')


class FanoutFields(RecordFieldGroup):
    _record_type = "fanout"
    _dtype = ChannelType.LONG  # DTYP of .VAL
    has_val_field = True
    copy_pvproperties(locals(), RecordFieldGroup)
    device_type = pvproperty(
        name="DTYP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.dtyp_fanout.get_string_tuple(),
        doc="Device Type",
    )
    forward_link_0 = pvproperty(
        name="LNK0", dtype=ChannelType.STRING, doc="Forward Link 0"
    )
    forward_link_1 = pvproperty(
        name="LNK1", dtype=ChannelType.STRING, doc="Forward Link 1"
    )
    forward_link_2 = pvproperty(
        name="LNK2", dtype=ChannelType.STRING, doc="Forward Link 2"
    )
    forward_link_3 = pvproperty(
        name="LNK3", dtype=ChannelType.STRING, doc="Forward Link 3"
    )
    forward_link_4 = pvproperty(
        name="LNK4", dtype=ChannelType.STRING, doc="Forward Link 4"
    )
    forward_link_5 = pvproperty(
        name="LNK5", dtype=ChannelType.STRING, doc="Forward Link 5"
    )
    forward_link_6 = pvproperty(
        name="LNK6", dtype=ChannelType.STRING, doc="Forward Link 6"
    )
    forward_link_7 = pvproperty(
        name="LNK7", dtype=ChannelType.STRING, doc="Forward Link 7"
    )
    forward_link_8 = pvproperty(
        name="LNK8", dtype=ChannelType.STRING, doc="Forward Link 8"
    )
    forward_link_9 = pvproperty(
        name="LNK9", dtype=ChannelType.STRING, doc="Forward Link 9"
    )
    forward_link_10 = pvproperty(
        name="LNKA", dtype=ChannelType.STRING, doc="Forward Link 10"
    )
    forward_link_11 = pvproperty(
        name="LNKB", dtype=ChannelType.STRING, doc="Forward Link 11"
    )
    forward_link_12 = pvproperty(
        name="LNKC", dtype=ChannelType.STRING, doc="Forward Link 12"
    )
    forward_link_13 = pvproperty(
        name="LNKD", dtype=ChannelType.STRING, doc="Forward Link 13"
    )
    forward_link_14 = pvproperty(
        name="LNKE", dtype=ChannelType.STRING, doc="Forward Link 14"
    )
    forward_link_15 = pvproperty(
        name="LNKF", dtype=ChannelType.STRING, doc="Forward Link 15"
    )
    offset_for_specified = pvproperty(
        name="OFFS", dtype=ChannelType.INT, doc="Offset for Specified", value=0
    )
    link_selection_loc = pvproperty(
        name="SELL", dtype=ChannelType.STRING, doc="Link Selection Loc"
    )
    select_mechanism = pvproperty(
        name="SELM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.fanoutSELM.get_string_tuple(),
        doc="Select Mechanism",
    )
    link_selection = pvproperty(
        name="SELN", dtype=ChannelType.INT, doc="Link Selection", value=1
    )
    shift_for_mask_mode = pvproperty(
        name="SHFT", dtype=ChannelType.INT, doc="Shift for Mask mode", value=-1
    )
    # used_to_trigger = pvproperty(name='VAL',
    #      dtype=ChannelType.LONG,
    # doc='Used to trigger')


class HistogramFields(RecordFieldGroup):
    _record_type = "histogram"
    _dtype = None  # DTYP of .VAL
    has_val_field = False
    copy_pvproperties(locals(), RecordFieldGroup)
    device_type = pvproperty(
        name="DTYP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.dtyp_histogram.get_string_tuple(),
        doc="Device Type",
    )
    collection_control = pvproperty(
        name="CMD",
        dtype=ChannelType.ENUM,
        enum_strings=menus.histogramCMD.get_string_tuple(),
        doc="Collection Control",
    )
    collection_status = pvproperty(
        name="CSTA",
        dtype=ChannelType.INT,
        doc="Collection Status",
        read_only=True,
        value=1,
    )
    high_operating_range = pvproperty(
        name="HOPR", dtype=ChannelType.LONG, doc="High Operating Range"
    )
    lower_signal_limit = pvproperty(
        name="LLIM", dtype=ChannelType.DOUBLE, doc="Lower Signal Limit "
    )
    low_operating_range = pvproperty(
        name="LOPR", dtype=ChannelType.LONG, doc="Low Operating Range"
    )
    counts_since_monitor = pvproperty(
        name="MCNT",
        dtype=ChannelType.INT,
        doc="Counts Since Monitor",
        read_only=True,
    )
    monitor_count_deadband = pvproperty(
        name="MDEL", dtype=ChannelType.INT, doc="Monitor Count Deadband"
    )
    num_of_array_elements = pvproperty(
        name="NELM",
        dtype=ChannelType.INT,
        doc="Num of Array Elements",
        read_only=True,
        value=1,
    )
    prev_simulation_mode = pvproperty(
        name="OLDSIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuSimm.get_string_tuple(),
        doc="Prev. Simulation Mode",
        read_only=True,
    )
    display_precision = pvproperty(
        name="PREC", dtype=ChannelType.INT, doc="Display Precision"
    )
    monitor_seconds_dband = pvproperty(
        name="SDEL", dtype=ChannelType.DOUBLE, doc="Monitor Seconds Dband"
    )
    sim_mode_async_delay = pvproperty(
        name="SDLY",
        dtype=ChannelType.DOUBLE,
        doc="Sim. Mode Async Delay",
        value=-1.0,
    )
    signal_value = pvproperty(
        name="SGNL", dtype=ChannelType.DOUBLE, doc="Signal Value"
    )
    simulation_mode_link = pvproperty(
        name="SIML", dtype=ChannelType.STRING, doc="Simulation Mode Link"
    )
    simulation_mode = pvproperty(
        name="SIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuYesNo.get_string_tuple(),
        doc="Simulation Mode",
    )
    simulation_mode_severity = pvproperty(
        name="SIMS",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Simulation Mode Severity",
    )
    simulation_input_link = pvproperty(
        name="SIOL", dtype=ChannelType.STRING, doc="Simulation Input Link"
    )
    sim_mode_scan = pvproperty(
        name="SSCN",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuScan.get_string_tuple(),
        doc="Sim. Mode Scan",
        value=0,
    )
    simulation_value = pvproperty(
        name="SVAL", dtype=ChannelType.DOUBLE, doc="Simulation Value"
    )
    signal_value_location = pvproperty(
        name="SVL", dtype=ChannelType.STRING, doc="Signal Value Location"
    )
    upper_signal_limit = pvproperty(
        name="ULIM", dtype=ChannelType.DOUBLE, doc="Upper Signal Limit"
    )
    element_width = pvproperty(
        name="WDTH",
        dtype=ChannelType.DOUBLE,
        doc="Element Width",
        read_only=True,
    )
    link_parent_attribute(
        display_precision, "precision",
    )
    link_parent_attribute(
        high_operating_range, "upper_ctrl_limit",
    )
    link_parent_attribute(
        low_operating_range, "lower_ctrl_limit",
    )


class Int64inFields(RecordFieldGroup, _LimitsLong):
    _record_type = "int64in"
    _dtype = ChannelType.LONG  # DTYP of .VAL
    has_val_field = True
    copy_pvproperties(locals(), RecordFieldGroup, _LimitsLong)
    device_type = pvproperty(
        name="DTYP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.dtyp_int64in.get_string_tuple(),
        doc="Device Type",
    )
    archive_deadband = pvproperty(
        name="ADEL", dtype=ChannelType.LONG, doc="Archive Deadband"
    )
    alarm_filter_time_constant = pvproperty(
        name="AFTC", dtype=ChannelType.DOUBLE, doc="Alarm Filter Time Constant"
    )
    alarm_filter_value = pvproperty(
        name="AFVL",
        dtype=ChannelType.DOUBLE,
        doc="Alarm Filter Value",
        read_only=True,
    )
    last_value_archived = pvproperty(
        name="ALST",
        dtype=ChannelType.LONG,
        doc="Last Value Archived",
        read_only=True,
    )
    units_name = pvproperty(
        name="EGU",
        dtype=ChannelType.CHAR,
        max_length=16,
        report_as_string=True,
        doc="Units name",
    )
    alarm_deadband = pvproperty(
        name="HYST", dtype=ChannelType.LONG, doc="Alarm Deadband"
    )
    input_specification = pvproperty(
        name="INP", dtype=ChannelType.STRING, doc="Input Specification"
    )
    last_value_alarmed = pvproperty(
        name="LALM",
        dtype=ChannelType.LONG,
        doc="Last Value Alarmed",
        read_only=True,
    )
    monitor_deadband = pvproperty(
        name="MDEL", dtype=ChannelType.LONG, doc="Monitor Deadband"
    )
    last_val_monitored = pvproperty(
        name="MLST",
        dtype=ChannelType.LONG,
        doc="Last Val Monitored",
        read_only=True,
    )
    prev_simulation_mode = pvproperty(
        name="OLDSIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuSimm.get_string_tuple(),
        doc="Prev. Simulation Mode",
        read_only=True,
    )
    sim_mode_async_delay = pvproperty(
        name="SDLY",
        dtype=ChannelType.DOUBLE,
        doc="Sim. Mode Async Delay",
        value=-1.0,
    )
    simulation_mode_link = pvproperty(
        name="SIML", dtype=ChannelType.STRING, doc="Simulation Mode Link"
    )
    simulation_mode = pvproperty(
        name="SIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuYesNo.get_string_tuple(),
        doc="Simulation Mode",
    )
    simulation_mode_severity = pvproperty(
        name="SIMS",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Simulation Mode Severity",
    )
    simulation_input_link = pvproperty(
        name="SIOL", dtype=ChannelType.STRING, doc="Simulation Input Link"
    )
    sim_mode_scan = pvproperty(
        name="SSCN",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuScan.get_string_tuple(),
        doc="Sim. Mode Scan",
        value=0,
    )
    simulation_value = pvproperty(
        name="SVAL", dtype=ChannelType.LONG, doc="Simulation Value"
    )
    # current_value = pvproperty(name='VAL',
    #      dtype=ChannelType.LONG,
    # doc='Current value')
    link_parent_attribute(archive_deadband, "log_atol", use_setattr=True)
    link_parent_attribute(monitor_deadband, "value_atol", use_setattr=True)


class Int64outFields(RecordFieldGroup, _LimitsLong):
    _record_type = "int64out"
    _dtype = ChannelType.LONG  # DTYP of .VAL
    has_val_field = True
    copy_pvproperties(locals(), RecordFieldGroup, _LimitsLong)
    device_type = pvproperty(
        name="DTYP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.dtyp_int64out.get_string_tuple(),
        doc="Device Type",
    )
    archive_deadband = pvproperty(
        name="ADEL", dtype=ChannelType.LONG, doc="Archive Deadband"
    )
    last_value_archived = pvproperty(
        name="ALST",
        dtype=ChannelType.LONG,
        doc="Last Value Archived",
        read_only=True,
    )
    desired_output_loc = pvproperty(
        name="DOL", dtype=ChannelType.STRING, doc="Desired Output Loc"
    )
    drive_high_limit = pvproperty(
        name="DRVH", dtype=ChannelType.LONG, doc="Drive High Limit"
    )
    drive_low_limit = pvproperty(
        name="DRVL", dtype=ChannelType.LONG, doc="Drive Low Limit"
    )
    units_name = pvproperty(
        name="EGU",
        dtype=ChannelType.CHAR,
        max_length=16,
        report_as_string=True,
        doc="Units name",
    )
    alarm_deadband = pvproperty(
        name="HYST", dtype=ChannelType.LONG, doc="Alarm Deadband"
    )
    invalid_output_action = pvproperty(
        name="IVOA",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuIvoa.get_string_tuple(),
        doc="INVALID output action",
    )
    invalid_output_value = pvproperty(
        name="IVOV", dtype=ChannelType.LONG, doc="INVALID output value"
    )
    last_value_alarmed = pvproperty(
        name="LALM",
        dtype=ChannelType.LONG,
        doc="Last Value Alarmed",
        read_only=True,
    )
    monitor_deadband = pvproperty(
        name="MDEL", dtype=ChannelType.LONG, doc="Monitor Deadband"
    )
    last_val_monitored = pvproperty(
        name="MLST",
        dtype=ChannelType.LONG,
        doc="Last Val Monitored",
        read_only=True,
    )
    prev_simulation_mode = pvproperty(
        name="OLDSIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuSimm.get_string_tuple(),
        doc="Prev. Simulation Mode",
        read_only=True,
    )
    output_mode_select = pvproperty(
        name="OMSL",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuOmsl.get_string_tuple(),
        doc="Output Mode Select",
    )
    output_specification = pvproperty(
        name="OUT", dtype=ChannelType.STRING, doc="Output Specification"
    )
    sim_mode_async_delay = pvproperty(
        name="SDLY",
        dtype=ChannelType.DOUBLE,
        doc="Sim. Mode Async Delay",
        value=-1.0,
    )
    simulation_mode_link = pvproperty(
        name="SIML", dtype=ChannelType.STRING, doc="Simulation Mode Link"
    )
    simulation_mode = pvproperty(
        name="SIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuYesNo.get_string_tuple(),
        doc="Simulation Mode",
    )
    simulation_mode_severity = pvproperty(
        name="SIMS",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Simulation Mode Severity",
    )
    simulation_output_link = pvproperty(
        name="SIOL", dtype=ChannelType.STRING, doc="Simulation Output Link"
    )
    sim_mode_scan = pvproperty(
        name="SSCN",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuScan.get_string_tuple(),
        doc="Sim. Mode Scan",
        value=0,
    )
    # desired_output = pvproperty(name='VAL',
    #      dtype=ChannelType.LONG,
    # doc='Desired Output')
    link_parent_attribute(archive_deadband, "log_atol", use_setattr=True)
    link_parent_attribute(monitor_deadband, "value_atol", use_setattr=True)


class LonginFields(RecordFieldGroup, _LimitsLong):
    _record_type = "longin"
    _dtype = ChannelType.LONG  # DTYP of .VAL
    has_val_field = True
    copy_pvproperties(locals(), RecordFieldGroup, _LimitsLong)
    device_type = pvproperty(
        name="DTYP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.dtyp_longin.get_string_tuple(),
        doc="Device Type",
    )
    archive_deadband = pvproperty(
        name="ADEL", dtype=ChannelType.LONG, doc="Archive Deadband"
    )
    alarm_filter_time_constant = pvproperty(
        name="AFTC", dtype=ChannelType.DOUBLE, doc="Alarm Filter Time Constant"
    )
    alarm_filter_value = pvproperty(
        name="AFVL",
        dtype=ChannelType.DOUBLE,
        doc="Alarm Filter Value",
        read_only=True,
    )
    last_value_archived = pvproperty(
        name="ALST",
        dtype=ChannelType.LONG,
        doc="Last Value Archived",
        read_only=True,
    )
    engineering_units = pvproperty(
        name="EGU",
        dtype=ChannelType.CHAR,
        max_length=16,
        report_as_string=True,
        doc="Engineering Units",
    )
    alarm_deadband = pvproperty(
        name="HYST", dtype=ChannelType.LONG, doc="Alarm Deadband"
    )
    input_specification = pvproperty(
        name="INP", dtype=ChannelType.STRING, doc="Input Specification"
    )
    last_value_alarmed = pvproperty(
        name="LALM",
        dtype=ChannelType.LONG,
        doc="Last Value Alarmed",
        read_only=True,
    )
    monitor_deadband = pvproperty(
        name="MDEL", dtype=ChannelType.LONG, doc="Monitor Deadband"
    )
    last_val_monitored = pvproperty(
        name="MLST",
        dtype=ChannelType.LONG,
        doc="Last Val Monitored",
        read_only=True,
    )
    prev_simulation_mode = pvproperty(
        name="OLDSIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuSimm.get_string_tuple(),
        doc="Prev. Simulation Mode",
        read_only=True,
    )
    sim_mode_async_delay = pvproperty(
        name="SDLY",
        dtype=ChannelType.DOUBLE,
        doc="Sim. Mode Async Delay",
        value=-1.0,
    )
    sim_mode_location = pvproperty(
        name="SIML", dtype=ChannelType.STRING, doc="Sim Mode Location"
    )
    simulation_mode = pvproperty(
        name="SIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuYesNo.get_string_tuple(),
        doc="Simulation Mode",
    )
    sim_mode_alarm_svrty = pvproperty(
        name="SIMS",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Sim mode Alarm Svrty",
    )
    sim_input_specifctn = pvproperty(
        name="SIOL", dtype=ChannelType.STRING, doc="Sim Input Specifctn"
    )
    sim_mode_scan = pvproperty(
        name="SSCN",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuScan.get_string_tuple(),
        doc="Sim. Mode Scan",
        value=0,
    )
    simulation_value = pvproperty(
        name="SVAL", dtype=ChannelType.LONG, doc="Simulation Value"
    )
    # current_value = pvproperty(name='VAL',
    #      dtype=ChannelType.LONG,
    # doc='Current value')
    link_parent_attribute(archive_deadband, "log_atol", use_setattr=True)
    link_parent_attribute(monitor_deadband, "value_atol", use_setattr=True)


class LongoutFields(RecordFieldGroup, _LimitsLong):
    _record_type = "longout"
    _dtype = ChannelType.LONG  # DTYP of .VAL
    has_val_field = True
    copy_pvproperties(locals(), RecordFieldGroup, _LimitsLong)
    device_type = pvproperty(
        name="DTYP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.dtyp_longout.get_string_tuple(),
        doc="Device Type",
    )
    archive_deadband = pvproperty(
        name="ADEL", dtype=ChannelType.LONG, doc="Archive Deadband"
    )
    last_value_archived = pvproperty(
        name="ALST",
        dtype=ChannelType.LONG,
        doc="Last Value Archived",
        read_only=True,
    )
    desired_output_loc = pvproperty(
        name="DOL", dtype=ChannelType.STRING, doc="Desired Output Loc"
    )
    drive_high_limit = pvproperty(
        name="DRVH", dtype=ChannelType.LONG, doc="Drive High Limit"
    )
    drive_low_limit = pvproperty(
        name="DRVL", dtype=ChannelType.LONG, doc="Drive Low Limit"
    )
    engineering_units = pvproperty(
        name="EGU",
        dtype=ChannelType.CHAR,
        max_length=16,
        report_as_string=True,
        doc="Engineering Units",
    )
    alarm_deadband = pvproperty(
        name="HYST", dtype=ChannelType.LONG, doc="Alarm Deadband"
    )
    invalid_output_action = pvproperty(
        name="IVOA",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuIvoa.get_string_tuple(),
        doc="INVALID output action",
    )
    invalid_output_value = pvproperty(
        name="IVOV", dtype=ChannelType.LONG, doc="INVALID output value"
    )
    last_value_alarmed = pvproperty(
        name="LALM",
        dtype=ChannelType.LONG,
        doc="Last Value Alarmed",
        read_only=True,
    )
    monitor_deadband = pvproperty(
        name="MDEL", dtype=ChannelType.LONG, doc="Monitor Deadband"
    )
    last_val_monitored = pvproperty(
        name="MLST",
        dtype=ChannelType.LONG,
        doc="Last Val Monitored",
        read_only=True,
    )
    prev_simulation_mode = pvproperty(
        name="OLDSIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuSimm.get_string_tuple(),
        doc="Prev. Simulation Mode",
        read_only=True,
    )
    output_mode_select = pvproperty(
        name="OMSL",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuOmsl.get_string_tuple(),
        doc="Output Mode Select",
    )
    output_specification = pvproperty(
        name="OUT", dtype=ChannelType.STRING, doc="Output Specification"
    )
    sim_mode_async_delay = pvproperty(
        name="SDLY",
        dtype=ChannelType.DOUBLE,
        doc="Sim. Mode Async Delay",
        value=-1.0,
    )
    sim_mode_location = pvproperty(
        name="SIML", dtype=ChannelType.STRING, doc="Sim Mode Location"
    )
    simulation_mode = pvproperty(
        name="SIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuYesNo.get_string_tuple(),
        doc="Simulation Mode",
    )
    sim_mode_alarm_svrty = pvproperty(
        name="SIMS",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Sim mode Alarm Svrty",
    )
    sim_output_specifctn = pvproperty(
        name="SIOL", dtype=ChannelType.STRING, doc="Sim Output Specifctn"
    )
    sim_mode_scan = pvproperty(
        name="SSCN",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuScan.get_string_tuple(),
        doc="Sim. Mode Scan",
        value=0,
    )
    # desired_output = pvproperty(name='VAL',
    #      dtype=ChannelType.LONG,
    # doc='Desired Output')
    link_parent_attribute(archive_deadband, "log_atol", use_setattr=True)
    link_parent_attribute(monitor_deadband, "value_atol", use_setattr=True)


class LsiFields(RecordFieldGroup):
    _record_type = "lsi"
    _dtype = None  # DTYP of .VAL
    has_val_field = False
    copy_pvproperties(locals(), RecordFieldGroup)
    device_type = pvproperty(
        name="DTYP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.dtyp_lsi.get_string_tuple(),
        doc="Device Type",
    )
    post_archive_monitors = pvproperty(
        name="APST",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuPost.get_string_tuple(),
        doc="Post Archive Monitors",
    )
    input_specification = pvproperty(
        name="INP", dtype=ChannelType.STRING, doc="Input Specification"
    )
    length_of_val = pvproperty(
        name="LEN", dtype=ChannelType.LONG, doc="Length of VAL", read_only=True
    )
    post_value_monitors = pvproperty(
        name="MPST",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuPost.get_string_tuple(),
        doc="Post Value Monitors",
    )
    prev_simulation_mode = pvproperty(
        name="OLDSIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuSimm.get_string_tuple(),
        doc="Prev. Simulation Mode",
        read_only=True,
    )
    length_of_oval = pvproperty(
        name="OLEN",
        dtype=ChannelType.LONG,
        doc="Length of OVAL",
        read_only=True,
    )
    sim_mode_async_delay = pvproperty(
        name="SDLY",
        dtype=ChannelType.DOUBLE,
        doc="Sim. Mode Async Delay",
        value=-1.0,
    )
    simulation_mode_link = pvproperty(
        name="SIML", dtype=ChannelType.STRING, doc="Simulation Mode Link"
    )
    simulation_mode = pvproperty(
        name="SIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuYesNo.get_string_tuple(),
        doc="Simulation Mode",
    )
    simulation_mode_severity = pvproperty(
        name="SIMS",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Simulation Mode Severity",
    )
    simulation_input_link = pvproperty(
        name="SIOL", dtype=ChannelType.STRING, doc="Simulation Input Link"
    )
    size_of_buffers = pvproperty(
        name="SIZV",
        dtype=ChannelType.INT,
        doc="Size of buffers",
        read_only=True,
        value=41,
    )
    sim_mode_scan = pvproperty(
        name="SSCN",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuScan.get_string_tuple(),
        doc="Sim. Mode Scan",
        value=0,
    )


class LsoFields(RecordFieldGroup):
    _record_type = "lso"
    _dtype = None  # DTYP of .VAL
    has_val_field = False
    copy_pvproperties(locals(), RecordFieldGroup)
    device_type = pvproperty(
        name="DTYP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.dtyp_lso.get_string_tuple(),
        doc="Device Type",
    )
    post_archive_monitors = pvproperty(
        name="APST",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuPost.get_string_tuple(),
        doc="Post Archive Monitors",
    )
    desired_output_link = pvproperty(
        name="DOL", dtype=ChannelType.STRING, doc="Desired Output Link"
    )
    invalid_output_action = pvproperty(
        name="IVOA",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuIvoa.get_string_tuple(),
        doc="INVALID Output Action",
    )
    invalid_output_value = pvproperty(
        name="IVOV",
        dtype=ChannelType.CHAR,
        max_length=40,
        report_as_string=True,
        doc="INVALID Output Value",
    )
    length_of_val = pvproperty(
        name="LEN", dtype=ChannelType.LONG, doc="Length of VAL", read_only=True
    )
    post_value_monitors = pvproperty(
        name="MPST",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuPost.get_string_tuple(),
        doc="Post Value Monitors",
    )
    prev_simulation_mode = pvproperty(
        name="OLDSIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuSimm.get_string_tuple(),
        doc="Prev. Simulation Mode",
        read_only=True,
    )
    length_of_oval = pvproperty(
        name="OLEN",
        dtype=ChannelType.LONG,
        doc="Length of OVAL",
        read_only=True,
    )
    output_mode_select = pvproperty(
        name="OMSL",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuOmsl.get_string_tuple(),
        doc="Output Mode Select",
    )
    output_specification = pvproperty(
        name="OUT", dtype=ChannelType.STRING, doc="Output Specification"
    )
    sim_mode_async_delay = pvproperty(
        name="SDLY",
        dtype=ChannelType.DOUBLE,
        doc="Sim. Mode Async Delay",
        value=-1.0,
    )
    simulation_mode_link = pvproperty(
        name="SIML", dtype=ChannelType.STRING, doc="Simulation Mode link"
    )
    simulation_mode = pvproperty(
        name="SIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuYesNo.get_string_tuple(),
        doc="Simulation Mode",
    )
    simulation_mode_severity = pvproperty(
        name="SIMS",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Simulation Mode Severity",
    )
    simulation_output_link = pvproperty(
        name="SIOL", dtype=ChannelType.STRING, doc="Simulation Output Link"
    )
    size_of_buffers = pvproperty(
        name="SIZV",
        dtype=ChannelType.INT,
        doc="Size of buffers",
        read_only=True,
        value=41,
    )
    sim_mode_scan = pvproperty(
        name="SSCN",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuScan.get_string_tuple(),
        doc="Sim. Mode Scan",
        value=0,
    )


class MbbiFields(RecordFieldGroup):
    _record_type = "mbbi"
    _dtype = ChannelType.ENUM  # DTYP of .VAL
    has_val_field = True
    copy_pvproperties(locals(), RecordFieldGroup)
    device_type = pvproperty(
        name="DTYP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.dtyp_mbbi.get_string_tuple(),
        doc="Device Type",
    )
    alarm_filter_time_constant = pvproperty(
        name="AFTC", dtype=ChannelType.DOUBLE, doc="Alarm Filter Time Constant"
    )
    alarm_filter_value = pvproperty(
        name="AFVL",
        dtype=ChannelType.DOUBLE,
        doc="Alarm Filter Value",
        read_only=True,
    )
    change_of_state_svr = pvproperty(
        name="COSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Change of State Svr",
    )
    eight_string = pvproperty(
        name="EIST",
        dtype=ChannelType.CHAR,
        max_length=26,
        report_as_string=True,
        doc="Eight String",
    )
    state_eight_severity = pvproperty(
        name="EISV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="State Eight Severity",
    )
    eight_value = pvproperty(
        name="EIVL", dtype=ChannelType.LONG, doc="Eight Value"
    )
    eleven_string = pvproperty(
        name="ELST",
        dtype=ChannelType.CHAR,
        max_length=26,
        report_as_string=True,
        doc="Eleven String",
    )
    state_eleven_severity = pvproperty(
        name="ELSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="State Eleven Severity",
    )
    eleven_value = pvproperty(
        name="ELVL", dtype=ChannelType.LONG, doc="Eleven Value"
    )
    fifteen_string = pvproperty(
        name="FFST",
        dtype=ChannelType.CHAR,
        max_length=26,
        report_as_string=True,
        doc="Fifteen String",
    )
    state_fifteen_severity = pvproperty(
        name="FFSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="State Fifteen Severity",
    )
    fifteen_value = pvproperty(
        name="FFVL", dtype=ChannelType.LONG, doc="Fifteen Value"
    )
    four_string = pvproperty(
        name="FRST",
        dtype=ChannelType.CHAR,
        max_length=26,
        report_as_string=True,
        doc="Four String",
    )
    state_four_severity = pvproperty(
        name="FRSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="State Four Severity",
    )
    four_value = pvproperty(
        name="FRVL", dtype=ChannelType.LONG, doc="Four Value"
    )
    fourteen_string = pvproperty(
        name="FTST",
        dtype=ChannelType.CHAR,
        max_length=26,
        report_as_string=True,
        doc="Fourteen String",
    )
    state_fourteen_sevr = pvproperty(
        name="FTSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="State Fourteen Sevr",
    )
    fourteen_value = pvproperty(
        name="FTVL", dtype=ChannelType.LONG, doc="Fourteen Value"
    )
    five_string = pvproperty(
        name="FVST",
        dtype=ChannelType.CHAR,
        max_length=26,
        report_as_string=True,
        doc="Five String",
    )
    state_five_severity = pvproperty(
        name="FVSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="State Five Severity",
    )
    five_value = pvproperty(
        name="FVVL", dtype=ChannelType.LONG, doc="Five Value"
    )
    input_specification = pvproperty(
        name="INP", dtype=ChannelType.STRING, doc="Input Specification"
    )
    last_value_alarmed = pvproperty(
        name="LALM",
        dtype=ChannelType.INT,
        doc="Last Value Alarmed",
        read_only=True,
    )
    hardware_mask = pvproperty(
        name="MASK", dtype=ChannelType.LONG, doc="Hardware Mask", read_only=True
    )
    last_value_monitored = pvproperty(
        name="MLST",
        dtype=ChannelType.INT,
        doc="Last Value Monitored",
        read_only=True,
    )
    nine_string = pvproperty(
        name="NIST",
        dtype=ChannelType.CHAR,
        max_length=26,
        report_as_string=True,
        doc="Nine String",
    )
    state_nine_severity = pvproperty(
        name="NISV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="State Nine Severity",
    )
    nine_value = pvproperty(
        name="NIVL", dtype=ChannelType.LONG, doc="Nine Value"
    )
    number_of_bits = pvproperty(
        name="NOBT", dtype=ChannelType.INT, doc="Number of Bits", read_only=True
    )
    prev_simulation_mode = pvproperty(
        name="OLDSIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuSimm.get_string_tuple(),
        doc="Prev. Simulation Mode",
        read_only=True,
    )
    one_string = pvproperty(
        name="ONST",
        dtype=ChannelType.CHAR,
        max_length=26,
        report_as_string=True,
        doc="One String",
    )
    state_one_severity = pvproperty(
        name="ONSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="State One Severity",
    )
    one_value = pvproperty(name="ONVL", dtype=ChannelType.LONG, doc="One Value")
    prev_raw_value = pvproperty(
        name="ORAW",
        dtype=ChannelType.LONG,
        doc="Prev Raw Value",
        read_only=True,
    )
    raw_value = pvproperty(name="RVAL", dtype=ChannelType.LONG, doc="Raw Value")
    states_defined = pvproperty(
        name="SDEF", dtype=ChannelType.INT, doc="States Defined", read_only=True
    )
    sim_mode_async_delay = pvproperty(
        name="SDLY",
        dtype=ChannelType.DOUBLE,
        doc="Sim. Mode Async Delay",
        value=-1.0,
    )
    shift = pvproperty(name="SHFT", dtype=ChannelType.INT, doc="Shift")
    simulation_mode_link = pvproperty(
        name="SIML", dtype=ChannelType.STRING, doc="Simulation Mode Link"
    )
    simulation_mode = pvproperty(
        name="SIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuSimm.get_string_tuple(),
        doc="Simulation Mode",
    )
    simulation_mode_severity = pvproperty(
        name="SIMS",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Simulation Mode Severity",
    )
    simulation_input_link = pvproperty(
        name="SIOL", dtype=ChannelType.STRING, doc="Simulation Input Link"
    )
    sim_mode_scan = pvproperty(
        name="SSCN",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuScan.get_string_tuple(),
        doc="Sim. Mode Scan",
        value=0,
    )
    simulation_value = pvproperty(
        name="SVAL", dtype=ChannelType.LONG, doc="Simulation Value"
    )
    seven_string = pvproperty(
        name="SVST",
        dtype=ChannelType.CHAR,
        max_length=26,
        report_as_string=True,
        doc="Seven String",
    )
    state_seven_severity = pvproperty(
        name="SVSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="State Seven Severity",
    )
    seven_value = pvproperty(
        name="SVVL", dtype=ChannelType.LONG, doc="Seven Value"
    )
    six_string = pvproperty(
        name="SXST",
        dtype=ChannelType.CHAR,
        max_length=26,
        report_as_string=True,
        doc="Six String",
    )
    state_six_severity = pvproperty(
        name="SXSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="State Six Severity",
    )
    six_value = pvproperty(name="SXVL", dtype=ChannelType.LONG, doc="Six Value")
    ten_string = pvproperty(
        name="TEST",
        dtype=ChannelType.CHAR,
        max_length=26,
        report_as_string=True,
        doc="Ten String",
    )
    state_ten_severity = pvproperty(
        name="TESV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="State Ten Severity",
    )
    ten_value = pvproperty(name="TEVL", dtype=ChannelType.LONG, doc="Ten Value")
    three_string = pvproperty(
        name="THST",
        dtype=ChannelType.CHAR,
        max_length=26,
        report_as_string=True,
        doc="Three String",
    )
    state_three_severity = pvproperty(
        name="THSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="State Three Severity",
    )
    three_value = pvproperty(
        name="THVL", dtype=ChannelType.LONG, doc="Three Value"
    )
    thirteen_string = pvproperty(
        name="TTST",
        dtype=ChannelType.CHAR,
        max_length=26,
        report_as_string=True,
        doc="Thirteen String",
    )
    state_thirteen_sevr = pvproperty(
        name="TTSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="State Thirteen Sevr",
    )
    thirteen_value = pvproperty(
        name="TTVL", dtype=ChannelType.LONG, doc="Thirteen Value"
    )
    twelve_string = pvproperty(
        name="TVST",
        dtype=ChannelType.CHAR,
        max_length=26,
        report_as_string=True,
        doc="Twelve String",
    )
    state_twelve_severity = pvproperty(
        name="TVSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="State Twelve Severity",
    )
    twelve_value = pvproperty(
        name="TVVL", dtype=ChannelType.LONG, doc="Twelve Value"
    )
    two_string = pvproperty(
        name="TWST",
        dtype=ChannelType.CHAR,
        max_length=26,
        report_as_string=True,
        doc="Two String",
    )
    state_two_severity = pvproperty(
        name="TWSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="State Two Severity",
    )
    two_value = pvproperty(name="TWVL", dtype=ChannelType.LONG, doc="Two Value")
    unknown_state_severity = pvproperty(
        name="UNSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Unknown State Severity",
    )
    zero_string = pvproperty(
        name="ZRST",
        dtype=ChannelType.CHAR,
        max_length=26,
        report_as_string=True,
        doc="Zero String",
    )
    state_zero_severity = pvproperty(
        name="ZRSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="State Zero Severity",
    )
    zero_value = pvproperty(
        name="ZRVL", dtype=ChannelType.LONG, doc="Zero Value"
    )
    # current_value = pvproperty(name='VAL',
    #      dtype=ChannelType.ENUM,
    # doc='Current Value')


class MbbidirectFields(RecordFieldGroup):
    _record_type = "mbbiDirect"
    _dtype = ChannelType.LONG  # DTYP of .VAL
    has_val_field = True
    copy_pvproperties(locals(), RecordFieldGroup)
    device_type = pvproperty(
        name="DTYP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.dtyp_mbbiDirect.get_string_tuple(),
        doc="Device Type",
    )
    bit_0 = pvproperty(name="B0", dtype=ChannelType.CHAR, doc="Bit 0")
    bit_1 = pvproperty(name="B1", dtype=ChannelType.CHAR, doc="Bit 1")
    bit_16 = pvproperty(name="B10", dtype=ChannelType.CHAR, doc="Bit 16")
    bit_17 = pvproperty(name="B11", dtype=ChannelType.CHAR, doc="Bit 17")
    bit_18 = pvproperty(name="B12", dtype=ChannelType.CHAR, doc="Bit 18")
    bit_19 = pvproperty(name="B13", dtype=ChannelType.CHAR, doc="Bit 19")
    bit_20 = pvproperty(name="B14", dtype=ChannelType.CHAR, doc="Bit 20")
    bit_21 = pvproperty(name="B15", dtype=ChannelType.CHAR, doc="Bit 21")
    bit_22 = pvproperty(name="B16", dtype=ChannelType.CHAR, doc="Bit 22")
    bit_23 = pvproperty(name="B17", dtype=ChannelType.CHAR, doc="Bit 23")
    bit_24 = pvproperty(name="B18", dtype=ChannelType.CHAR, doc="Bit 24")
    bit_25 = pvproperty(name="B19", dtype=ChannelType.CHAR, doc="Bit 25")
    bit_26 = pvproperty(name="B1A", dtype=ChannelType.CHAR, doc="Bit 26")
    bit_27 = pvproperty(name="B1B", dtype=ChannelType.CHAR, doc="Bit 27")
    bit_28 = pvproperty(name="B1C", dtype=ChannelType.CHAR, doc="Bit 28")
    bit_29 = pvproperty(name="B1D", dtype=ChannelType.CHAR, doc="Bit 29")
    bit_30 = pvproperty(name="B1E", dtype=ChannelType.CHAR, doc="Bit 30")
    bit_31 = pvproperty(name="B1F", dtype=ChannelType.CHAR, doc="Bit 31")
    bit_2 = pvproperty(name="B2", dtype=ChannelType.CHAR, doc="Bit 2")
    bit_3 = pvproperty(name="B3", dtype=ChannelType.CHAR, doc="Bit 3")
    bit_4 = pvproperty(name="B4", dtype=ChannelType.CHAR, doc="Bit 4")
    bit_5 = pvproperty(name="B5", dtype=ChannelType.CHAR, doc="Bit 5")
    bit_6 = pvproperty(name="B6", dtype=ChannelType.CHAR, doc="Bit 6")
    bit_7 = pvproperty(name="B7", dtype=ChannelType.CHAR, doc="Bit 7")
    bit_8 = pvproperty(name="B8", dtype=ChannelType.CHAR, doc="Bit 8")
    bit_9 = pvproperty(name="B9", dtype=ChannelType.CHAR, doc="Bit 9")
    bit_10 = pvproperty(name="BA", dtype=ChannelType.CHAR, doc="Bit 10")
    bit_11 = pvproperty(name="BB", dtype=ChannelType.CHAR, doc="Bit 11")
    bit_12 = pvproperty(name="BC", dtype=ChannelType.CHAR, doc="Bit 12")
    bit_13 = pvproperty(name="BD", dtype=ChannelType.CHAR, doc="Bit 13")
    bit_14 = pvproperty(name="BE", dtype=ChannelType.CHAR, doc="Bit 14")
    bit_15 = pvproperty(name="BF", dtype=ChannelType.CHAR, doc="Bit 15")
    input_specification = pvproperty(
        name="INP", dtype=ChannelType.STRING, doc="Input Specification"
    )
    hardware_mask = pvproperty(
        name="MASK", dtype=ChannelType.LONG, doc="Hardware Mask", read_only=True
    )
    last_value_monitored = pvproperty(
        name="MLST",
        dtype=ChannelType.LONG,
        doc="Last Value Monitored",
        read_only=True,
    )
    number_of_bits = pvproperty(
        name="NOBT", dtype=ChannelType.INT, doc="Number of Bits", read_only=True
    )
    prev_simulation_mode = pvproperty(
        name="OLDSIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuSimm.get_string_tuple(),
        doc="Prev. Simulation Mode",
        read_only=True,
    )
    prev_raw_value = pvproperty(
        name="ORAW",
        dtype=ChannelType.LONG,
        doc="Prev Raw Value",
        read_only=True,
    )
    raw_value = pvproperty(name="RVAL", dtype=ChannelType.LONG, doc="Raw Value")
    sim_mode_async_delay = pvproperty(
        name="SDLY",
        dtype=ChannelType.DOUBLE,
        doc="Sim. Mode Async Delay",
        value=-1.0,
    )
    shift = pvproperty(name="SHFT", dtype=ChannelType.INT, doc="Shift")
    simulation_mode_link = pvproperty(
        name="SIML", dtype=ChannelType.STRING, doc="Simulation Mode Link"
    )
    simulation_mode = pvproperty(
        name="SIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuSimm.get_string_tuple(),
        doc="Simulation Mode",
    )
    simulation_mode_severity = pvproperty(
        name="SIMS",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Simulation Mode Severity",
    )
    simulation_input_link = pvproperty(
        name="SIOL", dtype=ChannelType.STRING, doc="Simulation Input Link"
    )
    sim_mode_scan = pvproperty(
        name="SSCN",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuScan.get_string_tuple(),
        doc="Sim. Mode Scan",
        value=0,
    )
    simulation_value = pvproperty(
        name="SVAL", dtype=ChannelType.LONG, doc="Simulation Value"
    )
    # current_value = pvproperty(name='VAL',
    #      dtype=ChannelType.LONG,
    # doc='Current Value')


class MbboFields(RecordFieldGroup):
    _record_type = "mbbo"
    _dtype = ChannelType.ENUM  # DTYP of .VAL
    has_val_field = True
    copy_pvproperties(locals(), RecordFieldGroup)
    device_type = pvproperty(
        name="DTYP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.dtyp_mbbo.get_string_tuple(),
        doc="Device Type",
    )
    change_of_state_sevr = pvproperty(
        name="COSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Change of State Sevr",
    )
    desired_output_loc = pvproperty(
        name="DOL", dtype=ChannelType.STRING, doc="Desired Output Loc"
    )
    eight_string = pvproperty(
        name="EIST",
        dtype=ChannelType.CHAR,
        max_length=26,
        report_as_string=True,
        doc="Eight String",
    )
    state_eight_severity = pvproperty(
        name="EISV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="State Eight Severity",
    )
    eight_value = pvproperty(
        name="EIVL", dtype=ChannelType.LONG, doc="Eight Value"
    )
    eleven_string = pvproperty(
        name="ELST",
        dtype=ChannelType.CHAR,
        max_length=26,
        report_as_string=True,
        doc="Eleven String",
    )
    state_eleven_severity = pvproperty(
        name="ELSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="State Eleven Severity",
    )
    eleven_value = pvproperty(
        name="ELVL", dtype=ChannelType.LONG, doc="Eleven Value"
    )
    fifteen_string = pvproperty(
        name="FFST",
        dtype=ChannelType.CHAR,
        max_length=26,
        report_as_string=True,
        doc="Fifteen String",
    )
    state_fifteen_sevr = pvproperty(
        name="FFSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="State Fifteen Sevr",
    )
    fifteen_value = pvproperty(
        name="FFVL", dtype=ChannelType.LONG, doc="Fifteen Value"
    )
    four_string = pvproperty(
        name="FRST",
        dtype=ChannelType.CHAR,
        max_length=26,
        report_as_string=True,
        doc="Four String",
    )
    state_four_severity = pvproperty(
        name="FRSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="State Four Severity",
    )
    four_value = pvproperty(
        name="FRVL", dtype=ChannelType.LONG, doc="Four Value"
    )
    fourteen_string = pvproperty(
        name="FTST",
        dtype=ChannelType.CHAR,
        max_length=26,
        report_as_string=True,
        doc="Fourteen String",
    )
    state_fourteen_sevr = pvproperty(
        name="FTSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="State Fourteen Sevr",
    )
    fourteen_value = pvproperty(
        name="FTVL", dtype=ChannelType.LONG, doc="Fourteen Value"
    )
    five_string = pvproperty(
        name="FVST",
        dtype=ChannelType.CHAR,
        max_length=26,
        report_as_string=True,
        doc="Five String",
    )
    state_five_severity = pvproperty(
        name="FVSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="State Five Severity",
    )
    five_value = pvproperty(
        name="FVVL", dtype=ChannelType.LONG, doc="Five Value"
    )
    invalid_outpt_action = pvproperty(
        name="IVOA",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuIvoa.get_string_tuple(),
        doc="INVALID outpt action",
    )
    invalid_output_value = pvproperty(
        name="IVOV", dtype=ChannelType.INT, doc="INVALID output value"
    )
    last_value_alarmed = pvproperty(
        name="LALM",
        dtype=ChannelType.INT,
        doc="Last Value Alarmed",
        read_only=True,
    )
    hardware_mask = pvproperty(
        name="MASK", dtype=ChannelType.LONG, doc="Hardware Mask", read_only=True
    )
    last_value_monitored = pvproperty(
        name="MLST",
        dtype=ChannelType.INT,
        doc="Last Value Monitored",
        read_only=True,
    )
    nine_string = pvproperty(
        name="NIST",
        dtype=ChannelType.CHAR,
        max_length=26,
        report_as_string=True,
        doc="Nine String",
    )
    state_nine_severity = pvproperty(
        name="NISV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="State Nine Severity",
    )
    nine_value = pvproperty(
        name="NIVL", dtype=ChannelType.LONG, doc="Nine Value"
    )
    number_of_bits = pvproperty(
        name="NOBT", dtype=ChannelType.INT, doc="Number of Bits", read_only=True
    )
    prev_simulation_mode = pvproperty(
        name="OLDSIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuSimm.get_string_tuple(),
        doc="Prev. Simulation Mode",
        read_only=True,
    )
    output_mode_select = pvproperty(
        name="OMSL",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuOmsl.get_string_tuple(),
        doc="Output Mode Select",
    )
    one_string = pvproperty(
        name="ONST",
        dtype=ChannelType.CHAR,
        max_length=26,
        report_as_string=True,
        doc="One String",
    )
    state_one_severity = pvproperty(
        name="ONSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="State One Severity",
    )
    one_value = pvproperty(name="ONVL", dtype=ChannelType.LONG, doc="One Value")
    prev_raw_value = pvproperty(
        name="ORAW",
        dtype=ChannelType.LONG,
        doc="Prev Raw Value",
        read_only=True,
    )
    prev_readback_value = pvproperty(
        name="ORBV",
        dtype=ChannelType.LONG,
        doc="Prev Readback Value",
        read_only=True,
    )
    output_specification = pvproperty(
        name="OUT", dtype=ChannelType.STRING, doc="Output Specification"
    )
    readback_value = pvproperty(
        name="RBV", dtype=ChannelType.LONG, doc="Readback Value", read_only=True
    )
    raw_value = pvproperty(name="RVAL", dtype=ChannelType.LONG, doc="Raw Value")
    states_defined = pvproperty(
        name="SDEF", dtype=ChannelType.INT, doc="States Defined", read_only=True
    )
    sim_mode_async_delay = pvproperty(
        name="SDLY",
        dtype=ChannelType.DOUBLE,
        doc="Sim. Mode Async Delay",
        value=-1.0,
    )
    shift = pvproperty(name="SHFT", dtype=ChannelType.INT, doc="Shift")
    simulation_mode_link = pvproperty(
        name="SIML", dtype=ChannelType.STRING, doc="Simulation Mode Link"
    )
    simulation_mode = pvproperty(
        name="SIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuYesNo.get_string_tuple(),
        doc="Simulation Mode",
    )
    simulation_mode_severity = pvproperty(
        name="SIMS",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Simulation Mode Severity",
    )
    simulation_output_link = pvproperty(
        name="SIOL", dtype=ChannelType.STRING, doc="Simulation Output Link"
    )
    sim_mode_scan = pvproperty(
        name="SSCN",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuScan.get_string_tuple(),
        doc="Sim. Mode Scan",
        value=0,
    )
    seven_string = pvproperty(
        name="SVST",
        dtype=ChannelType.CHAR,
        max_length=26,
        report_as_string=True,
        doc="Seven String",
    )
    state_seven_severity = pvproperty(
        name="SVSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="State Seven Severity",
    )
    seven_value = pvproperty(
        name="SVVL", dtype=ChannelType.LONG, doc="Seven Value"
    )
    six_string = pvproperty(
        name="SXST",
        dtype=ChannelType.CHAR,
        max_length=26,
        report_as_string=True,
        doc="Six String",
    )
    state_six_severity = pvproperty(
        name="SXSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="State Six Severity",
    )
    six_value = pvproperty(name="SXVL", dtype=ChannelType.LONG, doc="Six Value")
    ten_string = pvproperty(
        name="TEST",
        dtype=ChannelType.CHAR,
        max_length=26,
        report_as_string=True,
        doc="Ten String",
    )
    state_ten_severity = pvproperty(
        name="TESV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="State Ten Severity",
    )
    ten_value = pvproperty(name="TEVL", dtype=ChannelType.LONG, doc="Ten Value")
    three_string = pvproperty(
        name="THST",
        dtype=ChannelType.CHAR,
        max_length=26,
        report_as_string=True,
        doc="Three String",
    )
    state_three_severity = pvproperty(
        name="THSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="State Three Severity",
    )
    three_value = pvproperty(
        name="THVL", dtype=ChannelType.LONG, doc="Three Value"
    )
    thirteen_string = pvproperty(
        name="TTST",
        dtype=ChannelType.CHAR,
        max_length=26,
        report_as_string=True,
        doc="Thirteen String",
    )
    state_thirteen_sevr = pvproperty(
        name="TTSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="State Thirteen Sevr",
    )
    thirteen_value = pvproperty(
        name="TTVL", dtype=ChannelType.LONG, doc="Thirteen Value"
    )
    twelve_string = pvproperty(
        name="TVST",
        dtype=ChannelType.CHAR,
        max_length=26,
        report_as_string=True,
        doc="Twelve String",
    )
    state_twelve_severity = pvproperty(
        name="TVSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="State Twelve Severity",
    )
    twelve_value = pvproperty(
        name="TVVL", dtype=ChannelType.LONG, doc="Twelve Value"
    )
    two_string = pvproperty(
        name="TWST",
        dtype=ChannelType.CHAR,
        max_length=26,
        report_as_string=True,
        doc="Two String",
    )
    state_two_severity = pvproperty(
        name="TWSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="State Two Severity",
    )
    two_value = pvproperty(name="TWVL", dtype=ChannelType.LONG, doc="Two Value")
    unknown_state_sevr = pvproperty(
        name="UNSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Unknown State Sevr",
    )
    zero_string = pvproperty(
        name="ZRST",
        dtype=ChannelType.CHAR,
        max_length=26,
        report_as_string=True,
        doc="Zero String",
    )
    state_zero_severity = pvproperty(
        name="ZRSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="State Zero Severity",
    )
    zero_value = pvproperty(
        name="ZRVL", dtype=ChannelType.LONG, doc="Zero Value"
    )
    # desired_value = pvproperty(name='VAL',
    #      dtype=ChannelType.ENUM,
    # doc='Desired Value')


class MbbodirectFields(RecordFieldGroup):
    _record_type = "mbboDirect"
    _dtype = ChannelType.LONG  # DTYP of .VAL
    has_val_field = True
    copy_pvproperties(locals(), RecordFieldGroup)
    device_type = pvproperty(
        name="DTYP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.dtyp_mbboDirect.get_string_tuple(),
        doc="Device Type",
    )
    bit_0 = pvproperty(name="B0", dtype=ChannelType.CHAR, doc="Bit 0")
    bit_1 = pvproperty(name="B1", dtype=ChannelType.CHAR, doc="Bit 1")
    bit_16 = pvproperty(name="B10", dtype=ChannelType.CHAR, doc="Bit 16")
    bit_17 = pvproperty(name="B11", dtype=ChannelType.CHAR, doc="Bit 17")
    bit_18 = pvproperty(name="B12", dtype=ChannelType.CHAR, doc="Bit 18")
    bit_19 = pvproperty(name="B13", dtype=ChannelType.CHAR, doc="Bit 19")
    bit_20 = pvproperty(name="B14", dtype=ChannelType.CHAR, doc="Bit 20")
    bit_21 = pvproperty(name="B15", dtype=ChannelType.CHAR, doc="Bit 21")
    bit_22 = pvproperty(name="B16", dtype=ChannelType.CHAR, doc="Bit 22")
    bit_23 = pvproperty(name="B17", dtype=ChannelType.CHAR, doc="Bit 23")
    bit_24 = pvproperty(name="B18", dtype=ChannelType.CHAR, doc="Bit 24")
    bit_25 = pvproperty(name="B19", dtype=ChannelType.CHAR, doc="Bit 25")
    bit_26 = pvproperty(name="B1A", dtype=ChannelType.CHAR, doc="Bit 26")
    bit_27 = pvproperty(name="B1B", dtype=ChannelType.CHAR, doc="Bit 27")
    bit_28 = pvproperty(name="B1C", dtype=ChannelType.CHAR, doc="Bit 28")
    bit_29 = pvproperty(name="B1D", dtype=ChannelType.CHAR, doc="Bit 29")
    bit_30 = pvproperty(name="B1E", dtype=ChannelType.CHAR, doc="Bit 30")
    bit_31 = pvproperty(name="B1F", dtype=ChannelType.CHAR, doc="Bit 31")
    bit_2 = pvproperty(name="B2", dtype=ChannelType.CHAR, doc="Bit 2")
    bit_3 = pvproperty(name="B3", dtype=ChannelType.CHAR, doc="Bit 3")
    bit_4 = pvproperty(name="B4", dtype=ChannelType.CHAR, doc="Bit 4")
    bit_5 = pvproperty(name="B5", dtype=ChannelType.CHAR, doc="Bit 5")
    bit_6 = pvproperty(name="B6", dtype=ChannelType.CHAR, doc="Bit 6")
    bit_7 = pvproperty(name="B7", dtype=ChannelType.CHAR, doc="Bit 7")
    bit_8 = pvproperty(name="B8", dtype=ChannelType.CHAR, doc="Bit 8")
    bit_9 = pvproperty(name="B9", dtype=ChannelType.CHAR, doc="Bit 9")
    bit_10 = pvproperty(name="BA", dtype=ChannelType.CHAR, doc="Bit 10")
    bit_11 = pvproperty(name="BB", dtype=ChannelType.CHAR, doc="Bit 11")
    bit_12 = pvproperty(name="BC", dtype=ChannelType.CHAR, doc="Bit 12")
    bit_13 = pvproperty(name="BD", dtype=ChannelType.CHAR, doc="Bit 13")
    bit_14 = pvproperty(name="BE", dtype=ChannelType.CHAR, doc="Bit 14")
    bit_15 = pvproperty(name="BF", dtype=ChannelType.CHAR, doc="Bit 15")
    desired_output_loc = pvproperty(
        name="DOL", dtype=ChannelType.STRING, doc="Desired Output Loc"
    )
    invalid_outpt_action = pvproperty(
        name="IVOA",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuIvoa.get_string_tuple(),
        doc="INVALID outpt action",
    )
    invalid_output_value = pvproperty(
        name="IVOV", dtype=ChannelType.LONG, doc="INVALID output value"
    )
    hardware_mask = pvproperty(
        name="MASK", dtype=ChannelType.LONG, doc="Hardware Mask", read_only=True
    )
    last_value_monitored = pvproperty(
        name="MLST",
        dtype=ChannelType.LONG,
        doc="Last Value Monitored",
        read_only=True,
    )
    number_of_bits = pvproperty(
        name="NOBT", dtype=ChannelType.INT, doc="Number of Bits", read_only=True
    )
    prev_simulation_mode = pvproperty(
        name="OLDSIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuSimm.get_string_tuple(),
        doc="Prev. Simulation Mode",
        read_only=True,
    )
    output_mode_select = pvproperty(
        name="OMSL",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuOmsl.get_string_tuple(),
        doc="Output Mode Select",
    )
    prev_raw_value = pvproperty(
        name="ORAW",
        dtype=ChannelType.LONG,
        doc="Prev Raw Value",
        read_only=True,
    )
    prev_readback_value = pvproperty(
        name="ORBV",
        dtype=ChannelType.LONG,
        doc="Prev Readback Value",
        read_only=True,
    )
    output_specification = pvproperty(
        name="OUT", dtype=ChannelType.STRING, doc="Output Specification"
    )
    readback_value = pvproperty(
        name="RBV", dtype=ChannelType.LONG, doc="Readback Value", read_only=True
    )
    raw_value = pvproperty(
        name="RVAL", dtype=ChannelType.LONG, doc="Raw Value", read_only=True
    )
    sim_mode_async_delay = pvproperty(
        name="SDLY",
        dtype=ChannelType.DOUBLE,
        doc="Sim. Mode Async Delay",
        value=-1.0,
    )
    shift = pvproperty(name="SHFT", dtype=ChannelType.INT, doc="Shift")
    simulation_mode_link = pvproperty(
        name="SIML", dtype=ChannelType.STRING, doc="Simulation Mode Link"
    )
    simulation_mode = pvproperty(
        name="SIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuYesNo.get_string_tuple(),
        doc="Simulation Mode",
    )
    simulation_mode_severity = pvproperty(
        name="SIMS",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Simulation Mode Severity",
    )
    simulation_output_link = pvproperty(
        name="SIOL", dtype=ChannelType.STRING, doc="Simulation Output Link"
    )
    sim_mode_scan = pvproperty(
        name="SSCN",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuScan.get_string_tuple(),
        doc="Sim. Mode Scan",
        value=0,
    )
    # word = pvproperty(name='VAL',
    #      dtype=ChannelType.LONG,
    # doc='Word')


class MotorFields(RecordFieldGroup, _Limits):
    _record_type = "motor"
    _dtype = ChannelType.DOUBLE  # DTYP of .VAL
    has_val_field = True
    copy_pvproperties(locals(), RecordFieldGroup, _Limits)
    device_type = pvproperty(
        name="DTYP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.dtyp_motor.get_string_tuple(),
        doc="Device Type",
    )
    seconds_to_velocity = pvproperty(
        name="ACCL",
        dtype=ChannelType.DOUBLE,
        doc="Seconds to Velocity",
        value=0.2,
    )
    archive_deadband = pvproperty(
        name="ADEL", dtype=ChannelType.DOUBLE, doc="Archive Deadband"
    )
    last_value_archived = pvproperty(
        name="ALST",
        dtype=ChannelType.DOUBLE,
        doc="Last Value Archived",
        read_only=True,
    )
    at_home = pvproperty(
        name="ATHM", dtype=ChannelType.INT, doc="At HOME", read_only=True
    )
    bl_seconds_to_velocity = pvproperty(
        name="BACC",
        dtype=ChannelType.DOUBLE,
        doc="BL Seconds to Velocity",
        value=0.5,
    )
    bl_distance = pvproperty(
        name="BDST", dtype=ChannelType.DOUBLE, doc="BL Distance (EGU)"
    )
    bl_velocity = pvproperty(
        name="BVEL", dtype=ChannelType.DOUBLE, doc="BL Velocity (EGU/s)"
    )
    card_number = pvproperty(
        name="CARD", dtype=ChannelType.INT, doc="Card Number", read_only=True
    )
    raw_cmnd_direction = pvproperty(
        name="CDIR",
        dtype=ChannelType.INT,
        doc="Raw cmnd direction",
        read_only=True,
    )
    enable_control = pvproperty(
        name="CNEN",
        dtype=ChannelType.ENUM,
        enum_strings=menus.motorTORQ.get_string_tuple(),
        doc="Enable control",
    )
    derivative_gain = pvproperty(
        name="DCOF", dtype=ChannelType.DOUBLE, doc="Derivative Gain", value=0
    )
    dial_high_limit = pvproperty(
        name="DHLM", dtype=ChannelType.DOUBLE, doc="Dial High Limit"
    )
    difference_dval_drbv = pvproperty(
        name="DIFF",
        dtype=ChannelType.DOUBLE,
        doc="Difference dval-drbv",
        read_only=True,
    )
    dmov_input_link = pvproperty(
        name="DINP", dtype=ChannelType.STRING, doc="DMOV Input Link"
    )
    user_direction = pvproperty(
        name="DIR",
        dtype=ChannelType.ENUM,
        enum_strings=menus.motorDIR.get_string_tuple(),
        doc="User Direction",
    )
    dial_low_limit = pvproperty(
        name="DLLM", dtype=ChannelType.DOUBLE, doc="Dial Low Limit"
    )
    readback_settle_time = pvproperty(
        name="DLY", dtype=ChannelType.DOUBLE, doc="Readback settle time (s)"
    )
    done_moving_to_value = pvproperty(
        name="DMOV",
        dtype=ChannelType.INT,
        doc="Done moving to value",
        read_only=True,
        value=1,
    )
    desired_output_loc = pvproperty(
        name="DOL", dtype=ChannelType.STRING, doc="Desired Output Loc"
    )
    dial_readback_value = pvproperty(
        name="DRBV",
        dtype=ChannelType.DOUBLE,
        doc="Dial Readback Value",
        read_only=True,
    )
    dial_desired_value = pvproperty(
        name="DVAL", dtype=ChannelType.DOUBLE, doc="Dial Desired Value (EGU"
    )
    engineering_units = pvproperty(
        name="EGU",
        dtype=ChannelType.CHAR,
        max_length=16,
        report_as_string=True,
        doc="Engineering Units",
    )
    encoder_step_size = pvproperty(
        name="ERES", dtype=ChannelType.DOUBLE, doc="Encoder Step Size (EGU)"
    )
    freeze_offset = pvproperty(
        name="FOF", dtype=ChannelType.INT, doc="Freeze Offset"
    )
    offset_freeze_switch = pvproperty(
        name="FOFF",
        dtype=ChannelType.ENUM,
        enum_strings=menus.motorFOFF.get_string_tuple(),
        doc="Offset-Freeze Switch",
    )
    move_fraction = pvproperty(
        name="FRAC", dtype=ChannelType.FLOAT, doc="Move Fraction", value=1
    )
    user_high_limit = pvproperty(
        name="HLM", dtype=ChannelType.DOUBLE, doc="User High Limit"
    )
    user_high_limit_switch = pvproperty(
        name="HLS",
        dtype=ChannelType.INT,
        doc="User High Limit Switch",
        read_only=True,
    )
    hw_limit_violation_svr = pvproperty(
        name="HLSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="HW Limit Violation Svr",
    )
    home_forward = pvproperty(
        name="HOMF", dtype=ChannelType.INT, doc="Home Forward"
    )
    home_reverse = pvproperty(
        name="HOMR", dtype=ChannelType.INT, doc="Home Reverse"
    )
    home_velocity = pvproperty(
        name="HVEL", dtype=ChannelType.DOUBLE, doc="Home Velocity (EGU/s)"
    )
    integral_gain = pvproperty(
        name="ICOF", dtype=ChannelType.DOUBLE, doc="Integral Gain", value=0
    )
    ignore_set_field = pvproperty(
        name="IGSET", dtype=ChannelType.INT, doc="Ignore SET field"
    )
    startup_commands = pvproperty(
        name="INIT",
        dtype=ChannelType.CHAR,
        max_length=40,
        report_as_string=True,
        doc="Startup commands",
    )
    jog_accel = pvproperty(
        name="JAR", dtype=ChannelType.DOUBLE, doc="Jog Accel. (EGU/s^2)"
    )
    jog_motor_forward = pvproperty(
        name="JOGF", dtype=ChannelType.INT, doc="Jog motor Forward"
    )
    jog_motor_reverse = pvproperty(
        name="JOGR", dtype=ChannelType.INT, doc="Jog motor Reverse"
    )
    jog_velocity = pvproperty(
        name="JVEL", dtype=ChannelType.DOUBLE, doc="Jog Velocity (EGU/s)"
    )
    last_dial_des_val = pvproperty(
        name="LDVL",
        dtype=ChannelType.DOUBLE,
        doc="Last Dial Des Val (EGU)",
        read_only=True,
    )
    user_low_limit = pvproperty(
        name="LLM", dtype=ChannelType.DOUBLE, doc="User Low Limit"
    )
    user_low_limit_switch = pvproperty(
        name="LLS",
        dtype=ChannelType.INT,
        doc="User Low Limit Switch",
        read_only=True,
    )
    soft_channel_position_lock = pvproperty(
        name="LOCK",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuYesNo.get_string_tuple(),
        doc="Soft Channel Position Lock",
        value="NO",
    )
    last_rel_value = pvproperty(
        name="LRLV",
        dtype=ChannelType.DOUBLE,
        doc="Last Rel Value (EGU)",
        read_only=True,
    )
    last_raw_des_val = pvproperty(
        name="LRVL",
        dtype=ChannelType.LONG,
        doc="Last Raw Des Val (steps",
        read_only=True,
    )
    last_spmg = pvproperty(
        name="LSPG",
        dtype=ChannelType.ENUM,
        enum_strings=menus.motorSPMG.get_string_tuple(),
        doc="Last SPMG",
        read_only=True,
        value=3,
    )
    last_user_des_val = pvproperty(
        name="LVAL",
        dtype=ChannelType.DOUBLE,
        doc="Last User Des Val (EGU)",
        read_only=True,
    )
    limit_violation = pvproperty(
        name="LVIO",
        dtype=ChannelType.INT,
        doc="Limit violation",
        read_only=True,
        value=1,
    )
    monitor_deadband = pvproperty(
        name="MDEL", dtype=ChannelType.DOUBLE, doc="Monitor Deadband"
    )
    motion_in_progress = pvproperty(
        name="MIP",
        dtype=ChannelType.INT,
        doc="Motion In Progress",
        read_only=True,
    )
    ran_out_of_retries = pvproperty(
        name="MISS",
        dtype=ChannelType.INT,
        doc="Ran out of retries",
        read_only=True,
    )
    last_val_monitored = pvproperty(
        name="MLST",
        dtype=ChannelType.DOUBLE,
        doc="Last Val Monitored",
        read_only=True,
    )
    monitor_mask = pvproperty(
        name="MMAP", dtype=ChannelType.LONG, doc="Monitor Mask", read_only=True
    )
    motor_is_moving = pvproperty(
        name="MOVN",
        dtype=ChannelType.INT,
        doc="Motor is moving",
        read_only=True,
    )
    motor_step_size = pvproperty(
        name="MRES", dtype=ChannelType.DOUBLE, doc="Motor Step Size (EGU)"
    )
    motor_status = pvproperty(
        name="MSTA", dtype=ChannelType.LONG, doc="Motor Status", read_only=True
    )
    monitor_mask_more = pvproperty(
        name="NMAP",
        dtype=ChannelType.LONG,
        doc="Monitor Mask (more)",
        read_only=True,
    )
    new_target_monitor = pvproperty(
        name="NTM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuYesNo.get_string_tuple(),
        doc="New Target Monitor",
        value="YES",
    )
    ntm_deadband_factor = pvproperty(
        name="NTMF", dtype=ChannelType.INT, doc="NTM Deadband Factor", value=2
    )
    user_offset = pvproperty(
        name="OFF", dtype=ChannelType.DOUBLE, doc="User Offset (EGU)"
    )
    output_mode_select = pvproperty(
        name="OMSL",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuOmsl.get_string_tuple(),
        doc="Output Mode Select",
    )
    output_specification = pvproperty(
        name="OUT", dtype=ChannelType.STRING, doc="Output Specification"
    )
    proportional_gain = pvproperty(
        name="PCOF", dtype=ChannelType.DOUBLE, doc="Proportional Gain", value=0
    )
    post_move_commands = pvproperty(
        name="POST",
        dtype=ChannelType.CHAR,
        max_length=40,
        report_as_string=True,
        doc="Post-move commands",
    )
    post_process_command = pvproperty(
        name="PP",
        dtype=ChannelType.INT,
        doc="Post process command",
        read_only=True,
        value=0,
    )
    display_precision = pvproperty(
        name="PREC", dtype=ChannelType.INT, doc="Display Precision"
    )
    pre_move_commands = pvproperty(
        name="PREM",
        dtype=ChannelType.CHAR,
        max_length=40,
        report_as_string=True,
        doc="Pre-move commands",
    )
    user_readback_value = pvproperty(
        name="RBV",
        dtype=ChannelType.DOUBLE,
        doc="User Readback Value",
        read_only=True,
    )
    retry_count = pvproperty(
        name="RCNT", dtype=ChannelType.INT, doc="Retry count", read_only=True
    )
    retry_deadband = pvproperty(
        name="RDBD", dtype=ChannelType.DOUBLE, doc="Retry Deadband (EGU)"
    )
    readback_location = pvproperty(
        name="RDBL", dtype=ChannelType.STRING, doc="Readback Location"
    )
    difference_rval_rrbv = pvproperty(
        name="RDIF",
        dtype=ChannelType.LONG,
        doc="Difference rval-rrbv",
        read_only=True,
    )
    raw_encoder_position = pvproperty(
        name="REP",
        dtype=ChannelType.LONG,
        doc="Raw Encoder Position",
        read_only=True,
    )
    raw_high_limit_switch = pvproperty(
        name="RHLS",
        dtype=ChannelType.INT,
        doc="Raw High Limit Switch",
        read_only=True,
    )
    rmp_input_link = pvproperty(
        name="RINP", dtype=ChannelType.STRING, doc="RMP Input Link"
    )
    raw_low_limit_switch = pvproperty(
        name="RLLS",
        dtype=ChannelType.INT,
        doc="Raw Low Limit Switch",
        read_only=True,
    )
    readback_outlink = pvproperty(
        name="RLNK", dtype=ChannelType.STRING, doc="Readback OutLink"
    )
    relative_value = pvproperty(
        name="RLV", dtype=ChannelType.DOUBLE, doc="Relative Value (EGU)"
    )
    retry_mode = pvproperty(
        name="RMOD",
        dtype=ChannelType.ENUM,
        enum_strings=menus.motorRMOD.get_string_tuple(),
        doc="Retry Mode",
        value="Default",
    )
    raw_motor_position = pvproperty(
        name="RMP",
        dtype=ChannelType.LONG,
        doc="Raw Motor Position",
        read_only=True,
    )
    raw_readback_value = pvproperty(
        name="RRBV",
        dtype=ChannelType.LONG,
        doc="Raw Readback Value",
        read_only=True,
    )
    readback_step_size = pvproperty(
        name="RRES", dtype=ChannelType.DOUBLE, doc="Readback Step Size (EGU"
    )
    max_retry_count = pvproperty(
        name="RTRY", dtype=ChannelType.INT, doc="Max retry count", value=10
    )
    raw_desired_value = pvproperty(
        name="RVAL", dtype=ChannelType.LONG, doc="Raw Desired Value (step"
    )
    raw_velocity = pvproperty(
        name="RVEL", dtype=ChannelType.LONG, doc="Raw Velocity", read_only=True
    )
    speed = pvproperty(
        name="S", dtype=ChannelType.DOUBLE, doc="Speed (revolutions/sec)"
    )
    bl_speed = pvproperty(
        name="SBAK", dtype=ChannelType.DOUBLE, doc="BL Speed (RPS)"
    )
    base_speed = pvproperty(
        name="SBAS", dtype=ChannelType.DOUBLE, doc="Base Speed (RPS)"
    )
    set_use_switch = pvproperty(
        name="SET",
        dtype=ChannelType.ENUM,
        enum_strings=menus.motorSET.get_string_tuple(),
        doc="Set/Use Switch",
    )
    max_speed = pvproperty(
        name="SMAX", dtype=ChannelType.DOUBLE, doc="Max. Speed (RPS)"
    )
    setpoint_deadband = pvproperty(
        name="SPDB", dtype=ChannelType.DOUBLE, doc="Setpoint Deadband (EGU)"
    )
    stop_pause_move_go = pvproperty(
        name="SPMG",
        dtype=ChannelType.ENUM,
        enum_strings=menus.motorSPMG.get_string_tuple(),
        doc="Stop/Pause/Move/Go",
        value=3,
    )
    steps_per_revolution = pvproperty(
        name="SREV",
        dtype=ChannelType.LONG,
        doc="Steps per Revolution",
        value=200,
    )
    set_set_mode = pvproperty(
        name="SSET", dtype=ChannelType.INT, doc="Set SET Mode"
    )
    stop_outlink = pvproperty(
        name="STOO", dtype=ChannelType.STRING, doc="STOP OutLink"
    )
    stop = pvproperty(name="STOP", dtype=ChannelType.INT, doc="Stop")
    status_update = pvproperty(
        name="STUP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.motorSTUP.get_string_tuple(),
        doc="Status Update",
        value="OFF",
    )
    set_use_mode = pvproperty(
        name="SUSE", dtype=ChannelType.INT, doc="Set USE Mode"
    )
    sync_position = pvproperty(
        name="SYNC", dtype=ChannelType.INT, doc="Sync position"
    )
    direction_of_travel = pvproperty(
        name="TDIR",
        dtype=ChannelType.INT,
        doc="Direction of Travel",
        read_only=True,
    )
    tweak_motor_forward = pvproperty(
        name="TWF", dtype=ChannelType.INT, doc="Tweak motor Forward"
    )
    tweak_motor_reverse = pvproperty(
        name="TWR", dtype=ChannelType.INT, doc="Tweak motor Reverse"
    )
    tweak_step_size = pvproperty(
        name="TWV", dtype=ChannelType.DOUBLE, doc="Tweak Step Size (EGU)"
    )
    use_encoder_if_present = pvproperty(
        name="UEIP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.motorUEIP.get_string_tuple(),
        doc="Use Encoder If Present",
    )
    egu_s_per_revolution = pvproperty(
        name="UREV", dtype=ChannelType.DOUBLE, doc="EGU's per Revolution"
    )
    use_rdbl_link_if_presen = pvproperty(
        name="URIP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.motorUEIP.get_string_tuple(),
        doc="Use RDBL Link If Presen",
    )
    base_velocity = pvproperty(
        name="VBAS", dtype=ChannelType.DOUBLE, doc="Base Velocity (EGU/s)"
    )
    velocity = pvproperty(
        name="VELO", dtype=ChannelType.DOUBLE, doc="Velocity (EGU/s)"
    )
    code_version = pvproperty(
        name="VERS",
        dtype=ChannelType.FLOAT,
        doc="Code Version",
        read_only=True,
        value=1,
    )
    max_velocity = pvproperty(
        name="VMAX", dtype=ChannelType.DOUBLE, doc="Max. Velocity (EGU/s)"
    )
    variable_offset = pvproperty(
        name="VOF", dtype=ChannelType.INT, doc="Variable Offset"
    )
    # user_desired_value = pvproperty(name='VAL',
    #      dtype=ChannelType.DOUBLE,
    # doc='User Desired Value (EGU')
    link_parent_attribute(
        display_precision, "precision",
    )
    link_parent_attribute(archive_deadband, "log_atol", use_setattr=True)
    link_parent_attribute(monitor_deadband, "value_atol", use_setattr=True)


class PermissiveFields(RecordFieldGroup):
    _record_type = "permissive"
    _dtype = ChannelType.LONG  # DTYP of .VAL
    has_val_field = True
    copy_pvproperties(locals(), RecordFieldGroup)
    device_type = pvproperty(
        name="DTYP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.dtyp_permissive.get_string_tuple(),
        doc="Device Type",
    )
    button_label = pvproperty(
        name="LABL",
        dtype=ChannelType.CHAR,
        max_length=20,
        report_as_string=True,
        doc="Button Label",
    )
    old_flag = pvproperty(
        name="OFLG", dtype=ChannelType.INT, doc="Old Flag", read_only=True
    )
    old_status = pvproperty(
        name="OVAL", dtype=ChannelType.INT, doc="Old Status", read_only=True
    )
    wait_flag = pvproperty(name="WFLG", dtype=ChannelType.INT, doc="Wait Flag")
    # status = pvproperty(name='VAL',
    #      dtype=ChannelType.INT,
    # doc='Status')


class PrintfFields(RecordFieldGroup):
    _record_type = "printf"
    _dtype = None  # DTYP of .VAL
    has_val_field = False
    copy_pvproperties(locals(), RecordFieldGroup)
    device_type = pvproperty(
        name="DTYP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.dtyp_printf.get_string_tuple(),
        doc="Device Type",
    )
    format_string = pvproperty(
        name="FMT",
        dtype=ChannelType.CHAR,
        max_length=81,
        report_as_string=True,
        doc="Format String",
    )
    input_0 = pvproperty(name="INP0", dtype=ChannelType.STRING, doc="Input 0")
    input_1 = pvproperty(name="INP1", dtype=ChannelType.STRING, doc="Input 1")
    input_2 = pvproperty(name="INP2", dtype=ChannelType.STRING, doc="Input 2")
    input_3 = pvproperty(name="INP3", dtype=ChannelType.STRING, doc="Input 3")
    input_4 = pvproperty(name="INP4", dtype=ChannelType.STRING, doc="Input 4")
    input_5 = pvproperty(name="INP5", dtype=ChannelType.STRING, doc="Input 5")
    input_6 = pvproperty(name="INP6", dtype=ChannelType.STRING, doc="Input 6")
    input_7 = pvproperty(name="INP7", dtype=ChannelType.STRING, doc="Input 7")
    input_8 = pvproperty(name="INP8", dtype=ChannelType.STRING, doc="Input 8")
    input_9 = pvproperty(name="INP9", dtype=ChannelType.STRING, doc="Input 9")
    invalid_link_string = pvproperty(
        name="IVLS",
        dtype=ChannelType.CHAR,
        max_length=16,
        report_as_string=True,
        doc="Invalid Link String",
        value="LNK",
    )
    length_of_val = pvproperty(
        name="LEN", dtype=ChannelType.LONG, doc="Length of VAL", read_only=True
    )
    output_specification = pvproperty(
        name="OUT", dtype=ChannelType.STRING, doc="Output Specification"
    )
    size_of_val_buffer = pvproperty(
        name="SIZV",
        dtype=ChannelType.INT,
        doc="Size of VAL buffer",
        read_only=True,
        value=41,
    )


class SelFields(RecordFieldGroup, _Limits):
    _record_type = "sel"
    _dtype = ChannelType.DOUBLE  # DTYP of .VAL
    has_val_field = True
    copy_pvproperties(locals(), RecordFieldGroup, _Limits)
    device_type = pvproperty(
        name="DTYP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.dtyp_sel.get_string_tuple(),
        doc="Device Type",
    )
    value_of_input_a = pvproperty(
        name="A", dtype=ChannelType.DOUBLE, doc="Value of Input A"
    )
    archive_deadband = pvproperty(
        name="ADEL", dtype=ChannelType.DOUBLE, doc="Archive Deadband"
    )
    last_value_archived = pvproperty(
        name="ALST",
        dtype=ChannelType.DOUBLE,
        doc="Last Value Archived",
        read_only=True,
    )
    value_of_input_b = pvproperty(
        name="B", dtype=ChannelType.DOUBLE, doc="Value of Input B"
    )
    value_of_input_c = pvproperty(
        name="C", dtype=ChannelType.DOUBLE, doc="Value of Input C"
    )
    value_of_input_d = pvproperty(
        name="D", dtype=ChannelType.DOUBLE, doc="Value of Input D"
    )
    value_of_input_e = pvproperty(
        name="E", dtype=ChannelType.DOUBLE, doc="Value of Input E"
    )
    engineering_units = pvproperty(
        name="EGU",
        dtype=ChannelType.CHAR,
        max_length=16,
        report_as_string=True,
        doc="Engineering Units",
    )
    value_of_input_f = pvproperty(
        name="F", dtype=ChannelType.DOUBLE, doc="Value of Input F"
    )
    value_of_input_g = pvproperty(
        name="G", dtype=ChannelType.DOUBLE, doc="Value of Input G"
    )
    value_of_input_h = pvproperty(
        name="H", dtype=ChannelType.DOUBLE, doc="Value of Input H"
    )
    alarm_deadband = pvproperty(
        name="HYST", dtype=ChannelType.DOUBLE, doc="Alarm Deadband"
    )
    value_of_input_i = pvproperty(
        name="I", dtype=ChannelType.DOUBLE, doc="Value of Input I"
    )
    input_a = pvproperty(name="INPA", dtype=ChannelType.STRING, doc="Input A")
    input_b = pvproperty(name="INPB", dtype=ChannelType.STRING, doc="Input B")
    input_c = pvproperty(name="INPC", dtype=ChannelType.STRING, doc="Input C")
    input_d = pvproperty(name="INPD", dtype=ChannelType.STRING, doc="Input D")
    input_e = pvproperty(name="INPE", dtype=ChannelType.STRING, doc="Input E")
    input_f = pvproperty(name="INPF", dtype=ChannelType.STRING, doc="Input F")
    input_g = pvproperty(name="INPG", dtype=ChannelType.STRING, doc="Input G")
    input_h = pvproperty(name="INPH", dtype=ChannelType.STRING, doc="Input H")
    input_i = pvproperty(name="INPI", dtype=ChannelType.STRING, doc="Input I")
    input_j = pvproperty(name="INPJ", dtype=ChannelType.STRING, doc="Input J")
    input_k = pvproperty(name="INPK", dtype=ChannelType.STRING, doc="Input K")
    input_l = pvproperty(name="INPL", dtype=ChannelType.STRING, doc="Input L")
    value_of_input_j = pvproperty(
        name="J", dtype=ChannelType.DOUBLE, doc="Value of Input J"
    )
    value_of_input_k = pvproperty(
        name="K", dtype=ChannelType.DOUBLE, doc="Value of Input K"
    )
    value_of_input_l = pvproperty(
        name="L", dtype=ChannelType.DOUBLE, doc="Value of Input L"
    )
    prev_value_of_a = pvproperty(
        name="LA",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of A",
        read_only=True,
    )
    last_value_alarmed = pvproperty(
        name="LALM",
        dtype=ChannelType.DOUBLE,
        doc="Last Value Alarmed",
        read_only=True,
    )
    prev_value_of_b = pvproperty(
        name="LB",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of B",
        read_only=True,
    )
    prev_value_of_c = pvproperty(
        name="LC",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of C",
        read_only=True,
    )
    prev_value_of_d = pvproperty(
        name="LD",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of D",
        read_only=True,
    )
    prev_value_of_e = pvproperty(
        name="LE",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of E",
        read_only=True,
    )
    prev_value_of_f = pvproperty(
        name="LF",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of F",
        read_only=True,
    )
    prev_value_of_g = pvproperty(
        name="LG",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of G",
        read_only=True,
    )
    prev_value_of_h = pvproperty(
        name="LH",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of H",
        read_only=True,
    )
    prev_value_of_i = pvproperty(
        name="LI",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of I",
        read_only=True,
    )
    prev_value_of_j = pvproperty(
        name="LJ",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of J",
        read_only=True,
    )
    prev_value_of_k = pvproperty(
        name="LK",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of K",
        read_only=True,
    )
    prev_value_of_l = pvproperty(
        name="LL",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of L",
        read_only=True,
    )
    monitor_deadband = pvproperty(
        name="MDEL", dtype=ChannelType.DOUBLE, doc="Monitor Deadband"
    )
    last_val_monitored = pvproperty(
        name="MLST",
        dtype=ChannelType.DOUBLE,
        doc="Last Val Monitored",
        read_only=True,
    )
    last_index_monitored = pvproperty(
        name="NLST",
        dtype=ChannelType.INT,
        doc="Last Index Monitored",
        read_only=True,
    )
    index_value_location = pvproperty(
        name="NVL", dtype=ChannelType.STRING, doc="Index Value Location"
    )
    display_precision = pvproperty(
        name="PREC", dtype=ChannelType.INT, doc="Display Precision"
    )
    select_mechanism = pvproperty(
        name="SELM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.selSELM.get_string_tuple(),
        doc="Select Mechanism",
    )
    index_value = pvproperty(
        name="SELN", dtype=ChannelType.INT, doc="Index value"
    )
    # result = pvproperty(name='VAL',
    #      dtype=ChannelType.DOUBLE,
    # doc='Result',read_only=True)
    link_parent_attribute(
        display_precision, "precision",
    )
    link_parent_attribute(archive_deadband, "log_atol", use_setattr=True)
    link_parent_attribute(monitor_deadband, "value_atol", use_setattr=True)


class SeqFields(RecordFieldGroup):
    _record_type = "seq"
    _dtype = ChannelType.LONG  # DTYP of .VAL
    has_val_field = True
    copy_pvproperties(locals(), RecordFieldGroup)
    device_type = pvproperty(
        name="DTYP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.dtyp_seq.get_string_tuple(),
        doc="Device Type",
    )
    delay_0 = pvproperty(name="DLY0", dtype=ChannelType.DOUBLE, doc="Delay 0")
    delay_1 = pvproperty(name="DLY1", dtype=ChannelType.DOUBLE, doc="Delay 1")
    delay_2 = pvproperty(name="DLY2", dtype=ChannelType.DOUBLE, doc="Delay 2")
    delay_3 = pvproperty(name="DLY3", dtype=ChannelType.DOUBLE, doc="Delay 3")
    delay_4 = pvproperty(name="DLY4", dtype=ChannelType.DOUBLE, doc="Delay 4")
    delay_5 = pvproperty(name="DLY5", dtype=ChannelType.DOUBLE, doc="Delay 5")
    delay_6 = pvproperty(name="DLY6", dtype=ChannelType.DOUBLE, doc="Delay 6")
    delay_7 = pvproperty(name="DLY7", dtype=ChannelType.DOUBLE, doc="Delay 7")
    delay_8 = pvproperty(name="DLY8", dtype=ChannelType.DOUBLE, doc="Delay 8")
    delay_9 = pvproperty(name="DLY9", dtype=ChannelType.DOUBLE, doc="Delay 9")
    delay_10 = pvproperty(name="DLYA", dtype=ChannelType.DOUBLE, doc="Delay 10")
    delay_11 = pvproperty(name="DLYB", dtype=ChannelType.DOUBLE, doc="Delay 11")
    delay_12 = pvproperty(name="DLYC", dtype=ChannelType.DOUBLE, doc="Delay 12")
    delay_13 = pvproperty(name="DLYD", dtype=ChannelType.DOUBLE, doc="Delay 13")
    delay_14 = pvproperty(name="DLYE", dtype=ChannelType.DOUBLE, doc="Delay 14")
    delay_15 = pvproperty(name="DLYF", dtype=ChannelType.DOUBLE, doc="Delay 15")
    value_0 = pvproperty(name="DO0", dtype=ChannelType.DOUBLE, doc="Value 0")
    value_1 = pvproperty(name="DO1", dtype=ChannelType.DOUBLE, doc="Value 1")
    value_2 = pvproperty(name="DO2", dtype=ChannelType.DOUBLE, doc="Value 2")
    value_3 = pvproperty(name="DO3", dtype=ChannelType.DOUBLE, doc="Value 3")
    value_4 = pvproperty(name="DO4", dtype=ChannelType.DOUBLE, doc="Value 4")
    value_5 = pvproperty(name="DO5", dtype=ChannelType.DOUBLE, doc="Value 5")
    value_6 = pvproperty(name="DO6", dtype=ChannelType.DOUBLE, doc="Value 6")
    value_7 = pvproperty(name="DO7", dtype=ChannelType.DOUBLE, doc="Value 7")
    value_8 = pvproperty(name="DO8", dtype=ChannelType.DOUBLE, doc="Value 8")
    value_9 = pvproperty(name="DO9", dtype=ChannelType.DOUBLE, doc="Value 9")
    value_10 = pvproperty(name="DOA", dtype=ChannelType.DOUBLE, doc="Value 10")
    value_11 = pvproperty(name="DOB", dtype=ChannelType.DOUBLE, doc="Value 11")
    value_12 = pvproperty(name="DOC", dtype=ChannelType.DOUBLE, doc="Value 12")
    value_13 = pvproperty(name="DOD", dtype=ChannelType.DOUBLE, doc="Value 13")
    value_14 = pvproperty(name="DOE", dtype=ChannelType.DOUBLE, doc="Value 14")
    value_15 = pvproperty(name="DOF", dtype=ChannelType.DOUBLE, doc="Value 15")
    input_link_0 = pvproperty(
        name="DOL0", dtype=ChannelType.STRING, doc="Input link 0"
    )
    input_link1 = pvproperty(
        name="DOL1", dtype=ChannelType.STRING, doc="Input link1"
    )
    input_link_2 = pvproperty(
        name="DOL2", dtype=ChannelType.STRING, doc="Input link 2"
    )
    input_link_3 = pvproperty(
        name="DOL3", dtype=ChannelType.STRING, doc="Input link 3"
    )
    input_link_4 = pvproperty(
        name="DOL4", dtype=ChannelType.STRING, doc="Input link 4"
    )
    input_link_5 = pvproperty(
        name="DOL5", dtype=ChannelType.STRING, doc="Input link 5"
    )
    input_link_6 = pvproperty(
        name="DOL6", dtype=ChannelType.STRING, doc="Input link 6"
    )
    input_link_7 = pvproperty(
        name="DOL7", dtype=ChannelType.STRING, doc="Input link 7"
    )
    input_link_8 = pvproperty(
        name="DOL8", dtype=ChannelType.STRING, doc="Input link 8"
    )
    input_link_9 = pvproperty(
        name="DOL9", dtype=ChannelType.STRING, doc="Input link 9"
    )
    input_link_10 = pvproperty(
        name="DOLA", dtype=ChannelType.STRING, doc="Input link 10"
    )
    input_link_11 = pvproperty(
        name="DOLB", dtype=ChannelType.STRING, doc="Input link 11"
    )
    input_link_12 = pvproperty(
        name="DOLC", dtype=ChannelType.STRING, doc="Input link 12"
    )
    input_link_13 = pvproperty(
        name="DOLD", dtype=ChannelType.STRING, doc="Input link 13"
    )
    input_link_14 = pvproperty(
        name="DOLE", dtype=ChannelType.STRING, doc="Input link 14"
    )
    input_link_15 = pvproperty(
        name="DOLF", dtype=ChannelType.STRING, doc="Input link 15"
    )
    output_link_0 = pvproperty(
        name="LNK0", dtype=ChannelType.STRING, doc="Output Link 0"
    )
    output_link_1 = pvproperty(
        name="LNK1", dtype=ChannelType.STRING, doc="Output Link 1"
    )
    output_link_2 = pvproperty(
        name="LNK2", dtype=ChannelType.STRING, doc="Output Link 2"
    )
    output_link_3 = pvproperty(
        name="LNK3", dtype=ChannelType.STRING, doc="Output Link 3"
    )
    output_link_4 = pvproperty(
        name="LNK4", dtype=ChannelType.STRING, doc="Output Link 4"
    )
    output_link_5 = pvproperty(
        name="LNK5", dtype=ChannelType.STRING, doc="Output Link 5"
    )
    output_link_6 = pvproperty(
        name="LNK6", dtype=ChannelType.STRING, doc="Output Link 6"
    )
    output_link_7 = pvproperty(
        name="LNK7", dtype=ChannelType.STRING, doc="Output Link 7"
    )
    output_link_8 = pvproperty(
        name="LNK8", dtype=ChannelType.STRING, doc="Output Link 8"
    )
    output_link_9 = pvproperty(
        name="LNK9", dtype=ChannelType.STRING, doc="Output Link 9"
    )
    output_link_10 = pvproperty(
        name="LNKA", dtype=ChannelType.STRING, doc="Output Link 10"
    )
    output_link_11 = pvproperty(
        name="LNKB", dtype=ChannelType.STRING, doc="Output Link 11"
    )
    output_link_12 = pvproperty(
        name="LNKC", dtype=ChannelType.STRING, doc="Output Link 12"
    )
    output_link_13 = pvproperty(
        name="LNKD", dtype=ChannelType.STRING, doc="Output Link 13"
    )
    output_link_14 = pvproperty(
        name="LNKE", dtype=ChannelType.STRING, doc="Output Link 14"
    )
    output_link_15 = pvproperty(
        name="LNKF", dtype=ChannelType.STRING, doc="Output Link 15"
    )
    offset_for_specified = pvproperty(
        name="OFFS", dtype=ChannelType.INT, doc="Offset for Specified", value=0
    )
    old_selection = pvproperty(
        name="OLDN", dtype=ChannelType.INT, doc="Old Selection"
    )
    display_precision = pvproperty(
        name="PREC", dtype=ChannelType.INT, doc="Display Precision"
    )
    link_selection_loc = pvproperty(
        name="SELL", dtype=ChannelType.STRING, doc="Link Selection Loc"
    )
    select_mechanism = pvproperty(
        name="SELM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.seqSELM.get_string_tuple(),
        doc="Select Mechanism",
    )
    link_selection = pvproperty(
        name="SELN", dtype=ChannelType.INT, doc="Link Selection", value=1
    )
    shift_for_mask_mode = pvproperty(
        name="SHFT", dtype=ChannelType.INT, doc="Shift for Mask mode", value=-1
    )
    # used_to_trigger = pvproperty(name='VAL',
    #      dtype=ChannelType.LONG,
    # doc='Used to trigger')
    link_parent_attribute(
        display_precision, "precision",
    )


class StateFields(RecordFieldGroup):
    _record_type = "state"
    _dtype = ChannelType.STRING  # DTYP of .VAL
    has_val_field = True
    copy_pvproperties(locals(), RecordFieldGroup)
    device_type = pvproperty(
        name="DTYP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.dtyp_state.get_string_tuple(),
        doc="Device Type",
    )
    prev_value = pvproperty(
        name="OVAL",
        dtype=ChannelType.CHAR,
        max_length=20,
        report_as_string=True,
        doc="Prev Value",
        read_only=True,
    )
    # value = pvproperty(name='VAL',
    #      dtype=ChannelType.CHAR,
    # max_length=20,report_as_string=True,doc='Value')


class StringinFields(RecordFieldGroup):
    _record_type = "stringin"
    _dtype = ChannelType.STRING  # DTYP of .VAL
    has_val_field = True
    copy_pvproperties(locals(), RecordFieldGroup)
    device_type = pvproperty(
        name="DTYP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.dtyp_stringin.get_string_tuple(),
        doc="Device Type",
    )
    post_archive_monitors = pvproperty(
        name="APST",
        dtype=ChannelType.ENUM,
        enum_strings=menus.stringinPOST.get_string_tuple(),
        doc="Post Archive Monitors",
    )
    input_specification = pvproperty(
        name="INP", dtype=ChannelType.STRING, doc="Input Specification"
    )
    post_value_monitors = pvproperty(
        name="MPST",
        dtype=ChannelType.ENUM,
        enum_strings=menus.stringinPOST.get_string_tuple(),
        doc="Post Value Monitors",
    )
    prev_simulation_mode = pvproperty(
        name="OLDSIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuSimm.get_string_tuple(),
        doc="Prev. Simulation Mode",
        read_only=True,
    )
    previous_value = pvproperty(
        name="OVAL",
        dtype=ChannelType.CHAR,
        max_length=40,
        report_as_string=True,
        doc="Previous Value",
        read_only=True,
    )
    sim_mode_async_delay = pvproperty(
        name="SDLY",
        dtype=ChannelType.DOUBLE,
        doc="Sim. Mode Async Delay",
        value=-1.0,
    )
    simulation_mode_link = pvproperty(
        name="SIML", dtype=ChannelType.STRING, doc="Simulation Mode Link"
    )
    simulation_mode = pvproperty(
        name="SIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuYesNo.get_string_tuple(),
        doc="Simulation Mode",
    )
    simulation_mode_severity = pvproperty(
        name="SIMS",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Simulation Mode Severity",
    )
    simulation_input_link = pvproperty(
        name="SIOL", dtype=ChannelType.STRING, doc="Simulation Input Link"
    )
    sim_mode_scan = pvproperty(
        name="SSCN",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuScan.get_string_tuple(),
        doc="Sim. Mode Scan",
        value=0,
    )
    simulation_value = pvproperty(
        name="SVAL",
        dtype=ChannelType.CHAR,
        max_length=40,
        report_as_string=True,
        doc="Simulation Value",
    )
    # current_value = pvproperty(name='VAL',
    #      dtype=ChannelType.CHAR,
    # max_length=40,report_as_string=True,doc='Current Value')


class StringoutFields(RecordFieldGroup):
    _record_type = "stringout"
    _dtype = ChannelType.STRING  # DTYP of .VAL
    has_val_field = True
    copy_pvproperties(locals(), RecordFieldGroup)
    device_type = pvproperty(
        name="DTYP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.dtyp_stringout.get_string_tuple(),
        doc="Device Type",
    )
    post_archive_monitors = pvproperty(
        name="APST",
        dtype=ChannelType.ENUM,
        enum_strings=menus.stringoutPOST.get_string_tuple(),
        doc="Post Archive Monitors",
    )
    desired_output_loc = pvproperty(
        name="DOL", dtype=ChannelType.STRING, doc="Desired Output Loc"
    )
    invalid_output_action = pvproperty(
        name="IVOA",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuIvoa.get_string_tuple(),
        doc="INVALID output action",
    )
    invalid_output_value = pvproperty(
        name="IVOV",
        dtype=ChannelType.CHAR,
        max_length=40,
        report_as_string=True,
        doc="INVALID output value",
    )
    post_value_monitors = pvproperty(
        name="MPST",
        dtype=ChannelType.ENUM,
        enum_strings=menus.stringoutPOST.get_string_tuple(),
        doc="Post Value Monitors",
    )
    prev_simulation_mode = pvproperty(
        name="OLDSIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuSimm.get_string_tuple(),
        doc="Prev. Simulation Mode",
        read_only=True,
    )
    output_mode_select = pvproperty(
        name="OMSL",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuOmsl.get_string_tuple(),
        doc="Output Mode Select",
    )
    output_specification = pvproperty(
        name="OUT", dtype=ChannelType.STRING, doc="Output Specification"
    )
    previous_value = pvproperty(
        name="OVAL",
        dtype=ChannelType.CHAR,
        max_length=40,
        report_as_string=True,
        doc="Previous Value",
        read_only=True,
    )
    sim_mode_async_delay = pvproperty(
        name="SDLY",
        dtype=ChannelType.DOUBLE,
        doc="Sim. Mode Async Delay",
        value=-1.0,
    )
    simulation_mode_link = pvproperty(
        name="SIML", dtype=ChannelType.STRING, doc="Simulation Mode Link"
    )
    simulation_mode = pvproperty(
        name="SIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuYesNo.get_string_tuple(),
        doc="Simulation Mode",
    )
    simulation_mode_severity = pvproperty(
        name="SIMS",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Simulation Mode Severity",
    )
    simulation_output_link = pvproperty(
        name="SIOL", dtype=ChannelType.STRING, doc="Simulation Output Link"
    )
    sim_mode_scan = pvproperty(
        name="SSCN",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuScan.get_string_tuple(),
        doc="Sim. Mode Scan",
        value=0,
    )
    # current_value = pvproperty(name='VAL',
    #      dtype=ChannelType.CHAR,
    # max_length=40,report_as_string=True,doc='Current Value')


class SubFields(RecordFieldGroup, _Limits):
    _record_type = "sub"
    _dtype = ChannelType.DOUBLE  # DTYP of .VAL
    has_val_field = True
    copy_pvproperties(locals(), RecordFieldGroup, _Limits)
    device_type = pvproperty(
        name="DTYP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.dtyp_sub.get_string_tuple(),
        doc="Device Type",
    )
    value_of_input_a = pvproperty(
        name="A", dtype=ChannelType.DOUBLE, doc="Value of Input A"
    )
    archive_deadband = pvproperty(
        name="ADEL", dtype=ChannelType.DOUBLE, doc="Archive Deadband"
    )
    last_value_archived = pvproperty(
        name="ALST",
        dtype=ChannelType.DOUBLE,
        doc="Last Value Archived",
        read_only=True,
    )
    value_of_input_b = pvproperty(
        name="B", dtype=ChannelType.DOUBLE, doc="Value of Input B"
    )
    bad_return_severity = pvproperty(
        name="BRSV",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Bad Return Severity",
    )
    value_of_input_c = pvproperty(
        name="C", dtype=ChannelType.DOUBLE, doc="Value of Input C"
    )
    value_of_input_d = pvproperty(
        name="D", dtype=ChannelType.DOUBLE, doc="Value of Input D"
    )
    value_of_input_e = pvproperty(
        name="E", dtype=ChannelType.DOUBLE, doc="Value of Input E"
    )
    engineering_units = pvproperty(
        name="EGU",
        dtype=ChannelType.CHAR,
        max_length=16,
        report_as_string=True,
        doc="Engineering Units",
    )
    value_of_input_f = pvproperty(
        name="F", dtype=ChannelType.DOUBLE, doc="Value of Input F"
    )
    value_of_input_g = pvproperty(
        name="G", dtype=ChannelType.DOUBLE, doc="Value of Input G"
    )
    value_of_input_h = pvproperty(
        name="H", dtype=ChannelType.DOUBLE, doc="Value of Input H"
    )
    alarm_deadband = pvproperty(
        name="HYST", dtype=ChannelType.DOUBLE, doc="Alarm Deadband"
    )
    value_of_input_i = pvproperty(
        name="I", dtype=ChannelType.DOUBLE, doc="Value of Input I"
    )
    init_routine_name = pvproperty(
        name="INAM",
        dtype=ChannelType.CHAR,
        max_length=40,
        report_as_string=True,
        doc="Init Routine Name",
        read_only=True,
    )
    input_a = pvproperty(name="INPA", dtype=ChannelType.STRING, doc="Input A")
    input_b = pvproperty(name="INPB", dtype=ChannelType.STRING, doc="Input B")
    input_c = pvproperty(name="INPC", dtype=ChannelType.STRING, doc="Input C")
    input_d = pvproperty(name="INPD", dtype=ChannelType.STRING, doc="Input D")
    input_e = pvproperty(name="INPE", dtype=ChannelType.STRING, doc="Input E")
    input_f = pvproperty(name="INPF", dtype=ChannelType.STRING, doc="Input F")
    input_g = pvproperty(name="INPG", dtype=ChannelType.STRING, doc="Input G")
    input_h = pvproperty(name="INPH", dtype=ChannelType.STRING, doc="Input H")
    input_i = pvproperty(name="INPI", dtype=ChannelType.STRING, doc="Input I")
    input_j = pvproperty(name="INPJ", dtype=ChannelType.STRING, doc="Input J")
    input_k = pvproperty(name="INPK", dtype=ChannelType.STRING, doc="Input K")
    input_l = pvproperty(name="INPL", dtype=ChannelType.STRING, doc="Input L")
    value_of_input_j = pvproperty(
        name="J", dtype=ChannelType.DOUBLE, doc="Value of Input J"
    )
    value_of_input_k = pvproperty(
        name="K", dtype=ChannelType.DOUBLE, doc="Value of Input K"
    )
    value_of_input_l = pvproperty(
        name="L", dtype=ChannelType.DOUBLE, doc="Value of Input L"
    )
    prev_value_of_a = pvproperty(
        name="LA",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of A",
        read_only=True,
    )
    last_value_alarmed = pvproperty(
        name="LALM",
        dtype=ChannelType.DOUBLE,
        doc="Last Value Alarmed",
        read_only=True,
    )
    prev_value_of_b = pvproperty(
        name="LB",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of B",
        read_only=True,
    )
    prev_value_of_c = pvproperty(
        name="LC",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of C",
        read_only=True,
    )
    prev_value_of_d = pvproperty(
        name="LD",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of D",
        read_only=True,
    )
    prev_value_of_e = pvproperty(
        name="LE",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of E",
        read_only=True,
    )
    prev_value_of_f = pvproperty(
        name="LF",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of F",
        read_only=True,
    )
    prev_value_of_g = pvproperty(
        name="LG",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of G",
        read_only=True,
    )
    prev_value_of_h = pvproperty(
        name="LH",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of H",
        read_only=True,
    )
    prev_value_of_i = pvproperty(
        name="LI",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of I",
        read_only=True,
    )
    prev_value_of_j = pvproperty(
        name="LJ",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of J",
        read_only=True,
    )
    prev_value_of_k = pvproperty(
        name="LK",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of K",
        read_only=True,
    )
    prev_value_of_l = pvproperty(
        name="LL",
        dtype=ChannelType.DOUBLE,
        doc="Prev Value of L",
        read_only=True,
    )
    monitor_deadband = pvproperty(
        name="MDEL", dtype=ChannelType.DOUBLE, doc="Monitor Deadband"
    )
    last_value_monitored = pvproperty(
        name="MLST",
        dtype=ChannelType.DOUBLE,
        doc="Last Value Monitored",
        read_only=True,
    )
    display_precision = pvproperty(
        name="PREC", dtype=ChannelType.INT, doc="Display Precision"
    )
    subroutine_name = pvproperty(
        name="SNAM",
        dtype=ChannelType.CHAR,
        max_length=40,
        report_as_string=True,
        doc="Subroutine Name",
    )
    # result = pvproperty(name='VAL',
    #      dtype=ChannelType.DOUBLE,
    # doc='Result')
    link_parent_attribute(
        display_precision, "precision",
    )
    link_parent_attribute(archive_deadband, "log_atol", use_setattr=True)
    link_parent_attribute(monitor_deadband, "value_atol", use_setattr=True)


class SubarrayFields(RecordFieldGroup):
    _record_type = "subArray"
    _dtype = None  # DTYP of .VAL
    has_val_field = False
    copy_pvproperties(locals(), RecordFieldGroup)
    device_type = pvproperty(
        name="DTYP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.dtyp_subArray.get_string_tuple(),
        doc="Device Type",
    )
    busy_indicator = pvproperty(
        name="BUSY", dtype=ChannelType.INT, doc="Busy Indicator", read_only=True
    )
    engineering_units = pvproperty(
        name="EGU",
        dtype=ChannelType.CHAR,
        max_length=16,
        report_as_string=True,
        doc="Engineering Units",
    )
    field_type_of_value = pvproperty(
        name="FTVL",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Field Type of Value",
        read_only=True,
    )
    high_operating_range = pvproperty(
        name="HOPR", dtype=ChannelType.DOUBLE, doc="High Operating Range"
    )
    substring_index = pvproperty(
        name="INDX", dtype=ChannelType.LONG, doc="Substring Index"
    )
    input_specification = pvproperty(
        name="INP", dtype=ChannelType.STRING, doc="Input Specification"
    )
    low_operating_range = pvproperty(
        name="LOPR", dtype=ChannelType.DOUBLE, doc="Low Operating Range"
    )
    maximum_elements = pvproperty(
        name="MALM",
        dtype=ChannelType.LONG,
        doc="Maximum Elements",
        read_only=True,
        value=1,
    )
    number_of_elements = pvproperty(
        name="NELM", dtype=ChannelType.LONG, doc="Number of Elements", value=1
    )
    number_elements_read = pvproperty(
        name="NORD",
        dtype=ChannelType.LONG,
        doc="Number elements read",
        read_only=True,
    )
    display_precision = pvproperty(
        name="PREC", dtype=ChannelType.INT, doc="Display Precision"
    )
    link_parent_attribute(
        display_precision, "precision",
    )
    link_parent_attribute(
        high_operating_range, "upper_ctrl_limit",
    )
    link_parent_attribute(
        low_operating_range, "lower_ctrl_limit",
    )
    link_parent_attribute(
        maximum_elements, "length", use_setattr=True, read_only=True
    )
    link_parent_attribute(
        number_of_elements, "max_length", use_setattr=True, read_only=True
    )


class WaveformFields(RecordFieldGroup):
    _record_type = "waveform"
    _dtype = None  # DTYP of .VAL
    has_val_field = False
    copy_pvproperties(locals(), RecordFieldGroup)
    device_type = pvproperty(
        name="DTYP",
        dtype=ChannelType.ENUM,
        enum_strings=menus.dtyp_waveform.get_string_tuple(),
        doc="Device Type",
    )
    post_archive_monitors = pvproperty(
        name="APST",
        dtype=ChannelType.ENUM,
        enum_strings=menus.waveformPOST.get_string_tuple(),
        doc="Post Archive Monitors",
    )
    busy_indicator = pvproperty(
        name="BUSY", dtype=ChannelType.INT, doc="Busy Indicator", read_only=True
    )
    engineering_units = pvproperty(
        name="EGU",
        dtype=ChannelType.CHAR,
        max_length=16,
        report_as_string=True,
        doc="Engineering Units",
    )
    field_type_of_value = pvproperty(
        name="FTVL",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuFtype.get_string_tuple(),
        doc="Field Type of Value",
        read_only=True,
    )
    hash_of_onchange_data = pvproperty(
        name="HASH", dtype=ChannelType.LONG, doc="Hash of OnChange data."
    )
    high_operating_range = pvproperty(
        name="HOPR", dtype=ChannelType.DOUBLE, doc="High Operating Range"
    )
    input_specification = pvproperty(
        name="INP", dtype=ChannelType.STRING, doc="Input Specification"
    )
    low_operating_range = pvproperty(
        name="LOPR", dtype=ChannelType.DOUBLE, doc="Low Operating Range"
    )
    post_value_monitors = pvproperty(
        name="MPST",
        dtype=ChannelType.ENUM,
        enum_strings=menus.waveformPOST.get_string_tuple(),
        doc="Post Value Monitors",
    )
    number_of_elements = pvproperty(
        name="NELM",
        dtype=ChannelType.LONG,
        doc="Number of Elements",
        read_only=True,
        value=1,
    )
    number_elements_read = pvproperty(
        name="NORD",
        dtype=ChannelType.LONG,
        doc="Number elements read",
        read_only=True,
    )
    prev_simulation_mode = pvproperty(
        name="OLDSIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuSimm.get_string_tuple(),
        doc="Prev. Simulation Mode",
        read_only=True,
    )
    display_precision = pvproperty(
        name="PREC", dtype=ChannelType.INT, doc="Display Precision"
    )
    rearm_the_waveform = pvproperty(
        name="RARM", dtype=ChannelType.INT, doc="Rearm the waveform"
    )
    sim_mode_async_delay = pvproperty(
        name="SDLY",
        dtype=ChannelType.DOUBLE,
        doc="Sim. Mode Async Delay",
        value=-1.0,
    )
    simulation_mode_link = pvproperty(
        name="SIML", dtype=ChannelType.STRING, doc="Simulation Mode Link"
    )
    simulation_mode = pvproperty(
        name="SIMM",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuYesNo.get_string_tuple(),
        doc="Simulation Mode",
    )
    simulation_mode_severity = pvproperty(
        name="SIMS",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuAlarmSevr.get_string_tuple(),
        doc="Simulation Mode Severity",
    )
    simulation_input_link = pvproperty(
        name="SIOL", dtype=ChannelType.STRING, doc="Simulation Input Link"
    )
    sim_mode_scan = pvproperty(
        name="SSCN",
        dtype=ChannelType.ENUM,
        enum_strings=menus.menuScan.get_string_tuple(),
        doc="Sim. Mode Scan",
        value=0,
    )
    link_parent_attribute(
        display_precision, "precision",
    )
    link_parent_attribute(
        high_operating_range, "upper_ctrl_limit",
    )
    link_parent_attribute(
        low_operating_range, "lower_ctrl_limit",
    )
    link_parent_attribute(
        number_of_elements, "max_length", use_setattr=True, read_only=True
    )
