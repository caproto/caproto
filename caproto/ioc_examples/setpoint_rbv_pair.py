#!/usr/bin/env python3
from caproto import ChannelType
from caproto.server import PVGroup, get_pv_pair_wrapper, ioc_arg_parser, run

# Create _two_ PVs with a single pvproperty_with_rbv:
pvproperty_with_rbv = get_pv_pair_wrapper(setpoint_suffix='',
                                          readback_suffix='_RBV')
# NOTE: _RBV is areaDetector-like naming suffix for a read-back value


class Group(PVGroup):
    # Creates {prefix}pair and {prefix}pair_RBV
    pair = pvproperty_with_rbv(
        dtype=int,
        doc='This is the first pair, of data type int',
    )
    # Creates {prefix}pair2 and {prefix}pair2_RBV
    pair2 = pvproperty_with_rbv(
        dtype=float,
        doc='pair2 has a separate data type of float'
    )
    # Creates {prefix}pair3 and {prefix}pair3_RBV
    pair3 = pvproperty_with_rbv(
        dtype=ChannelType.ENUM,
        doc='Setpoint is a "bo" record; readback is a "bi" record.',
        enum_strings=['No', 'Yes'],
        setpoint_kw=dict(record='bo'),
        readback_kw=dict(record='bi'),
    )

    # We can then directly decorate our functions with the putters from the
    # setpoint:
    @pair.setpoint.putter
    async def pair(obj, instance, value):
        # accept the value immediately
        await obj.readback.write(value)
        # NOTE: you can access the Group instance through obj.parent
        print(obj.parent)


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='setpoint_rbv:',
        desc='Run an IOC with two setpoint/readback pairs.')
    ioc = Group(**ioc_options)
    run(ioc.pvdb, **run_options)
