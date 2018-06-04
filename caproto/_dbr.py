# Manually written with reference to:
# http://www.aps.anl.gov/epics/base/R3-16/0-docs/CAproto/index.html#payload-data-types
# https://github.com/epics-base/epics-base/blob/813166128eae1240cdd643869808abe1c4621321/src/ca/client/db_access.h

# The organizational code, making use of Enum, comes from pypvasync by Kenneth
# Lauer.

import ctypes
import datetime
import collections
from enum import IntEnum, IntFlag
from ._constants import (EPICS2UNIX_EPOCH, EPICS_EPOCH, MAX_STRING_SIZE,
                         MAX_UNITS_SIZE, MAX_ENUM_STRING_SIZE, MAX_ENUM_STATES)


__all__ = ('AccessRights', 'AlarmSeverity', 'AlarmStatus', 'ConnStatus',
           'TimeStamp', 'ChannelType', 'SubscriptionType', 'DbrStringArray',
           'epics_timestamp_to_unix', 'timestamp_to_epics',
           'field_types', 'DBR_TYPES', 'native_type', 'native_types',
           'status_types', 'time_types', 'graphical_types', 'control_types',
           'char_types', 'string_types', 'int_types', 'float_types',
           'enum_types', 'char_types', 'native_float_types',
           'native_int_types')


class AccessRights(IntFlag):
    NO_ACCESS = 0
    READ = 1
    WRITE = 2


class AlarmSeverity(IntEnum):
    NO_ALARM = 0
    MINOR_ALARM = 1
    MAJOR_ALARM = 2
    INVALID_ALARM = 3


class AlarmStatus(IntEnum):
    NO_ALARM = 0
    READ = 1
    WRITE = 2
    HIHI = 3
    HIGH = 4
    LOLO = 5
    LOW = 6
    STATE = 7
    COS = 8
    COMM = 9
    TIMEOUT = 10
    HWLIMIT = 11
    CALC = 12
    SCAN = 13
    LINK = 14
    SOFT = 15
    BAD_SUB = 16
    UDF = 17
    DISABLE = 18
    SIMM = 19
    READ_ACCESS = 20
    WRITE_ACCESS = 21


# EPICS Constants
class ECA(IntEnum):
    NORMAL = 1
    TIMEOUT = 80
    IODONE = 339
    ISATTACHED = 424
    BADCHID = 410


class ConnStatus(IntEnum):
    CS_CONN = 2
    OP_CONN_UP = 6
    OP_CONN_DOWN = 7
    CS_NEVER_SEARCH = 4


class ChannelType(IntEnum):
    STRING = 0
    INT = 1
    FLOAT = 2
    ENUM = 3
    CHAR = 4
    LONG = 5
    DOUBLE = 6

    STS_STRING = 7
    STS_INT = 8
    STS_FLOAT = 9
    STS_ENUM = 10
    STS_CHAR = 11
    STS_LONG = 12
    STS_DOUBLE = 13

    TIME_STRING = 14
    TIME_INT = 15
    TIME_FLOAT = 16
    TIME_ENUM = 17
    TIME_CHAR = 18
    TIME_LONG = 19
    TIME_DOUBLE = 20

    GR_STRING = 21  # not implemented by EPICS
    GR_INT = 22
    GR_FLOAT = 23
    GR_ENUM = 24
    GR_CHAR = 25
    GR_LONG = 26
    GR_DOUBLE = 27

    CTRL_STRING = 28  # not implemented by EPICS
    CTRL_INT = 29
    CTRL_FLOAT = 30
    CTRL_ENUM = 31
    CTRL_CHAR = 32
    CTRL_LONG = 33
    CTRL_DOUBLE = 34

    PUT_ACKT = 35
    PUT_ACKS = 36

    STSACK_STRING = 37
    CLASS_NAME = 38


class SubscriptionType(IntFlag):
    '''Subscription masks

    DBE_VALUE
    Trigger an event when a significant change in the channel's value occurs.
    (In epics-base, relies on the monitor deadband field under DCT.)

    DBE_ARCHIVE (DBE_LOG)
    Trigger an event when an archive significant change in the channel's value
    occurs.
    (In epics-base, relies on the archiver monitor deadband field under DCT.)

    DBE_ALARM
    Trigger an event when the alarm state changes

    DBE_PROPERTY
    Trigger an event when a property change (control limit, graphical limit,
    status string, enum string ...) occurs.
    '''

    DBE_VALUE = 1
    DBE_LOG = 2
    DBE_ALARM = 4
    DBE_PROPERTY = 8


string_t = MAX_STRING_SIZE * ctypes.c_char  # epicsOldString
char_t = ctypes.c_char  # epicsUint8
short_t = ctypes.c_int16  # epicsInt16
ushort_t = ctypes.c_uint16  # epicsUInt16
int_t = ctypes.c_int16  # epicsInt16
long_t = ctypes.c_int32  # epicsInt32
ulong_t = ctypes.c_uint32  # epicsUInt32
float_t = ctypes.c_float  # epicsFloat32
double_t = ctypes.c_double  # epicsFloat64


