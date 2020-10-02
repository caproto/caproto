"""
This module is installed as an entry-point, available from the shell as:

caproto-put ...

It can equivalently be invoked as:

python3 -m caproto.commandline.put ...

For access to the underlying functionality from a Python script or interactive
Python session, do not import this module; instead import caproto.sync.client.
"""
import argparse
import ast
import sys
from datetime import datetime
import logging
from .. import set_handler, __version__
from ..sync.client import read_write_read
from .._log import _set_handler_with_logger
from .._utils import ShowVersionAction


def main():
    parser = argparse.ArgumentParser(description='Write a value to a PV.',
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
    parser.add_argument('--notify', '-c', action='store_true',
                        help=("Request notification of completion, and wait "
                              "for it."))
    parser.add_argument('--priority', '-p', type=int, default=0,
                        help="Channel Access Virtual Circuit priority. "
                             "Lowest is 0; highest is 99.")
    fmt_group.add_argument('--terse', '-t', action='store_true',
                           help=("Display data only. Unpack scalars: "
                                 "[3.] -> 3."))
    # caget calls this "wide mode" with -a  (used for array mode in caput) and
    # caput calls it "long mode" with -l.
    fmt_group.add_argument('--wide', '-l', action='store_true',
                           help=("Wide mode, showing "
                                 "'name timestamp value status'"
                                 "(implies -d 'time')"))
    # TODO caget/caput also include a 'srvr' column which seems to be `sid`. We
    # would need a pretty invasive refactor to access that from here.
    parser.add_argument('-n', action='store_true',
                        help=("Retrieve enums as integers (default is "
                              "strings)."))
    parser.add_argument('--array', '-a', action='store_true',
                        help=("Interprets `data` as an array, delimited by "
                              "space"))
    parser.add_argument('--file', action='store_true',
                        help=("Interprets `data` as a file"))
    parser.add_argument('--array-pad', type=int, default=0,
                        help=("Pad the array up to a specified length"))
    parser.add_argument('-S', dest='as_string', action='store_true',
                        help=("Interpret `data` as a string of characters."))
    parser.add_argument('--no-color', action='store_true',
                        help="Suppress ANSI color codes in log messages.")
    parser.add_argument('--no-repeater', action='store_true',
                        help=("Do not spawn a Channel Access repeater daemon "
                              "process."))
    parser.add_argument('--version', '-V', action='show_version',
                        default=argparse.SUPPRESS,
                        help="Show caproto version and exit.")
    args = parser.parse_args()
    if args.verbose:
        if args.verbose <= 2:
            _set_handler_with_logger(color=not args.no_color, level='DEBUG', logger_name='caproto.ch')
            _set_handler_with_logger(color=not args.no_color, level='DEBUG', logger_name='caproto.ctx')
        else:
            set_handler(color=not args.no_color, level='DEBUG')
    logger = logging.LoggerAdapter(logging.getLogger('caproto.ch'), {'pv': args.pv_name})

    if args.file:
        with open(str(args.data), mode='r') as file:
            raw_data = file.read()
    else:
        raw_data = args.data

    if args.as_string:
        # interpret as string
        data = raw_data
    elif args.array:
        data = [ast.literal_eval(val) for val in raw_data.split(' ')]
        if args.array_pad > 0:
            if len(data) < args.array:
                data.extend([0] * (args.array - len(data)))
            elif len(data) > args.array:
                logger.error('Pad value smaller than array size')
                sys.exit(1)
    else:
        try:
            data = ast.literal_eval(raw_data)
        except ValueError:
            # interpret as string
            data = raw_data

    if args.wide:
        read_data_type = 'time'
    else:
        read_data_type = None
    logger.debug('Data argument %s parsed as %r (Python type %s).',
                 args.data, data, type(data).__name__)
    try:
        initial, _, final = read_write_read(pv_name=args.pv_name, data=data,
                                            read_data_type=read_data_type,
                                            notify=args.notify,
                                            timeout=args.timeout,
                                            priority=args.priority,
                                            force_int_enums=args.n,
                                            repeater=not args.no_repeater)
        if args.format is None:
            format_str = '{which} : {pv_name: <40}  {response.data}'
        else:
            format_str = args.format
        if args.terse:
            if len(initial.data) == 1:
                format_str = '{response.data[0]}'
            else:
                format_str = '{response.data}'
        elif args.wide:
            # TODO Make this look more like caput -l
            format_str = '{pv_name} {timestamp} {response.data} {response.status.name}'
        tokens = dict(pv_name=args.pv_name, response=initial)
        if hasattr(initial.metadata, 'timestamp'):
            dt = datetime.fromtimestamp(initial.metadata.timestamp)
            tokens['timestamp'] = dt
        print(format_str.format(which='Old', **tokens))
        tokens = dict(pv_name=args.pv_name, response=final)
        if hasattr(final.metadata, 'timestamp'):
            dt = datetime.fromtimestamp(final.metadata.timestamp)
            tokens['timestamp'] = dt
        print(format_str.format(which='New', **tokens))
    except BaseException as exc:
        if args.verbose:
            # Show the full traceback.
            raise
        else:
            # Print a one-line error message.
            print(exc)


if __name__ == '__main__':
    main()
