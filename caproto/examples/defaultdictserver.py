#!/usr/bin/env python3

import curio
from collections import defaultdict
import caproto.curio.server as ccs
from caproto import ChannelData


class ReallyDefaultDict(defaultdict):
    def __contains__(self, key):
        return True


def main():
    print('''
*** WARNING ***
This script spawns an EPICS IOC which responds to ALL caget, caput, camonitor
requests.  As this is effectively a PV black hole, it may affect the
performance and functionality of other IOCs on your network.
*** WARNING ***

Press return if you have acknowledged the above, or Ctrl-C to quit.''')

    try:
        input()
    except KeyboardInterrupt:
        print()
        return

    curio.run(
        ccs.start_server(ReallyDefaultDict(lambda: ChannelData(value=0)),
                         bind_addr='127.0.0.1')
    )


if __name__ == '__main__':
    main()
