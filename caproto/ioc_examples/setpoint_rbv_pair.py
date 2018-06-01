#!/usr/bin/env python3
import sys
import trio

from caproto.trio.server import start_server
from caproto.server import (PVGroup, get_pv_pair_wrapper)


# Create _two_ PVs with a single pvproperty_with_rbv:
pvproperty_with_rbv = get_pv_pair_wrapper(setpoint_suffix='',
                                          readback_suffix='_RBV')
# NOTE: _RBV is areaDetector-like naming suffix for a read-back value


class Group(PVGroup):
    # Creates {prefix}pair and {prefix}pair_RBV
    pair = pvproperty_with_rbv(dtype=int, doc='This is the first pair')
    # Creates {prefix}pair2 and {prefix}pair2_RBV
    pair2 = pvproperty_with_rbv(dtype=float, doc='This is pair2')

    # TODO: @danielballan to rename the above appropriately

    # We can then directly decorate our functions with the putters from the
    # setpoint:
    @pair.setpoint.putter
    async def pair(obj, instance, value):
        # accept the value immediately
        await obj.readback.write(value)
        # NOTE: you can access the Group instance through obj.parent
        print(obj.parent)

    # And the readback getter:
    @pair.readback.getter
    async def pair(obj, instance):
        # NOTE: this is effectively a no-operation method
        # that is, with or without this method definition, self.readback.value
        # will be returned automatically
        return obj.readback.value


if __name__ == '__main__':
    try:
        prefix = sys.argv[1]
    except IndexError:
        prefix = 'setpoint_rbv:'

    ioc = Group(prefix)
    from pprint import pprint
    pprint(ioc.pvdb)

    trio.run(start_server, ioc.pvdb)