class DbrStringArray(collections.UserList):
    '''A mockup of numpy.array, intended to hold byte strings

    String arrays in numpy are special and inconvenient to work with.
    '''

    def __getitem__(self, i):
        res = self.data[i]
        return type(self)(res) if isinstance(i, slice) else res

    @classmethod
    def frombuffer(cls, buf, data_count=None):
        'Create a DbrStringArray from a buffer'
        if data_count is None:
            data_count = max((1, len(buf) // MAX_STRING_SIZE))

        def safely_find_eos():
            'Find null terminator, else MAX_STRING_SIZE/length of the string'
            try:
                return min((MAX_STRING_SIZE, buf.index(b'\00')))
            except ValueError:
                return min((MAX_STRING_SIZE, len(buf)))

        buf = bytes(buf)
        strings = cls()
        for i in range(data_count):
            strings.append(buf[:safely_find_eos()])
            buf = buf[MAX_STRING_SIZE:]

        return strings

    def tobytes(self):
        # numpy compat
        return b''.join(item[:MAX_STRING_SIZE].ljust(MAX_STRING_SIZE, b'\x00')
                        for item in self)


class DbrTypeBase(ctypes.BigEndianStructure):
    '''Base class for all DBR types'''
    _pack_ = 1
    info_fields = ()

    def to_dict(self):
        d = {field: getattr(self, field)
             for field in self.info_fields}
        if 'status' in d:
            d['status'] = AlarmStatus(d['status'])
        if 'severity' in d:
            d['severity'] = AlarmSeverity(d['severity'])
        return d

    def __repr__(self):
        formatted_args = ", ".join(["{!s}={!r}".format(k, v)
                                    for k, v in self.to_dict().items()])
        return "{}({})".format(type(self).__name__, formatted_args)


class TimeStamp(DbrTypeBase):
    '''An EPICS timestamp with 32-bit seconds and nanoseconds'''
    _fields_ = [
        ('secondsSinceEpoch', ctypes.c_uint32),
        ('nanoSeconds', ctypes.c_uint32)
    ]

    info_fields = ('timestamp', )

    @property
    def timestamp(self):
        'Timestamp as UNIX timestamp (seconds)'
        return epics_timestamp_to_unix(self.secondsSinceEpoch,
                                       self.nanoSeconds)

    @classmethod
    def from_unix_timestamp(cls, timestamp):
        sec, nano = timestamp_to_epics(timestamp)
        return cls(secondsSinceEpoch=sec, nanoSeconds=nano)

    def as_datetime(self):
        'Timestamp as a datetime'
        return datetime.datetime.utcfromtimestamp(self.timestamp)


class TimeTypeBase(DbrTypeBase):
    '''DBR_TIME_* base'''
    # access to secondsSinceEpoch and nanoSeconds:
    _anonymous_ = ('stamp', )
    info_fields = ('status', 'severity', 'timestamp')

    @property
    def timestamp(self):
        '''Unix timestamp'''
        return self.stamp.timestamp


class StatusTypeBase(DbrTypeBase):
    '''DBR_STS_* base'''
    info_fields = ('status', 'severity', )


class GraphicControlBase(DbrTypeBase):
    '''DBR_CTRL_* and DBR_GR_* base'''
    graphic_fields = ('upper_disp_limit', 'lower_disp_limit',
                      'upper_alarm_limit', 'upper_warning_limit',
                      'lower_warning_limit', 'lower_alarm_limit')
    control_fields = ('upper_ctrl_limit', 'lower_ctrl_limit')
    info_fields = ('status', 'severity', ) + graphic_fields


class GraphicControlUnits(GraphicControlBase):
    '''DBR_CTRL/DBR_GR with units'''


class ControlTypeUnits(GraphicControlUnits):
    '''DBR_CTRL with units'''
    info_fields = (GraphicControlBase.info_fields +
                   GraphicControlBase.control_fields + ('units', ))


class GraphicTypeUnits(GraphicControlUnits):
    '''DBR_GR with units'''
    info_fields = GraphicControlBase.info_fields + ('units', )


class GraphicControlPrecision(GraphicControlBase):
    '''DBR_CTRL/DBR_GR with precision and units'''


class ControlTypePrecision(GraphicControlPrecision):
    '''DBR_CTRL with precision and units'''
    info_fields = (GraphicControlBase.info_fields +
                   GraphicControlBase.control_fields +
                   ('precision', 'units', ))


class GraphicTypePrecision(GraphicControlPrecision):
    '''DBR_GR with precision and units'''
    info_fields = (GraphicControlBase.info_fields +
                   ('precision', 'units', ))


class DbrNativeValueType(DbrTypeBase):
    '''Native DBR_ types: no metadata, value only'''
    info_fields = ('value', )


# Native value types
class DBR_STRING(DbrNativeValueType):
    DBR_ID = ChannelType.STRING
    _fields_ = [('value', string_t)]


class DBR_INT(DbrNativeValueType):
    DBR_ID = ChannelType.INT
    _fields_ = [('value', int_t)]


class DBR_FLOAT(DbrNativeValueType):
    DBR_ID = ChannelType.FLOAT
    _fields_ = [('value', float_t)]


class DBR_ENUM(DbrNativeValueType):
    DBR_ID = ChannelType.ENUM
    _fields_ = [('value', ushort_t)]


class DBR_CHAR(DbrNativeValueType):
    DBR_ID = ChannelType.CHAR
    _fields_ = [('value', char_t)]


class DBR_LONG(DbrNativeValueType):
    DBR_ID = ChannelType.LONG
    _fields_ = [('value', long_t)]


class DBR_DOUBLE(DbrNativeValueType):
    DBR_ID = ChannelType.DOUBLE
    _fields_ = [('value', double_t)]


# Status types
class DBR_STS_STRING(StatusTypeBase):
    DBR_ID = ChannelType.STS_STRING
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
    ]


class DBR_STS_INT(StatusTypeBase):
    DBR_ID = ChannelType.STS_INT
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
    ]


