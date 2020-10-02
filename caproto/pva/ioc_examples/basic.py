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


@pva.pva_dataclass(name='epics:nt/NTScalar:1.0')
class NormativeIsh:
    value: float

    @pva.pva_dataclass
    class alarm_t:
        severity: pva.Int32
        status: pva.Int32
        message: str

    alarm: alarm_t

    @pva.pva_dataclass
    class time_t:
        secondsPastEpoch: pva.Int64
        nanoSeconds: pva.UInt32
        userTag: pva.UInt32

    timeStamp: time_t


pvdb = {
    'test': MyData(value=5, info='a string'),
    'test2': MyData(value=6, info='a different string'),
    'test3': NormativeIsh(value=1.0),
}


class AuthenticationError(RuntimeError):
    ...


class DataWrapper:
    def __init__(self, pvname, data):
        self.pvname = pvname
        self.data = data

    def authenticate(self, authorization):
        if authorization['method'] == 'ca':
            # user = authorization['data'].user
            # if user != 'klauer':
            #     raise AuthenticationError(f'No, {user}.')
            return

        if authorization['method'] in {'anonymous', ''}:
            ...

    async def auth_write(self, request, *, authorization):
        self.authenticate(authorization)
        return self.data

    async def auth_read_interface(self, *, authorization):
        self.authenticate(authorization)
        return self.data

    async def auth_read(self, request, *, authorization):
        self.authenticate(authorization)
        return await self.read(request)

    async def read(self, request):
        # self.data.value += 1
        return self.data

    async def write(self, update):
        print('saw a write!', update)
        pva.fill_dataclass(self.data, update.data)


def main():
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='caproto:pva:',
        desc='A basic caproto-pva test server.'
    )

    prefix = ioc_options['prefix']
    prefixed_pvdb = {
        prefix + key: DataWrapper(prefix + key, value)
        for key, value in pvdb.items()
    }
    warnings.warn("The parsed IOC options are ignored by this IOC for now.")
    run(prefixed_pvdb, **run_options)


if __name__ == '__main__':
    main()
