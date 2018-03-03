import logging
import inspect

import curio

import ophyd

from caproto.curio.server import start_server
from caproto.curio import high_level_server
from caproto.curio.high_level_server import (logger, PVGroup)


def ophyd_component_to_caproto(attr, component, *, defined_classes, depth=0, dev=None):
    indent = '    ' * depth
    sig = getattr(dev, attr) if dev is not None else None

    if isinstance(component, ophyd.DynamicDeviceComponent):
        yield f"{indent}    {attr} = TODO()"
        return
    elif issubclass(component.cls, ophyd.Device):
        kwargs = dict()
        if isinstance(component, ophyd.FormattedComponent):
            # TODO Component vs FormattedComponent
            kwargs['prefix'] = "''"

        to_describe = sig if sig is not None else component.cls
        yield from ophyd_device_to_caproto_ioc(to_describe, depth=depth + 1,
                                               defined_classes=defined_classes)

        yield f"{indent}    {attr} = TODO_above_class()"
        return

    kwargs = dict(name=repr(component.suffix))

    if isinstance(component, ophyd.FormattedComponent):
        # TODO Component vs FormattedComponent
        kwargs['prefix'] = "''"

    if sig and sig.connected:
        value = component.get()
        try:
            value = value[0]
        except TypeError:
            ...
        kwargs['dtype'] = str(type(value))
    else:
        kwargs = getattr(component, 'kwargs', {})
        is_string = kwargs.get('string', False)
        if is_string:
            kwargs['dtype'] = 'str'
        else:
            kwargs['dtype'] = 'unknown'

    # if component.__doc__:
    #     kwargs['doc'] = repr(component.__doc__)

    kw_str = ', '.join(f'{key}={value}'
                       for key, value in kwargs.items())

    if issubclass(component.cls, ophyd.EpicsSignalWithRBV):
        yield f"{indent}    {attr} = pvproperty_with_rbv({kw_str})"
    else:
        yield f"{indent}    {attr} = pvproperty({kw_str})"


def ophyd_device_to_caproto_ioc(dev, *, depth=0, defined_classes=None):
    if defined_classes is None:
        defined_classes = {}

    if inspect.isclass(dev):
        # we can introspect Device directly, but we cannot connect to PVs and
        # tell about their data type
        cls, dev = dev, None
    else:
        # if connected, we can reach out to PVs and determine data types
        cls = dev.__class__

    indent = '    ' * depth

    yield f"{indent}class {cls.__name__}IOC(caproto.PVGroup):"

    for attr, component in cls._sig_attrs.items():
        yield from ophyd_component_to_caproto(attr, component, depth=depth,
                                              dev=dev,
                                              defined_classes=defined_classes)


for line in ophyd_device_to_caproto_ioc(ophyd.ImagePlugin):
    print(line)

import sys; sys.exit(0)

logger.setLevel(logging.DEBUG)
logging.basicConfig()

pvproperty_with_rbv = high_level_server.get_pv_pair_wrapper(setpoint_suffix='',
                                                            readback_suffix='_RBV')

class Group(PVGroup):
    pair = pvproperty_with_rbv(dtype=int, doc='pair1')
    pair2 = pvproperty_with_rbv(dtype=int, doc='pair2')

    @pair.setpoint.putter
    async def pair(self, instance, value):
        # accept the value immediately
        # TODO: self is actually the subgroup.
        await self.readback.write(value)
        # TODO: update RBV at accept time, or at finished process time?

    @pair.readback.getter
    async def pair(self, instance):
        # unnecessary implementation, just for example
        return self.readback.value


print('outside of scope')

ioc = Group('prefix:')
print('full pvdb')
from pprint import pprint
pprint(ioc.pvdb)

curio.run(start_server, ioc.pvdb)
