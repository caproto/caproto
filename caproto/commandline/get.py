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
from .. import ChannelType, color_logs, field_types
from ..sync.client import read


def main():
    parser = argparse.ArgumentParser(description='Read the value of a PV.')
    parser.register('action', 'list_types', _ListTypesAction)
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
    parser.add_argument('-d', type=str, default=None, metavar="DATA_TYPE",
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
    args = parser.parse_args()
    if args.no_color:
        color_logs(False)
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
            if args.format is None:
                format_str = '{pv_name: <40}  {response.data}'
            else:
                format_str = args.format
            if args.terse:
                if len(response.data) == 1:
                    format_str = '{response.data[0]}'
                else:
                    format_str = '{response.data}'
            elif args.wide:
                # TODO Make this look more like caget -a
                format_str = '{pv_name} {timestamp} {response.data} {response.status.name}'
            tokens = dict(pv_name=pv_name, response=response)
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
        parser.exit()


if __name__ == '__main__':
    main()
