"""
This module is installed as an entry-point, available from the shell as:

caproto-monitor ...

It can equivalently be invoked as:

python3 -m caproto.commandline.monitor ...

For access to the underlying functionality from a Python script or interactive
Python session, do not import this module; instead import caproto.sync.client.
"""
import argparse
from datetime import datetime
import functools
import time
from ..sync.client import subscribe, block
from .. import SubscriptionType, set_handler, __version__
from .._log import _set_handler_with_logger
from .._utils import ShowVersionAction
from .cli_print_formats import (format_response_data, gen_data_format,
                                clean_format_args, format_str_adjust)


def main():
    parser = argparse.ArgumentParser(description='Read the value of a PV.',
                                     epilog=f'caproto version {__version__}')
    parser.register('action', 'show_version', ShowVersionAction)
    fmt_group = parser.add_mutually_exclusive_group()
    exit_group = parser.add_mutually_exclusive_group()
    parser.add_argument('pv_names', type=str, nargs='+',
                        help="PV (channel) name")
    fmt_group.add_argument('--format', type=str,
                           help=("Python format string. Available tokens are "
                                 "{pv_name}, {response}, {callback_count}. "
                                 "Additionally, if this data type includes "
                                 "time, {timestamp}, {timedelta} and usages "
                                 "like {timestamp:%%Y-%%m-%%d %%H:%%M:%%S} are"
                                 " supported."))
    parser.add_argument('--verbose', '-v', action='count',
                        help="Show more log messages. (Use -vvv for even more.)")
    exit_group.add_argument('--duration', type=float, default=None,
                            help=("Maximum number seconds to run before "
                                  "exiting. Runs indefinitely by default."))
    exit_group.add_argument('--maximum', type=int, default=None,
                            help=("Maximum number of monitor events to "
                                  "process exiting. Unlimited by "
                                  "default."))
    parser.add_argument('--timeout', '-w', type=float, default=1,
                        help=("Timeout ('wait') in seconds for server "
                              "responses."))
    parser.add_argument('-m', type=str, metavar='MASK', default='va',
                        help=("Channel Access mask. Any combination of "
                              "'v' (value), 'a' (alarm), 'l' (log/archive), "
                              "'p' (property). Default is 'va'."))
    parser.add_argument('--priority', '-p', type=int, default=0,
                        help="Channel Access Virtual Circuit priority. "
                             "Lowest is 0; highest is 99.")
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

    mask = 0
    if 'v' in args.m:
        mask |= SubscriptionType.DBE_VALUE
    if 'a' in args.m:
        mask |= SubscriptionType.DBE_ALARM
    if 'l' in args.m:
        mask |= SubscriptionType.DBE_LOG
    if 'p' in args.m:
        mask |= SubscriptionType.DBE_PROPERTY

    history = []
    tokens = {'callback_count': 0}

    def callback(pv_name, response):
        tokens['callback_count'] += 1

        data_fmt = gen_data_format(args=args, data=response.data)

        if args.format is None:
            if args.F is None:
                format_str = ("{pv_name: <40}  {timestamp:%Y-%m-%d %H:%M:%S.%f} "
                              "{response.data}")
            else:
                format_str = ("{pv_name}  {timestamp:%Y-%m-%d %H:%M:%S.%f} "
                              "{response.data}")
        else:
            format_str = args.format

        format_str = format_str_adjust(format_str=format_str, data_fmt=data_fmt)

        response_data_str = format_response_data(data=response.data,
                                                 data_fmt=data_fmt)

        tokens['pv_name'] = pv_name
        tokens['response'] = response
        dt = datetime.fromtimestamp(response.metadata.timestamp)
        tokens['timestamp'] = dt
        tokens['response_data'] = response_data_str

        if history:
            # Add a {timedelta} token using the previous timestamp.
            td = dt - history.pop()
        else:
            # Special case for the first reading: show difference between
            # timestamp and current time -- showing how old the most recent
            # update is.
            td = datetime.fromtimestamp(time.time()) - dt
        history.append(dt)
        tokens['timedelta'] = td
        print(format_str.format(**tokens), flush=True)

        if args.maximum is not None:
            if tokens['callback_count'] >= args.maximum:
                raise KeyboardInterrupt()
    try:
        subs = []
        cbs = []
        for pv_name in args.pv_names:
            sub = subscribe(pv_name,
                            mask=mask,
                            priority=args.priority)
            cb = functools.partial(callback, pv_name)
            sub.add_callback(cb)
            cbs.append(cb)  # Hold ref to keep cb from being garbage collected.
            subs.append(sub)
        # Wait to be interrupted by KeyboardInterrupt.
        block(*subs, duration=args.duration, timeout=args.timeout,
              force_int_enums=args.n,
              repeater=not args.no_repeater)
    except BaseException as exc:
        if args.verbose:
            # Show the full traceback.
            raise
        else:
            # Print a one-line error message.
            print(exc)


if __name__ == '__main__':
    main()
