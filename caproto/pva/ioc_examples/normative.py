#!/usr/bin/env python3
"""
A basic caproto-pva test server with normative types.
"""
import caproto.pva as pva
from caproto.pva.server import ioc_arg_parser, run


class MyIOC(pva.PVAGroup):
    int_nt = pva.pvaproperty(value=32, name='int')


def main():
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='caproto:pva:',
        desc='A basic caproto-pva test server.'
    )

    ioc = MyIOC(**ioc_options)
    server_info = pva.ServerRPC(prefix='', server_instance=ioc)
    ioc.pvdb.update(server_info.pvdb)
    run(ioc.pvdb, **run_options)


if __name__ == '__main__':
    main()
