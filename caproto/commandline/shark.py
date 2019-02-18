"""
This module is installed as an entry-point, available as:

caproto-shark ...

It can equivalently be invoked as:

python3 -m caproto.commandline.shark ...

For access to the underlying functionality from a Python script or interactive
Python session, do not import this module; instead import caproto.sync.shark.
"""
import argparse
import sys
from ..sync.shark import shark
from .. import __version__, CLIENT, SERVER
from .._utils import ShowVersionAction


def main():
    parser = argparse.ArgumentParser(description='Parse CA network traffic.',
                                     epilog=f'caproto version {__version__}')
    parser.register('action', 'show_version', ShowVersionAction)
    parser.add_argument('--version', '-V', action='show_version',
                        default=argparse.SUPPRESS,
                        help="Show caproto version and exit.")
    parser.add_argument('--format', type=str,
                        help=("Python format string. Available tokens are "
                              "{timestamp}, {ethernet}, {ip}, {transport}, "
                              "{role}, {command} and {src} and {dst}, which "
                              "are {ip.src} and {ip.dst} decoded into "
                              "numbers-and-dots form."),
                        default=('{timestamp} '
                                 '{src}:{transport.sport}->{dst}:{transport.dport} '
                                 '{command}'))
    args = parser.parse_args()
    try:
        for namespace in shark(sys.stdin.buffer):
            print(args.format.format(timestamp=namespace.timestamp,
                                     ethernet=repr(namespace.ethernet),
                                     ip=repr(namespace.ip),
                                     transport=repr(namespace.transport),
                                     src=namespace.src,
                                     dst=namespace.dst,
                                     role=namespace.role,
                                     command=namespace.command))
    except BaseException as exc:
        raise


if __name__ == '__main__':
    main()
