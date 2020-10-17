#!/usr/bin/env python3
"""
A basic caproto-pva test server with normative types.
"""
from caproto.pva.server import (PVAGroup, ServerRPC, ioc_arg_parser,
                                pvaproperty, run)


class NormativeIOC(PVAGroup):
    nt_bool = pvaproperty(value=True)
    nt_int = pvaproperty(value=42)
    nt_float = pvaproperty(value=42.1)
    nt_string = pvaproperty(value='test')
    nt_int_array = pvaproperty(value=[42])
    nt_float_array = pvaproperty(value=[42.1])
    nt_string_array = pvaproperty(value=['test'])


def main():
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='caproto:pva:',
        desc='A basic caproto-pva test server for normative types.'
    )

    ioc = NormativeIOC(**ioc_options)
    server_info = ServerRPC(prefix='', server_instance=ioc)
    ioc.pvdb.update(server_info.pvdb)
    run(ioc.pvdb, **run_options)


if __name__ == '__main__':
    main()
