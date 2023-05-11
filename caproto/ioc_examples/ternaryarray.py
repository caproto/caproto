import asyncio
import subprocess
import sys
import time

from enum import Enum
from functools import partial
from collections import OrderedDict
from caproto.server import PVGroup, ioc_arg_parser, pvproperty, run
from ophyd import Device, DeviceStatus, EpicsSignal, EpicsSignalRO, FormattedComponent


class StateEnum(Enum):
    In = True
    Out = False
    Unknown = None


class TernaryDeviceSim:
    """
    A device with three states.

    Parameters
    ----------
    delay: float, optional
        The time it takes for the device to change from state-0 to state-1.
    """

    def __init__(self, delay=0.5):
        self._delay = delay
        self._state = None

    async def set(self):
        if not self._state:
            self._state = None
            await asyncio.sleep(self._delay)
            self._state = True

    async def reset(self):
        if self._state or self._state is None:
            self._state = None
            await asyncio.sleep(self._delay)
            self._state = False

    @property
    def state(self):
        return self._state


class TernaryArrayIOC(PVGroup):
    """
    Example IOC that has an array of TernaryDevices.

    Parameters
    ----------
    count: integer
        The number of devices in the array.
    """

    def __init__(self, count=10, *args, **kwargs):
        self._devices = [TernaryDeviceSim() for i in range(count)]

        # Dynamically setup the pvs.
        for i in range(count):
            # Create the set pv.
            setattr(
                self,
                f"device{i}_set",
                pvproperty(value=0, dtype=int, name=f"device{i}_set"),
            )

            # Create the set putter.
            partial_set = partial(self.set_putter, i)
            partial_set.__name__ = f"set_putter{i}"
            getattr(self, f"device{i}_set").putter(partial_set)

            # Create the reset pv.
            setattr(
                self,
                f"device{i}_reset",
                pvproperty(value=0, dtype=int, name=f"device{i}_reset"),
            )

            # Create the reset putter.
            partial_reset = partial(self.reset_putter, i)
            partial_reset.__name__ = f"reset_putter{i}"
            getattr(self, f"device{i}_reset").putter(partial_reset)

            # Create the readback pv.
            setattr(
                self,
                f"device{i}_rbv",
                pvproperty(value="Unknown", dtype=str, name=f"device{i}_rbv"),
            )

            # Create the readback scan.
            partial_scan = partial(self.general_scan, i)
            partial_scan.__name__ = f"scan{i}"
            getattr(self, f"device{i}_rbv").scan(period=0.1)(partial_scan)

        # Unfortunate hack to register the late pvs.
        self.__dict__["_pvs_"] = OrderedDict(PVGroup.find_pvproperties(self.__dict__))
        super().__init__(*args, **kwargs)

    async def set_putter(self, index, group, instance, value):
        if value:
            await self._devices[index].set()

    async def reset_putter(self, index, group, instance, value):
        if value:
            await self._devices[index].reset()

    async def general_scan(self, index, group, instance, async_lib):
        # A hacky way to write to the pv.
        await self.pvdb[f"{self.prefix}device{index}_rbv"].write(
            StateEnum(self._devices[index].state).name
        )
        # This is the normal way to do this, but it doesn't work correctly for this example.
        # await getattr(self, f'device{index}_rbv').write(StateEnum(self._devices[index].state).name)


class TernaryDevice(Device):
    """
    A general purpose ophyd device with set and reset signals, and a state signal
    with 3 posible signals.
    """

    set_cmd = FormattedComponent(EpicsSignal, "{self._set_name}")
    reset_cmd = FormattedComponent(EpicsSignal, "{self._reset_name}")
    state_rbv = FormattedComponent(EpicsSignalRO, "{self._state_name}")

    def __init__(
        self, *args, set_name, reset_name, state_name, state_enum, **kwargs
    ) -> None:
        self._state_enum = state_enum
        self._set_name = set_name
        self._reset_name = reset_name
        self._state_name = state_name
        self._state = None
        super().__init__(*args, **kwargs)

    def set(self, value=True):
        if value not in {True, False, 0, 1}:
            raise ValueError("value must be one of the following: True, False, 0, 1")

        target_value = bool(value)

        st = DeviceStatus(self)

        # If the device already has the requested state, return a finished status.
        if self._state == bool(value):
            st._finished()
            return st
        self._set_st = st

        def state_cb(value, timestamp, **kwargs):
            """
            Updates self._state and checks if the status should be marked as finished.
            """
            try:
                self._state = self._state_enum[value].value
            except KeyError:
                raise ValueError(f"self._state_enum does not contain value: {value}")
            if self._state == target_value:
                self._set_st = None
                st._finished()

        # Subscribe the callback to the readback signal.
        # The callback will be called each time the PV value changes.
        self.state_rbv.subscribe(state_cb)

        # Write to the signal.
        if value:
            set_cmd.set(1)
        else:
            reset_cmd.set(1)
        return st

    def reset(self):
        self.set(False)

    def get(self):
        return self._state


