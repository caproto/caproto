#!/usr/bin/env python3

from caproto.server import ioc_arg_parser, run
from collections import defaultdict
from caproto import ChannelData
import logging
logger = logging.getLogger('caproto')

class ReallyDefaultDict(dict):
    def __contains__(self, key):
        if 'ALS:701' in key:
            logger.critical(f'Captured {key}')
            return True

    def __missing__(self, key):
        logger.info(f'Checking key {key}')
        if 'ALS:701' in key:
            logger.critical(f'Captured {key}')
            return ChannelData(value=0)

def main():
    print('''
*** WARNING ***
This script spawns an EPICS IOC which responds to ALL caget, caput, camonitor
requests.  As this is effectively a PV black hole, it may affect the
performance and functionality of other IOCs on your network.

The script ignores the --interfaces command line argument, always
binding only to 127.0.0.1, superseding the usual default (0.0.0.0) and any
user-provided value.
*** WARNING ***

Press return if you have acknowledged the above, or Ctrl-C to quit.''')

    try:
        input()
    except KeyboardInterrupt:
        print()
        return

    _, run_options = ioc_arg_parser(
        default_prefix='',
        desc="PV black hole")
    #run_options['interfaces'] = ['127.0.0.1']
    run(ReallyDefaultDict(),
        **run_options)


if __name__ == '__main__':
    main()
