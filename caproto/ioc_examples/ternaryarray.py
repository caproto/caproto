import asyncio
import threading
import time

from functools import partialmethod

from caproto.server import PVGroup, ioc_arg_parser, pvproperty, run
from ophyd import EpicsSignal, EpicsSignalRO, PVPositionerPC
from ophyd import Component as Cpt


class TernaryDevice:
    """
    A device with three states.

    Parameters
    ----------
    delay: float, optional
        The time it takes for the device to change from state-0 to state-1.
    """

    def __init__(self, delay=0.1):
        self._delay = delay
        self._state = 0

    def set(self):
        if not self._state:
            self._state = 1
            time.sleep(self._delay)
            self._state = 2

    def reset(self):
        if self._state == 2:
            self._state = 1
            time.sleep(self._delay)
            self._state = 0

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
        super().__init__(*args, **kwargs)
        self._count = count
        self._devices = [TernaryDevice() for i in range(count)]

        # Create pvs for all of the devices.
        for i in range(count):
            setattr(self, f'device{i}', pvproperty(value=0, dtype=int, name=f'device{i}'))
            setattr(self, f'device{i}_rbv', pvproperty(value=0, dtype=int, name=f'device{i}_rbv'))

        # Assign putters of all of the setpoint pvs.
        for i in range(count):
            getattr(self, f'device{i}').putter(partialmethod(general_putter, i))

    async def general_putter(self, index, instance, value):
        if value:
            self.devices[index].set()
        else:
            self.devices[index].reset()

    async def device_poller(self):
        while True:
            for i in range(self.count):
                await getattr(self, f'device{i}_rbv').write(self._devices[i].state)


"""
if __name__ == "__main__":
    ioc_options, run_options = ioc_arg_parser(
        default_prefix="TernaryArray:", desc="TernaryArray IOC"
    )
    ioc = TernaryArrayIOC(**ioc_options)

    print("PVs:", list(ioc.pvdb))
    run(ioc.pvdb, **run_options)
"""
