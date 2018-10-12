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
import logging
import time
from ..sync.client import subscribe, block
from .. import SubscriptionType, color_logs


def main():
    parser = argparse.ArgumentParser(description='Read the value of a PV.')
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
    args = parser.parse_args()
    if args.no_color:
        color_logs(False)
    if args.verbose:
        logging.getLogger('caproto.ch').setLevel('DEBUG')
        logging.getLogger(f'caproto.ctx').setLevel('DEBUG')
        if args.verbose > 2:
            logging.getLogger('caproto').setLevel('DEBUG')

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
        if args.format is None:
            format_str = ("{pv_name: <40}  {timestamp:%Y-%m-%d %H:%M:%S.%f} "
                          "{response.data}")
        else:
            format_str = args.format
        tokens['pv_name'] = pv_name
        tokens['response'] = response
        dt = datetime.fromtimestamp(response.metadata.timestamp)
        tokens['timestamp'] = dt
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
