#!/usr/bin/env python3
"""
A basic caproto-pva test server.

This is very much preliminary API.
"""
import typing

import caproto.pva as pva
from caproto.pva.server import ioc_arg_parser, run


@pva.pva_dataclass
class MyData:
    value: int
    info: str


@pva.pva_dataclass
class NestedData:
    my_data: MyData
    value: float


class MyIOC(pva.PVAGroup):
    test = pva.pvaproperty(value=MyData(value=5, info='a string'))
    test2 = pva.pvaproperty(value=MyData(value=6, info='a different string'))
    test3 = pva.pvaproperty(value=NestedData)
    long_write = pva.pvaproperty(value=MyData())
    rpc = pva.pvaproperty(value=MyData())

    @test.putter  # (accepts=['value'])   (potential API?)
    async def test(self, instance, update: pva.WriteUpdate):
        """
        Put handler.

        Default handling: `update.accept()` (take everything)

        The following also work::

            1. update.accept('value', 'info')
            2. update.reject('info')
            3. if 'value' in update:
                  instance.value = update.instance.value
        """
        ...

    @test.startup
    async def test(self, instance, async_lib):
        self.async_lib = async_lib

        while True:
            async with self.test as test:
                test.value = test.value + 1
                test.info = f'testing {test.value}'

            await async_lib.library.sleep(0.5)

    @test.shutdown
    async def test(self, instance, async_lib):
        print('shutdown')

    @test2.startup
    async def test2(self, instance, async_lib):
        while True:
            async with self.test2 as test2, self.test3 as test3:
                # Swap values
                test2.value, test3.value = int(test3.value), float(test2.value)

            await async_lib.library.sleep(2.0)

    @rpc.call
    async def rpc(self, instance, data):
        # Some awf... nice normative type stuff comes through here (NTURI):
        print('RPC call data is', data)
        print('Scheme:', data.scheme)
        print('Query:', data.query)
        print('Path:', data.path)

        # Echo back the query value, if available:
        query = data.query
        value = int(getattr(query, 'value', '1234'))
        return MyData(value=value)

    @long_write.putter
    async def long_write(self, instance, update: pva.WriteUpdate):
        await self.async_lib.library.sleep(10)


class ServerRPC(pva.PVAGroup):
    """
    Helper group for supporting ``pvlist`` and other introspection tools.
    """

    @pva.pva_dataclass
    class HelpInfo:
        # TODO: technically epics:nt/NTScalar
        value: str

    @pva.pva_dataclass
    class ChannelListing:
        # TODO: technically epics:nt/NTScalarArray
        value: typing.List[str]

    @pva.pva_dataclass
    class ServerInfo:
        # responseHandlers.cpp
        version: str
        implLang: str
        host: str
        process: str
        startTime: str

    # This is the special
    server = pva.pvaproperty(value=ServerInfo(), name='server')

    def __init__(self, *args, server_instance, **kwargs):
        super().__init__(*args, **kwargs)
        self.server_instance = server_instance

    @server.call
    async def server(self, instance, data):
        # Some awf... nice normative type stuff comes through here (NTURI):
        self.log.debug('RPC call data is: %s', data)
        self.log.debug('Scheme: %s', data.scheme)
        self.log.debug('Query: %s', data.query)
        self.log.debug('Path: %s', data.path)

        # Echo back the query value, if available:
        try:
            operation = data.query.op
        except AttributeError:
            raise ValueError('Malformed request (expected .query.op)')

        if operation == 'help':
            return self.HelpInfo(value='Me too')

        if operation == 'info':
            return self.ServerInfo()

        if operation == 'channels':
            pvnames = list(sorted(self.server_instance.pvdb))
            pvnames.remove(self.server.name)
            return self.ChannelListing(value=pvnames)


def main():
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='caproto:pva:',
        desc='A basic caproto-pva test server.'
    )

    ioc = MyIOC(**ioc_options)
    server_info = ServerRPC(prefix='', server_instance=ioc)
    ioc.pvdb.update(server_info.pvdb)
    run(ioc.pvdb, **run_options)


if __name__ == '__main__':
    main()
