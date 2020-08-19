#!/usr/bin/env python3
"""
NOTICE

This particular example predates the IOC class framework that makes IOC
specification much more succinct.
"""
import warnings

# import caproto as ca
import caproto.pva as pva
from caproto.pva.server import ioc_arg_parser, run

# import numpy as np


pvdb = {'caproto': 'foobar'}


def main():
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='type_varieties:',
        desc='Run an IOC with PVs of various data types.')
    prefix = ioc_options['prefix']
    prefixed_pvdb = {prefix + key: value for key, value in pvdb.items()}
    warnings.warn("The IOC options are ignored by this IOC. "
                  "It needs to be updated.")
    run(prefixed_pvdb, **run_options)


if __name__ == '__main__':
    main()
