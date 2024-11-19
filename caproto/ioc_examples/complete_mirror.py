#!/usr/bin/env python3
import json

from functools import cached_property, partial
from caproto.asyncio.client import Context
from caproto.server import PVGroup, pvproperty, run, template_arg_parser
from caproto import AccessRights
from caproto.sync.client import make_channel_from_address


class PreloadedContext(Context):
    def __init__(self, *args, cache=None, **kwargs):
        super().__init__(*args, **kwargs)
        cache = cache or {}
        for name, (addr, version) in cache.items():
            self.broadcaster.results.mark_name_found(name, addr)
            self.broadcaster.server_protocol_versions[addr] = version


class MirrorFrame(PVGroup):
    """
    Subscribe to a PV and serve its value.

    The default prefix is ``mirror:``.

    PVs
    ---
    value
    """

    def __init__(self, *args, **kwargs):
        self.pv = None
        self.subscription = None
        self._callbacks = set()
        self._pvs = set()
        self._subs = set()
        super().__init__(*args, **kwargs)

    @cached_property
    def client_context(self):
        return PreloadedContext(cache=self.config)


def make_mirror(config, read_only=True):
    def make_pvproperty(pv_str, addr_ver):
        addr, ver = addr_ver
        chan = make_channel_from_address(pv_str, addr, 0, 5)

        value = pvproperty(
            value=0,
            dtype=chan.native_data_type,
            max_length=chan.native_data_count,
            read_only=read_only or (AccessRights.WRITE not in chan.access_right),
        )

        async def _callback(inst, sub, response):
            # Update our own value based on the monitored one:
            print(sub.pv)
            await inst.write(
                response.data,
                # We can even make the timestamp the same:
                timestamp=response.metadata.timestamp,
            )

        @value.startup
        async def value(self, instance, async_lib):
            # Note that the asyncio context must be created here so that it knows
            # which asyncio loop to use:

            name = (lambda _=pv_str: _)()
            print(f"{name=}")
            (pv,) = await self.client_context.get_pvs(name)

            # Subscribe to the target PV and register self._callback.
            subscription = pv.subscribe(data_type="time")
            cb = partial(_callback, instance)
            subscription.add_callback(cb)
            self._callbacks.add(cb)
            self._pvs.add(pv)
            self._subs.add(subscription)

        return value

    return type(
        "Mirror",
        (MirrorFrame,),
        {
            **{
                pv_str: make_pvproperty(pv_str, addr_ver)
                for pv_str, addr_ver in config.items()
            },
            "config": config,
        },
    )


if __name__ == "__main__":
    parser, split_args = template_arg_parser(
        default_prefix="mirror:",
        desc="Mirror the value of another floating-point PV.",
        supported_async_libs=("asyncio",),
    )
    parser.add_argument(
        "--config",
        help="JSON mapping of PVs to mirror and server information",
        required=True,
        type=str,
    )
    # TODO use sync client to connect once and pull the types
    args = parser.parse_args()
    ioc_options, run_options = split_args(args)
    config = {k: (tuple(v[0]), v[1]) for k, v in json.loads(args.config).items()}
    ioc = make_mirror(config)(**ioc_options)
    run(ioc.pvdb, **run_options)
