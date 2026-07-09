import msgspec
from msgspec import Struct, Meta
from typing import Annotated, Optional


from caproto.server import PVGroup, ioc_arg_parser, pvproperty, run

from caproto import ChannelType
from caproto.server import PvpropertyByte, PvpropertyStringRO, PvpropertyCharRO

import numpy as np

# Numpy serialization code copied from
# https://github.com/jcrist/msgspec/issues/174#issuecomment-1645533136


class NumpySerializedRepresentation(msgspec.Struct, gc=False, array_like=True):
    dtype: str
    shape: tuple
    data: bytes


class Table(msgspec.Struct):
    a: NumpySerializedRepresentation
    b: NumpySerializedRepresentation


numpy_array_encoder = msgspec.msgpack.Encoder()
numpy_array_decoder = msgspec.msgpack.Decoder(type=NumpySerializedRepresentation)


def encode_hook(obj):
    if isinstance(obj, np.ndarray):
        return msgspec.msgpack.Ext(
            1,
            numpy_array_encoder.encode(
                NumpySerializedRepresentation(
                    dtype=obj.dtype.str, shape=obj.shape, data=obj.data
                )
            ),
        )
    return obj


def ext_hook(type, data: memoryview):
    if type == 1:
        serialized_array_rep = numpy_array_decoder.decode(data)
        return np.frombuffer(
            serialized_array_rep.data, dtype=serialized_array_rep.dtype
        ).reshape(serialized_array_rep.shape)
    return data


dec = msgspec.msgpack.Decoder(ext_hook=ext_hook)
enc = msgspec.msgpack.Encoder(enc_hook=encode_hook)


class StructuredJson(PVGroup):
    columns = pvproperty(value="", dtype=PvpropertyStringRO, max_length=100)
    encoding = pvproperty(value="msgpack_extended", dtype=PvpropertyStringRO)
    value = pvproperty(
        value=b"", dtype=PvpropertyByte, max_length=100_000, strip_null_terminator=False
    )

    def __init__(self, init_data, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._data = self._validate_table(init_data)
        self._struct = self._data.__class__

    @staticmethod
    def _validate_table(table):
        shapes = [getattr(table, k).shape for k in table.__struct_fields__]
        if not all(len(s) == 1 for s in shapes):
            raise ValueError
        if not all(s == shapes[0] for s in shapes):
            raise ValueError
        return table

    async def __ainit__(self, async_lib):
        await self.columns.write(self._data.__struct_fields__)
        await self.value.write(enc.encode(self._data))

    @value.putter
    async def value(self, instance, value):
        self._data = self._validate_table(self._struct(**dec.decode(value)))
        print(f"{self._data=}")
        return value


if __name__ == "__main__":
    ioc_options, run_options = ioc_arg_parser(
        default_prefix="msgpack:",
        desc="Run an IOC that serves json as bytes",
    )
    ioc = StructuredJson(Table(np.arange(5), np.arange(5) ** 2), **ioc_options)
    run(ioc.pvdb, startup_hook=ioc.__ainit__, **run_options)


def local_get(pv):
    from caproto.sync.client import read

    result = read(pv)
    tbl = Table(**dec.decode(result.data))
    print(tbl)
    return tbl


def local_put(pv, value):
    from caproto.sync.client import write

    res = enc.encode(value)
    return write(pv, res)


# from structured_table import local_put, local_get, Table
# print(local_get('msgpack:value'))
# local_put('msgpack:value', Table(np.linspace(0, 2*np.pi, 25), np.sin(np.linspace(0, 2*np.pi, 25))))
# print(local_get('msgpack:value'))
# local_put('msgpack:value', Table(np.linspace(0, 2*np.pi, 25), np.cos(np.linspace(0, 2*np.pi, 25))))
# print(local_get('msgpack:value'))
