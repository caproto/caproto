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
from .. import ChannelType, color_logs
from ..sync.client import read
from ..sync.repeater import spawn_repeater


def main():
    parser = argparse.ArgumentParser(description='Read the value of a PV.')
    parser.register('action', 'list_types', _ListTypesAction)
    fmt_group = parser.add_mutually_exclusive_group()
    parser.add_argument('pv_names', type=str, nargs='+',
                        help="PV (channel) name(s) separated by spaces")
    parser.add_argument('-d', type=str, default=None, metavar="DATA_TYPE",
                        help=("Request a certain data type. Accepts numeric "
                              "code ('3') or case-insensitive string ('enum')"
                              ". See --list-types"))
    fmt_group.add_argument('--format', type=str,
                           help=("Python format string. Available tokens are "
                                 "{pv_name} and {response}. Additionally, if "
                                 "this data type includes time, {timestamp} "
                                 "and usages like "
                                 "{timestamp:%%Y-%%m-%%d %%H:%%M:%%S} are "
                                 "supported."))
    parser.add_argument('--list-types', action='list_types',
                        default=argparse.SUPPRESS,
                        help="List allowed values for -d and exit.")
    parser.add_argument('-n', action='store_true',
                        help=("Retrieve enums as integers (default is "
                              "strings)."))
    parser.add_argument('--priority', '-p', type=int, default=0,
                        help="Channel Access Virtual Circuit priority. "
                             "Lowest is 0; highest is 99.")
    fmt_group.add_argument('--terse', '-t', action='store_true',
                           help=("Display data only. Unpack scalars: "
                                 "[3.] -> 3."))
    parser.add_argument('--timeout', '-w', type=float, default=1,
                        help=("Timeout ('wait') in seconds for server "
                              "responses."))
    parser.add_argument('--verbose', '-v', action='store_true',
                        help="Verbose mode. (Use -vvv for more.)")
    parser.add_argument('-vvv', action='store_true',
                        help=argparse.SUPPRESS)
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
    if args.vvv:
        logging.getLogger('caproto').setLevel('DEBUG')
    if not args.no_repeater:
        spawn_repeater()
    data_type = parse_data_type(args.d)
    try:
        for pv_name in args.pv_names:
            response = read(pv_name=pv_name,
                            data_type=data_type,
                            timeout=args.timeout,
                            priority=args.priority,
                            force_int_enums=args.n,
                            repeater=False)
            if args.format is None:
                format_str = '{pv_name: <40}  {response.data}'
            else:
                format_str = args.format
            if args.terse:
                if len(response.data) == 1:
                    format_str = '{response.data[0]}'
                else:
                    format_str = '{response.data}'
            tokens = dict(pv_name=pv_name, response=response)
            if hasattr(response.metadata, 'timestamp'):
                dt = datetime.fromtimestamp(response.metadata.timestamp)
                tokens['timestamp'] = dt
            print(format_str.format(**tokens))

    except BaseException as exc:
        if args.verbose or args.vvv:
            # Show the full traceback.
            raise
        else:
            # Print a one-line error message.
            print(exc)


def parse_data_type(raw_data_type):
    """
    Parse raw_data_type string as ChannelType. None passes through.

    '3', 'ENUM', and 'enum' all parse as <ChannelType.ENUM 3>.
    """
    if raw_data_type is None:
        data_type = None
    else:
        assert isinstance(raw_data_type, str)
        # ChannelType is an IntEnum.
        # If d is int, use ChannelType(d). If string, ChannelType[d].
        try:
            data_type_int = int(raw_data_type)
        except ValueError:
            data_type = ChannelType[raw_data_type.upper()]
        else:
            data_type = ChannelType(data_type_int)
    return data_type


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
        for elem in ChannelType:
            print(f'{elem.value: <2} {elem.name}')
        parser.exit()


if __name__ == '__main__':
    main()
