#!/usr/bin/env python3
import numpy as np
import ophyd

from caproto.server import (PVGroup, pvproperty, SubGroup, get_pv_pair_wrapper,
                            ioc_arg_parser, run)
from caproto.server.conversion import ophyd_device_to_caproto_ioc


async def get_images(w, h):
    img = np.zeros((w, h), dtype=np.int32)
    while True:
        for i in range(256):
            img[:, :] = (i << 16) | (i << 8) | i
            yield img


class SC(ophyd.areadetector.cam.SimDetectorCam):
    pool_max_buffers = None


class IP(ophyd.ImagePlugin):
    pool_max_buffers = None


class Detector(ophyd.SimDetector):
    image1 = ophyd.Component(IP, 'image1:')
    cam = ophyd.Component(SC, 'cam1:')


pvproperty_with_rbv = get_pv_pair_wrapper(setpoint_suffix='',
                                          readback_suffix='_RBV')


# -- DetectorGroup --
class DetectorGroup(PVGroup):
    # configuration_names = pvproperty(name=None, dtype=str)

    class SimDetectorCamGroup(PVGroup):
        # configuration_names = pvproperty(name=None, dtype=str)
        array_counter = pvproperty_with_rbv(name='ArrayCounter', dtype=int)
        array_rate = pvproperty(
            name='ArrayRate_RBV', dtype=float, read_only=True)
        asyn_io = pvproperty(name='AsynIO', dtype=int)
        nd_attributes_file = pvproperty(
            name='NDAttributesFile', dtype=str, max_length=256)
        pool_alloc_buffers = pvproperty(
            name='PoolAllocBuffers', dtype=int, read_only=True)
        pool_free_buffers = pvproperty(
            name='PoolFreeBuffers', dtype=int, read_only=True)
        pool_max_buffers = pvproperty(
            name='PoolMaxBuffers', dtype=int, read_only=True)
        pool_max_mem = pvproperty(
            name='PoolMaxMem', dtype=float, read_only=True)
        pool_used_buffers = pvproperty(
            name='PoolUsedBuffers', dtype=float, read_only=True)
        pool_used_mem = pvproperty(
            name='PoolUsedMem', dtype=float, read_only=True)
        port_name = pvproperty(name='PortName_RBV', dtype=str, read_only=True)
        acquire = pvproperty_with_rbv(name='Acquire', dtype=int)
        acquire_period = pvproperty_with_rbv(name='AcquirePeriod', dtype=float)
        acquire_time = pvproperty_with_rbv(name='AcquireTime', dtype=float)
        array_callbacks = pvproperty_with_rbv(name='ArrayCallbacks', dtype=int)

        class SimDetectorCamArraySizeGroup(PVGroup):
            array_size_x = pvproperty(
                name='ArraySizeX_RBV', dtype=int, read_only=True)
            array_size_y = pvproperty(
                name='ArraySizeY_RBV', dtype=int, read_only=True)
            array_size_z = pvproperty(
                name='ArraySizeZ_RBV', dtype=int, read_only=True)

        array_size = SubGroup(SimDetectorCamArraySizeGroup, prefix='')

        array_size_bytes = pvproperty(
            name='ArraySize_RBV', dtype=int, read_only=True)
        bin_x = pvproperty_with_rbv(name='BinX', dtype=int)
        bin_y = pvproperty_with_rbv(name='BinY', dtype=int)
        color_mode = pvproperty_with_rbv(name='ColorMode', dtype=int)
        data_type = pvproperty_with_rbv(name='DataType', dtype=int)
        detector_state = pvproperty(
            name='DetectorState_RBV', dtype=int, read_only=True)
        frame_type = pvproperty_with_rbv(name='FrameType', dtype=int)
        gain = pvproperty_with_rbv(name='Gain', dtype=float)
        image_mode = pvproperty_with_rbv(name='ImageMode', dtype=int)
        manufacturer = pvproperty(
            name='Manufacturer_RBV', dtype=str, read_only=True)

        class SimDetectorCamMaxSizeGroup(PVGroup):
            max_size_x = pvproperty(
                name='MaxSizeX_RBV', dtype=int, read_only=True)
            max_size_y = pvproperty(
                name='MaxSizeY_RBV', dtype=int, read_only=True)

        max_size = SubGroup(SimDetectorCamMaxSizeGroup, prefix='')

        min_x = pvproperty_with_rbv(name='MinX', dtype=int)
        min_y = pvproperty_with_rbv(name='MinY', dtype=int)
        model = pvproperty(name='Model_RBV', dtype=str, read_only=True)
        num_exposures = pvproperty_with_rbv(name='NumExposures', dtype=int)
        num_exposures_counter = pvproperty(
            name='NumExposuresCounter_RBV', dtype=int, read_only=True)
        num_images = pvproperty_with_rbv(name='NumImages', dtype=int)
        num_images_counter = pvproperty(
            name='NumImagesCounter_RBV', dtype=int, read_only=True)
        read_status = pvproperty(name='ReadStatus', dtype=int)

        class SimDetectorCamReverseGroup(PVGroup):
            reverse_x = pvproperty_with_rbv(name='ReverseX', dtype=int)
            reverse_y = pvproperty_with_rbv(name='ReverseY', dtype=int)

        reverse = SubGroup(SimDetectorCamReverseGroup, prefix='')

        shutter_close_delay = pvproperty_with_rbv(
            name='ShutterCloseDelay', dtype=float)
        shutter_close_epics = pvproperty(name='ShutterCloseEPICS', dtype=float)
        shutter_control = pvproperty_with_rbv(name='ShutterControl', dtype=int)
        shutter_control_epics = pvproperty(
            name='ShutterControlEPICS', dtype=int)
        shutter_fanout = pvproperty(name='ShutterFanout', dtype=int)
        shutter_mode = pvproperty_with_rbv(name='ShutterMode', dtype=int)
        shutter_open_delay = pvproperty_with_rbv(
            name='ShutterOpenDelay', dtype=float)
        shutter_open_epics = pvproperty(name='ShutterOpenEPICS', dtype=float)
        shutter_status_epics = pvproperty(
            name='ShutterStatusEPICS_RBV', dtype=int, read_only=True)
        shutter_status = pvproperty(
            name='ShutterStatus_RBV', dtype=int, read_only=True)

        class SimDetectorCamSizeGroup(PVGroup):
            size_x = pvproperty_with_rbv(name='SizeX', dtype=int)
            size_y = pvproperty_with_rbv(name='SizeY', dtype=int)

        size = SubGroup(SimDetectorCamSizeGroup, prefix='')

        status_message = pvproperty(
            name='StatusMessage_RBV',
            dtype=str,
            max_length=256,
            read_only=True)
        string_from_server = pvproperty(
            name='StringFromServer_RBV',
            dtype=str,
            max_length=256,
            read_only=True)
        string_to_server = pvproperty(
            name='StringToServer_RBV',
            dtype=str,
            max_length=256,
            read_only=True)
        temperature = pvproperty_with_rbv(name='Temperature', dtype=float)
        temperature_actual = pvproperty(name='TemperatureActual', dtype=float)
        time_remaining = pvproperty(
            name='TimeRemaining_RBV', dtype=float, read_only=True)
        trigger_mode = pvproperty_with_rbv(name='TriggerMode', dtype=int)

        class SimDetectorCamGainRgbGroup(PVGroup):
            gain_red = pvproperty_with_rbv(name='GainRed', dtype=float)
            gain_green = pvproperty_with_rbv(name='GainGreen', dtype=float)
            gain_blue = pvproperty_with_rbv(name='GainBlue', dtype=float)

        gain_rgb = SubGroup(SimDetectorCamGainRgbGroup, prefix='')

        class SimDetectorCamGainXyGroup(PVGroup):
            gain_x = pvproperty_with_rbv(name='GainX', dtype=float)
            gain_y = pvproperty_with_rbv(name='GainY', dtype=float)

        gain_xy = SubGroup(SimDetectorCamGainXyGroup, prefix='')

        noise = pvproperty_with_rbv(name='Noise', dtype=int)

        class SimDetectorCamPeakNumGroup(PVGroup):
            peak_num_x = pvproperty_with_rbv(name='PeakNumX', dtype=int)
            peak_num_y = pvproperty_with_rbv(name='PeakNumY', dtype=int)

        peak_num = SubGroup(SimDetectorCamPeakNumGroup, prefix='')

        class SimDetectorCamPeakStartGroup(PVGroup):
            peak_start_x = pvproperty_with_rbv(name='PeakStartX', dtype=int)
            peak_start_y = pvproperty_with_rbv(name='PeakStartY', dtype=int)

        peak_start = SubGroup(SimDetectorCamPeakStartGroup, prefix='')

        class SimDetectorCamPeakStepGroup(PVGroup):
            peak_step_x = pvproperty_with_rbv(name='PeakStepX', dtype=int)
            peak_step_y = pvproperty_with_rbv(name='PeakStepY', dtype=int)

        peak_step = SubGroup(SimDetectorCamPeakStepGroup, prefix='')

        peak_variation = pvproperty_with_rbv(name='PeakVariation', dtype=int)

        class SimDetectorCamPeakWidthGroup(PVGroup):
            peak_width_x = pvproperty_with_rbv(name='PeakWidthX', dtype=int)
            peak_width_y = pvproperty_with_rbv(name='PeakWidthY', dtype=int)

        peak_width = SubGroup(SimDetectorCamPeakWidthGroup, prefix='')

        reset = pvproperty_with_rbv(name='Reset', dtype=int)
        sim_mode = pvproperty_with_rbv(name='SimMode', dtype=int)

    cam = SubGroup(SimDetectorCamGroup, prefix='cam1:')

    class ImagePluginGroup(PVGroup):
        # configuration_names = pvproperty(name=None, dtype=str)
        array_counter = pvproperty_with_rbv(name='ArrayCounter', dtype=int)
        array_rate = pvproperty(
            name='ArrayRate_RBV', dtype=float, read_only=True)
        asyn_io = pvproperty(name='AsynIO', dtype=int)
        nd_attributes_file = pvproperty(
            name='NDAttributesFile', dtype=str, max_length=256)
        pool_alloc_buffers = pvproperty(
            name='PoolAllocBuffers', dtype=int, read_only=True)
        pool_free_buffers = pvproperty(
            name='PoolFreeBuffers', dtype=int, read_only=True)
        pool_max_buffers = pvproperty(
            name='PoolMaxBuffers', dtype=int, read_only=True)
        pool_max_mem = pvproperty(
            name='PoolMaxMem', dtype=float, read_only=True)
        pool_used_buffers = pvproperty(
            name='PoolUsedBuffers', dtype=float, read_only=True)
        pool_used_mem = pvproperty(
            name='PoolUsedMem', dtype=float, read_only=True)
        port_name = pvproperty(name='PortName_RBV', dtype=str, read_only=True)
        # asyn_pipeline_config = pvproperty(name=None, dtype=str)
        # width = pvproperty(name='ArraySize0_RBV', dtype=int, read_only=True)
        # height = pvproperty(name='ArraySize1_RBV', dtype=int, read_only=True)
        # depth = pvproperty(name='ArraySize2_RBV', dtype=int, read_only=True)

        class ImagePluginArraySizeGroup(PVGroup):
            height = pvproperty(
                name='ArraySize1_RBV', dtype=int, read_only=True)
            width = pvproperty(
                name='ArraySize0_RBV', dtype=int, read_only=True)
            depth = pvproperty(
                name='ArraySize2_RBV', dtype=int, read_only=True)

        array_size = SubGroup(ImagePluginArraySizeGroup, prefix='')

        bayer_pattern = pvproperty(
            name='BayerPattern_RBV', dtype=int, read_only=True)
        blocking_callbacks = pvproperty_with_rbv(
            name='BlockingCallbacks', dtype=str)
        color_mode = pvproperty(
            name='ColorMode_RBV', dtype=int, read_only=True)
        data_type = pvproperty(name='DataType_RBV', dtype=str, read_only=True)
        # dim0_sa = pvproperty(name='Dim0SA', dtype=int, max_length=10)
        # dim1_sa = pvproperty(name='Dim1SA', dtype=int, max_length=10)
        # dim2_sa = pvproperty(name='Dim2SA', dtype=int, max_length=10)

        class ImagePluginDimSaGroup(PVGroup):
            dim0 = pvproperty(name='Dim0SA', dtype=int, max_length=10)
            dim1 = pvproperty(name='Dim1SA', dtype=int, max_length=10)
            dim2 = pvproperty(name='Dim2SA', dtype=int, max_length=10)

        dim_sa = SubGroup(ImagePluginDimSaGroup, prefix='')

        dimensions = pvproperty(
            name='Dimensions_RBV', dtype=int, max_length=10, read_only=True)
        dropped_arrays = pvproperty_with_rbv(name='DroppedArrays', dtype=int)
        enable = pvproperty_with_rbv(name='EnableCallbacks', dtype=str)
        min_callback_time = pvproperty_with_rbv(
            name='MinCallbackTime', dtype=float)
        nd_array_address = pvproperty_with_rbv(
            name='NDArrayAddress', dtype=int)
        nd_array_port = pvproperty_with_rbv(name='NDArrayPort', dtype=str)
        ndimensions = pvproperty(
            name='NDimensions_RBV', dtype=int, read_only=True)
        plugin_type = pvproperty(
            name='PluginType_RBV', dtype=str, read_only=True)
        queue_free = pvproperty(name='QueueFree', dtype=int)
        queue_free_low = pvproperty(name='QueueFreeLow', dtype=float)
        queue_size = pvproperty(name='QueueSize', dtype=int)
        queue_use = pvproperty(name='QueueUse', dtype=float)
        queue_use_high = pvproperty(name='QueueUseHIGH', dtype=float)
        queue_use_hihi = pvproperty(name='QueueUseHIHI', dtype=float)
        time_stamp = pvproperty(
            name='TimeStamp_RBV', dtype=float, read_only=True)
        unique_id = pvproperty(name='UniqueId_RBV', dtype=int, read_only=True)
        array_data = pvproperty(
            name='ArrayData', dtype=int, max_length=300000)

        # NOTE: this portion written by hand:
        @array_data.startup
        async def array_data(self, instance, async_lib):
            await self.plugin_type.write('NDPluginStdArrays')

            w, h = 256, 256
            await self.array_size.width.write(w)
            await self.array_size.height.write(h)
            await self.array_size.depth.write(0)
            await self.ndimensions.write(2)
            await self.dimensions.write([w, h, 0])

            async for image in get_images(w, h):
                await self.array_data.write(image.flatten())
                await async_lib.library.sleep(1.0)
        # END hand-written portion

    image1 = SubGroup(ImagePluginGroup, prefix='image1:')

# -- end autogenerated code --


def generate_detector_code(prefix='13SIM1:'):
    '''
    Use the simDetector IOC to automatically create code for our detector,
    with the help of ophyd and `ophyd_device_to_caproto_ioc`
    '''
    my_detector = Detector('13SIM1:', name='detector')
    try:
        my_detector.wait_for_connection(5.0)
    except TimeoutError:
        print('Connection timed out')
        return
    else:
        print('Connected to detector')

    dev_dict = ophyd_device_to_caproto_ioc(my_detector)
    print('# -- autogenerated code --')
    for dev, lines in dev_dict.items():
        print(f'# -- {dev} --')

        for line in lines:
            print(line)

        print(f'# -- end {dev} --')
    print('# -- end autogenerated code --')


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='adimage:',
        desc='Simulate an Area Detector IOC.')
    ioc = DetectorGroup(**ioc_options)
    generate_detector_code()

    detector_ioc = DetectorGroup(ioc_options['prefix'])
    run(ioc.pvdb, **run_options)
