# Manually written with reference to:
# http://www.aps.anl.gov/epics/base/R3-16/0-docs/CAproto/index.html#payload-data-types
# https://github.com/epics-base/epics-base/blob/813166128eae1240cdd643869808abe1c4621321/src/ca/client/db_access.h
import ctypes


MAX_UNITS_SIZE = 8
MAX_ENUM_STRING_SIZE = 26
MAX_ENUM_STATES = 16

DO_REPLY = 10
NO_REPLY = 5


dbr_string = 40 * ctypes.c_char  # epicsOldString
dbr_char = ctypes.c_char # epicsUint8
dbr_short = ctypes.c_short  # epicsInt16
dbr_ushort = ctypes.c_ushort # epicsUInt16
dbr_int = ctypes.c_int16  # epicsInt16
dbr_enum = ctypes.c_uint16  # epicsUInt16
dbr_long = ctypes.c_long  # epicsInt32
dbr_ulong = ctypes.c_ulong  # epicsUInt32
dbr_float = ctypes.c_float  # epicsFloat32
dbr_double = ctypes.c_double # epicsFloat64
dbr_stsack_string_t = 40 * ctypes.c_char # epicsOldString
dbr_class_name_t = 40 * ctypes.c_char  # epicsOldString


class DBR_STRING(ctypes.BigEndianStructure):
    DBR_ID = 0
    _fields_ = [
        ('value', dbr_string),
    ]


class DBR_INT(ctypes.BigEndianStructure):
    DBR_ID = 1
    _fields_ = [
        ('value', dbr_int),
    ]


class DBR_FLOAT(ctypes.BigEndianStructure):
    DBR_ID = 2
    _fields_ = [
        ('value', dbr_float),
    ]


class DBR_ENUM(ctypes.BigEndianStructure):
    DBR_ID = 3
    _fields_ = [
        ('value', dbr_enum),
    ]


class DBR_CHAR(ctypes.BigEndianStructure):
    DBR_ID = 4
    _fields_ = [
        ('value', dbr_char),
    ]


class DBR_LONG(ctypes.BigEndianStructure):
    DBR_ID = 5
    _fields_ = [
        ('value', dbr_long),
    ]


class DBR_DOUBLE(ctypes.BigEndianStructure):
    DBR_ID = 6
    _fields_ = [
        ('value', dbr_double),
    ]


class DBR_STS_STRING(ctypes.BigEndianStructure):
    # struct dbr_sts_string {
    #     dbr_short_t    status;             /* status of value */
    #     dbr_short_t    severity;        /* severity of alarm */
    #     dbr_string_t    value;            /* current value */
    # };
    DBR_ID = 7
    _fields_ = [
        ('status', dbr_short),
        ('severity', dbr_short),
        ('value',  dbr_string),
    ]


class DBR_STS_INT(ctypes.BigEndianStructure):
    # /* structure for an short status field */
    # struct dbr_sts_int{
    #     dbr_short_t    status;             /* status of value */
    #     dbr_short_t    severity;        /* severity of alarm */
    #     dbr_short_t    value;            /* current value */
    # };
    DBR_ID = 8
    _fields_ = [
        ('status', dbr_short),
        ('severity', dbr_short),
        ('value', dbr_short),
    ]


class DBR_STS_FLOAT(ctypes.BigEndianStructure):
    # /* structure for a  float status field */
    # struct dbr_sts_float{
    #     dbr_short_t    status;             /* status of value */
    #     dbr_short_t    severity;        /* severity of alarm */
    #     dbr_float_t    value;            /* current value */
    # };
    DBR_ID = 9
    _fields_ = [
        ('status', dbr_short),
        ('severity', dbr_short),
        ('value', dbr_float),
    ]


class DBR_STS_ENUM(ctypes.BigEndianStructure):
    # /* structure for a  enum status field */
    # struct dbr_sts_enum{
    #     dbr_short_t    status;             /* status of value */
    #     dbr_short_t    severity;        /* severity of alarm */
    #     dbr_enum_t    value;            /* current value */
    # };
    DBR_ID = 10
    _fields_ = [
        ('status', dbr_short),
        ('severity', dbr_short),
        ('value', dbr_enum),
    ]


