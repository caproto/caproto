"""
This module is installed as an entry-point, available as:

caproto-get ...

It can equivalently be invoked as:

python3 -m caproto.commandline.get ...

For access to the underlying functionality from a Python script or interactive
Python session, do not import this module; instead import caproto.sync.client.
"""
import argparse
from datetime import datetime
import logging
import numbers
import re
import sys
from .. import ChannelType, set_handler, field_types, __version__
from ..sync.client import read
from .._utils import ShowVersionAction


class _DataFormat:

    def __init__(self):
        self.format = ""
        self.prefix = ""
        self.separator = None
        self.float_round = False    # floating point data value
        #                             must be rounded to the nearest integer (long)
        self.float_server_precision = False  # The floating point data value must be requested
        #                                      from the server as string
        self.no_brackets = False             # Print data as scalar (no brackets)

    def is_set(self):
        ''' Returns True if format string is not empty '''
        return len(self.format) > 0


def _clean_format_args(args=None):
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

    This function clears data in 'args' for all arguments from the same format group except
    the last in sequence as the arguments appear in command line. Since format arguments
    for floating point and integer data belong to separate group of parameters, processing
    is performed separately for floats and ints.

    args - class that contains data extracted from command line arguments (returned by parser.parseargs())
    Function changes fields of 'args' and returns no value.

    Note: this function is a patch, which necessary because equivalent functionality is not available
    from 'argparse' module.
    '''

    double_fmt = ["e", "f", "g", "s", "lx", "lo", "lb"]
    int_fmt = ["0x", "0o", "0b"]

    def _find_last_arg(list_args=[]):
        sa = sys.argv
        fm_selected = None
        for ag in reversed(sa):
            for fm in list_args:
                p = re.compile("^-{}.*".format(fm))
                if p.match(ag) is not None:
                    fm_selected = fm
                    break
            if fm_selected is not None:
                break
        return fm_selected

    arg_float = _find_last_arg(list_args=double_fmt)
    if arg_float is not None:
        if arg_float != "e":
            args.float_e = None
        if arg_float != "f":
            args.float_f = None
        if arg_float != "g":
            args.float_g = None
        if arg_float != "s":
            args.float_s = False
        if arg_float != "lx":
            args.float_lx = False
        if arg_float != "lo":
            args.float_lo = False
        if arg_float != "lb":
            args.float_lb = False

    arg_int = _find_last_arg(list_args=int_fmt)
    if arg_int is not None:
        if arg_int != "0x":
            args.int_0x = False
        if arg_int != "0o":
            args.int_0o = False
        if arg_int != "0b":
            args.int_Ob = False


def _gen_data_format(args=None, data=None):
    '''
    Generates format specification for printing 'response.data' field

      args - class that contains data on cmd line arguments (returned by parser.parseargs())
      data - iterable object (typically numpy.narray), which contains data entries returned
                by the server

      Returns the instance of DataFormat class. Format is set to empty string if the function
          is unable to select correct format.
    '''

    # Remove contradicting format arguments. This function may be simply removed from code
    #        if the functionality is not desired.
    _clean_format_args(args=args)

    df = _DataFormat()

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


def _print_response_data(data=None, data_fmt=None):
    '''
    Prints data contained in iterable 'data' to a string according to format specifications 'data_fmt'
    Returns a string containing printed data.
    '''

    if data_fmt is None:
        data_fmt = _DataFormat()

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

    if not data_fmt.no_brackets:
        s += "["
    add_sep = False
    for v in data:
        # Strings (or arrays of strings) are returned by the server in the form of lists
        #    of type 'bytes'. They need to be converted to regular strings for printing.
        if(isinstance(v, bytes)):
            v = v.decode()
        if add_sep:
            s += sep
        add_sep = True
        # Round the value if needed (if floating point number needs to be converted to closest int)
        if data_fmt.float_round and isinstance(v, float):
            v = int(round(v))
        s += ("{0:}{1:" + data_fmt.format + "}").format(data_fmt.prefix, v)
    if not data_fmt.no_brackets:
        s += "]"

    return s


def main():
    parser = argparse.ArgumentParser(description='Read the value of a PV.',
                                     epilog=f'caproto version {__version__}')
    parser.register('action', 'list_types', _ListTypesAction)
    parser.register('action', 'show_version', ShowVersionAction)
    fmt_group = parser.add_mutually_exclusive_group()
    parser.add_argument('pv_names', type=str, nargs='+',
                        help="PV (channel) name(s) separated by spaces")
    parser.add_argument('--verbose', '-v', action='count',
                        help="Show more log messages. (Use -vvv for even more.)")
    fmt_group.add_argument('--format', type=str,
                           help=("Python format string. Available tokens are "
                                 "{pv_name} and {response}. Additionally, if "
                                 "this data type includes time, {timestamp} "
                                 "and usages like "
                                 "{timestamp:%%Y-%%m-%%d %%H:%%M:%%S} are "
                                 "supported."))
    parser.add_argument('--timeout', '-w', type=float, default=1,
                        help=("Timeout ('wait') in seconds for server "
                              "responses."))
    parser.add_argument('--notify', '-c', action='store_true',
                        help=("This is a vestigial argument that now has no "
                              "effect in caget but is provided for "
                              "for backward-compatibility with caget "
                              "invocations."))
    parser.add_argument('--priority', '-p', type=int, default=0,
                        help="Channel Access Virtual Circuit priority. "
                             "Lowest is 0; highest is 99.")
    fmt_group.add_argument('--terse', '-t', action='store_true',
                           help=("Display data only. Unpack scalars: "
                                 "[3.] -> 3."))
    # caget calls this "wide mode" with -a and caput calls it "long mode" with
    # -l. We will support both -a and -l in both caproto-get and caproto-put.
    fmt_group.add_argument('--wide', '-a', '-l', action='store_true',
                           help=("Wide mode, showing "
                                 "'name timestamp value status'"
                                 "(implies -d 'time')"))
    # TODO caget/caput also include a 'srvr' column which seems to be `sid`. We
    # would need a pretty invasive refactor to access that from here.
    #
    # Note: -d, -a and -t are mutually exclusive options in caget. Option -a (or --wide)
    #   overwrites data_type in request, therefore data_type can not be specified as a parameter
    fmt_group.add_argument('-d', type=str, default=None, metavar="DATA_TYPE",
                           help=("Request a class of data type (native, status, "
                                 "time, graphic, control) or a specific type. "
                                 "Accepts numeric "
                                 "code ('3') or case-insensitive string ('enum')"
                                 ". See --list-types."))
    parser.add_argument('--list-types', action='list_types',
                        default=argparse.SUPPRESS,
                        help="List allowed values for -d and exit.")
    parser.add_argument('-n', action='store_true',
                        help=("Retrieve enums as integers (default is "
                              "strings)."))
    parser.add_argument('--no-color', action='store_true',
                        help="Suppress ANSI color codes in log messages.")
    parser.add_argument('--no-repeater', action='store_true',
                        help=("Do not spawn a Channel Access repeater daemon "
                              "process."))
    parser.add_argument('--version', '-V', action='show_version',
                        default=argparse.SUPPRESS,
                        help="Show caproto version and exit.")

    fmt_group_float = parser.add_argument_group(
        title="Floating point type format",
        description=("If --format is set, the following arguments change formatting of the "
                     "{response.data} field if floating point value is displayed. "
                     "The default format is %g."))
    fmt_group_float.add_argument(
        '-e', dest="float_e", type=int, metavar="<nr>", action="store",
        help=("Use %%e format with precision of <nr> digits (e.g. -e5 or -e 5)"))
    fmt_group_float.add_argument(
        '-f', dest="float_f", type=int, metavar="<nr>", action="store",
        help=("Use %%f format with precision of <nr> digits (e.g. -f5 or -f 5)"))
    fmt_group_float.add_argument(
        '-g', dest="float_g", type=int, metavar="<nr>", action="store",
        help=("Use %%g format with precision of <nr> digits (e.g. -g5 or -g 5)"))
    fmt_group_float.add_argument(
        '-s', dest="float_s", action="store_true",
        help=("Get value as string (honors server-side precision"))
    fmt_group_float.add_argument(
        '-lx', dest="float_lx", action="store_true",
        help=("Round to long integer and print as hex number"))
    fmt_group_float.add_argument(
        '-lo', dest="float_lo", action="store_true",
        help=("Round to long integer and print as octal number"))
    fmt_group_float.add_argument(
        '-lb', dest="float_lb", action="store_true",
        help=("Round to long integer and print as binary number"))

    fmt_group_int = parser.add_argument_group(
        title="Integer number format",
        description="If --format is set, the following arguments change formatting of the "
                    "{response.data} field if integer value is displayed. "
                    "Decimal number is displayed by default.")
    fmt_group_int.add_argument('-0x', dest="int_0x", action="store_true",
                               help=("Print as hex number"))
    fmt_group_int.add_argument('-0o', dest="int_0o", action="store_true",
                               help=("Print as octal number"))
    fmt_group_int.add_argument('-0b', dest="int_0b", action="store_true",
                               help=("Print as binary number"))

    fmt_group_sep = parser.add_argument_group(title="Custom output field separator")
    fmt_group_sep.add_argument(
        '-F', type=str, metavar="<ofs>", action="store",
        help=("Use <ofs> as an alternate output field separator (e.g. -F*, -F'*', -F '*', -F ' ** ')"))

    args = parser.parse_args()
    if args.no_color:
        set_handler(color=False)
    if args.verbose:
        logging.getLogger(f'caproto.ch').setLevel('DEBUG')
        logging.getLogger(f'caproto.ctx').setLevel('DEBUG')
        if args.verbose > 2:
            logging.getLogger('caproto').setLevel('DEBUG')
    data_type = args.d
    # data_type might be '0', 'STRING', or a class like 'control'.
    # The client functions accepts 0, ChannelType.STRING, or 'control'.
    try:
        data_type = int(data_type)  # '0' -> 0
    except (ValueError, TypeError):
        if isinstance(data_type, str):
            # Ignore DBR_ (or dbr_) prefix in data_type
            if len(data_type) >= 4 and data_type.lower()[0:4] == "dbr_":
                data_type = data_type[4:]
            if data_type.lower() not in field_types:
                # 'STRING' -> ChannelType.STRING
                data_type = ChannelType[data_type.upper()]
            # else assume a class like 'control', which can pass through
    if args.wide:
        data_type = 'time'
    try:
        for pv_name in args.pv_names:

            response = read(pv_name=pv_name,
                            data_type=data_type,
                            timeout=args.timeout,
                            priority=args.priority,
                            force_int_enums=args.n,
                            repeater=not args.no_repeater)

            data_fmt = _gen_data_format(args=args, data=response.data)

            if args.format is None:
                if args.F is None:
                    format_str = '{pv_name: <40}  {response.data}'
                else:
                    format_str = '{pv_name}  {response.data}'
            else:
                format_str = args.format

            if args.terse:
                format_str = '{response.data}'
                if len(response.data) == 1:
                    # Only single entries are printed as scalars (without brackets)
                    data_fmt.no_brackets = True

            elif args.wide:
                # TODO Make this look more like caget -a
                format_str = '{pv_name} {timestamp} {response.data} {response.status.name}'

            # In 'format_str': replace all instances of '{response.data}' with '{response_data}'
            p = re.compile("{response.data}")
            format_str = p.sub("{response_data}", format_str)
            # If a separator is specified (argument -F), then put the separators between each field
            if data_fmt.separator is not None:
                p = re.compile("} *{")
                format_str = p.sub("}" + "{}".format(data_fmt.separator) + "{", format_str)

            response_data_str = _print_response_data(data=response.data, data_fmt=data_fmt)

            tokens = dict(pv_name=pv_name, response=response, response_data=response_data_str)
            if hasattr(response.metadata, 'timestamp'):
                dt = datetime.fromtimestamp(response.metadata.timestamp)
                tokens['timestamp'] = dt
            print(format_str.format(**tokens))

    except BaseException as exc:
        if args.verbose:
            # Show the full traceback.
            raise
        else:
            # Print a one-line error message.
            print(exc)


class _ListTypesAction(argparse.Action):
    # a special action that allows the usage --list-types to override
    # any 'required args' requirements, the same way that --help does

    def __init__(self,
                 option_strings,
                 dest=argparse.SUPPRESS,
                 default=argparse.SUPPRESS,
                 help=None):
        super(_ListTypesAction, self).__init__(
            option_strings=option_strings,
            dest=dest,
            default=default,
            nargs=0,
            help=help)

    def __call__(self, parser, namespace, values, option_string=None):
        print("Request a general class of types:")
        print()
        for field_type in field_types:
            print(field_type)
        print()
        print("or one of the following specific types, specified by "
              "number or by (case-insensitive) name:")
        print()
        for elem in ChannelType:
            print(f'{elem.value: <2} {elem.name}')
        print()
        print("Type name may be preceded by 'DBR_' for compatiblity with EPICS caget utility")
        print("   (ex. DBR_STRING is equivalent to STRING)")
        parser.exit()


if __name__ == '__main__':
    main()
