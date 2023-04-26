import asyncio
import threading
import time

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
        for i in range(count):
            setattr(self, f'device{i}', pvproperty(value=0, dtype=int, name=f'device{i}'))
            setattr(self, f'device{i}_rbv', pvproperty(value=0, dtype=int, name=f'device{i}_rbv'))

    async def device_poller(self):
        while True:
            for i in range(self.count):
                await getattr(self, f'device{i}_rbv').write(self._devices[i].state)

    @Kp.putter
    async def Kp(self, instance, value):
        self._temperature_controller.Kp = value
        return value


if __name__ == "__main__":
    ioc_options, run_options = ioc_arg_parser(
        default_prefix="TernaryArray:", desc="Lakeshore IOC"
    )
    ioc = TernaryArrayIOC(**ioc_options)

    print("PVs:", list(ioc.pvdb))
    run(ioc.pvdb, **run_options)