class DBR_STS_FLOAT(StatusTypeBase):
    DBR_ID = ChannelType.STS_FLOAT
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
    ]


class DBR_STS_ENUM(StatusTypeBase):
    DBR_ID = ChannelType.STS_ENUM
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
    ]


class DBR_STS_CHAR(StatusTypeBase):
    DBR_ID = ChannelType.STS_CHAR
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
        ('RISC_pad', char_t),
    ]


class DBR_STS_LONG(StatusTypeBase):
    DBR_ID = ChannelType.STS_LONG
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
    ]


class DBR_STS_DOUBLE(StatusTypeBase):
    DBR_ID = ChannelType.STS_DOUBLE
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
        ('RISC_pad', long_t),
    ]


# Time types
class DBR_TIME_STRING(TimeTypeBase):
    DBR_ID = ChannelType.TIME_STRING
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
        ('stamp', TimeStamp),
    ]


class DBR_TIME_INT(TimeTypeBase):
    DBR_ID = ChannelType.TIME_INT
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
        ('stamp', TimeStamp),
        ('RISC_pad', short_t),
    ]


class DBR_TIME_FLOAT(TimeTypeBase):
    DBR_ID = ChannelType.TIME_FLOAT
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
        ('stamp', TimeStamp),
    ]


class DBR_TIME_ENUM(TimeTypeBase):
    DBR_ID = ChannelType.TIME_ENUM
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
        ('stamp', TimeStamp),
        ('RISC_pad', short_t),
    ]


class DBR_TIME_CHAR(TimeTypeBase):
    DBR_ID = ChannelType.TIME_CHAR
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
        ('stamp', TimeStamp),
        ('RISC_pad0', short_t),
        ('RISC_pad1', char_t),
    ]


class DBR_TIME_LONG(TimeTypeBase):
    DBR_ID = ChannelType.TIME_LONG
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
        ('stamp', TimeStamp),
    ]


class DBR_TIME_DOUBLE(TimeTypeBase):
    DBR_ID = ChannelType.TIME_DOUBLE
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
        ('stamp', TimeStamp),
        ('RISC_pad', long_t),
    ]


# DBR_GR_STRING (21) is not implemented by EPICS. - use DBR_STS_STRING


# Graphic types
class DBR_GR_INT(GraphicTypeUnits):
    DBR_ID = ChannelType.GR_INT
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
        ('units', MAX_UNITS_SIZE * char_t),
        ('upper_disp_limit', short_t),
        ('lower_disp_limit', short_t),
        ('upper_alarm_limit', short_t),
        ('upper_warning_limit', short_t),
        ('lower_warning_limit', short_t),
        ('lower_alarm_limit', short_t),
    ]


class DBR_GR_FLOAT(GraphicTypePrecision):
    DBR_ID = ChannelType.GR_FLOAT
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
        ('precision', short_t),
        ('RISC_pad0', short_t),
        ('units', MAX_UNITS_SIZE * char_t),
        ('upper_disp_limit', float_t),
        ('lower_disp_limit', float_t),
        ('upper_alarm_limit', float_t),
        ('upper_warning_limit', float_t),
        ('lower_warning_limit', float_t),
        ('lower_alarm_limit', float_t),
    ]


class _EnumWithStrings:
    @property
    def enum_strings(self):
        '''Enum byte strings as a tuple'''
        return tuple(self.strs[i].value
                     for i in range(self.no_str))

    @enum_strings.setter
    def enum_strings(self, enum_strings):
        for i, bytes_ in enumerate(enum_strings):
            bytes_ = bytes_[:MAX_ENUM_STRING_SIZE - 1]
            self.strs[i][:] = bytes_.ljust(MAX_ENUM_STRING_SIZE, b'\x00')
        self.no_str = len(enum_strings)


class DBR_GR_ENUM(GraphicControlBase, _EnumWithStrings):
    DBR_ID = ChannelType.GR_ENUM
    graphic_fields = ()
    control_fields = ()
    info_fields = ('status', 'severity', 'enum_strings', )
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
        ('no_str', short_t),  # number of strings
        ('strs', MAX_ENUM_STATES * (MAX_ENUM_STRING_SIZE * char_t)),
    ]


