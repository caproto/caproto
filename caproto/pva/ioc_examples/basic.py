#!/usr/bin/env python3
"""
A basic caproto-pva test server.

This is very much preliminary API.
"""
import warnings

import caproto.pva as pva
from caproto.pva.server import ioc_arg_parser, run


@pva.pva_dataclass
class MyData:
    value: int
    info: str


pvdb = {
    'test': MyData(value=5, info='a string'),
    'test2': MyData(value=6, info='a different string'),
}


def main():
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='caproto:pva:',
        desc='A basic caproto-pva test server.'
    )

    prefix = ioc_options['prefix']
    prefixed_pvdb = {prefix + key: value for key, value in pvdb.items()}
    warnings.warn("The IOC options are ignored by this IOC. "
                  "It needs to be updated.")
    run(prefixed_pvdb, **run_options)


if __name__ == '__main__':
    main()
