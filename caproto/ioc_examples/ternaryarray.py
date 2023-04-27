import asyncio

from functools import partial
from collections import OrderedDict
from caproto.server import PVGroup, ioc_arg_parser, pvproperty, run
from ophyd import EpicsSignal, EpicsSignalRO, PVPositionerPC
from ophyd import Component as Cpt


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
        if self._state:
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
            # Create the setpoint pv.
            setattr(
                self, f"device{i}", pvproperty(value=0, dtype=int, name=f"device{i}")
            )

            # Create the setpoint putter.
            partial_putter = partial(self.general_putter, i)
            partial_putter.__name__ = f"putter{i}"
            getattr(self, f"device{i}").putter(partial_putter)

            # Create the readback pv.
            setattr(
                self,
                f"device{i}_rbv",
                pvproperty(value=0, dtype=int, name=f"device{i}_rbv"),
            )

            # Create the readback scan.
            partial_scan = partial(self.general_scan, i)
            partial_scan.__name__ = f"scan{i}"
            getattr(self, f"device{i}_rbv").scan(period=0.1)(partial_scan)

        # Unfortunate hack to register the late pvs.
        self.__dict__["_pvs_"] = OrderedDict(PVGroup.find_pvproperties(self.__dict__))
        super().__init__(*args, **kwargs)

    async def general_putter(self, index, group, instance, value):
        if value:
            await self._devices[index].set()
        else:
            await self._devices[index].reset()

    async def general_scan(self, index, group, instance, async_lib):
        # A hacky way to write to the pv.
        await self.pvdb[f"{self.prefix}device{index}_rbv"].write(
            self._devices[index].state
        )
        # This is the normal way to do this, but it doesn't work correctly for this example.
        # await getattr(self, f'device{index}_rbv').write(self._devices[index].state)



class TernaryDevice(Device):
    set_cmd = FormattedComponent(EpicsSignal, self._set_name)
    reset_cmd = FormattedComponent(EpicsSignal, self._reset_name)
    state_rbv = FormattedComponent(EpicsSignalRO, self._state_name)

    def __init__(self, *args, set_name, reset_name, state_name,**kwargs) -> None:
        self._set_name = set_name
        self._reset_name = reset_name
        self._state_name = state_name
        self._state = None
        super().__init__(*args, **kwargs)

    def set(self, value=True):
        st = DeviceStatus(self)
        if self.get() == value:
            st._finished()
            return st
        self._set_st = st

        def state_cb(value, timestamp, **kwargs):
            self._state = value
        self.state_rbv.subscribe(state_cb)

        if value:
            set_cmd.set(1)
        else:
            reset_cmd.set(1)
        return st

    def reset(self):
        self.set(False)

    def get(self):
        return self._state


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
