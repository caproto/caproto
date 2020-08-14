import argparse
import dataclasses
import logging
import pprint

from ... import __version__
from ..._log import _set_handler_with_logger, set_handler
from ..._utils import ShowVersionAction
from ..sync.client import read

logger = logging.getLogger('caproto.pva.ctx')
serialization_logger = logging.getLogger('caproto.pva.serialization')


def main():
    parser = argparse.ArgumentParser(
        description='Read the value of a PV.',
        epilog=f'caproto version {__version__}'
    )
    parser.register('action', 'show_version', ShowVersionAction)
    fmt_group = parser.add_mutually_exclusive_group()
    parser.add_argument('pv_names', type=str, nargs='+',
                        help="PV (channel) name(s) separated by spaces")
    parser.add_argument('-r', '--pvrequest', type=str, default='field()',
                        help=("PVRequest"))
    fmt_group.add_argument('--terse', '-t', action='store_true',
                           help=("Display data only. Unpack scalars: "
                                 "[3.] -> 3."))
    parser.add_argument('--timeout', '-w', type=float, default=1,
                        help=("Timeout ('wait') in seconds for server "
                              "responses."))
    parser.add_argument('--verbose', '-v', action='count',
                        help="Show more log messages. (Use -vvv for even more.)")
    parser.add_argument('--no-color', action='store_true',
                        help="Suppress ANSI color codes in log messages.")
    parser.add_argument('--version', '-V', action='show_version',
                        default=argparse.SUPPRESS,
                        help="Show caproto version and exit.")

    args = parser.parse_args()
    if args.verbose:
        if args.verbose <= 2:
            for name in ('caproto.pva.ch', 'caproto.pva.ctx'):
                _set_handler_with_logger(color=not args.no_color, level='DEBUG',
                                         logger_name=name)
        else:
            set_handler(color=not args.no_color, level='DEBUG')

    try:
        for pv_name in args.pv_names:
            response = read(pv_name=pv_name, pvrequest=args.pvrequest,
                            verbose=args.verbose, timeout=args.timeout)

            dcls = response.dataclass_instance
            if args.terse:
                dcls = getattr(dcls, 'value', dcls)
                print(dcls)
            else:
                # TODO: make an option, somehow
                pprint.pprint(dataclasses.asdict(dcls))

    except BaseException as exc:
        if args.verbose:
            # Show the full traceback.
            raise
        else:
            # Print a one-line error message.
            print(exc)


if __name__ == '__main__':
    main()
