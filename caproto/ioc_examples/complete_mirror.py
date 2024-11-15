#!/usr/bin/env python3
import json

from functools import cached_property
from caproto.asyncio.client import Context
from caproto.server import PVGroup, pvproperty, run, template_arg_parser


class PreloadedContext(Context):
    def __init__(self, *args, cache=None, **kwargs):
        super().__init__(*args, **kwargs)
        cache = cache or {}
        for name, (addr, version) in cache.items():
            self.broadcaster.results.mark_name_found(name, addr)
            self.broadcaster.server_protocol_versions[addr] = version



class Mirror(PVGroup):
    """
    Subscribe to a PV and serve its value.

    The default prefix is ``mirror:``.

    PVs
    ---
    value
    """
    # TODO This assumes the type of the value is float.
    value = pvproperty(value=0, dtype=float, read_only=True)

    def __init__(self, *args, config, **kwargs):
        self.config = config
        self.pv = None
        self.subscription = None
        super().__init__(*args, **kwargs)

    async def _callback(self, pv, response):
        # Update our own value based on the monitored one:
        await self.value.write(
            response.data,
            # We can even make the timestamp the same:
            timestamp=response.metadata.timestamp,
        )

    @cached_property
    def client_context(self):
        return PreloadedContext(cache=self.config)

    @value.startup
    async def value(self, instance, async_lib):
        # Note that the asyncio context must be created here so that it knows
        # which asyncio loop to use:

        self.pv, = await self.client_context.get_pvs(next(iter(self.config)))

        # Subscribe to the target PV and register self._callback.
        self.subscription = self.pv.subscribe(data_type='time')
        self.subscription.add_callback(self._callback)


if __name__ == '__main__':
    parser, split_args = template_arg_parser(
        default_prefix='mirror:',
        desc='Mirror the value of another floating-point PV.',
        supported_async_libs=('asyncio',)
    )
    parser.add_argument('--config',
                        help='JSON mapping of PVs to mirror and server information', required=True, type=str)
    # TODO use sync client to connect once and pull the types
    args = parser.parse_args()
    ioc_options, run_options = split_args(args)
    config = {k: (tuple(v[0]), v[1]) for k, v in json.loads(args.config).items()}
    ioc = Mirror(config=config, **ioc_options)
    run(ioc.pvdb, **run_options)