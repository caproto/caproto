import ctypes
import pytest

import caproto as ca
from caproto._constants import (MAX_STRING_SIZE, MAX_UNITS_SIZE,
                                MAX_ENUM_STATES, MAX_ENUM_STRING_SIZE)

string_t = MAX_STRING_SIZE * ctypes.c_char
char_t = ctypes.c_char
short_t = ctypes.c_int16
ushort_t = ctypes.c_uint16
int_t = ctypes.c_int16
long_t = ctypes.c_int32
ulong_t = ctypes.c_uint32
float_t = ctypes.c_float
double_t = ctypes.c_double


class DBR_STRING(ctypes.BigEndianStructure):
    DBR_ID = 0
    _pack_ = 1
    _fields_ = [
        ('value', string_t),
    ]


class DBR_INT(ctypes.BigEndianStructure):
    DBR_ID = 1
    _pack_ = 1
    _fields_ = [
        ('value', int_t),
    ]


class DBR_FLOAT(ctypes.BigEndianStructure):
    DBR_ID = 2
    _pack_ = 1
    _fields_ = [
        ('value', float_t),
    ]


class DBR_ENUM(ctypes.BigEndianStructure):
    DBR_ID = 3
    _pack_ = 1
    _fields_ = [
        ('value', ushort_t),
    ]


class DBR_CHAR(ctypes.BigEndianStructure):
    DBR_ID = 4
    _pack_ = 1
    _fields_ = [
        ('value', char_t),
    ]


class DBR_LONG(ctypes.BigEndianStructure):
    DBR_ID = 5
    _pack_ = 1
    _fields_ = [
        ('value', long_t),
    ]


class DBR_DOUBLE(ctypes.BigEndianStructure):
    DBR_ID = 6
    _pack_ = 1
    _fields_ = [
        ('value', double_t),
    ]


class DBR_STS_STRING(ctypes.BigEndianStructure):
    DBR_ID = 7
    _pack_ = 1
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
    ]


class DBR_STS_INT(ctypes.BigEndianStructure):
    DBR_ID = 8
    _pack_ = 1
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
    ]


class DBR_STS_FLOAT(ctypes.BigEndianStructure):
    DBR_ID = 9
    _pack_ = 1
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
    ]


class DBR_STS_ENUM(ctypes.BigEndianStructure):
    DBR_ID = 10
    _pack_ = 1
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
    ]


class DBR_STS_CHAR(ctypes.BigEndianStructure):
    DBR_ID = 11
    _pack_ = 1
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
        ('RISC_pad', char_t),
    ]


class DBR_STS_LONG(ctypes.BigEndianStructure):
    DBR_ID = 12
    _pack_ = 1
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
    ]


class DBR_STS_DOUBLE(ctypes.BigEndianStructure):
    DBR_ID = 13
    _pack_ = 1
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
        ('RISC_pad', long_t),
    ]


class DBR_TIME_STRING(ctypes.BigEndianStructure):
    DBR_ID = 14
    _pack_ = 1
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
        ('secondsSinceEpoch', ctypes.c_uint32),
        ('nanoSeconds', ctypes.c_uint32),
    ]


class DBR_TIME_INT(ctypes.BigEndianStructure):
    DBR_ID = 15
    _pack_ = 1
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
        ('secondsSinceEpoch', ctypes.c_uint32),
        ('nanoSeconds', ctypes.c_uint32),
        ('RISC_pad', short_t),
    ]


class DBR_TIME_FLOAT(ctypes.BigEndianStructure):
    DBR_ID = 16
    _pack_ = 1
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
        ('secondsSinceEpoch', ctypes.c_uint32),
        ('nanoSeconds', ctypes.c_uint32),
    ]


class DBR_TIME_ENUM(ctypes.BigEndianStructure):
    DBR_ID = 17
    _pack_ = 1
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
        ('secondsSinceEpoch', ctypes.c_uint32),
        ('nanoSeconds', ctypes.c_uint32),
        ('RISC_pad', short_t),
    ]


class DBR_TIME_CHAR(ctypes.BigEndianStructure):
    DBR_ID = 18
    _pack_ = 1
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
        ('secondsSinceEpoch', ctypes.c_uint32),
        ('nanoSeconds', ctypes.c_uint32),
        ('RISC_pad0', short_t),
        ('RISC_pad1', char_t),
    ]


class DBR_TIME_LONG(ctypes.BigEndianStructure):
    DBR_ID = 19
    _pack_ = 1
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
        ('secondsSinceEpoch', ctypes.c_uint32),
        ('nanoSeconds', ctypes.c_uint32),
    ]


class DBR_TIME_DOUBLE(ctypes.BigEndianStructure):
    DBR_ID = 20
    _pack_ = 1
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
        ('secondsSinceEpoch', ctypes.c_uint32),
        ('nanoSeconds', ctypes.c_uint32),
        ('RISC_pad', long_t),
    ]


class DBR_GR_INT(ctypes.BigEndianStructure):
    DBR_ID = 22
    _pack_ = 1
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


