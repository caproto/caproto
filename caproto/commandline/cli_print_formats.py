
'''
This module contains functions for formatting data output for CLI utilities
(get.py and monitor.py). Format is selected based on command-line arguments.
'''

import numbers
import sys
import re


class _DataPrintFormat:

    def __init__(self):
        self.format = ""
        self.prefix = ""
        self.separator = None
        self.float_round = False    # floating point data value
        #                             must be rounded to the nearest integer (long)
        self.float_server_precision = False  # The floating point data value must be requested
        #                                      from the server as string
        self.no_brackets = False             # Print data as scalar (no brackets)


def _clean_args_for_group(args_parsed=None, group_args=None, group_attrs=None):
    '''
    Cleans (sets to None) attributes of class 'args_parsed'. The only attribute that is
    left corresponds to the argument that is specified last in the command line (sys.argv)

    args_parsed - the class with attributes holding values of command line parameters
    group_args - the list of the arguments in the group (ex. ["-0x", "-0o", "-0b"])
    group_attrs - the list of corresponding attributes of 'args_parsed':
                                                   ["int_0x", "int_0o", "int_0b"]
    '''

    if args_parsed is None or group_args is None or group_attrs is None:
        return

    if len(group_args) != len(group_attrs):
        return

    sa = sys.argv

    arg_selected = None
    for ag in reversed(sa):
        for arg in group_args:
            # Select appropriate regular expression for comparing arguments
            reg_expr = "^{}$"  # Default is perfect match (typically for argument
            #                    that starts with --)
            # If the argument starts with '-', then match the beginning of the string
            if len(ag) > 1 and ag[0] == '-' and ag[1] != '-':
                reg_expr = "^{}.*"

            p = re.compile(reg_expr.format(arg))
            if p.match(ag) is not None:
                arg_selected = arg
                break

        if arg_selected is not None:
            break

    if arg_selected is not None:
        n_arg = group_args.index(arg_selected)
        for i, attr in enumerate(group_attrs):
            if i != n_arg and hasattr(args_parsed, attr):
                setattr(args_parsed, attr, None)


def clean_format_args(args=None):
    '''
    The function removes contradicting arguments, which define output format for floating point
        and integer data values, improving compatibility with EPICS caget.

    EPICS caget allows multiple contradicting format specifications and discards
        all except the last one according to the order in which they are specified.
        For example, for a floating point pv with the value 56.3452093 the
        following format will be applied depending on the sequence of arguments:

        ARGUMENTS                DISPLAYED VALUE

        -e5 -lx -f5              56.34521
        -f5 -lx -e5              5.63452e+01
        -f5 -e5 -lx              0x38

    This function clears data in 'parsed_args' for all arguments from the same format group except
    the last in sequence as the arguments appear in command line. Since format arguments
    for floating point and integer data belong to separate group of parameters, processing
    is performed separately for floats and ints.

    args - class that contains data extracted from command line arguments (returned by parser.parseargs())
    Function changes fields of 'args' and returns no value.

    Note: this function is a patch, which necessary because equivalent functionality is not available
    from 'argparse' module.
    '''

    # Arguments from group 1 (floating point)
    double_args = ["-e", "-f", "-g", "-s", "-lx", "-lo", "-lb"]
    double_attrs = ["float_e", "float_f", "float_g", "float_s", "float_lx", "float_lo", "float_lb"]

    _clean_args_for_group(args, double_args, double_attrs)

    # Arguments from group 2 (floating point)
    int_args = ["-0x", "-0o", "-0b"]
    int_attrs = ["int_0x", "int_0o", "int_0b"]

    _clean_args_for_group(args, int_args, int_attrs)


