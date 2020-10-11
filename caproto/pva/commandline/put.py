import argparse
import ast
import json
import logging

from ... import __version__
from ..._utils import ShowVersionAction
from ..sync.client import read_write_read
from ._shared import configure_logging

logger = logging.getLogger('caproto.pva.ctx')


def main():
    parser = argparse.ArgumentParser(
        description='Write a value to a PV.',
        epilog=f'caproto version {__version__}')
    parser.register('action', 'show_version', ShowVersionAction)
    fmt_group = parser.add_mutually_exclusive_group()
    parser.add_argument('pv_name', type=str,
                        help="PV (channel) name")
    parser.add_argument('data', type=str,
                        help="Value or values to write.")
    parser.add_argument('--verbose', '-v', action='count',
                        help="Show more log messages. (Use -vvv for even more.)")
    fmt_group.add_argument('--format', type=str,
                           help=("Python format string. Available tokens are "
                                 "{pv_name}, {response} and {which} (Old/New)."
                                 "Additionally, "
                                 "this data type includes time, {timestamp} "
                                 "and usages like "
                                 "{timestamp:%%Y-%%m-%%d %%H:%%M:%%S} are "
                                 "supported."))
    parser.add_argument('--timeout', '-w', type=float, default=1,
                        help=("Timeout ('wait') in seconds for server "
                              "responses."))
    fmt_group.add_argument('--terse', '-t', action='store_true',
                           help=("Display data only. Unpack scalars: "
                                 "[3.] -> 3."))
    fmt_group.add_argument('--wide', '-l', action='store_true',
                           help=("Wide mode, showing "
                                 "'name timestamp value status'"
                                 "(implies -d 'time')"))
    parser.add_argument('--file', action='store_true',
                        help=("Interprets `data` as a file"))
    parser.add_argument('--no-color', action='store_true',
                        help="Suppress ANSI color codes in log messages.")
    parser.add_argument('--version', '-V', action='show_version',
                        default=argparse.SUPPRESS,
                        help="Show caproto version and exit.")
    args = parser.parse_args()

    configure_logging(verbose=args.verbose, color=not args.no_color)

    logger = logging.LoggerAdapter(logging.getLogger('caproto.pva.ch'), {'pv': args.pv_name})

    if args.file:
        with open(str(args.data), mode='r') as file:
            raw_data = file.read()
    else:
        raw_data = args.data

    try:
        data = json.loads(raw_data)
    except ValueError:
        try:
            data = ast.literal_eval(raw_data)
        except ValueError:
            # interpret as string
            data = raw_data
            if data.startswith('{'):  # }
                raise ValueError('You probably meant for this to be JSON')

    logger.debug('Data argument %s parsed as %r (Python type %s).',
                 args.data, data, type(data).__name__)
    try:
        initial, _, final = read_write_read(
            pv_name=args.pv_name, data=data, timeout=args.timeout,
        )

        if args.terse:
            initial = getattr(initial, 'value', initial)

        print('Old:', initial)

        if args.terse:
            final = getattr(final, 'value', final)
        print('New:', final)
    except BaseException as exc:
        if args.verbose:
            # Show the full traceback.
            raise
        else:
            # Print a one-line error message.
            print(exc)


if __name__ == '__main__':
    main()
