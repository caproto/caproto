#!/usr/bin/env python3
from caproto.server import pvproperty, PVGroup, ioc_arg_parser, run
from textwrap import dedent


class ProcessIOC(PVGroup):
    """
    IOC which exposes `record.PROC` with a `putter`.
    """

    record = pvproperty(value=1, record='bo')
    count = pvproperty(value=-1)

    @record.fields.process_record.startup
    async def record(fields, instance, value):  # noqa
        process_ioc = fields.parent.group
        await process_ioc.count.write(value=0)
        fields.log.warning('Startup hook executed. Initialized to %d',
                           process_ioc.count.value)

    @record.fields.process_record.putter
    async def record(fields, instance, value):  # noqa
        process_ioc = fields.parent.group

        new_value = process_ioc.count.value + 1
        process_ioc.log.warning('Processing! Incremented to: %d', new_value)
        await process_ioc.count.write(value=new_value)


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='process_test:',
        desc=dedent(ProcessIOC.__doc__))
    ioc = ProcessIOC(**ioc_options)
    run(ioc.pvdb, **run_options)
