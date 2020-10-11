import argparse
import datetime
import logging

from ... import __version__
from ..._utils import ShowVersionAction
from .._dataclass import get_pv_structure
from .._utils import timestamp_to_datetime
from ..sync.client import monitor
from ._shared import configure_logging

logger = logging.getLogger('caproto.pva.ctx')


def main():
    parser = argparse.ArgumentParser(
        description='Monitor the value of a PV.',
        epilog=f'caproto version {__version__}',
    )
    parser.register('action', 'show_version', ShowVersionAction)
    parser.add_argument('pv_names', type=str, nargs='+',
                        help="PV (channel) name(s) separated by spaces")
    parser.add_argument('-r', '--pvrequest', type=str, default='field()',
                        help=("PVRequest"))
    fmt_group = parser.add_mutually_exclusive_group()
    fmt_group.add_argument('--terse', '-t', action='store_true',
                           help=("Display data only. Unpack scalars: "
                                 "[3.] -> 3."))
    fmt_group.add_argument('--full', action='store_true',
                           help=("Print full structure each time"))
    fmt_group.add_argument('--format', type=str, default='{timestamp} {pv_name} {value}',
                           help=("Python format string. Available tokens are "
                                 "{pv_name} and {data}. Additionally, if "
                                 "this data type includes time, {timestamp} "
                                 "and usages like "
                                 "{timestamp:%%Y-%%m-%%d %%H:%%M:%%S} are "
                                 "supported. "))
    parser.add_argument('--timeout', '-w', type=float, default=1,
                        help=("Timeout ('wait') in seconds for server "
                              "responses."))
    parser.add_argument('--verbose', '-v', action='count',
                        help="Show more log messages. (Use -vvv for even more.)")
    parser.add_argument('--maximum', type=int, default=None,
                        help="Maximum number of monitor events to display.")
    parser.add_argument('--no-color', action='store_true',
                        help="Suppress ANSI color codes in log messages.")
    parser.add_argument('--version', '-V', action='show_version',
                        default=argparse.SUPPRESS,
                        help="Show caproto version and exit.")
    args = parser.parse_args()

    configure_logging(verbose=args.verbose, color=not args.no_color)

    try:
        pv_name = args.pv_names[0]
        if args.terse:
            format_str = '{timestamp} {pv_name} {value}'
        else:
            format_str = args.format

        timestamp = '(No timestamp)'

        results = monitor(pv_name=pv_name, pvrequest=args.pvrequest,
                          verbose=args.verbose, timeout=args.timeout,
                          maximum_events=args.maximum)
        for idx, (event, data) in enumerate(results):
            if idx == 0 and (args.verbose or 0) > 0:
                print(get_pv_structure(data).summary())

            try:
                timestamp = timestamp_to_datetime(
                    data.timeStamp.secondsPastEpoch,
                    data.timeStamp.nanoseconds,
                )
            except AttributeError:
                # May not have a timestamp
                timestamp = datetime.datetime.now()

            if args.full:
                print(format_str.format(pv_name=pv_name,
                                        timestamp=timestamp,
                                        value=data))
                continue

            try:
                print(format_str.format(pv_name=pv_name,
                                        timestamp=timestamp,
                                        value=data))
            except Exception as ex:
                print('(print format failed)', ex, data)

    except BaseException as exc:
        if args.verbose:
            # Show the full traceback.
            raise
        else:
            # Print a one-line error message.
            print(exc)


if __name__ == '__main__':
    main()