class DBR_GR_CHAR(GraphicTypeUnits):
    DBR_ID = ChannelType.GR_CHAR
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
        ('units', MAX_UNITS_SIZE * char_t),
        ('upper_disp_limit', char_t),
        ('lower_disp_limit', char_t),
        ('upper_alarm_limit', char_t),
        ('upper_warning_limit', char_t),
        ('lower_warning_limit', char_t),
        ('lower_alarm_limit', char_t),
        ('RISC_pad', char_t),
    ]


class DBR_GR_LONG(GraphicTypeUnits):
    DBR_ID = ChannelType.GR_LONG
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
        ('units', MAX_UNITS_SIZE * char_t),
        ('upper_disp_limit', long_t),
        ('lower_disp_limit', long_t),
        ('upper_alarm_limit', long_t),
        ('upper_warning_limit', long_t),
        ('lower_warning_limit', long_t),
        ('lower_alarm_limit', long_t),
    ]


class DBR_GR_DOUBLE(GraphicTypePrecision):
    DBR_ID = ChannelType.GR_DOUBLE
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
        ('precision', short_t),
        ('RISC_pad0', short_t),
        ('units', MAX_UNITS_SIZE * char_t),
        ('upper_disp_limit', double_t),
        ('lower_disp_limit', double_t),
        ('upper_alarm_limit', double_t),
        ('upper_warning_limit', double_t),
        ('lower_warning_limit', double_t),
        ('lower_alarm_limit', double_t),
    ]


# DBR_CTRL_STRING (28) is not implemented by lib

# Control types
class DBR_CTRL_INT(ControlTypeUnits):
    DBR_ID = ChannelType.CTRL_INT
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
        ('units', MAX_UNITS_SIZE * char_t),
        ('upper_disp_limit', short_t),
        ('lower_disp_limit', short_t),
        ('upper_alarm_limit', short_t),
        ('upper_warning_limit', short_t),
        ('lower_warning_limit', short_t),
        ('lower_alarm_limit', short_t),
        ('upper_ctrl_limit', short_t),
        ('lower_ctrl_limit', short_t),
    ]


class DBR_CTRL_FLOAT(ControlTypePrecision):
    DBR_ID = ChannelType.CTRL_FLOAT
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
        ('precision', short_t),
        ('RISC_pad0', short_t),
        ('units', MAX_UNITS_SIZE * char_t),
        ('upper_disp_limit', float_t),
        ('lower_disp_limit', float_t),
        ('upper_alarm_limit', float_t),
        ('upper_warning_limit', float_t),
        ('lower_warning_limit', float_t),
        ('lower_alarm_limit', float_t),
        ('upper_ctrl_limit', float_t),
        ('lower_ctrl_limit', float_t),
    ]


class DBR_CTRL_ENUM(GraphicControlBase, _EnumWithStrings):
    DBR_ID = ChannelType.CTRL_ENUM
    control_fields = ()
    graphic_fields = ()
    info_fields = ('status', 'severity', 'enum_strings', )

    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
        ('no_str', short_t),  # number of strings
        ('strs', MAX_ENUM_STATES * (MAX_ENUM_STRING_SIZE * char_t)),
    ]

    @property
    def enum_strings(self):
        '''Enum byte strings as a tuple'''
        return tuple(self.strs[i].value
                     for i in range(self.no_str))

    @enum_strings.setter
    def enum_strings(self, enum_strings):
        for i, bytes_ in enumerate(enum_strings):
            bytes_ = bytes_[:MAX_ENUM_STRING_SIZE - 1]
            self.strs[i][:] = bytes_.ljust(MAX_ENUM_STRING_SIZE, b'\x00')
        self.no_str = len(enum_strings)


class DBR_CTRL_CHAR(ControlTypeUnits):
    DBR_ID = ChannelType.CTRL_CHAR
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
        ('units', MAX_UNITS_SIZE * char_t),
        ('upper_disp_limit', char_t),
        ('lower_disp_limit', char_t),
        ('upper_alarm_limit', char_t),
        ('upper_warning_limit', char_t),
        ('lower_warning_limit', char_t),
        ('lower_alarm_limit', char_t),
        ('upper_ctrl_limit', char_t),
        ('lower_ctrl_limit', char_t),
        ('RISC_pad', char_t),
    ]


class DBR_CTRL_LONG(ControlTypeUnits):
    DBR_ID = ChannelType.CTRL_LONG
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
        ('units', MAX_UNITS_SIZE * char_t),
        ('upper_disp_limit', long_t),
        ('lower_disp_limit', long_t),
        ('upper_alarm_limit', long_t),
        ('upper_warning_limit', long_t),
        ('lower_warning_limit', long_t),
        ('lower_alarm_limit', long_t),
        ('upper_ctrl_limit', long_t),
        ('lower_ctrl_limit', long_t),
    ]


