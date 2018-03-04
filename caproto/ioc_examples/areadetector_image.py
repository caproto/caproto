import logging
import inspect

import curio

import ophyd

from caproto.curio.server import start_server
# from caproto.curio import high_level_server
from caproto.curio.high_level_server import (logger, PVGroup, pvproperty,
                                             SubGroup, get_pv_pair_wrapper)


def underscore_to_camel_case(s):
    'Convert abc_def_ghi -> AbcDefGhi'
    def capitalize_first(substring):
        return substring[:1].upper() + substring[1:]
    return ''.join(map(capitalize_first, s.split('_')))


def ophyd_component_to_caproto(attr, component, *, depth=0, dev=None):
    indent = '    ' * depth
    sig = getattr(dev, attr) if dev is not None else None

    if isinstance(component, ophyd.DynamicDeviceComponent):
        cpt_dict = ophyd_device_to_caproto_ioc(component, depth=depth)
        cpt_name, = cpt_dict.keys()
        cpt_dict[''] = [
            '',
            f"{indent}{attr} = SubGroup({cpt_name}, prefix='')",
            '',
        ]
        return cpt_dict

    elif issubclass(component.cls, ophyd.Device):
        kwargs = dict()
        if isinstance(component, ophyd.FormattedComponent):
            # TODO Component vs FormattedComponent
            kwargs['name'] = "''"

        to_describe = sig if sig is not None else component.cls

        cpt_dict = ophyd_device_to_caproto_ioc(to_describe, depth=depth)
        cpt_name, = cpt_dict.keys()
        cpt_dict[''] = [
            '',
            f"{indent}{attr} = caproto.SubGroup({cpt_name}, prefix='')",
            ''
        ]
        return cpt_dict

    kwargs = dict(name=repr(component.suffix))

    if isinstance(component, ophyd.FormattedComponent):
        # TODO Component vs FormattedComponent
        kwargs['name'] = "''"
    else:  # if hasattr(component, 'suffix'):
        kwargs['name'] = repr(component.suffix)

    if sig and sig.connected:
        value = component.get()
        try:
            value = value[0]
        except TypeError:
            ...
        kwargs['dtype'] = str(type(value))
    else:
        cpt_kwargs = getattr(component, 'kwargs', {})
        is_string = cpt_kwargs.get('string', False)
        if is_string:
            kwargs['dtype'] = 'str'
        else:
            kwargs['dtype'] = 'unknown'

    # if component.__doc__:
    #     kwargs['doc'] = repr(component.__doc__)

    kw_str = ', '.join(f'{key}={value}'
                       for key, value in kwargs.items())

    if issubclass(component.cls, ophyd.EpicsSignalWithRBV):
        line = f"{indent}{attr} = pvproperty_with_rbv({kw_str})"
    elif issubclass(component.cls, ophyd.EpicsSignalRO):
        line = f"{indent}{attr} = pvproperty({kw_str})"
    elif issubclass(component.cls, ophyd.EpicsSignal):
        line = f"{indent}{attr} = pvproperty({kw_str})"
    else:
        line = f"{indent}# {attr} = pvproperty({kw_str})"

    # single line, no new subclass defined
    return {'': [line]}


def ophyd_device_to_caproto_ioc(dev, *, depth=0):
    if isinstance(dev, ophyd.DynamicDeviceComponent):
        # DynamicDeviceComponent: attr: (sig_cls, prefix, kwargs)
        attr_components = {
            attr: ophyd.Component(sig_cls, prefix, **kwargs)
            for attr, (sig_cls, prefix, kwargs) in dev.defn.items()
        }
        dev_name = f'{dev.attr}_group'
        # TODO can't inspect
        cls, dev = dev, None
    else:
        if inspect.isclass(dev):
            # we can introspect Device directly, but we cannot connect to PVs
            # and tell about their data type
            cls, dev = dev, None
        else:
            # if connected, we can reach out to PVs and determine data types
            cls = dev.__class__
        attr_components = cls._sig_attrs
        dev_name = f'{cls.__name__}_group'

    dev_name = underscore_to_camel_case(dev_name)
    indent = '    ' * depth

    dev_lines = [f"{indent}class {dev_name}(PVGroup):"]

    for attr, component in attr_components.items():
        cpt_lines = ophyd_component_to_caproto(attr, component,
                                               depth=depth + 1,
                                               dev=dev)
        if isinstance(cpt_lines, dict):
            # new device/sub-group, for now add it on
            for new_dev, lines in cpt_lines.items():
                dev_lines.extend(lines)
        else:
            dev_lines.extend(cpt_lines)

    return {dev_name: dev_lines}


class Detector(ophyd.SimDetector):
    image1 = ophyd.Component(ophyd.ImagePlugin, 'image1:')


