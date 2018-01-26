# Manually written with reference to:
# http://www.aps.anl.gov/epics/base/R3-16/0-docs/CAproto/index.html#payload-data-types
# https://github.com/epics-base/epics-base/blob/813166128eae1240cdd643869808abe1c4621321/src/ca/client/db_access.h

# The organizational code, making use of Enum, comes from pypvasync by Kenneth
# Lauer.

import array
import ctypes
import datetime
from enum import IntEnum
from ._constants import (EPICS2UNIX_EPOCH, EPICS_EPOCH, MAX_STRING_SIZE,
                         MAX_UNITS_SIZE, MAX_ENUM_STRING_SIZE, MAX_ENUM_STATES)

try:
    import numpy
except ImportError:
    USE_NUMPY = False
else:
    USE_NUMPY = True


class AccessRights(IntEnum):
    NO_ACCESS = 0
    READ = 1
    WRITE = 2
    READ_WRITE = 3


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


class SubscriptionType(IntEnum):
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


def native_type(ftype):
    '''return native field type from TIME or CTRL variant'''
    return _native_map[ftype]


def promote_type(ftype, *, use_status=False, use_time=False, use_ctrl=False,
                 use_gr=False):
    """Promotes a native field type to its STS, TIME, CTRL, or GR variant.

    Returns
    -------
    ftype : int
        the promoted field value.
    """
    if sum([use_status, use_time, use_ctrl, use_gr]) > 1:
        raise ValueError("Only one of the kwargs may be True.")
    elif ftype in special_types:
        # Special types have no promoted versions
        return ftype

    if _native_map:  # only during initialization
        # Demote it back to a native type, if necessary
        ftype = _native_map[ChannelType(ftype)]

    # Use the fact that the types are ordered in blocks and that the STRING
    # variant is the first element of each block.
    if use_ctrl:
        if ftype == ChannelType.STRING:
            return ChannelType.TIME_STRING
        ftype += ChannelType.CTRL_STRING
    elif use_time:
        ftype += ChannelType.TIME_STRING
    elif use_status:
        ftype += ChannelType.STS_STRING
    elif use_gr:
        if ftype == ChannelType.STRING:
            return ChannelType.STS_STRING
        ftype += ChannelType.GR_STRING
    return ChannelType(ftype)


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


def array_type_code(native_type):
    '''Get an array.array type code for a given native type'''
    return _array_type_code_map[native_type]


def native_to_builtin(value, native_type, data_count):
    '''Convert from a native EPICS DBR type to a builtin Python type

    Notes:
     - A waveform of characters is just a bytestring.
     - A waveform of strings is an array whose elements are fixed-length (40-
       character) strings.
     - Enums are just integers that happen to have special significance.
     - Everything else is, straightforwardly, an array of numbers.
    '''

    if USE_NUMPY:
        # Return an ndarray
        dt = _numpy_map[native_type]
        if native_type == ChannelType.STRING and len(value) < MAX_STRING_SIZE:
            # caput behaves this way
            return numpy.frombuffer(
                bytes(value).ljust(MAX_STRING_SIZE, b'\x00'), dtype=dt)

        return numpy.frombuffer(value, dtype=dt)
    else:
        # TODO
        raise NotImplementedError("the non-numpy version has not been "
                                  "written yet")


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
    _fields_ = [('secondsSinceEpoch', ctypes.c_uint32),
                ('nanoSeconds', ctypes.c_uint32)]

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
    _fields_ = [('status', short_t),
                ('severity', short_t),
                ('stamp', TimeStamp)
                ]
    info_fields = ('status', 'severity', 'timestamp')

    @property
    def timestamp(self):
        '''Unix timestamp'''
        return self.stamp.timestamp


class StatusTypeBase(DbrTypeBase):
    '''DBR_STS_* base'''
    info_fields = ('status', 'severity', )
    _fields_ = [('status', short_t),
                ('severity', short_t)
                ]


