#!/usr/bin/env python3
import json
import contextvars
from functools import cached_property, partial


from caproto.asyncio.client import Context
from caproto.server import PVGroup, pvproperty, run, template_arg_parser
from caproto import AccessRights

import caproto as ca
import caproto.sync.client as csc


internal_process = contextvars.ContextVar("internal_process", default=False)


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
        self._pvs = {}
        self._subs = set()
        super().__init__(*args, **kwargs)

    @cached_property
    def client_context(self):
        return PreloadedContext(cache=self.config)


def make_mirror(config, read_only=False):
    chans = []

    def make_pvproperty(pv_str, addr_ver):
        addr, ver = addr_ver
        chan = csc.make_channel_from_address(pv_str, addr, 0, 5)
        chans.append(chan)

        # TODO make this public
        resp = csc._read(
            chan,
            1,
            ca.field_types["control"][chan.native_data_type],
            chan.native_data_count,
            notify=True,
            force_int_enums=False,
        )

        if chan.native_data_type in ca.enum_types:
            extra = {
                "enum_strings": tuple(
                    k.decode(chan.string_encoding) for k in resp.metadata.enum_strings
                )
            }
        else:
            extra = {}
        print(extra)

        value = pvproperty(
            value=resp.data,
            dtype=chan.native_data_type,
            max_length=chan.native_data_count,
            read_only=read_only or (AccessRights.WRITE not in chan.access_rights),
            **extra,
        )

        async def _callback(inst, sub, response):
            # Update our own value based on the monitored one:
            print(sub.pv)
            try:
                internal_process.set(True)
                await inst.write(
                    response.data,
                    # We can even make the timestamp the same:
                    timestamp=response.metadata.timestamp,
                )
            finally:
                internal_process.set(False)

        @value.startup
        async def value(self, instance, async_lib):
            # Note that the asyncio context must be created here so that it knows
            # which asyncio loop to use:

            (pv,) = await self.client_context.get_pvs(pv_str)

            # Subscribe to the target PV and register self._callback.
            subscription = pv.subscribe(data_type="time")
            cb = partial(_callback, instance)
            subscription.add_callback(cb)
            self._callbacks.add(cb)
            self._pvs[pv_str] = pv
            self._subs.add(subscription)

        @value.putter
        async def value(self, instance, value):
            if not internal_process.get():
                pv = self._pvs[pv_str]
                print(type(instance), value)
                await pv.write(value)
            return value

        return value

    try:
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
    finally:
        try:
            for chan in chans:
                if chan.states[ca.CLIENT] is ca.CONNECTED:
                    csc.send(chan.circuit, chan.clear(), chan.name)
        finally:
            for socket in csc.sockets.values():
                socket.close()

            csc.sockets.clear()
            csc.global_circuits.clear()


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
