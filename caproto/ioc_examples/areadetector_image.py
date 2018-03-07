import logging

import curio

import ophyd

from caproto.curio.server import start_server
# from caproto.curio import high_level_server
from caproto.curio.high_level_server import (logger, PVGroup, pvproperty,
                                             SubGroup, get_pv_pair_wrapper)

from caproto.curio.conversion import ophyd_device_to_caproto_ioc


class Detector(ophyd.SimDetector):
    image1 = ophyd.Component(ophyd.ImagePlugin, 'image1:')


# dev_dict = ophyd_device_to_caproto_ioc(ophyd.ImagePlugin)
my_detector = Detector('13SIM1:', name='detector')
try:
    my_detector.wait_for_connection(1.0)
except TimeoutError:
    print('Connection timed out')
else:
    print('Connected to detector')

dev_dict = ophyd_device_to_caproto_ioc(my_detector)
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