class DBR_STS_CHAR(ctypes.BigEndianStructure):
    # /* structure for a char status field */
    # struct dbr_sts_char{
    #     dbr_short_t    status;         /* status of value */
    #     dbr_short_t    severity;    /* severity of alarm */
    #     dbr_char_t    RISC_pad;    /* RISC alignment */
    #     dbr_char_t    value;        /* current value */
    # };
    DBR_ID = 11
    _fields_ = [
        ('status', dbr_short),
        ('severity', dbr_short),
        ('RISC_pad', dbr_char),
        ('value', dbr_char),
    ]


class DBR_STS_LONG(ctypes.BigEndianStructure):
    # /* structure for a long status field */
    # struct dbr_sts_long{
    #     dbr_short_t    status;             /* status of value */
    #     dbr_short_t    severity;        /* severity of alarm */
    #     dbr_long_t    value;            /* current value */
    # };
    DBR_ID = 12
    _fields_ = [
        ('status', dbr_short),
        ('severity', dbr_short),
        ('value', dbr_long),
    ]


class DBR_STS_DOUBLE(ctypes.BigEndianStructure):
    # /* structure for a double status field */
    # struct dbr_sts_double{
    #     dbr_short_t    status;             /* status of value */
    #     dbr_short_t    severity;        /* severity of alarm */
    #     dbr_long_t    RISC_pad;        /* RISC alignment */
    #     dbr_double_t    value;            /* current value */
    # };
    DBR_ID = 13
    _fields_ = [
        ('status', dbr_short),
        ('severity', dbr_short),
        ('RISC_pad', dbr_long),
        ('value', dbr_double),
    ]


class DBR_TIME_STRING(ctypes.BigEndianStructure):
    # /* structure for a  string time field */
    # struct dbr_time_string{
    #     dbr_short_t    status;             /* status of value */
    #     dbr_short_t    severity;        /* severity of alarm */
    #     epicsTimeStamp    stamp;            /* time stamp */
    #     dbr_string_t    value;            /* current value */
    # };
    DBR_ID = 14
    _fields_ = [
        ('status', dbr_short),
        ('severity', dbr_short),
        ('secondsSinceEpoch', dbr_long),
        ('nanoSeconds', dbr_ulong),
        ('value', 40 * dbr_char),
    ]


class DBR_TIME_INT(ctypes.BigEndianStructure):
    # /* structure for an short time field */
    # struct dbr_time_short{
    #     dbr_short_t    status;             /* status of value */
    #     dbr_short_t    severity;        /* severity of alarm */
    #     epicsTimeStamp    stamp;            /* time stamp */
    #     dbr_short_t    RISC_pad;        /* RISC alignment */
    #     dbr_short_t    value;            /* current value */
    # };
    DBR_ID = 15
    _fields_ = [
        ('status', dbr_short),
        ('severity', dbr_short),
        ('secondsSinceEpoch', dbr_long),
        ('nanoSeconds', dbr_ulong),
        ('RISC_pad', dbr_short),
        ('value', dbr_ushort),
    ]


class DBR_TIME_FLOAT(ctypes.BigEndianStructure):
    # /* structure for a  float time field */
    # struct dbr_time_float{
    #     dbr_short_t    status;             /* status of value */
    #     dbr_short_t    severity;        /* severity of alarm */
    #     epicsTimeStamp    stamp;            /* time stamp */
    #     dbr_float_t    value;            /* current value */
    # };
    DBR_ID = 16
    _fields_ = [
        ('status', dbr_short),
        ('severity', dbr_short),
        ('secondsSinceEpoch', dbr_long),
        ('nanoSeconds', dbr_ulong),
        ('value', dbr_float),
    ]


class DBR_TIME_ENUM(ctypes.BigEndianStructure):
    # /* structure for a  enum time field */
    # struct dbr_time_enum{
    #     dbr_short_t    status;             /* status of value */
    #     dbr_short_t    severity;        /* severity of alarm */
    #     epicsTimeStamp    stamp;            /* time stamp */
    #     dbr_short_t    RISC_pad;        /* RISC alignment */
    #     dbr_enum_t    value;            /* current value */
    # };
    # 
    DBR_ID = 17
    _fields_ = [
        ('status', dbr_short),
        ('severity', dbr_short),
        ('secondsSinceEpoch', dbr_long),
        ('nanoSeconds', dbr_ulong),
        ('RISC_pad', dbr_short),
        ('value', dbr_enum),
    ]


