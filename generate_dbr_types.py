# Generate Python ctypes Structures to store EPICS data types.
import os
from collections import namedtuple, OrderedDict
from jinja2 import Environment, FileSystemLoader


def getpath(*args):
    """Get absolute path of joined directories relative to this file"""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), *args))


JINJA_ENV = Environment(loader=FileSystemLoader(getpath('.')))
template = JINJA_ENV.get_template('dbr_types.tpl')


TYPE_MAP = {# 'dbr_string': 'ctypes.c_char_p',  # deal with these separately
            'dbr_short': 'ctypes.c_ushort',
            'dbr_int': 'ctypes.c_ushort',
            'dbr_float': 'ctypes.c_float',
            'dbr_enum': 'ctypes.c_ushort',  # Where do the enum strings go?
            'dbr_char': 'ctypes.c_char',  # Is this the right char type?
            'dbr_long': 'ctypes.c_ulong',
            'dbr_double': 'ctypes.c_double',
           }


dbr_types = OrderedDict()
for name, _type in TYPE_MAP.items():
    dbr_types[name] = OrderedDict([('value', _type)])
for suffix in ['short', 'int', 'float', 'enum', 'long']:
    name = 'dbl_sts_%s' % suffix
    dbr_types[name] = OrderedDict([('status', 'dbr_short'),
                                   ('severity', 'dbr_short'),
                                   ('value', 'dbr_%s' % suffix)])
# Special-case char and double to include RISC_pad.
dbr_types['dbr_sts_char'] = OrderedDict([('status', 'dbr_short'),
                                         ('severity', 'dbr_short'),
                                         ('RISC_pad', 'dbr_char'),
                                         ('value', 'dbr_char')])
dbr_types['dbr_sts_double'] = OrderedDict([('status', 'dbr_short'),
                                           ('severity', 'dbr_short'),
                                           ('RISC_pad', 'dbr_long'),
                                           ('value', 'dbr_long')])
# Additional structure for a string status and ack field
#dbr_types['dbr_stsack_string'] = OrderedDict([('status', 'dbr_short'),
#                                              ('severity', 'dbr_short'),
#                                              ('ackt', 'dbr_short'),
#                                              ('acks', 'dbr_short'),
#                                              ('value', 'dbr_string')])


# TODO many more, documented below

"""
from http://ladd00.triumf.ca/~olchansk/midas/db__access_8h_source.html

00319 /* values returned for each field type
00320  *    DBR_STRING  returns a NULL terminated string
00321  * DBR_SHORT   returns an unsigned short
00322  * DBR_INT     returns an unsigned short
00323  * DBR_FLOAT   returns an IEEE floating point value
00324  * DBR_ENUM returns an unsigned short which is the enum item
00325  * DBR_CHAR returns an unsigned char
00326  * DBR_LONG returns an unsigned long
00327  * DBR_DOUBLE  returns a double precision floating point number
00328  * DBR_STS_STRING returns a string status structure (dbr_sts_string)
00329  * DBR_STS_SHORT  returns a short status structure (dbr_sts_short)
00330  * DBR_STS_INT returns a short status structure (dbr_sts_int)
00331  * DBR_STS_FLOAT  returns a float status structure (dbr_sts_float)
00332  * DBR_STS_ENUM   returns an enum status structure (dbr_sts_enum)
00333  * DBR_STS_CHAR   returns a char status structure (dbr_sts_char)
00334  * DBR_STS_LONG   returns a long status structure (dbr_sts_long)
00335  * DBR_STS_DOUBLE returns a double status structure (dbr_sts_double)
00336  * DBR_TIME_STRING   returns a string time structure (dbr_time_string)
00337  * DBR_TIME_SHORT returns a short time structure (dbr_time_short)
00338  * DBR_TIME_INT   returns a short time structure (dbr_time_short)
00339  * DBR_TIME_FLOAT returns a float time structure (dbr_time_float)
00340  * DBR_TIME_ENUM  returns an enum time structure (dbr_time_enum)
00341  * DBR_TIME_CHAR  returns a char time structure (dbr_time_char)
00342  * DBR_TIME_LONG  returns a long time structure (dbr_time_long)
00343  * DBR_TIME_DOUBLE   returns a double time structure (dbr_time_double)
00344  * DBR_GR_STRING  returns a graphic string structure (dbr_gr_string)
00345  * DBR_GR_SHORT   returns a graphic short structure (dbr_gr_short)
00346  * DBR_GR_INT  returns a graphic short structure (dbr_gr_int)
00347  * DBR_GR_FLOAT   returns a graphic float structure (dbr_gr_float)
00348  * DBR_GR_ENUM returns a graphic enum structure (dbr_gr_enum)
00349  * DBR_GR_CHAR returns a graphic char structure (dbr_gr_char)
00350  * DBR_GR_LONG returns a graphic long structure (dbr_gr_long)
00351  * DBR_GR_DOUBLE  returns a graphic double structure (dbr_gr_double)
00352  * DBR_CTRL_STRING   returns a control string structure (dbr_ctrl_int)
00353  * DBR_CTRL_SHORT returns a control short structure (dbr_ctrl_short)
00354  * DBR_CTRL_INT   returns a control short structure (dbr_ctrl_int)
00355  * DBR_CTRL_FLOAT returns a control float structure (dbr_ctrl_float)
00356  * DBR_CTRL_ENUM  returns a control enum structure (dbr_ctrl_enum)
00357  * DBR_CTRL_CHAR  returns a control char structure (dbr_ctrl_char)
00358  * DBR_CTRL_LONG  returns a control long structure (dbr_ctrl_long)
00359  * DBR_CTRL_DOUBLE   returns a control double structure (dbr_ctrl_double)
00360  */
"""


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