class GraphicControlBase(DbrTypeBase):
    '''DBR_CTRL_* and DBR_GR_* base'''
    graphic_fields = ('upper_disp_limit', 'lower_disp_limit',
                      'upper_alarm_limit', 'upper_warning_limit',
                      'lower_warning_limit', 'lower_alarm_limit')
    control_fields = ('upper_ctrl_limit', 'lower_ctrl_limit')
    info_fields = ('status', 'severity', ) + graphic_fields
    _fields_ = [('status', short_t),
                ('severity', short_t)
                ]

    @classmethod
    def build_control_fields(cls, data_type):
        '''Build list of _fields_ for a specific data_type'''
        return [(field, data_type) for field in
                cls.graphic_fields + cls.control_fields]

    @classmethod
    def build_graphic_fields(cls, data_type):
        '''Build list of _fields_ for a specific data_type'''
        return [(field, data_type) for field in cls.graphic_fields]


class GraphicControlUnits(GraphicControlBase):
    '''DBR_CTRL/DBR_GR with units'''
    _fields_ = [('units', char_t * MAX_UNITS_SIZE),
                ]


class ControlTypeUnits(GraphicControlUnits):
    '''DBR_CTRL with units'''
    info_fields = (GraphicControlBase.info_fields +
                   GraphicControlBase.control_fields + ('units', ))


class GraphicTypeUnits(GraphicControlUnits):
    '''DBR_GR with units'''
    info_fields = GraphicControlBase.info_fields + ('units', )


class GraphicControlPrecision(GraphicControlBase):
    '''DBR_CTRL/DBR_GR with precision and units'''
    _fields_ = [('precision', short_t),
                ('RISC_pad0', short_t),
                ('units', char_t * MAX_UNITS_SIZE),
                ]


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


class DBR_STS_INT(StatusTypeBase):
    DBR_ID = ChannelType.STS_INT


class DBR_STS_FLOAT(StatusTypeBase):
    DBR_ID = ChannelType.STS_FLOAT


class DBR_STS_ENUM(StatusTypeBase):
    DBR_ID = ChannelType.STS_ENUM


class DBR_STS_CHAR(StatusTypeBase):
    DBR_ID = ChannelType.STS_CHAR
    _fields_ = [
        ('RISC_pad', char_t),
    ]


class DBR_STS_LONG(StatusTypeBase):
    DBR_ID = ChannelType.STS_LONG


class DBR_STS_DOUBLE(StatusTypeBase):
    DBR_ID = ChannelType.STS_DOUBLE
    _fields_ = [
        ('RISC_pad', long_t),
    ]


# Time types
class DBR_TIME_STRING(TimeTypeBase):
    DBR_ID = ChannelType.TIME_STRING
    _fields_ = []


class DBR_TIME_INT(TimeTypeBase):
    DBR_ID = ChannelType.TIME_INT
    _fields_ = [
        ('RISC_pad', short_t),
    ]


class DBR_TIME_FLOAT(TimeTypeBase):
    DBR_ID = ChannelType.TIME_FLOAT
    _fields_ = []


class DBR_TIME_ENUM(TimeTypeBase):
    DBR_ID = ChannelType.TIME_ENUM
    _fields_ = [
        ('RISC_pad', short_t),
    ]


class DBR_TIME_CHAR(TimeTypeBase):
    DBR_ID = ChannelType.TIME_CHAR
    _fields_ = [
        ('RISC_pad0', short_t),
        ('RISC_pad1', char_t),
    ]


class DBR_TIME_LONG(TimeTypeBase):
    DBR_ID = ChannelType.TIME_LONG
    _fields_ = []


class DBR_TIME_DOUBLE(TimeTypeBase):
    DBR_ID = ChannelType.TIME_DOUBLE
    _fields_ = [
        ('RISC_pad', long_t),
    ]


# DBR_GR_STRING (21) is not implemented by EPICS. - use DBR_STS_STRING


# Graphic types
class DBR_GR_INT(GraphicTypeUnits):
    DBR_ID = ChannelType.GR_INT
    _fields_ = GraphicTypeUnits.build_graphic_fields(short_t)


class DBR_GR_FLOAT(GraphicTypePrecision):
    DBR_ID = ChannelType.GR_FLOAT
    _fields_ = GraphicTypeUnits.build_graphic_fields(float_t)


