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
from datetime import datetime
import logging
from ..sync.client import read_write_read
from .. import color_logs


def main():
    parser = argparse.ArgumentParser(description='Write a value to a PV.')
    fmt_group = parser.add_mutually_exclusive_group()
    parser.add_argument('pv_name', type=str,
                        help="PV (channel) name")
    parser.add_argument('data', type=str,
                        help="Value or values to write.")
    parser.add_argument('--verbose', '-v', action='store_true',
                        help="Show DEBUG log messages.")
    parser.add_argument('-vvv', action='store_true',
                        help=argparse.SUPPRESS)
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
    # caget calls this "wide mode" with -a and caput calls it "long mode" with
    # -l. We will support both -a and -l in both caproto-get and caproto-put.
    fmt_group.add_argument('--wide', '-a', '-l', action='store_true',
                           help=("Wide mode, showing "
                                 "'name timestamp value status'"
                                 "(implies -d 'time')"))
    # TODO caget/caput also include a 'srvr' column which seems to be `sid`. We
    # would need a pretty invasive refactor to access that from here.
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
    if args.vvv:
        logging.getLogger('caproto').setLevel('DEBUG')
    logger = logging.getLogger(f'caproto.ch.{args.pv_name}')
    try:
        data = ast.literal_eval(args.data)
    except ValueError:
        # interpret as string
        data = args.data
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
        if args.verbose or args.vvv:
            # Show the full traceback.
            raise
        else:
            # Print a one-line error message.
            print(exc)


if __name__ == '__main__':
    main()