# dev_dict = ophyd_device_to_caproto_ioc(ophyd.ImagePlugin)
dev_dict = ophyd_device_to_caproto_ioc(Detector)
for dev, lines in dev_dict.items():
    print(f'# -- {dev} --')
    for line in lines:
        print(line)

# -- ImagepluginGroup --
pvproperty_with_rbv = get_pv_pair_wrapper(setpoint_suffix='',
                                          readback_suffix='_RBV')


class ImagepluginGroup(PVGroup):
    configuration_names = pvproperty(name=None, dtype=int)
    array_counter = pvproperty_with_rbv(name='ArrayCounter', dtype=int)
    array_rate = pvproperty(name='ArrayRate_RBV', dtype=int)
    asyn_io = pvproperty(name='AsynIO', dtype=int)
    nd_attributes_file = pvproperty(name='NDAttributesFile', dtype=str)
    pool_alloc_buffers = pvproperty(name='PoolAllocBuffers', dtype=int)
    pool_free_buffers = pvproperty(name='PoolFreeBuffers', dtype=int)
    pool_max_buffers = pvproperty(name='PoolMaxBuffers', dtype=int)
    pool_max_mem = pvproperty(name='PoolMaxMem', dtype=int)
    pool_used_buffers = pvproperty(name='PoolUsedBuffers', dtype=int)
    pool_used_mem = pvproperty(name='PoolUsedMem', dtype=int)
    port_name = pvproperty(name='PortName_RBV', dtype=str)
    asyn_pipeline_config = pvproperty(name=None, dtype=int)
    # width = pvproperty(name='ArraySize0_RBV', dtype=int)
    # height = pvproperty(name='ArraySize1_RBV', dtype=int)
    # depth = pvproperty(name='ArraySize2_RBV', dtype=int)

    class ArraySizeGroup(PVGroup):
        height = pvproperty(name='ArraySize1_RBV', dtype=int)
        width = pvproperty(name='ArraySize0_RBV', dtype=int)
        depth = pvproperty(name='ArraySize2_RBV', dtype=int)

    array_size = SubGroup(ArraySizeGroup, prefix='')
    bayer_pattern = pvproperty(name='BayerPattern_RBV', dtype=int)
    blocking_callbacks = pvproperty_with_rbv(name='BlockingCallbacks',
                                             dtype=str)
    color_mode = pvproperty(name='ColorMode_RBV', dtype=int)
    data_type = pvproperty(name='DataType_RBV', dtype=str)
    # dim0_sa = pvproperty(name='Dim0SA', dtype=int)
    # dim1_sa = pvproperty(name='Dim1SA', dtype=int)
    # dim2_sa = pvproperty(name='Dim2SA', dtype=int)

    class DimSaGroup(PVGroup):
        dim0 = pvproperty(name='Dim0SA', dtype=int)
        dim1 = pvproperty(name='Dim1SA', dtype=int)
        dim2 = pvproperty(name='Dim2SA', dtype=int)

    dim_sa = SubGroup(DimSaGroup, prefix='')
    dimensions = pvproperty(name='Dimensions_RBV', dtype=int)
    dropped_arrays = pvproperty_with_rbv(name='DroppedArrays', dtype=int)
    enable = pvproperty_with_rbv(name='EnableCallbacks', dtype=str)
    min_callback_time = pvproperty_with_rbv(name='MinCallbackTime', dtype=int)
    nd_array_address = pvproperty_with_rbv(name='NDArrayAddress', dtype=int)
    nd_array_port = pvproperty_with_rbv(name='NDArrayPort', dtype=int)
    ndimensions = pvproperty(name='NDimensions_RBV', dtype=int)
    plugin_type = pvproperty(name='PluginType_RBV', dtype=int)
    queue_free = pvproperty(name='QueueFree', dtype=int)
    queue_free_low = pvproperty(name='QueueFreeLow', dtype=int)
    queue_size = pvproperty(name='QueueSize', dtype=int)
    queue_use = pvproperty(name='QueueUse', dtype=int)
    queue_use_high = pvproperty(name='QueueUseHIGH', dtype=int)
    queue_use_hihi = pvproperty(name='QueueUseHIHI', dtype=int)
    time_stamp = pvproperty(name='TimeStamp_RBV', dtype=int)
    unique_id = pvproperty(name='UniqueId_RBV', dtype=int)
    array_data = pvproperty(name='ArrayData', dtype=int)


logger.setLevel(logging.DEBUG)
logging.basicConfig()


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
b = ImagepluginGroup('prefix:')
# pprint(b.pvdb)
# import sys; sys.exit(0)
curio.run(start_server, ioc.pvdb)