class DBR_GR_ENUM(GraphicControlBase):
    DBR_ID = ChannelType.GR_ENUM
    graphic_fields = ()
    control_fields = ()
    info_fields = ('status', 'severity', 'enum_strings', )
    _fields_ = [
        ('no_str', short_t),  # number of strings
        ('strs', MAX_ENUM_STATES * (MAX_ENUM_STRING_SIZE * char_t)),
    ]

    @property
    def enum_strings(self):
        '''Enum byte strings as a tuple'''
        return tuple(self.strs[i].value
                     for i in range(self.no_str))


class DBR_GR_CHAR(GraphicTypeUnits):
    DBR_ID = ChannelType.GR_CHAR
    _fields_ = (GraphicTypeUnits.build_graphic_fields(char_t) +
                [('RISC_pad', char_t)])


class DBR_GR_LONG(GraphicTypeUnits):
    DBR_ID = ChannelType.GR_LONG
    _fields_ = GraphicTypeUnits.build_graphic_fields(long_t)


class DBR_GR_DOUBLE(GraphicTypePrecision):
    DBR_ID = ChannelType.GR_DOUBLE
    _fields_ = GraphicTypePrecision.build_graphic_fields(double_t)


# DBR_CTRL_STRING (28) is not implemented by libca.

# Control types
class DBR_CTRL_INT(ControlTypeUnits):
    DBR_ID = ChannelType.CTRL_INT
    _fields_ = ControlTypeUnits.build_control_fields(short_t)


class DBR_CTRL_FLOAT(ControlTypePrecision):
    DBR_ID = ChannelType.CTRL_FLOAT
    _fields_ = ControlTypePrecision.build_control_fields(float_t)


class DBR_CTRL_ENUM(GraphicControlBase):
    DBR_ID = ChannelType.CTRL_ENUM
    control_fields = ()
    graphic_fields = ()
    info_fields = ('status', 'severity', 'enum_strings', )

    _fields_ = [('no_str', short_t),
                ('strs', (char_t * MAX_ENUM_STRING_SIZE) * MAX_ENUM_STATES),
                ]

    @property
    def enum_strings(self):
        '''Enum byte strings as a tuple'''
        return tuple(self.strs[i].value
                     for i in range(self.no_str))


class DBR_CTRL_CHAR(ControlTypeUnits):
    DBR_ID = ChannelType.CTRL_CHAR
    _fields_ = (ControlTypeUnits.build_control_fields(char_t) +
                [('RISC_pad', char_t)])


class DBR_CTRL_LONG(ControlTypeUnits):
    DBR_ID = ChannelType.CTRL_LONG
    _fields_ = ControlTypeUnits.build_control_fields(long_t)


class DBR_CTRL_DOUBLE(ControlTypePrecision):
    DBR_ID = ChannelType.CTRL_DOUBLE
    _fields_ = ControlTypePrecision.build_control_fields(double_t)


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


# All native types available
native_types = (ChannelType.STRING, ChannelType.INT, ChannelType.FLOAT,
                ChannelType.ENUM, ChannelType.CHAR, ChannelType.LONG,
                ChannelType.DOUBLE)

# Special types without any corresponding promoted versions
special_types = (ChannelType.PUT_ACKS, ChannelType.PUT_ACKS,
                 ChannelType.STSACK_STRING, ChannelType.CLASS_NAME)

# Map of promoted types to native types, to be filled below
_native_map = {}

# ChannelTypes grouped by included metadata
status_types = tuple(promote_type(nt, use_status=True) for nt in native_types)
time_types = tuple(promote_type(nt, use_time=True) for nt in native_types)
graphical_types = tuple(promote_type(nt, use_gr=True) for nt in native_types
                        if nt != ChannelType.STRING)
control_types = tuple(promote_type(nt, use_ctrl=True) for nt in native_types
                      if nt != ChannelType.STRING)

# ChannelTypes grouped by value data type
char_types = (ChannelType.CHAR, ChannelType.TIME_CHAR, ChannelType.CTRL_CHAR,
              ChannelType.STS_CHAR)

string_types = (ChannelType.STRING, ChannelType.TIME_STRING,
                ChannelType.CTRL_STRING, ChannelType.STS_STRING)

