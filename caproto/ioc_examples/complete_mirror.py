#!/usr/bin/env python3
import contextvars
from collections import defaultdict
from functools import cached_property, partial
from pathlib import Path

from caproto.asyncio.client import Context
from caproto.server import PVGroup, pvproperty, run, template_arg_parser
from caproto import AccessRights
from caproto.server.records.base import RecordFieldGroup

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


class MirrorFrameBase(PVGroup):
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


class MirrorFrame(MirrorFrameBase):
    @cached_property
    def client_context(self):
        return PreloadedContext(cache=self.config)


class MirrorRecordFrame(MirrorFrameBase):
    @cached_property
    def client_context(self):
        return self.parent.group.client_context


def pvproperty_from_channel(chan, force_read_only, name=None):
    # TODO make this public
    pv_str = chan.name
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

    value = pvproperty(
        value=resp.data if len(resp.data) else None,
        dtype=chan.native_data_type,
        max_length=chan.native_data_count,
        read_only=force_read_only or (AccessRights.WRITE not in chan.access_rights),
        name=name,
        **extra,
    )

    async def _callback(inst, sub, response):
        # Update our own value based on the monitored one:
        try:
            internal_process.set(True)
            await inst.write(
                response.data,
                # We can even make the timestamp the same:
                timestamp=response.metadata.timestamp,
            )
        except ca.CaprotoValueError:
            print(inst, inst.name, response.data)
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
        if internal_process.get():
            return value
        else:
            pv = self._pvs[pv_str]
            if chan.native_data_type in ca.enum_types:
                value = instance.get_raw_value(value)

            await pv.write(value, timeout=500)
            # trust the monitor took care of it
            raise ca.SkipWrite()

    return value


def make_pvproperty(pv_str, addr_ver, fields, force_read_only):
    print(addr_ver)
    addr, ver = addr_ver
    chans = []
    try:
        if len(fields) == 1:
            chans.append(csc.make_channel_from_address(pv_str, addr, 0, 5))
            return pvproperty_from_channel(chans[0], force_read_only)
        else:
            fields_pvproperties = {}
            for field in fields:
                chan = csc.make_channel_from_address(f"{pv_str}.{field}", addr, 0, 5)
                chans.append(chan)
                fields_pvproperties[field] = pvproperty_from_channel(
                    chan, force_read_only, field
                )
            val_field = fields_pvproperties.pop("VAL", None)
            has_val_field = val_field is not None
            Records = type(
                "Records",
                (MirrorRecordFrame,),
                {**fields_pvproperties, "has_val_field": has_val_field},
            )
            if has_val_field:
                return pvproperty.from_pvspec(val_field.pvspec._replace(record=Records))

            else:
                return pvproperty(record=Records)

    finally:
        for chan in chans:
            if chan.states[ca.CLIENT] is ca.CONNECTED:
                csc.send(chan.circuit, chan.clear(), chan.name)


def make_mirror(config, force_read_only=False):
    records = defaultdict(lambda: ([], []))

    for pv, host_addr in config.items():
        record, sep, field = pv.partition(".")
        if not field:
            field = "VAL"
        records[record][0].append(field)
        records[record][1].append(host_addr)

    try:
        return type(
            "Mirror",
            (MirrorFrame,),
            {
                **{
                    pv_str: make_pvproperty(
                        pv_str, next(iter(set(addr_ver))), fields, force_read_only
                    )
                    for pv_str, (fields, addr_ver) in records.items()
                },
                "config": config,
            },
        )
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
        "--host",
        help="ip address of IOC to be mirrored",
        required=True,
        type=str,
    )
    parser.add_argument(
        "--pvlist",
        help="File to read to get PV list",
        required=False,
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--port",
        help="port number of IOC to be mirrored",
        required=True,
        type=int,
    )
    parser.add_argument(
        "--ca-version",
        help="version of the CA protocol the mirrored IOC speaks",
        required=False,
        type=int,
        default=13,
    )
    parser.add_argument("pvs", help="PVs to be mirrored", type=str, nargs="*")

    args = parser.parse_args()
    if args.pvlist is not None:
        with open(args.pvlist) as fin:
            pvs_from_file = [
                pv
                for pv in [line.strip() for line in fin.readlines()]
                if pv and not pv.startswith("#")
            ]
    else:
        pvs_from_file = []

    ioc_options, run_options = split_args(args)

    config = {
        k: ((args.host, args.port), args.ca_version) for k in args.pvs + pvs_from_file
    }
    ioc = make_mirror(config)(**ioc_options)
    run(ioc.pvdb, **run_options)