class DBR_CTRL_DOUBLE(ControlTypePrecision):
    DBR_ID = ChannelType.CTRL_DOUBLE
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
        ('precision', short_t),
        ('RISC_pad0', short_t),
        ('units', MAX_UNITS_SIZE * char_t),
        ('upper_disp_limit', double_t),
        ('lower_disp_limit', double_t),
        ('upper_alarm_limit', double_t),
        ('upper_warning_limit', double_t),
        ('lower_warning_limit', double_t),
        ('lower_alarm_limit', double_t),
        ('upper_ctrl_limit', double_t),
        ('lower_ctrl_limit', double_t),
    ]


# Remaining "special" types
class DbrSpecialType(DbrTypeBase):
    ...


class DBR_PUT_ACKT(DbrSpecialType):
    DBR_ID = ChannelType.PUT_ACKT
    info_fields = ('value', )
    _fields_ = [('value', ushort_t)]


class DBR_PUT_ACKS(DbrSpecialType):
    DBR_ID = ChannelType.PUT_ACKS
    info_fields = ('value', )
    _fields_ = [('value', ushort_t)]


class DBR_STSACK_STRING(DbrSpecialType):
    DBR_ID = ChannelType.STSACK_STRING
    info_fields = ('status', 'severity', 'ackt', 'acks', 'value')
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
        ('ackt', ushort_t),
        ('acks', ushort_t),
        ('value', string_t),
    ]


class DBR_CLASS_NAME(DbrSpecialType):
    DBR_ID = ChannelType.CLASS_NAME
    info_fields = ('value', )
    _fields_ = [('value', string_t)]

# End of DBR type classes