class DBR_TIME_CHAR(ctypes.BigEndianStructure):
    # /* structure for a char time field */
    # struct dbr_time_char{
    #     dbr_short_t    status;             /* status of value */
    #     dbr_short_t    severity;        /* severity of alarm */
    #     epicsTimeStamp    stamp;            /* time stamp */
    #     dbr_short_t    RISC_pad0;        /* RISC alignment */
    #     dbr_char_t    RISC_pad1;        /* RISC alignment */
    #     dbr_char_t    value;            /* current value */
    # };
    DBR_ID = 18
    _fields_ = [
        ('status', dbr_short),
        ('severity', dbr_short),
        ('secondsSinceEpoch', dbr_long),
        ('nanoSeconds', dbr_ulong),
        ('RISC_pad0', dbr_short),
        ('RISC_pad0', dbr_char),
        ('value', dbr_char),
    ]


class DBR_TIME_LONG(ctypes.BigEndianStructure):
    # /* structure for a long time field */
    # struct dbr_time_long{
    #     dbr_short_t    status;             /* status of value */
    #     dbr_short_t    severity;        /* severity of alarm */
    #     epicsTimeStamp    stamp;            /* time stamp */
    #     dbr_long_t    value;            /* current value */
    # };
    DBR_ID = 19
    _fields_ = [
        ('status', dbr_short),
        ('severity', dbr_short),
        ('secondsSinceEpoch', dbr_long),
        ('nanoSeconds', dbr_ulong),
        ('value', dbr_long),
    ]


class DBR_TIME_DOUBLE(ctypes.BigEndianStructure):
    # /* structure for a double time field */
    # struct dbr_time_double{
    #     dbr_short_t    status;             /* status of value */
    #     dbr_short_t    severity;        /* severity of alarm */
    #     epicsTimeStamp    stamp;            /* time stamp */
    #     dbr_long_t    RISC_pad;        /* RISC alignment */
    #     dbr_double_t    value;            /* current value */
    # };
    DBR_ID = 20
    _fields_ = [
        ('status', dbr_short),
        ('severity', dbr_short),
        ('secondsSinceEpoch', dbr_long),
        ('nanoSeconds', dbr_ulong),
        ('RISC_Pad', dbr_long),
        ('value', dbr_double),
    ]


# DBR_GR_STRING (21) is not implemented by EPICS.


class DBR_GR_INT(ctypes.BigEndianStructure):
    # struct dbr_gr_int{
    #     dbr_short_t    status;             /* status of value */
    #     dbr_short_t    severity;        /* severity of alarm */
    #     char        units[MAX_UNITS_SIZE];    /* units of value */
    #     dbr_short_t    upper_disp_limit;    /* upper limit of graph */
    #     dbr_short_t    lower_disp_limit;    /* lower limit of graph */
    #     dbr_short_t    upper_alarm_limit;    
    #     dbr_short_t    upper_warning_limit;
    #     dbr_short_t    lower_warning_limit;
    #     dbr_short_t    lower_alarm_limit;
    #     dbr_short_t    value;            /* current value */
    # };
    DBR_ID = 22
    _fields_ = [
        ('status', dbr_short),
        ('severity', dbr_short),
        ('units', MAX_UNITS_SIZE * dbr_char),
        ('upper_disp_limit', dbr_short),
        ('lower_disp_limit', dbr_short),
        ('upper_alarm_limit', dbr_short),
        ('upper_warning_limit', dbr_short),
        ('lower_warning_limit', dbr_short),
        ('lower_alarm_limit', dbr_short),
        ('value', dbr_short),
    ]