class ExampleTernary(TernaryDevice):
    """
    This class is an example about how to create a TernaryDevice specialization
    for a specific implementation.
    """

    def __init__(self, index, *args, **kwargs):
        super().__init__(
            *args,
            name=f"Filter{index}",
            set_name=f"TernaryArray:device{index}_set",
            reset_name=f"TernaryArray:device{index}_reset",
            state_name=f"TernaryArray:device{index}_rbv",
            state_enum=StateEnum,
            **kwargs,
        )


ternary1 = ExampleTernary(1)


class CmsFilter(TernaryDevice):
    """
    This class is an example about how to create a TernaryDevice specialization
    for a specific implementation.
    """

    def __init__(self, index, *args, **kwargs):
        super().__init__(
            *args,
            name=f"Filter{index}",
            set_name=f"XF:11BMB-OP{{Fltr:{index}}}Cmd:Opn-Cmd",
            reset_name=f"XF:11BMB-OP{{Fltr:{index}}}Cmd:Cls-Cmd",
            state_name=f"XF:11BMB-OP{{Fltr:{index}}}Pos-Sts",
            state_enum=StateEnum,
            **kwargs,
        )


cms_filter1 = CmsFilter(1)


class ArrayDevice(Device):
    """
    An ophyd.Device that is an array of devices.

    The set method takes a list of values.
    the get method returns a list of values.
    Parameters
    ----------
    devices: iterable
        The array of ophyd devices.
    """
    def __init__(self, devices, *args, **kwargs):
        types = {type(device) for device in devices}
        if len(types) != 1:
            raise TypeError("All devices must have the same type")

        self._devices = devices
        super().__init__(*args, **kwargs)

    def set(self, values):
        if len(values) != len(self._devices):
            raise ValueError(
                f"The number of values ({len(values)}) must match "
                f"the number of devices ({len(self._devices)})"
            )

        # If the device already has the requested state, return a finished status.
        diff = [self._devices[i].get() != value for i, value in enumerate(values)]
        if not any(diff):
            return DeviceStatus(self, success=True, done=True)

        # Set the value of each device and return a union of the statuses.
        st = self._devices[0].set(values[0])
        for i, value in enumerate(values[1:]):
            st &= self._devices[i].set(value)
        return st

    def get(self):
        return [device.get() for device in self._devices]

#class ArrayDevice(Device):
#    devices = DDC({f"device{i:01}": (FilterDevice, f"PVblahblah{i}", {}_ for i in range(10))})


#def build_array_device(N, class_name="ArrayDevice"):
#    class_dict = {"devices": {f"device{i:01}": (FilterDevice, f"PVblahblah{i}", {}_ for i in range(N))}}
#    bases = (Device,)
#    return type(class_name, bases, class_dict)

def start_test_ioc():
    ioc = TernaryArrayIOC(prefix='TernaryArray:')
    print("Prefix =", "TernaryArray:")
    print("PVs:", list(ioc.pvdb))
    run(ioc.pvdb)


ps = None
def process_cleanup(f):
    def wrap():
        try:
            f()
        finally:
            ps.kill()
    return wrap


@process_cleanup
def test_arraydevice():
    global ps
    arraydevice = ArrayDevice([ExampleTernary(i) for i in range(10)],
                              name='arraydevice')
    ps = subprocess.Popen([sys.executable, '-c', 'from caproto.ioc_examples.ternaryarray import start_test_ioc; start_test_ioc()'])
    arraydevice.set([1,1,1,0,0,0,1,1,1,0])


"""
if __name__ == "__main__":
    ioc_options, run_options = ioc_arg_parser(
        default_prefix="TernaryArray:", desc="TernaryArray IOC"
    )
    ioc = TernaryArrayIOC(**ioc_options)
    print("Prefix =", "TernaryArray:")
    print("PVs:", list(ioc.pvdb))
    run(ioc.pvdb, **run_options)
"""