# Full mapping of promoted -> native field types, and native -> promoted types
field_types = {
    'native': {
        # Native
        ChannelType.STRING: ChannelType.STRING,
        ChannelType.INT: ChannelType.INT,
        ChannelType.FLOAT: ChannelType.FLOAT,
        ChannelType.ENUM: ChannelType.ENUM,
        ChannelType.CHAR: ChannelType.CHAR,
        ChannelType.LONG: ChannelType.LONG,
        ChannelType.DOUBLE: ChannelType.DOUBLE,

        # Status
        ChannelType.STS_STRING: ChannelType.STRING,
        ChannelType.STS_INT: ChannelType.INT,
        ChannelType.STS_FLOAT: ChannelType.FLOAT,
        ChannelType.STS_ENUM: ChannelType.ENUM,
        ChannelType.STS_CHAR: ChannelType.CHAR,
        ChannelType.STS_LONG: ChannelType.LONG,
        ChannelType.STS_DOUBLE: ChannelType.DOUBLE,

        # Time
        ChannelType.TIME_STRING: ChannelType.STRING,
        ChannelType.TIME_INT: ChannelType.INT,
        ChannelType.TIME_FLOAT: ChannelType.FLOAT,
        ChannelType.TIME_ENUM: ChannelType.ENUM,
        ChannelType.TIME_CHAR: ChannelType.CHAR,
        ChannelType.TIME_LONG: ChannelType.LONG,
        ChannelType.TIME_DOUBLE: ChannelType.DOUBLE,

        # Graphic
        ChannelType.GR_STRING: ChannelType.STRING,
        ChannelType.GR_INT: ChannelType.INT,
        ChannelType.GR_FLOAT: ChannelType.FLOAT,
        ChannelType.GR_ENUM: ChannelType.ENUM,
        ChannelType.GR_CHAR: ChannelType.CHAR,
        ChannelType.GR_LONG: ChannelType.LONG,
        ChannelType.GR_DOUBLE: ChannelType.DOUBLE,

        # Control
        ChannelType.CTRL_STRING: ChannelType.STRING,
        ChannelType.CTRL_INT: ChannelType.INT,
        ChannelType.CTRL_FLOAT: ChannelType.FLOAT,
        ChannelType.CTRL_ENUM: ChannelType.ENUM,
        ChannelType.CTRL_CHAR: ChannelType.CHAR,
        ChannelType.CTRL_LONG: ChannelType.LONG,
        ChannelType.CTRL_DOUBLE: ChannelType.DOUBLE,

        # Special
        ChannelType.PUT_ACKT: ChannelType.PUT_ACKT,
        ChannelType.PUT_ACKS: ChannelType.PUT_ACKS,
        ChannelType.STSACK_STRING: ChannelType.STSACK_STRING,
        ChannelType.CLASS_NAME: ChannelType.CLASS_NAME,
    },

    'status': {
        # Native
        ChannelType.STRING: ChannelType.STS_STRING,
        ChannelType.INT: ChannelType.STS_INT,
        ChannelType.FLOAT: ChannelType.STS_FLOAT,
        ChannelType.ENUM: ChannelType.STS_ENUM,
        ChannelType.CHAR: ChannelType.STS_CHAR,
        ChannelType.LONG: ChannelType.STS_LONG,
        ChannelType.DOUBLE: ChannelType.STS_DOUBLE,

        # Status
        ChannelType.STS_STRING: ChannelType.STS_STRING,
        ChannelType.STS_INT: ChannelType.STS_INT,
        ChannelType.STS_FLOAT: ChannelType.STS_FLOAT,
        ChannelType.STS_ENUM: ChannelType.STS_ENUM,
        ChannelType.STS_CHAR: ChannelType.STS_CHAR,
        ChannelType.STS_LONG: ChannelType.STS_LONG,
        ChannelType.STS_DOUBLE: ChannelType.STS_DOUBLE,

        # Time
        ChannelType.TIME_STRING: ChannelType.STS_STRING,
        ChannelType.TIME_INT: ChannelType.STS_INT,
        ChannelType.TIME_FLOAT: ChannelType.STS_FLOAT,
        ChannelType.TIME_ENUM: ChannelType.STS_ENUM,
        ChannelType.TIME_CHAR: ChannelType.STS_CHAR,
        ChannelType.TIME_LONG: ChannelType.STS_LONG,
        ChannelType.TIME_DOUBLE: ChannelType.STS_DOUBLE,

        # Graphic
        ChannelType.STS_STRING: ChannelType.STS_STRING,
        ChannelType.GR_INT: ChannelType.STS_INT,
        ChannelType.GR_FLOAT: ChannelType.STS_FLOAT,
        ChannelType.GR_ENUM: ChannelType.STS_ENUM,
        ChannelType.GR_CHAR: ChannelType.STS_CHAR,
        ChannelType.GR_LONG: ChannelType.STS_LONG,
        ChannelType.GR_DOUBLE: ChannelType.STS_DOUBLE,

        # Control
        # ChannelType.TIME_STRING: ChannelType.STS_STRING,
        ChannelType.CTRL_INT: ChannelType.STS_INT,
        ChannelType.CTRL_FLOAT: ChannelType.STS_FLOAT,
        ChannelType.CTRL_ENUM: ChannelType.STS_ENUM,
        ChannelType.CTRL_CHAR: ChannelType.STS_CHAR,
        ChannelType.CTRL_LONG: ChannelType.STS_LONG,
        ChannelType.CTRL_DOUBLE: ChannelType.STS_DOUBLE,

        # Special types
        ChannelType.PUT_ACKT: ChannelType.PUT_ACKT,
        ChannelType.PUT_ACKS: ChannelType.PUT_ACKS,
        ChannelType.STSACK_STRING: ChannelType.STSACK_STRING,
        ChannelType.CLASS_NAME: ChannelType.CLASS_NAME,
    },

    'time': {
        # Native
        ChannelType.STRING: ChannelType.TIME_STRING,
        ChannelType.INT: ChannelType.TIME_INT,
        ChannelType.FLOAT: ChannelType.TIME_FLOAT,
        ChannelType.ENUM: ChannelType.TIME_ENUM,
        ChannelType.CHAR: ChannelType.TIME_CHAR,
        ChannelType.LONG: ChannelType.TIME_LONG,
        ChannelType.DOUBLE: ChannelType.TIME_DOUBLE,

        # Status
        ChannelType.STS_STRING: ChannelType.TIME_STRING,
        ChannelType.STS_INT: ChannelType.TIME_INT,
        ChannelType.STS_FLOAT: ChannelType.TIME_FLOAT,
        ChannelType.STS_ENUM: ChannelType.TIME_ENUM,
        ChannelType.STS_CHAR: ChannelType.TIME_CHAR,
        ChannelType.STS_LONG: ChannelType.TIME_LONG,
        ChannelType.STS_DOUBLE: ChannelType.TIME_DOUBLE,

        # Time
        ChannelType.TIME_STRING: ChannelType.TIME_STRING,
        ChannelType.TIME_INT: ChannelType.TIME_INT,
        ChannelType.TIME_FLOAT: ChannelType.TIME_FLOAT,
        ChannelType.TIME_ENUM: ChannelType.TIME_ENUM,
        ChannelType.TIME_CHAR: ChannelType.TIME_CHAR,
        ChannelType.TIME_LONG: ChannelType.TIME_LONG,
        ChannelType.TIME_DOUBLE: ChannelType.TIME_DOUBLE,

        # Graphic
        ChannelType.STS_STRING: ChannelType.TIME_STRING,
        ChannelType.GR_INT: ChannelType.TIME_INT,
        ChannelType.GR_FLOAT: ChannelType.TIME_FLOAT,
        ChannelType.GR_ENUM: ChannelType.TIME_ENUM,
        ChannelType.GR_CHAR: ChannelType.TIME_CHAR,
        ChannelType.GR_LONG: ChannelType.TIME_LONG,
        ChannelType.GR_DOUBLE: ChannelType.TIME_DOUBLE,

        # Control
        # ChannelType.TIME_STRING: ChannelType.TIME_STRING,
        ChannelType.CTRL_INT: ChannelType.TIME_INT,
        ChannelType.CTRL_FLOAT: ChannelType.TIME_FLOAT,
        ChannelType.CTRL_ENUM: ChannelType.TIME_ENUM,
        ChannelType.CTRL_CHAR: ChannelType.TIME_CHAR,
        ChannelType.CTRL_LONG: ChannelType.TIME_LONG,
        ChannelType.CTRL_DOUBLE: ChannelType.TIME_DOUBLE,

        # Special types
        ChannelType.PUT_ACKT: ChannelType.PUT_ACKT,
        ChannelType.PUT_ACKS: ChannelType.PUT_ACKS,
        ChannelType.STSACK_STRING: ChannelType.STSACK_STRING,
        ChannelType.CLASS_NAME: ChannelType.CLASS_NAME,
    },

    'graphic': {
        # Native
        ChannelType.STRING: ChannelType.STS_STRING,
        ChannelType.INT: ChannelType.GR_INT,
        ChannelType.FLOAT: ChannelType.GR_FLOAT,
        ChannelType.ENUM: ChannelType.GR_ENUM,
        ChannelType.CHAR: ChannelType.GR_CHAR,
        ChannelType.LONG: ChannelType.GR_LONG,
        ChannelType.DOUBLE: ChannelType.GR_DOUBLE,

        # Status
        ChannelType.STS_STRING: ChannelType.STS_STRING,
        ChannelType.STS_INT: ChannelType.GR_INT,
        ChannelType.STS_FLOAT: ChannelType.GR_FLOAT,
        ChannelType.STS_ENUM: ChannelType.GR_ENUM,
        ChannelType.STS_CHAR: ChannelType.GR_CHAR,
        ChannelType.STS_LONG: ChannelType.GR_LONG,
        ChannelType.STS_DOUBLE: ChannelType.GR_DOUBLE,

        # Time
        ChannelType.TIME_STRING: ChannelType.STS_STRING,
        ChannelType.TIME_INT: ChannelType.GR_INT,
        ChannelType.TIME_FLOAT: ChannelType.GR_FLOAT,
        ChannelType.TIME_ENUM: ChannelType.GR_ENUM,
        ChannelType.TIME_CHAR: ChannelType.GR_CHAR,
        ChannelType.TIME_LONG: ChannelType.GR_LONG,
        ChannelType.TIME_DOUBLE: ChannelType.GR_DOUBLE,

        # Graphic
        ChannelType.STS_STRING: ChannelType.STS_STRING,
        ChannelType.GR_INT: ChannelType.GR_INT,
        ChannelType.GR_FLOAT: ChannelType.GR_FLOAT,
        ChannelType.GR_ENUM: ChannelType.GR_ENUM,
        ChannelType.GR_CHAR: ChannelType.GR_CHAR,
        ChannelType.GR_LONG: ChannelType.GR_LONG,
        ChannelType.GR_DOUBLE: ChannelType.GR_DOUBLE,

        # Control
        # ChannelType.TIME_STRING: ChannelType.STS_STRING,
        ChannelType.CTRL_INT: ChannelType.GR_INT,
        ChannelType.CTRL_FLOAT: ChannelType.GR_FLOAT,
        ChannelType.CTRL_ENUM: ChannelType.GR_ENUM,
        ChannelType.CTRL_CHAR: ChannelType.GR_CHAR,
        ChannelType.CTRL_LONG: ChannelType.GR_LONG,
        ChannelType.CTRL_DOUBLE: ChannelType.GR_DOUBLE,

        # Special types
        ChannelType.PUT_ACKT: ChannelType.PUT_ACKT,
        ChannelType.PUT_ACKS: ChannelType.PUT_ACKS,
        ChannelType.STSACK_STRING: ChannelType.STSACK_STRING,
        ChannelType.CLASS_NAME: ChannelType.CLASS_NAME,
    },

    'control': {
        # Native
        ChannelType.STRING: ChannelType.TIME_STRING,
        ChannelType.INT: ChannelType.CTRL_INT,
        ChannelType.FLOAT: ChannelType.CTRL_FLOAT,
        ChannelType.ENUM: ChannelType.CTRL_ENUM,
        ChannelType.CHAR: ChannelType.CTRL_CHAR,
        ChannelType.LONG: ChannelType.CTRL_LONG,
        ChannelType.DOUBLE: ChannelType.CTRL_DOUBLE,

        # Status
        ChannelType.STS_STRING: ChannelType.TIME_STRING,
        ChannelType.STS_INT: ChannelType.CTRL_INT,
        ChannelType.STS_FLOAT: ChannelType.CTRL_FLOAT,
        ChannelType.STS_ENUM: ChannelType.CTRL_ENUM,
        ChannelType.STS_CHAR: ChannelType.CTRL_CHAR,
        ChannelType.STS_LONG: ChannelType.CTRL_LONG,
        ChannelType.STS_DOUBLE: ChannelType.CTRL_DOUBLE,

        # Time
        ChannelType.TIME_STRING: ChannelType.TIME_STRING,
        ChannelType.TIME_INT: ChannelType.CTRL_INT,
        ChannelType.TIME_FLOAT: ChannelType.CTRL_FLOAT,
        ChannelType.TIME_ENUM: ChannelType.CTRL_ENUM,
        ChannelType.TIME_CHAR: ChannelType.CTRL_CHAR,
        ChannelType.TIME_LONG: ChannelType.CTRL_LONG,
        ChannelType.TIME_DOUBLE: ChannelType.CTRL_DOUBLE,

        # Graphic
        ChannelType.STS_STRING: ChannelType.TIME_STRING,
        ChannelType.GR_INT: ChannelType.CTRL_INT,
        ChannelType.GR_FLOAT: ChannelType.CTRL_FLOAT,
        ChannelType.GR_ENUM: ChannelType.CTRL_ENUM,
        ChannelType.GR_CHAR: ChannelType.CTRL_CHAR,
        ChannelType.GR_LONG: ChannelType.CTRL_LONG,
        ChannelType.GR_DOUBLE: ChannelType.CTRL_DOUBLE,

        # Control
        # ChannelType.TIME_STRING: ChannelType.TIME_STRING,
        ChannelType.CTRL_INT: ChannelType.CTRL_INT,
        ChannelType.CTRL_FLOAT: ChannelType.CTRL_FLOAT,
        ChannelType.CTRL_ENUM: ChannelType.CTRL_ENUM,
        ChannelType.CTRL_CHAR: ChannelType.CTRL_CHAR,
        ChannelType.CTRL_LONG: ChannelType.CTRL_LONG,
        ChannelType.CTRL_DOUBLE: ChannelType.CTRL_DOUBLE,

        # Special types
        ChannelType.PUT_ACKT: ChannelType.PUT_ACKT,
        ChannelType.PUT_ACKS: ChannelType.PUT_ACKS,
        ChannelType.STSACK_STRING: ChannelType.STSACK_STRING,
        ChannelType.CLASS_NAME: ChannelType.CLASS_NAME,
    },
}