class DBR_GR_FLOAT(ctypes.BigEndianStructure):
    # /* structure for a graphic floating point field */
    # struct dbr_gr_float{
    #     dbr_short_t    status;             /* status of value */
    #     dbr_short_t    severity;        /* severity of alarm */
    #     dbr_short_t    precision;        /* number of decimal places */
    #     dbr_short_t    RISC_pad0;        /* RISC alignment */
    #     char        units[MAX_UNITS_SIZE];    /* units of value */
    #     dbr_float_t    upper_disp_limit;    /* upper limit of graph */
    #     dbr_float_t    lower_disp_limit;    /* lower limit of graph */
    #     dbr_float_t    upper_alarm_limit;    
    #     dbr_float_t    upper_warning_limit;
    #     dbr_float_t    lower_warning_limit;
    #     dbr_float_t    lower_alarm_limit;
    #     dbr_float_t    value;            /* current value */
    # };
    DBR_ID = 23
    _fields_ = [
        ('status', dbr_short),
        ('severity', dbr_short),
        ('precision', dbr_short),
        ('RISC_pad0', dbr_short),
        ('units', MAX_UNITS_SIZE * dbr_char),
        ('upper_disp_limit', dbr_float),
        ('lower_disp_limit', dbr_float),
        ('upper_alarm_limit', dbr_float),
        ('upper_warning_limit', dbr_float),
        ('lower_warning_limit', dbr_float),
        ('lower_alarm_limit', dbr_float),
        ('value', dbr_float),
    ]


class DBR_GR_ENUM(ctypes.BigEndianStructure):
    # /* structure for a graphic enumeration field */
    # struct dbr_gr_enum{
    #     dbr_short_t    status;             /* status of value */
    #     dbr_short_t    severity;        /* severity of alarm */
    #     dbr_short_t    no_str;            /* number of strings */
    #     char        strs[MAX_ENUM_STATES][MAX_ENUM_STRING_SIZE];
    #                         /* state strings */
    #     dbr_enum_t    value;            /* current value */
    # };
    DBR_ID = 24
    _fields_ = [
        ('status', dbr_short),
        ('severity', dbr_short),
        ('no_str', dbr_short),  # number of strings
        ('strs', MAX_ENUM_STATES * MAX_ENUM_STRING_SIZE * dbr_char),
        ('value', dbr_enum),
    ]
    

class DBR_GR_CHAR(ctypes.BigEndianStructure):
    # /* structure for a graphic char field */
    # struct dbr_gr_char{
    #     dbr_short_t    status;             /* status of value */
    #     dbr_short_t    severity;        /* severity of alarm */
    #     char        units[MAX_UNITS_SIZE];    /* units of value */
    #     dbr_char_t    upper_disp_limit;    /* upper limit of graph */
    #     dbr_char_t    lower_disp_limit;    /* lower limit of graph */
    #     dbr_char_t    upper_alarm_limit;    
    #     dbr_char_t    upper_warning_limit;
    #     dbr_char_t    lower_warning_limit;
    #     dbr_char_t    lower_alarm_limit;
    #     dbr_char_t    RISC_pad;        /* RISC alignment */
    #     dbr_char_t    value;            /* current value */
    # };
    DBR_ID = 25
    _fields_ = [
        ('status', dbr_short),
        ('severity', dbr_short),
        ('units', MAX_UNITS_SIZE * dbr_char),
        ('upper_disp_limit', dbr_char),
        ('lower_disp_limit', dbr_char),
        ('upper_alarm_limit', dbr_char),
        ('upper_warning_limit', dbr_char),
        ('lower_warning_limit', dbr_char),
        ('lower_alarm_limit', dbr_char),
        ('value', dbr_char),
    ]


class DBR_GR_LONG(ctypes.BigEndianStructure):
    # /* structure for a graphic long field */
    # struct dbr_gr_long{
    #     dbr_short_t    status;             /* status of value */
    #     dbr_short_t    severity;        /* severity of alarm */
    #     char        units[MAX_UNITS_SIZE];    /* units of value */
    #     dbr_long_t    upper_disp_limit;    /* upper limit of graph */
    #     dbr_long_t    lower_disp_limit;    /* lower limit of graph */
    #     dbr_long_t    upper_alarm_limit;    
    #     dbr_long_t    upper_warning_limit;
    #     dbr_long_t    lower_warning_limit;
    #     dbr_long_t    lower_alarm_limit;
    #     dbr_long_t    value;            /* current value */
    # };
    DBR_ID = 26
    _fields_ = [
        ('status', dbr_short),
        ('severity', dbr_short),
        ('units', MAX_UNITS_SIZE * dbr_char),
        ('upper_disp_limit', dbr_long),
        ('lower_disp_limit', dbr_long),
        ('upper_alarm_limit', dbr_long),
        ('upper_warning_limit', dbr_long),
        ('lower_warning_limit', dbr_long),
        ('lower_alarm_limit', dbr_long),
        ('value', dbr_long),
    ]