def gen_data_format(args=None, data=None):
    '''
    Generates format specification for printing 'response.data' field

      args - class that contains data on cmd line arguments (returned by parser.parseargs())
      data - iterable object (typically numpy.narray), which contains data entries returned
                by the server

      Returns the instance of DataFormat class. Format is set to empty string if the function
          is unable to select correct format.
    '''

    df = _DataPrintFormat()

    # Both arguments 'arg' and 'data' are needed to produce meaningful result
    if args is None or data is None or len(data) == 0:
        return df

    # If no format was specified, the default is "g" (as in EPICS caget)
    df.format = "g"

    # 'data' contains a list (or array) of strings
    if(isinstance(data[0], str) or isinstance(data[0], bytes)):
        df.format = "s"

    # 'data' contains an array of floats
    if(isinstance(data[0], float)):
        # Check if any of the format specification arguments were passed
        if args.float_e is not None:
            df.format = ".{}e".format(args.float_e)
        elif args.float_f is not None:
            df.format = ".{}f".format(args.float_f)
        elif args.float_g is not None:
            df.format = ".{}g".format(args.float_g)
        elif args.float_s:
            # This feature is not implemented yet. Instead use floating point
            #    value supplied by the server and print it in %f format.
            #    This is still gives some elementary support for the argument -s.
            df.format = "f"
            df.float_server_precision = True
        elif args.float_lx:  # Rounded hexadecimal
            df.format = "X"
            df.prefix = "0x"
            df.float_round = True
        elif args.float_lo:  # Rounded octal
            df.format = "o"
            df.prefix = "0o"
            df.float_round = True
        elif args.float_lb:  # Rounded binary
            df.format = "b"
            df.prefix = "0b"
            df.float_round = True

    # 'data' contains an array of integers
    if(isinstance(data[0], numbers.Integral)):
        if args.int_0x:
            df.format = "X"   # Hexadecimal
            df.prefix = "0x"
        elif args.int_0o:
            df.format = "o"   # Octal
            df.prefix = "0o"
        elif args.int_0b:
            df.format = "b"   # Binary
            df.prefix = "0b"

    # Separator: may be a single character (quoted or not quoted) or quoted multiple characters
    #          including spaces. EPICS caget allows only single character separators.
    #          Quoted separator also may be an empty string (no separator), but this is
    #          a meaningless feature.
    if args.F is not None:
        df.separator = args.F

    return df


def format_str_adjust(format_str=None, data_fmt=None):
    '''
    Performs the following changes to the format string 'format_str':
        1. Replaces all occurrances of '{response.data}' with '{response_data}'
        2. Inserts separator between fields if a separator is specified
    '''

    if format_str is None:
        return None

    if data_fmt is None:
        data_fmt = _DataPrintFormat()  # No separator will be inserted

    # In 'format_str': replace all instances of '{response.data}' with '{response_data}'
    p = re.compile("{response.data}")
    format_str = p.sub("{response_data}", format_str)

    # If a separator is specified (argument -F), then put the separators between each field
    if data_fmt.separator is not None:
        p = re.compile("} *{")
        format_str = p.sub("}" + "{}".format(data_fmt.separator) + "{", format_str)

    return format_str


def format_response_data(data=None, data_fmt=None):
    '''
    Prints data contained in iterable object 'data' to a string according to format specifications 'data_fmt'
    Returns a string containing printed data.
    '''

    if data_fmt is None:
        data_fmt = _DataPrintFormat()

    s = ""

    # There must be at least some elements in 'data' array
    if data is None or len(data) == 0:
        # Used to display empty array received from the server
        return "[]"

    # Format does NOT NEED to be set for the function to print properly.
    #    The default python printing format for the type is used then.

    sep = " "  # Default
    # Note, that the separator may be an empty string and it still overrides the default " "
    if data_fmt.separator is not None:
        sep = data_fmt.separator

    # Strings (or arrays of strings) are returned in the form of lists
    #    of type 'bytes'. They need to be converted to regular strings for printing.
    if(isinstance(data[0], bytes)):
        data = [v.decode() for v in data]
    # Round floating point numbers and convert to nearest integers (if required)
    if(isinstance(data[0], float) and data_fmt.float_round):
        data = [int(round(v)) for v in data]
    # Convert to strings by printing values using selected format and prefix (0x, 0o or 0b)
    data_str = [("{}{:" + data_fmt.format + "}").format(data_fmt.prefix, v) for v in data]
    s = sep.join(data_str)
    if not data_fmt.no_brackets:
        s = "[" + s + "]"

    return s
