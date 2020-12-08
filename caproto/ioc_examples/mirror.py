#!/usr/bin/env python3
from caproto.asyncio.client import Context
from caproto.server import PVGroup, pvproperty, run, template_arg_parser


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

    def __init__(self, *args, target, **kwargs):
        self.target = target  # PV to mirror
        self.client_context = None
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

    @value.startup
    async def value(self, instance, async_lib):
        # Note that the asyncio context must be created here so that it knows
        # which asyncio loop to use:
        self.client_context = Context()

        self.pv, = await self.client_context.get_pvs(self.target)

        # Subscribe to the target PV and register self._callback.
        self.subscription = self.pv.subscribe(data_type='time')
        self.subscription.add_callback(self._callback)


if __name__ == '__main__':
    parser, split_args = template_arg_parser(
        default_prefix='mirror:',
        desc='Mirror the value of another floating-point PV.',
        supported_async_libs=('asyncio',)
    )
    parser.add_argument('--target',
                        help='The PV to mirror', required=True, type=str)
    args = parser.parse_args()
    ioc_options, run_options = split_args(args)
    ioc = Mirror(target=args.target, **ioc_options)
    run(ioc.pvdb, **run_options)