class DBR_GR_DOUBLE(ctypes.BigEndianStructure):
    # /* structure for a graphic double field */
    # struct dbr_gr_double{
    #     dbr_short_t    status;             /* status of value */
    #     dbr_short_t    severity;        /* severity of alarm */
    #     dbr_short_t    precision;        /* number of decimal places */
    #     dbr_short_t    RISC_pad0;        /* RISC alignment */
    #     char        units[MAX_UNITS_SIZE];    /* units of value */
    #     dbr_double_t    upper_disp_limit;    /* upper limit of graph */
    #     dbr_double_t    lower_disp_limit;    /* lower limit of graph */
    #     dbr_double_t    upper_alarm_limit;    
    #     dbr_double_t    upper_warning_limit;
    #     dbr_double_t    lower_warning_limit;
    #     dbr_double_t    lower_alarm_limit;
    #     dbr_double_t    value;            /* current value */
    # };
    DBR_ID = 27
    _fields_ = [
        ('status', dbr_short),
        ('severity', dbr_short),
        ('precision', dbr_short),
        ('RISC_pad0', dbr_short),
        ('units', MAX_UNITS_SIZE * dbr_char),
        ('upper_disp_limit', dbr_double),
        ('lower_disp_limit', dbr_double),
        ('upper_alarm_limit', dbr_double),
        ('upper_warning_limit', dbr_double),
        ('lower_warning_limit', dbr_double),
        ('lower_alarm_limit', dbr_double),
        ('value', dbr_double),
    ]


# DBR_GR_STRING (28) is not implemented by EPICS.


class DBR_CTRL_INT(ctypes.BigEndianStructure):
    DBR_ID = 29
    # /* structure for a control integer */
    # struct dbr_ctrl_int{
    #     dbr_short_t    status;             /* status of value */
    #     dbr_short_t    severity;        /* severity of alarm */
    #     char        units[MAX_UNITS_SIZE];    /* units of value */
    #     dbr_short_t    upper_disp_limit;    /* upper limit of graph */
    #     dbr_short_t    lower_disp_limit;    /* lower limit of graph */
    #     dbr_short_t    upper_alarm_limit;    
    #     dbr_short_t    upper_warning_limit;
    #     dbr_short_t    lower_warning_limit;
    #     dbr_short_t    lower_alarm_limit;
    #     dbr_short_t    upper_ctrl_limit;    /* upper control limit */
    #     dbr_short_t    lower_ctrl_limit;    /* lower control limit */
    #     dbr_short_t    value;            /* current value */
    # };
    _fields_ = [
        ('status', dbr_short),
        ('severity', dbr_short),
        ('precision', dbr_short),
        ('units', MAX_UNITS_SIZE * dbr_char),
        ('upper_disp_limit', dbr_short),
        ('lower_disp_limit', dbr_short),
        ('upper_alarm_limit', dbr_short),
        ('upper_warning_limit', dbr_short),
        ('lower_warning_limit', dbr_short),
        ('lower_alarm_limit', dbr_short),
        ('upper_ctrl_limit', dbr_short),
        ('lower_ctrl_limit', dbr_short),
        ('value', dbr_short),
    ]


