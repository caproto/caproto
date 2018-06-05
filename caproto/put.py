import argparse
from datetime import datetime
import logging
from .sync.client import write
from .sync.repeater import spawn_repeater, repeater_args
from . import color_logs


def main():
    parser = argparse.ArgumentParser(description='Write a value to a PV.')
    fmt_group = parser.add_mutually_exclusive_group()
    parser.add_argument('pv_name', type=str,
                        help="PV (channel) name")
    parser.add_argument('data', type=str,
                        help="Value or values to write.")
    fmt_group.add_argument('--format', type=str,
                           help=("Python format string. Available tokens are "
                                 "{pv_name} and {response}. Additionally, "
                                 "this data type includes time, {timestamp} "
                                 "and usages like "
                                 "{timestamp:%%Y-%%m-%%d %%H:%%M:%%S} are "
                                 "supported."))
    parser.add_argument('--no-repeater', action='store_true',
                        help=("Do not spawn a Channel Access repeater daemon "
                              "process."))
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
                        help="Show DEBUG log messages.")
    parser.add_argument('-vvv', action='store_true',
                        help=argparse.SUPPRESS)
    parser.add_argument('--no-color', action='store_true',
                        help="Suppress ANSI color codes in log messages.")
    args = parser.parse_args()
    if not args.no_repeater:
        # Spawn the repeater (if needed) manually here so we can pass through
        # preferences about verboseness etc.
        spawn_repeater(repeater_args(args))
    if args.no_color:
        color_logs(False)
    if args.verbose:
        logging.getLogger('caproto.put').setLevel('DEBUG')
    if args.vvv:
        logging.getLogger('caproto').setLevel('DEBUG')
    try:
        initial, final = write(pv_name=args.pv_name, data=args.data,
                               timeout=args.timeout,
                               priority=args.priority,
                               repeater=not args.no_repeater)
        if args.format is None:
            format_str = '{pv_name: <40}  {response.data}'
        else:
            format_str = args.format
        if args.terse:
            if len(initial.data) == 1:
                format_str = '{response.data[0]}'
            else:
                format_str = '{response.data}'
        tokens = dict(pv_name=args.pv_name, response=initial)
        if hasattr(initial.metadata, 'timestamp'):
            dt = datetime.fromtimestamp(initial.metadata.timestamp)
            tokens['timestamp'] = dt
        print(format_str.format(**tokens))
        tokens = dict(pv_name=args.pv_name, response=final)
        if hasattr(final.metadata, 'timestamp'):
            dt = datetime.fromtimestamp(final.metadata.timestamp)
            tokens['timestamp'] = dt
        tokens = dict(pv_name=args.pv_name, response=final)
        print(format_str.format(**tokens))
    except BaseException as exc:
        if args.verbose or args.vvv:
            # Show the full traceback.
            raise
        else:
            # Print a one-line error message.
            print(exc)


if __name__ == '__main__':
    main()
