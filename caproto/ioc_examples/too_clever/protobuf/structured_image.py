import msgspec
from msgspec import Struct, Meta
from typing import Annotated, Optional

import numpy as np

from caproto.server import PVGroup, ioc_arg_parser, pvproperty, run

from caproto import ChannelType
from caproto.server import (
    PvpropertyByte,
    PvpropertyStringRO,
    PvpropertyCharRO,
    PvpropertyIntegerRO,
)

import image_pb2


def encode(frame, data):
    im = image_pb2.Image()
    im.frame = frame
    im.row, im.col = data.shape
    im.dtype = str(data.dtype)
    im.image_data = data.tobytes()
    return im.SerializeToString()


def decode(val):
    im = image_pb2.Image()
    im.ParseFromString(val)
    data = np.frombuffer(im.image_data, dtype=im.dtype).reshape(im.row, im.col)
    return im.frame, data


class StructuredImage(PVGroup):
    shape = pvproperty(value=(), dtype=PvpropertyIntegerRO, max_length=10)
    encoding = pvproperty(value="protobuf:caproto.Image", dtype=PvpropertyStringRO)
    value = pvproperty(
        value=b"",
        dtype=PvpropertyByte,
        max_length=1_000_000,
        strip_null_terminator=False,
    )

    def __init__(self, frame, init_data, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._data = init_data
        self._frame = frame

    async def __ainit__(self, async_lib):
        await self.shape.write(self._data.shape)

        await self.value.write(encode(self._frame, self._data))

    @value.putter
    async def value(self, instance, value):
        # TODO check the shape
        self._frame, self._data = decode(value)
        return value


if __name__ == "__main__":
    ioc_options, run_options = ioc_arg_parser(
        default_prefix="protobuf:",
        desc="Run an IOC that serves json as bytes",
    )
    ioc = StructuredImage(0, np.arange(15).reshape(5, 3), **ioc_options)
    run(ioc.pvdb, startup_hook=ioc.__ainit__, **run_options)