class DBR_CTRL_FLOAT(ctypes.BigEndianStructure):
    # /* structure for a control floating point field */
    # struct dbr_ctrl_float{
    #     dbr_short_t    status;             /* status of value */
    #     dbr_short_t    severity;        /* severity of alarm */
    #     dbr_short_t    precision;        /* number of decimal places */
    #     dbr_short_t    RISC_pad;        /* RISC alignment */
    #     char        units[MAX_UNITS_SIZE];    /* units of value */
    #     dbr_float_t    upper_disp_limit;    /* upper limit of graph */
    #     dbr_float_t    lower_disp_limit;    /* lower limit of graph */
    #     dbr_float_t    upper_alarm_limit;    
    #     dbr_float_t    upper_warning_limit;
    #     dbr_float_t    lower_warning_limit;
    #     dbr_float_t    lower_alarm_limit;
    #      dbr_float_t    upper_ctrl_limit;    /* upper control limit */
    #     dbr_float_t    lower_ctrl_limit;    /* lower control limit */
    #     dbr_float_t    value;            /* current value */
    # };
    DBR_ID = 30
    _fields_ = [
        ('status', dbr_short),
        ('severity', dbr_short),
        ('precision', dbr_short),
        ('RISC_pad0', dbr_short),
        ('units', MAX_UNITS_SIZE * dbr_char),
        ('upper_disp_limit', dbr_float),
        ('lower_disp_limit', dbr_float),
        ('upper_alarm_limit', dbr_float),
        ('upper_warning_limit', dbr_float),
        ('lower_warning_limit', dbr_float),
        ('lower_alarm_limit', dbr_float),
        ('upper_ctrl_limit', dbr_float),
        ('lower_ctrl_limit', dbr_float),
        ('value', dbr_float),
    ]


class DBR_CTRL_ENUM(ctypes.BigEndianStructure):
    # /* structure for a control enumeration field */
    # struct dbr_ctrl_enum{
    #     dbr_short_t    status;             /* status of value */
    #     dbr_short_t    severity;        /* severity of alarm */
    #     dbr_short_t    no_str;            /* number of strings */
    #     char    strs[MAX_ENUM_STATES][MAX_ENUM_STRING_SIZE];
    #                     /* state strings */
    #     dbr_enum_t    value;        /* current value */
    # };
    DBR_ID = 31
    _fields_ = [
        ('status', dbr_short),
        ('severity', dbr_short),
        ('no_str', dbr_short),  # number of strings
        ('strs', MAX_ENUM_STATES * MAX_ENUM_STRING_SIZE * dbr_char),
        ('value', dbr_enum),
    ]


class DBR_CTRL_CHAR(ctypes.BigEndianStructure):
    # /* structure for a control char field */
    # struct dbr_ctrl_char{
    #     dbr_short_t    status;             /* status of value */
    #     dbr_short_t    severity;        /* severity of alarm */
    #     char        units[MAX_UNITS_SIZE];    /* units of value */
    #     dbr_char_t    upper_disp_limit;    /* upper limit of graph */
    #     dbr_char_t    lower_disp_limit;    /* lower limit of graph */
    #     dbr_char_t    upper_alarm_limit;    
    #     dbr_char_t    upper_warning_limit;
    #     dbr_char_t    lower_warning_limit;
    #     dbr_char_t    lower_alarm_limit;
    #     dbr_char_t    upper_ctrl_limit;    /* upper control limit */
    #     dbr_char_t    lower_ctrl_limit;    /* lower control limit */
    #     dbr_char_t    RISC_pad;        /* RISC alignment */
    #     dbr_char_t    value;            /* current value */
    # };
    DBR_ID = 32
    _fields_ = [
        ('status', dbr_short),
        ('severity', dbr_short),
        ('units', MAX_UNITS_SIZE * dbr_char),
        ('upper_disp_limit', dbr_char),
        ('lower_disp_limit', dbr_char),
        ('upper_alarm_limit', dbr_char),
        ('upper_warning_limit', dbr_char),
        ('lower_warning_limit', dbr_char),
        ('lower_alarm_limit', dbr_char),
        ('upper_ctrl_limit', dbr_char),
        ('lower_ctrl_limit', dbr_char),
        ('RISC_pad', dbr_char),
        ('value', dbr_char),
    ]


class DBR_CTRL_LONG(ctypes.BigEndianStructure):
    # /* structure for a control long field */
    # struct dbr_ctrl_long{
    #     dbr_short_t    status;             /* status of value */
    #     dbr_short_t    severity;        /* severity of alarm */
    #     char        units[MAX_UNITS_SIZE];    /* units of value */
    #     dbr_long_t    upper_disp_limit;    /* upper limit of graph */
    #     dbr_long_t    lower_disp_limit;    /* lower limit of graph */
    #     dbr_long_t    upper_alarm_limit;    
    #     dbr_long_t    upper_warning_limit;
    #     dbr_long_t    lower_warning_limit;
    #     dbr_long_t    lower_alarm_limit;
    #     dbr_long_t    upper_ctrl_limit;    /* upper control limit */
    #     dbr_long_t    lower_ctrl_limit;    /* lower control limit */
    #     dbr_long_t    value;            /* current value */
    # };
    DBR_ID = 33
    _fields_ = [
        ('status', dbr_short),
        ('severity', dbr_short),
        ('units', MAX_UNITS_SIZE * dbr_char),
        ('upper_disp_limit', dbr_long),
        ('lower_disp_limit', dbr_long),
        ('upper_alarm_limit', dbr_long),
        ('upper_warning_limit', dbr_long),
        ('lower_warning_limit', dbr_long),
        ('lower_alarm_limit', dbr_long),
        ('upper_ctrl_limit', dbr_long),
        ('lower_ctrl_limit', dbr_long),
        ('value', dbr_long),
    ]