# All native types available
native_types = {ChannelType.STRING, ChannelType.INT, ChannelType.FLOAT,
                ChannelType.ENUM, ChannelType.CHAR, ChannelType.LONG,
                ChannelType.DOUBLE}

# Special types without any corresponding promoted versions
special_types = {ChannelType.PUT_ACKT, ChannelType.PUT_ACKS,
                 ChannelType.STSACK_STRING, ChannelType.CLASS_NAME}

# ChannelTypes grouped by included metadata
status_types = set(field_types['status'].values()) - set(special_types)
time_types = set(field_types['time'].values()) - set(special_types)
graphical_types = (set(field_types['graphic'].values()) - set(special_types) -
                   {ChannelType.STS_STRING})
control_types = (set(field_types['control'].values()) - set(special_types) -
                 {ChannelType.TIME_STRING})

# ChannelTypes grouped by value data type
char_types = {ChannelType.CHAR, ChannelType.TIME_CHAR, ChannelType.CTRL_CHAR,
              ChannelType.STS_CHAR
              }

string_types = {ChannelType.STRING, ChannelType.TIME_STRING,
                ChannelType.CTRL_STRING, ChannelType.STS_STRING
                }

int_types = {ChannelType.INT, ChannelType.TIME_INT, ChannelType.CTRL_INT,
             ChannelType.LONG, ChannelType.TIME_LONG, ChannelType.CTRL_LONG,
             }

