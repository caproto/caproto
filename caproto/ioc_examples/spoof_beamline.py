#!/usr/bin/env python3
from caproto.server import ioc_arg_parser, run

from collections import defaultdict
from caproto import (ChannelString, ChannelEnum, ChannelDouble,
                     ChannelChar, ChannelData)
import re


PLUGIN_TYPE_PVS = [
    (re.compile('image\\d:'), 'NDPluginStdArrays'),
    (re.compile('Stats\\d:'), 'NDPluginStats'),
    (re.compile('CC\\d:'), 'NDPluginColorConvert'),
    (re.compile('Proc\\d:'), 'NDPluginProcess'),
    (re.compile('Over\\d:'), 'NDPluginOverlay'),
    (re.compile('ROI\\d:'), 'NDPluginROI'),
    (re.compile('Trans\\d:'), 'NDPluginTransform'),
    (re.compile('netCDF\\d:'), 'NDFileNetCDF'),
    (re.compile('TIFF\\d:'), 'NDFileTIFF'),
    (re.compile('JPEG\\d:'), 'NDFileJPEG'),
    (re.compile('Nexus\\d:'), 'NDPluginNexus'),
    (re.compile('HDF\\d:'), 'NDFileHDF5'),
    (re.compile('Magick\\d:'), 'NDFileMagick'),
    (re.compile('TIFF\\d:'), 'NDFileTIFF'),
    (re.compile('HDF\\d:'), 'NDFileHDF5'),
    (re.compile('Current\\d:'), 'NDPluginStats'),
    (re.compile('SumAll'), 'NDPluginStats'),
]


class ReallyDefaultDict(defaultdict):
    def __contains__(self, key):
        return True

    def __missing__(self, key):
        if (key.endswith('-SP') or key.endswith('-I') or
                key.endswith('-RB') or key.endswith('-Cmd')):
            key, *_ = key.rpartition('-')
            return self[key]
        if key.endswith('_RBV') or key.endswith(':RBV'):
            return self[key[:-4]]
        ret = self[key] = self.default_factory(key)
        return ret


def fabricate_channel(key):
    if 'PluginType' in key:
        for pattern, val in PLUGIN_TYPE_PVS:
            if pattern.search(key):
                return ChannelString(value=val)
    elif 'ArrayPort' in key:
        return ChannelString(value=key)
    elif 'EnableCallbacks' in key:
        return ChannelEnum(value=0, enum_strings=['Disabled', 'Enabled'])
    elif 'BlockingCallbacks' in key:
        return ChannelEnum(value=0, enum_strings=['No', 'Yes'])
    elif 'Auto' in key:
        return ChannelEnum(value=0, enum_strings=['No', 'Yes'])
    elif 'ImageMode' in key:
        return ChannelEnum(value=0, enum_strings=['Single', 'Multiple', 'Continuous'])
    elif 'TriggerMode' in key:
        return ChannelEnum(value=0, enum_strings=['Internal', 'External'])
    elif 'FileWriteMode' in key:
        return ChannelEnum(value=0, enum_strings=['Single'])
    elif 'FilePathExists' in key:
        return ChannelData(value=1)
    elif ('file' in key.lower() and 'number' not in key.lower() and
          'mode' not in key.lower()):
        return ChannelChar(value='a' * 250)
    return ChannelDouble(value=0.0)


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
    print('''

                         PV blackhole started

''')
    _, run_options = ioc_arg_parser(
        default_prefix='',
        desc="PV black hole")
    run_options['interfaces'] = ['127.0.0.1']
    run(ReallyDefaultDict(fabricate_channel),
        **run_options)


if __name__ == '__main__':
    main()
