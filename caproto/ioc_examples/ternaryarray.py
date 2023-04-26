import asyncio
import threading
import time

from functools import partial, partialmethod, wraps

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

    def __init__(self, delay=0.5):
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
        self._devices = [TernaryDevice() for i in range(count)]
        super().__init__(*args, **kwargs)

        # Dynamically setup the pvs.
        for i in range(count):
            # Create the setpoint pv.
            setattr(self, f'device{i}', pvproperty(value=0, dtype=int, name=f'device{i}'))

            # Create the setpoint putter.
            partial_putter = partial(self.general_putter, self, i)
            partial_putter.__name__ = f"putter{i}"
            getattr(self, f'device{i}').putter(partial_putter)

            # Create the readback pv.
            setattr(self, f'device{i}_rbv', pvproperty(value=0, dtype=int, name=f'device{i}_rbv'))

            # Create the readback scan.
            partial_scan = partial(self.general_scan, self, i)
            partial_scan.__name__ = f"scan{i}"
            getattr(self, f'device{i}_rbv').scan(partial_scan, period=0.1)

    async def general_putter(self, index, instance, value):
        if value:
            self._devices[index].set()
        else:
            self._devices[index].reset()

    async def general_scan(self, index, instance, async_lib):
        await getattr(self, f'device{index}_rbv').write(self._devices[index].state)

"""
if __name__ == "__main__":
    ioc_options, run_options = ioc_arg_parser(
        default_prefix="TernaryArray:", desc="TernaryArray IOC"
    )
    ioc = TernaryArrayIOC(**ioc_options)

    print("PVs:", list(ioc.pvdb))
    run(ioc.pvdb, **run_options)
"""