float_types = {ChannelType.FLOAT, ChannelType.TIME_FLOAT,
               ChannelType.CTRL_FLOAT,
               ChannelType.DOUBLE, ChannelType.TIME_DOUBLE,
               ChannelType.CTRL_DOUBLE,
               }

enum_types = {ChannelType.ENUM, ChannelType.STS_ENUM, ChannelType.TIME_ENUM,
              ChannelType.CTRL_ENUM
              }

char_types = {ChannelType.CHAR, ChannelType.TIME_CHAR, ChannelType.CTRL_CHAR}

native_float_types = {ChannelType.FLOAT, ChannelType.DOUBLE}

native_int_types = {ChannelType.INT, ChannelType.CHAR, ChannelType.LONG,
                    ChannelType.ENUM
                    }

# map of Epics DBR types to ctypes types
DBR_TYPES = {
    cls.DBR_ID: cls
    for name, cls in globals().items()
    if (name.startswith('DBR_') and issubclass(cls, DbrTypeBase) and
        hasattr(cls, 'DBR_ID'))
}

# Unimplemented STRING types are mapped to DBR_TIME_STRING
DBR_TYPES[ChannelType.GR_STRING] = DBR_STS_STRING
DBR_TYPES[ChannelType.CTRL_STRING] = DBR_TIME_STRING


def native_type(ftype):
    '''return native field type from TIME or CTRL variant'''
    return field_types['native'][ftype]


def epics_timestamp_to_unix(seconds_since_epoch, nano_seconds):
    '''UNIX timestamp (seconds) from Epics TimeStamp structure'''
    return (EPICS2UNIX_EPOCH + seconds_since_epoch + 1.e-6 *
            int(1.e-3 * nano_seconds))


def timestamp_to_epics(ts):
    '''Python timestamp from EPICS TimeStamp structure'''
    if isinstance(ts, float):
        ts = datetime.datetime.utcfromtimestamp(ts)
    dt = ts - EPICS_EPOCH
    return int(dt.total_seconds()), int(dt.microseconds * 1e3)
