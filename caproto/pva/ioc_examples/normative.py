#!/usr/bin/env python3
"""
A basic caproto-pva test server with normative types.
"""
import caproto.pva as pva
from caproto.pva.server import ioc_arg_parser, run


class MyIOC(pva.PVAGroup):
    bool_nt = pva.pvaproperty(value=True, name='bool')
    int_nt = pva.pvaproperty(value=42, name='int')
    float_nt = pva.pvaproperty(value=42.1, name='float')
    string_nt = pva.pvaproperty(value='test', name='str')
    int_array = pva.pvaproperty(value=[42])
    float_array = pva.pvaproperty(value=[42.1])
    string_array = pva.pvaproperty(value=['test'])


def main():
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='caproto:pva:',
        desc='A basic caproto-pva test server for normative types.'
    )

    ioc = MyIOC(**ioc_options)
    server_info = pva.ServerRPC(prefix='', server_instance=ioc)
    ioc.pvdb.update(server_info.pvdb)
    run(ioc.pvdb, **run_options)


if __name__ == '__main__':
    main()
