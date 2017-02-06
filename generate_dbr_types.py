# Generate Python ctypes Structures to store EPICS data types.
# Based on http://www.aps.anl.gov/epics/base/R3-16/0-docs/CAproto/index.html
# excerpts from which are given in comments below.

# Also see
# https://github.com/epics-base/epics-base/blob/813166128eae1240cdd643869808abe1c4621321/src/ca/client/db_access.h
import os
from collections import namedtuple, OrderedDict
from jinja2 import Environment, FileSystemLoader


def getpath(*args):
    """Get absolute path of joined directories relative to this file"""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), *args))


JINJA_ENV = Environment(loader=FileSystemLoader(getpath('.')))
template = JINJA_ENV.get_template('dbr_types.tpl')


TYPE_MAP = OrderedDict([
    ('STRING', '40 * ctypes.c_char'),
    ('INT',    'ctypes.c_ushort'),
    ('FLOAT',  'ctypes.c_float'),
    ('ENUM',   'ctypes.c_ushort'),  # Where do the enum strings go?
    ('CHAR',   'ctypes.c_char'),  # Is this the right char type?
    ('LONG',   'ctypes.c_long'),
    ('DOUBLE', 'ctypes.c_double'),
    ])



dbr_types = OrderedDict()

# the basic types
for i, (suffix, _type) in enumerate(TYPE_MAP.items()):
    name = 'DBR_%s' % suffix
    dbr_id = i
    dbr_types[(dbr_id, name)] = OrderedDict([('value', _type)])

# From documentation at
# http://www.aps.anl.gov/epics/base/R3-16/0-docs/CAproto/index.html
# 
# struct metaSTS {
#     epicsInt16 status;
#     epicsInt16 severity;
# };
for i, suffix in enumerate(TYPE_MAP):
    name = 'DBR_STS_%s' % suffix
    dbr_id = i + len(TYPE_MAP)
    dbr_types[(dbr_id, name)] = OrderedDict([
        ('status', 'ctypes.c_short'),
        ('severity', 'ctypes.c_short'),
        ('value', TYPE_MAP[suffix])])

# struct metaTIME {
#     epicsInt16 status;
#     epicsInt16 severity;
#     epicsInt32 secondsSinceEpoch;
#     epicsUInt32 nanoSeconds;
# };
for i, suffix in enumerate(TYPE_MAP):
    name = 'DBR_TIME_%s' % suffix
    dbr_id = i + 2 * len(TYPE_MAP)
    dbr_types[(dbr_id, name)] = OrderedDict([
        ('status', 'ctypes.c_short'),
        ('severity', 'ctypes.c_short'),
        # Note that the EPICS Epoch is 1990-01-01T00:00:00Z. This is 631152000
        # seconds after the POSIX Epoch of 1970-01-01T00:00:00Z.
        ('secondsSinceEpoch', 'ctypes.c_long'),
        ('nanoSeconds', 'ctypes.c_ulong'),
        ('value', TYPE_MAP[suffix])])

# This is a guess based on the documentation for GR_INT, shown below.
dbr_types[(21, 'DBR_GR_STRING')] = OrderedDict([
     ('status', 'ctypes.c_short'),
     ('severity', 'ctypes.c_short'),
     ('units', '8 * ctypes.c_char'),
     ('upper_display_limit', 'ctypes.c_short'),
     ('lower_display_limit', 'ctypes.c_short'),
     ('upper_alarm_limit', 'ctypes.c_short'),
     ('upper_warning_limit', 'ctypes.c_short'),
     ('lower_warning_limit', 'ctypes.c_short'),
     ('lower_alarm_limit', 'ctypes.c_short'),
     # Note weird ordering of these last two entries.
     ('value', TYPE_MAP['STRING'])])


# struct metaGR_INT {
#         epicsInt16 status;
#         epicsInt16 severity;
#         char units[8];
#         epicsInt16 upper_display_limit;
#         epicsInt16 lower_display_limit;
#         epicsInt16 upper_alarm_limit;
#         epicsInt16 upper_warning_limit;
#         epicsInt16 lower_warning_limit;
#         epicsInt16 lower_alarm_limit;
# };
dbr_types[(22, 'DBR_GR_INT')] = OrderedDict([
    ('status', 'ctypes.c_short'),
    ('severity', 'ctypes.c_short'),
    ('units', '8 * ctypes.c_char'),
    ('upper_display_limit', 'ctypes.c_short'),
    ('lower_display_limit', 'ctypes.c_short'),
    ('upper_alarm_limit', 'ctypes.c_short'),
    ('upper_warning_limit', 'ctypes.c_short'),
    ('lower_warning_limit', 'ctypes.c_short'),
    ('lower_alarm_limit', 'ctypes.c_short'),
    # Note weird ordering of these last two entries.
    ('value', TYPE_MAP['STRING'])])