int_types = (ChannelType.INT, ChannelType.TIME_INT, ChannelType.CTRL_INT,
             ChannelType.CTRL_INT, ChannelType.LONG, ChannelType.TIME_LONG,
             ChannelType.CTRL_LONG, ChannelType.CTRL_LONG)

float_types = (ChannelType.FLOAT, ChannelType.TIME_FLOAT,
               ChannelType.CTRL_FLOAT, ChannelType.CTRL_FLOAT,
               ChannelType.DOUBLE, ChannelType.TIME_DOUBLE,
               ChannelType.CTRL_DOUBLE, ChannelType.CTRL_DOUBLE)

enum_types = (ChannelType.ENUM, ChannelType.STS_ENUM, ChannelType.TIME_ENUM,
              ChannelType.CTRL_ENUM)
char_types = (ChannelType.CHAR, ChannelType.TIME_CHAR, ChannelType.CTRL_CHAR)
native_float_types = (ChannelType.FLOAT, ChannelType.DOUBLE)
native_int_types = (ChannelType.INT, ChannelType.CHAR, ChannelType.LONG,
                    ChannelType.ENUM)

# Fill in the map of promoted types to native types
_native_map.update({promote_type(native_type, **kw): native_type
                    for kw in [dict(),
                               dict(use_status=True),
                               dict(use_time=True),
                               dict(use_gr=True),
                               dict(use_ctrl=True)]
                    for native_type in native_types
                    })

# Special types need to be added as well:
_native_map.update({
    ChannelType.GR_STRING: ChannelType.STRING,
    ChannelType.CTRL_STRING: ChannelType.STRING,

    ChannelType.PUT_ACKS: ChannelType.PUT_ACKS,
    ChannelType.PUT_ACKT: ChannelType.PUT_ACKT,
    ChannelType.STSACK_STRING: ChannelType.STSACK_STRING,
    ChannelType.CLASS_NAME: ChannelType.CLASS_NAME,
})

# map of Epics DBR types to ctypes types
DBR_TYPES = {cls.DBR_ID: cls
             for name, cls in globals().items()
             if (name.startswith('DBR_') and issubclass(cls, DbrTypeBase)
                 and hasattr(cls, 'DBR_ID'))
             }

# Unimplemented STRING types are mapped to DBR_TIME_STRING
DBR_TYPES[ChannelType.GR_STRING] = DBR_STS_STRING
DBR_TYPES[ChannelType.CTRL_STRING] = DBR_TIME_STRING


if USE_NUMPY:
    _numpy_map = {
        ch_type: numpy.dtype(dtype).newbyteorder('>')
        for ch_type, dtype in
        [(ChannelType.INT, numpy.int16),
         (ChannelType.FLOAT, numpy.float32),
         (ChannelType.ENUM, numpy.uint16),
         (ChannelType.CHAR, numpy.uint8),
         (ChannelType.LONG, numpy.int32),
         (ChannelType.DOUBLE, numpy.float64),
         (ChannelType.STRING, '>S40'),
         (ChannelType.CHAR, 'b'),
         (ChannelType.STSACK_STRING, numpy.uint8),
         (ChannelType.CLASS_NAME, numpy.uint8),
         (ChannelType.PUT_ACKT, numpy.ushort),
         (ChannelType.PUT_ACKS, numpy.ushort),
         ]
    }


_array_type_code_map = {
    ChannelType.STRING: 'B',  # TO DO
    ChannelType.INT: 'h',
    ChannelType.FLOAT: 'f',
    ChannelType.ENUM: 'H',
    ChannelType.CHAR: 'b',
    ChannelType.LONG: 'i',
    ChannelType.DOUBLE: 'd',

    ChannelType.STSACK_STRING: 'b',
    ChannelType.CLASS_NAME: 'b',

    ChannelType.PUT_ACKS: 'H',  # ushort_t
    ChannelType.PUT_ACKT: 'H',
}

for _type in set(native_types) - set([ChannelType.STRING]):
    assert (array.array(_array_type_code_map[_type]).itemsize ==
            ctypes.sizeof(DBR_TYPES[_type])), '{!r} check failed'.format(_type)

del _type