class DBR_GR_FLOAT(ctypes.BigEndianStructure):
    DBR_ID = 23
    _pack_ = 1
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


class DBR_GR_ENUM(ctypes.BigEndianStructure):
    DBR_ID = 24
    _pack_ = 1
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
        ('no_str', short_t),  # number of strings
        ('strs', MAX_ENUM_STATES * (MAX_ENUM_STRING_SIZE * char_t)),
    ]


class DBR_GR_CHAR(ctypes.BigEndianStructure):
    DBR_ID = 25
    _pack_ = 1
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


class DBR_GR_LONG(ctypes.BigEndianStructure):
    DBR_ID = 26
    _pack_ = 1
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


class DBR_GR_DOUBLE(ctypes.BigEndianStructure):
    DBR_ID = 27
    _pack_ = 1
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


class DBR_CTRL_INT(ctypes.BigEndianStructure):
    DBR_ID = 29
    _pack_ = 1
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


class DBR_CTRL_FLOAT(ctypes.BigEndianStructure):
    DBR_ID = 30
    _pack_ = 1
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


class DBR_CTRL_ENUM(ctypes.BigEndianStructure):
    DBR_ID = 31
    _pack_ = 1
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
        ('no_str', short_t),  # number of strings
        ('strs', MAX_ENUM_STATES * (MAX_ENUM_STRING_SIZE * char_t)),
    ]


class DBR_CTRL_CHAR(ctypes.BigEndianStructure):
    DBR_ID = 32
    _pack_ = 1
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


class DBR_CTRL_LONG(ctypes.BigEndianStructure):
    DBR_ID = 33
    _pack_ = 1
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


class DBR_CTRL_DOUBLE(ctypes.BigEndianStructure):
    DBR_ID = 34
    _pack_ = 1
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


class DBR_PUT_ACKT(ctypes.BigEndianStructure):
    DBR_ID = 35
    _pack_ = 1
    _fields_ = [
        ('value', ushort_t),
    ]


class DBR_PUT_ACKS(ctypes.BigEndianStructure):
    DBR_ID = 36
    _pack_ = 1
    _fields_ = [
        ('value', ushort_t),
    ]


class DBR_STSACK_STRING(ctypes.BigEndianStructure):
    DBR_ID = 37
    _pack_ = 1
    _fields_ = [
        ('status', short_t),
        ('severity', short_t),
        ('ackt', ushort_t),
        ('acks', ushort_t),
        ('value', string_t),
    ]


dbr_types = [(getattr(ca._dbr, attr), globals()[attr])
             for attr in sorted(globals())
             if attr.startswith('DBR_') and
             issubclass(globals()[attr], ctypes.BigEndianStructure)]


@pytest.mark.parametrize('dbr, expected_dbr', dbr_types)
def test_dbr_types(dbr, expected_dbr):
    expected = ctypes.sizeof(expected_dbr)
    assert ctypes.sizeof(dbr) == expected

    for field, type_ in expected_dbr._fields_:
        if field == 'secondsSinceEpoch':
            dbr_offset = (dbr.stamp.offset +
                          ca.TimeStamp.secondsSinceEpoch.offset)
            dbr_size = ca.TimeStamp.secondsSinceEpoch.size
        elif field == 'nanoSeconds':
            dbr_offset = dbr.stamp.offset + ca.TimeStamp.nanoSeconds.offset
            dbr_size = ca.TimeStamp.nanoSeconds.size
        else:
            dbr_offset = getattr(dbr, field).offset
            dbr_size = getattr(dbr, field).size

        expected_offset = getattr(expected_dbr, field).offset
        msg = 'offset of field {}/{} incorrect'.format(field, type_)
        assert dbr_offset == expected_offset, msg

        expected_size = getattr(expected_dbr, field).size
        msg = 'size of field {}/{} incorrect'.format(field, type_)
        assert dbr_size == expected_size, msg


def get_all_fields(cls):
    fields = []
    for base_cls in cls.__bases__:
        fields.extend(get_all_fields(base_cls))

    if hasattr(cls, '_fields_'):
        for field, type_ in cls._fields_:
            fields.append((field, type_))

    print('checking', cls, '->', fields)
    return fields


@pytest.mark.parametrize('dbr, expected_dbr', dbr_types)
def test_dict_parameters(dbr, expected_dbr):
    inst = dbr()
    info_dict = inst.to_dict()
    fields = get_all_fields(dbr)
    field_names = set(field for field, type_ in fields)
    valid_to_skip = {
        # RISC padding bytes
        'RISC_pad', 'RISC_pad0', 'RISC_pad1',
        # timestamp is a structure now, auto-converted to unix timestamp
        # in the field 'timestamp'
        'stamp',
        # enum strings come back as 'enum_strings' key, so count
        # of strings and the ctypes 'strs' are not useful
        'no_str', 'strs'}
    remaining = field_names - set(info_dict.keys()) - valid_to_skip
    assert len(remaining) == 0, 'fields not captured in info_keys'
