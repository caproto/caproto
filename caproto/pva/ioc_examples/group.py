#!/usr/bin/env python3
"""
A basic caproto-pva test server using PVAGroup.
"""
import caproto.pva as pva
from caproto.pva.server import (PVAGroup, ioc_arg_parser, pva_dataclass,
                                pvaproperty, run)


@pva_dataclass
class MyData:
    value: int
    info: str


@pva_dataclass
class NestedData:
    my_data: MyData
    value: float


class MyIOC(PVAGroup):
    test = pvaproperty(value=MyData(value=5, info='a string'))
    test2 = pvaproperty(value=MyData(value=6, info='a different string'))
    test3 = pvaproperty(value=NestedData)
    long_write = pvaproperty(value=MyData())
    rpc = pvaproperty(value=MyData())

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
