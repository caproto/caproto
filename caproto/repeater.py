import argparse
import logging
import os
from .sync.repeater import run
from . import color_logs


def main():
    parser = argparse.ArgumentParser(
        description="""
Run a Channel Access Repeater.

If the Repeater port is already in use, assume a Repeater is already running
and exit. That port number is set by the environment variable
EPICS_CA_REPEATER_PORT. It defaults to the standard 5065. The current value is
{}.""".format(os.environ.get('EPICS_CA_REPEATER_PORT', 5065)))

    group = parser.add_mutually_exclusive_group()
    group.add_argument('-q', '--quiet', action='store_true',
                       help=("Suppress INFO log messages. "
                             "(Still show WARNING or higher.)"))
    group.add_argument('-v', '--verbose', action='store_true',
                       help="Verbose mode. (Use -vvv for more.)")
    group.add_argument('-vvv', action='store_true',
                       help=argparse.SUPPRESS)
    parser.add_argument('--no-color', action='store_true',
                        help="Suppress ANSI color codes in log messages.")
    args = parser.parse_args()
    if args.no_color:
        color_logs(False)
    if args.vvv:
        logging.getLogger('caproto').setLevel('DEBUG')
    else:
        if args.verbose:
            level = 'DEBUG'
        elif args.quiet:
            level = 'WARNING'
        else:
            level = 'INFO'
        logging.getLogger('caproto.repeater').setLevel(level)
    try:
        run()
    except BaseException as exc:
        if args.verbose or args.vvv:
            # Show the full traceback.
            raise
        else:
            # Print a one-line error message.
            print(exc)


if __name__ == '__main__':
    main()
