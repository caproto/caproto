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
from .. import __version__
from .._utils import ShowVersionAction


def main():
    parser = argparse.ArgumentParser(
        description='Parse pcap (tcpdump) output and pretty-print CA commands.',
        epilog=f'caproto version {__version__}')
    parser.register('action', 'show_version', ShowVersionAction)
    parser.add_argument('--format', type=str,
                        help=("Python format string. Available tokens are "
                              "{timestamp}, {ethernet}, {ip}, {transport}, "
                              "{command} and {src} and {dst}, which are "
                              "{ip.src} and {ip.dst} decoded into "
                              "numbers-and-dots form."),
                        default=('{timestamp} '
                                 '{src}:{transport.sport}->{dst}:{transport.dport} '
                                 '{command}'))
    parser.add_argument('--version', '-V', action='show_version',
                        default=argparse.SUPPRESS,
                        help="Show caproto version and exit.")
    args = parser.parse_args()
    try:
        for namespace in shark(sys.stdin.buffer):
            print(args.format.format(timestamp=namespace.timestamp,
                                     ethernet=namespace.ethernet,
                                     ip=namespace.ip,
                                     transport=namespace.transport,
                                     src=namespace.src,
                                     dst=namespace.dst,
                                     command=namespace.command))

    except KeyboardInterrupt:
        return


if __name__ == '__main__':
    main()