# struct metaGR_FLOAT {
#         epicsInt16 status;
#         epicsInt16 severity;
#         epicsInt16 precision;
#         epicsInt16 padding;
#         char units[8];
#     epicsFloat32 upper_display_limit;
#     epicsFloat32 lower_display_limit;
#     epicsFloat32 upper_alarm_limit;
#     epicsFloat32 upper_warning_limit;
#     epicsFloat32 lower_warning_limit;
#     epicsFloat32 lower_alarm_limit;
# };
dbr_types[(23, 'DBR_GR_FLOAT')] = OrderedDict([
    ('status', 'ctypes.c_short'),
    ('severity', 'ctypes.c_short'),
    ('preicison', 'ctypes.c_short'),
    ('padding', 'ctypes.c_short'),
    ('units', '8 * ctypes.c_char'),
    ('upper_display_limit', 'ctypes.c_short'),
    ('lower_display_limit', 'ctypes.c_short'),
    ('upper_alarm_limit', 'ctypes.c_short'),
    ('upper_warning_limit', 'ctypes.c_short'),
    ('lower_warning_limit', 'ctypes.c_short'),
    ('lower_alarm_limit', 'ctypes.c_short'),
    # Note weird ordering of these last two entries.
    ('value', TYPE_MAP['FLOAT'])])

# struct metaGR_ENUM {
#     epicsInt16 status;
#     epicsInt16 severity;
#     epicsInt16 number_of_string_used;
#     char strings[16][26];
# };
dbr_types[(24, 'DBR_GR_ENUM')] = OrderedDict([
    ('status', 'ctypes.c_short'),
    ('severity', 'ctypes.c_short'),
    ('number_of_string_used', 'ctypes.c_short'),
    ('strings', '16 * 26 * ctypes.c_char'),
    ('value', TYPE_MAP['ENUM'])])

# struct metaGR_INT {
#         epicsInt16 status;
#         epicsInt16 severity;
#         char units[8];
#         epicsInt8 upper_display_limit;
#         epicsInt8 lower_display_limit;
#     epicsInt8 upper_alarm_limit;
#         epicsInt8 upper_warning_limit;
#         epicsInt8 lower_warning_limit;
#         epicsInt8 lower_alarm_limit;
# };
dbr_types[(25, 'DBR_GR_CHAR')] = OrderedDict([
    ('status', 'ctypes.c_short'),
    ('severity', 'ctypes.c_short'),
    ('units', '8 * ctypes.c_char'),
    ('upper_display_limit', 'ctypes.c_char'),
    ('lower_display_limit', 'ctypes.c_char'),
    ('upper_alarm_limit', 'ctypes.c_char'),
    ('upper_warning_limit', 'ctypes.c_char'),
    ('lower_warning_limit', 'ctypes.c_char'),
    ('lower_alarm_limit', 'ctypes.c_char'),
    # Note weird ordering of these last two entries.
    ('value', TYPE_MAP['STRING'])])

dbr_types[(26, 'DBR_GR_LONG')] = OrderedDict([
    ('status', 'ctypes.c_short'),
    ('severity', 'ctypes.c_short'),
    ('units', '8 * ctypes.c_char'),
    ('upper_display_limit', 'ctypes.c_long'),
    ('lower_display_limit', 'ctypes.c_long'),
    ('upper_alarm_limit', 'ctypes.c_long'),
    ('upper_warning_limit', 'ctypes.c_long'),
    ('lower_warning_limit', 'ctypes.c_long'),
    ('lower_alarm_limit', 'ctypes.c_long'),
    # Note weird ordering of these last two entries.
    ('value', TYPE_MAP['LONG'])])

# struct metaGR_FLOAT {
#     epicsInt16 status;
#     epicsInt16 severity;
#     epicsInt16 precision;
#     epicsInt16 padding;
#     char units[8];
#     epicsFloat64 upper_display_limit;
#     epicsFloat64 lower_display_limit;
#     epicsFloat64 upper_alarm_limit;
#     epicsFloat64 upper_warning_limit;
#     epicsFloat64 lower_warning_limit;
#     epicsFloat64 lower_alarm_limit;
# };
dbr_types[(27, 'DBR_GR_DOUBLE')] = OrderedDict([
    ('status', 'ctypes.c_short'),
    ('severity', 'ctypes.c_short'),
    ('units', '8 * ctypes.c_char'),
    ('upper_display_limit', 'ctypes.c_double'),
    ('lower_display_limit', 'ctypes.c_double'),
    ('upper_alarm_limit', 'ctypes.c_double'),
    ('upper_warning_limit', 'ctypes.c_double'),
    ('lower_warning_limit', 'ctypes.c_double'),
    ('lower_alarm_limit', 'ctypes.c_double'),
    # Note weird ordering of these last two entries.
    ('value', TYPE_MAP['DOUBLE'])])

def write_dbr_types(path=None):
    """
    Generate dbr_types.py from dbr_types.tpl.
    """
    if path is None:
        path = getpath('.')
    with open(os.path.join(path, 'dbr_types.py'), 'w') as f:
        f.write(template.render(dbr_types=dbr_types))


if __name__ == '__main__':
    write_dbr_types()