class DBR_CTRL_DOUBLE(ctypes.BigEndianStructure):
    # /* structure for a control double field */
    # struct dbr_ctrl_double{
    #     dbr_short_t    status;             /* status of value */
    #     dbr_short_t    severity;        /* severity of alarm */
    #     dbr_short_t    precision;        /* number of decimal places */
    #     dbr_short_t    RISC_pad0;        /* RISC alignment */
    #     char        units[MAX_UNITS_SIZE];    /* units of value */
    #     dbr_double_t    upper_disp_limit;    /* upper limit of graph */
    #     dbr_double_t    lower_disp_limit;    /* lower limit of graph */
    #     dbr_double_t    upper_alarm_limit;    
    #     dbr_double_t    upper_warning_limit;
    #     dbr_double_t    lower_warning_limit;
    #     dbr_double_t    lower_alarm_limit;
    #     dbr_double_t    upper_ctrl_limit;    /* upper control limit */
    #     dbr_double_t    lower_ctrl_limit;    /* lower control limit */
    #     dbr_double_t    value;            /* current value */
    # };
    DBR_ID = 34
    _fields_ = [
        ('status', dbr_short),
        ('severity', dbr_short),
        ('precision', dbr_short),
        ('RISC_pad0', dbr_short),
        ('units', MAX_UNITS_SIZE * dbr_char),
        ('upper_disp_limit', dbr_double),
        ('lower_disp_limit', dbr_double),
        ('upper_alarm_limit', dbr_double),
        ('upper_warning_limit', dbr_double),
        ('lower_warning_limit', dbr_double),
        ('lower_alarm_limit', dbr_double),
        ('upper_ctrl_limit', dbr_double),
        ('lower_ctrl_limit', dbr_double),
        ('value', dbr_double),
    ]


class DBR_PUT_ACKT(ctypes.BigEndianStructure):
    DBR_ID = 35
    _fields_ = [
        ('value', dbr_ushort),
    ]


class DBR_PUT_ACKS(ctypes.BigEndianStructure):
    DBR_ID = 36
    _fields_ = [
        ('value', dbr_ushort),
    ]


class DBR_STSACK_STRING(ctypes.BigEndianStructure):
    # /* structure for a  string status and ack field */
    # struct dbr_stsack_string{
    #     dbr_ushort_t    status;             /* status of value */
    #     dbr_ushort_t    severity;        /* severity of alarm */
    #     dbr_ushort_t    ackt;             /* ack transient? */
    #     dbr_ushort_t    acks;            /* ack severity    */
    #     dbr_string_t    value;            /* current value */
    # };
    DBR_ID = 37
    _fields_ = [
        ('status', dbr_short),
        ('severity', dbr_short),
        ('ackt', dbr_ushort),
        ('acks', dbr_ushort),
        ('value', 40 * dbr_char),
    ]


class DBR_CLASS_NAME(ctypes.BigEndianStructure):
    DBR_ID = 38
    _fields_ = [
        ('value', dbr_ushort),
    ]


DBR_SHORT = DBR_INT
DBR_STS_SHORT = DBR_STS_INT
DBR_TIME_SHORT = DBR_TIME_INT
DBR_GR_SHORT = DBR_GR_INT
DBR_CTRL_SHORT = DBR_CTRL_INT


_all_types = [c for c in globals().values() if hasattr(c, 'DBR_ID')]
DBR_TYPES = {}
for t in _all_types:
    DBR_TYPES[t.DBR_ID] = t
