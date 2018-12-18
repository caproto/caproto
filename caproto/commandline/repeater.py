"""
This module is installed as an entry-point, available from the shell as:

caproto-repeater ...

It can equivalently be invoked as:

python3 -m caproto.commandline.repeater ...

For access to the underlying functionality from a Python script or interactive
Python session, do not import this module; instead import
caproto.sync.repeater.
"""
import argparse
import logging
import os
from ..sync.repeater import run
from .. import set_handler, __version__
from .._utils import ShowVersionAction


def main():
    parser = argparse.ArgumentParser(
        description="""
Run a Channel Access Repeater.

If the Repeater port is already in use, assume a Repeater is already running
and exit. That port number is set by the environment variable
EPICS_CA_REPEATER_PORT. It defaults to the standard 5065. The current value is
{}.""".format(os.environ.get('EPICS_CA_REPEATER_PORT', 5065)),
        epilog=f'caproto version {__version__}')
    parser.register('action', 'show_version', ShowVersionAction)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-q', '--quiet', action='store_true',
                       help=("Suppress INFO log messages. "
                             "(Still show WARNING or higher.)"))
    group.add_argument('-v', '--verbose', action='count',
                       help="Verbose mode. (Use -vvv for more.)")
    parser.add_argument('--no-color', action='store_true',
                        help="Suppress ANSI color codes in log messages.")
    parser.add_argument('--version', '-V', action='show_version',
                        default=argparse.SUPPRESS,
                        help="Show caproto version and exit.")
    args = parser.parse_args()
    if args.no_color:
        set_handler(color=False)
    if args.verbose and args.verbose > 2:
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
        if args.verbose:
            # Show the full traceback.
            raise
        else:
            # Print a one-line error message.
            print(exc)


if __name__ == '__main__':
    main()
