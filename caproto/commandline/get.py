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
from .. import ChannelType, set_handler, field_types, __version__
from ..sync.client import read
from .._log import _set_handler_with_logger
from .._utils import ShowVersionAction
from .cli_print_formats import (format_response_data, gen_data_format,
                                clean_format_args, format_str_adjust)


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
    # --format may be specified even if -t (--terse) or -a (--wide) options are
    #    selected. In this case --format specified in command line will be ignored
    #    (overwritten by default format for -t or -a)
    parser.add_argument('--format', type=str,
                        help=("Python format string. Available tokens are "
                              "{pv_name} and {response}. Additionally, if "
                              "this data type includes time, {timestamp} "
                              "and usages like "
                              "{timestamp:%%Y-%%m-%%d %%H:%%M:%%S} are "
                              "supported. If the format string is specified, "
                              "--terse and --wide options have no effect "
                              "on the output formatting."))
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
        help=("Get value as string (honors server-side precision)"))
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
    # Remove contradicting format arguments. This function may be simply removed from code
    #        if the functionality is not desired.
    clean_format_args(args=args)

    if args.verbose:
        if args.verbose <= 2:
            _set_handler_with_logger(color=not args.no_color, level='DEBUG', logger_name='caproto.ch')
            _set_handler_with_logger(color=not args.no_color, level='DEBUG', logger_name='caproto.ctx')
        else:
            set_handler(color=not args.no_color, level='DEBUG')
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

            data_fmt = gen_data_format(args=args, data=response.data)

            if args.format is None:
                # The following are default output formats.
                # The --format argument ALWAYS overwrites the default format.
                # (i.e. --wide and --terse have not effect if --format is specified)

                if args.terse:
                    format_str = '{response.data}'
                    if len(response.data) == 1:
                        # Only single entries are printed as scalars (without brackets)
                        data_fmt.no_brackets = True

                elif args.wide:
                    # TODO Make this look more like caget -a
                    format_str = '{pv_name} {timestamp} {response.data} {response.status.name}'

                elif args.F is None:
                    format_str = '{pv_name: <40}  {response.data}'

                else:
                    format_str = '{pv_name}  {response.data}'

            else:
                format_str = args.format

            format_str = format_str_adjust(format_str=format_str, data_fmt=data_fmt)

            response_data_str = format_response_data(data=response.data,
                                                     data_fmt=data_fmt)

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
