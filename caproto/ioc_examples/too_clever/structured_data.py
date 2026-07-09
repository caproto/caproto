import msgspec
from msgspec import Struct, Meta
from typing import Annotated, Optional


from caproto.server import PVGroup, ioc_arg_parser, pvproperty, run

from caproto import ChannelType
from caproto.server import PvpropertyByte, PvpropertyStringRO, PvpropertyCharRO


class StructuredJson(PVGroup):
    schema = pvproperty(value="", dtype=PvpropertyCharRO, max_length=100_000)
    encoding = pvproperty(value="ascii", dtype=PvpropertyStringRO)
    value = pvproperty(value=b"", dtype=PvpropertyByte, max_length=100_000)

    def __init__(self, init_data, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._data = init_data
        self._struct = init_data.__class__

    async def __ainit__(self, async_lib):
        schema = msgspec.json.schema(self._struct)
        print(schema)
        await self.schema.write(msgspec.json.encode(schema).decode())
        await self.value.write(msgspec.json.encode(self._data))

    @value.putter
    async def value(self, instance, value):
        self._data = msgspec.json.decode(value, type=self._struct)
        print(f"{self._data=}")
        return value


if __name__ == "__main__":
    # A float constrained to values > 0
    PositiveFloat = Annotated[float, Meta(gt=0)]

    class Dimensions(Struct):
        """Dimensions for a product, all measurements in centimeters"""

        length: PositiveFloat
        width: PositiveFloat
        height: PositiveFloat

    ioc_options, run_options = ioc_arg_parser(
        default_prefix="json:",
        desc="Run an IOC that serves json as bytes",
    )
    ioc = StructuredJson(Dimensions(length=1, width=2, height=3), **ioc_options)
    run(ioc.pvdb, startup_hook=ioc.__ainit__, **run_options)
