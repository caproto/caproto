"""
An IOC with a simulated temperature controller.
This demonstrates how to do put_completion with a caproto ioc and ophyd device.

Another interesting part of this example is the use of settle_time.
Settle_time allows us to wait an additional amount after the put_completion.
It is used here to wait for the stabilization of the material temperature
after the setpoint ramp is complete.

This also includes a simulated material that can be heated/cooled and a
PID controller that can be connected to arbitrary systems. The PIDController
has a ramp feature so that the setpoint ramps to the target value gradually.

This example has two non-standard dependencies: ophyd, and simple_pid
"""

import asyncio
import contextvars
import functools
import threading
import time

from collections import deque
from simple_pid import PID
from caproto.server import PVGroup, ioc_arg_parser, pvproperty, run
from ophyd import EpicsSignal, EpicsSignalRO, PVPositionerPC
from ophyd import Component as Cpt


class ThermalMaterial:
    """
    A material that you can heat and cool.

    Parameters
    ----------
    thermal_mass: float, optional
        How the material's energy relates to its temperature.
    start_temp: float, optional
        Starting temperature of the material.
    ambient_temp: float, optional
        The temperature of the environment.
    heater_power: float, optional
        The rate at which the heater is adding energy to the sample.
    cooling_constant: float, optional
        How readily the sample releases energy to the environment.
    """

    def __init__(
        self,
        thermal_mass=100,
        start_temp=100,
        ambient_temp=0,
        heater_power=0,
        cooling_constant=1,
    ):
        self.energy = start_temp * thermal_mass
        self.thermal_mass = thermal_mass
        self.ambient_temp = ambient_temp
        self._heater_power = heater_power
        self.cooling_constant = cooling_constant
        self.time = time.time()
        self._run = True
        threading.Thread(target=self._simulate).start()

    @property
    def temperature(self):
        return self.energy / self.thermal_mass

    @property
    def heater_power(self):
        return self._heater_power

    @heater_power.setter
    def heater_power(self, value):
        self._heater_power = value

    def set_heater_power(self, value):
        self._heater_power = value

    def stop(self):
        self._run = False

    def _cooling(self):
        return -1 * self.cooling_constant * (self.temperature - self.ambient_temp)

    def _heating(self):
        return self.heater_power

    def _simulate(self):
        while self._run:
            now = time.time()
            time_delta = now - self.time
            self.time = now
            self.energy += self._cooling() * time_delta
            self.energy += self._heating() * time_delta
            time.sleep(0.1)


class PIDController(PID):
    """
    General purpose PID controller that supports ramping.

    Parameters
    ----------
    get_feedback: callable
        A function that returns the feedback value of the system.
    set_output: callable
        A function that sets the output value of the system.
    ramp_rate: int, float
        The rate that the setpoint should ramp at.
    setpoint: int, float

    Example
    -------
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation
    from caproto.ioc_examples.lakeshore import (PIDController,
    ThermalMaterial)

    sample = ThermalMaterial()
    setpoint = 150

    temperature_controller = PIDController(
        lambda: sample.temperature,
        sample.set_heater_power,
        Kp=1,
        Ki=0.1,
        Kd=0.05,
        ramp_rate=1,
        setpoint=setpoint,
    )

    def update(i):
        x_values = temperature_controller.history['timestamp']
        plt.cla()
        plt.plot(x_values, temperature_controller.history['feedback'])
        plt.plot(x_values, temperature_controller.history['output'])
        plt.plot(x_values, temperature_controller.history['setpoint'])
        plt.xlabel('time')
        plt.ylabel('temperature')
        plt.title('Temperature Controller')
        plt.gcf().autofmt_xdate()
        plt.tight_layout()

    ani = FuncAnimation(plt.gcf(), update, 1000)
    plt.tight_layout()
    plt.show(block=False)
    """

    def __init__(
        self, get_feedback, set_output, ramp_rate=1, setpoint=150, *args, **kwargs
    ):
        self._setpoint = setpoint
        self.ramp_rate = ramp_rate
        super().__init__(setpoint=setpoint, *args, **kwargs)
        self._get_feedback = get_feedback
        self._set_output = set_output
        self._feedback = None
        self._output = None
        self._run = True
        self._ramping = False
        self.history = {
            "output": deque(maxlen=600),
            "feedback": deque(maxlen=600),
            "setpoint": deque(maxlen=600),
            "timestamp": deque(maxlen=600),
        }
        threading.Thread(target=self._executor).start()

    @property
    def output(self):
        return self._output

    @property
    def feedback(self):
        return self._feedback

    @property
    def setpoint(self):
        return self._setpoint

    @setpoint.setter
    def setpoint(self, value):
        """
        Always set ramping to true at the same time as
        the setpoint change. Is will avoid a race condition,
        and will allow the client to just check for ramping = False
        to determine completion.
        """
        self._setpoint_target = value
        self._ramping = True
        if self.ramp_rate is None:
            self._setpoint = value

    @property
    def ramping(self):
        return self._ramping

    def stop(self):
        self._run = False

    def _executor(self):
        iteration_time = 0.1
        while self._run:
            self._feedback = self._get_feedback()
            self._output = self.__call__(self._get_feedback())
            self.history["output"].append(self._output)
            self.history["feedback"].append(self._feedback)
            self.history["setpoint"].append(self.setpoint)
            self.history["timestamp"].append(time.time())
            self._set_output(self._output)

            # Ramping logic.
            remaining = self._setpoint_target - self.setpoint
            self._ramping = bool(remaining)
            if isinstance(self.ramp_rate, (int, float)):
                if remaining > 0:
                    self._setpoint += min(
                        self.ramp_rate * iteration_time, abs(remaining)
                    )
                elif remaining < 0:
                    self._setpoint -= min(
                        self.ramp_rate * iteration_time, abs(remaining)
                    )
            elif self.ramp_rate is None and remaining != 0:
                self._setpoint = self._setpoint_target

            time.sleep(iteration_time)


internal_process = contextvars.ContextVar("internal_process", default=False)


def no_reentry(func):
    """
    This is needed for put completion.
    """

    @functools.wraps(func)
    async def inner(*args, **kwargs):
        if internal_process.get():
            return
        try:
            internal_process.set(True)
            return await func(*args, **kwargs)
        finally:
            internal_process.set(False)

    return inner


class LakeshoreIOC(PVGroup):
    """
    Simulated Lakeshore IOC with put completion on the setpoint.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sample = ThermalMaterial()

        self._temperature_controller = PIDController(
            lambda: self._sample.temperature,
            self._sample.set_heater_power,
            Kp=1,
            Ki=0.1,
            Kd=0.05,
            setpoint=150,
        )

    async def device_poller(self):
        while True:
            await self.Kp_rbv.write(self._temperature_controller.Kp)
            await self.Ki_rbv.write(self._temperature_controller.Ki)
            await self.Kd_rbv.write(self._temperature_controller.Kd)
            await self.setpoint_rbv.write(self._temperature_controller.setpoint)
            await self.feedback_rbv.write(self._temperature_controller.feedback)
            await self.ramp_rate_rbv.write(self._temperature_controller.ramp_rate)
            await self.output_rbv.write(self._temperature_controller.output)
            await asyncio.sleep(.1)

    Kp = pvproperty(value=0, dtype=float, name="Kp", doc="PID parameter Kp")
    Kp_rbv = pvproperty(dtype=float, name="Kp_rbv", doc="PID parameter Kp readback")

    @Kp.putter
    async def Kp(self, instance, value):
        self._temperature_controller.Kp = value
        return value

    Ki = pvproperty(value=0, dtype=float, name="Ki", doc="PID parameter Ki")
    Ki_rbv = pvproperty(dtype=float, name="Ki_rbv", doc="PID parameter Ki readback")

    @Ki.putter
    async def Ki(self, instance, value):
        self._temperature_controller.Ki = value
        return value

    Kd = pvproperty(value=0, dtype=float, name="Kd", doc="PID parameter Kd")
    Kd_rbv = pvproperty(dtype=float, name="Kd_rbv", doc="PID parameter Kd readback")

    @Kd.putter
    async def Kd(self, instance, value):
        self._temperature_controller.Kd = value
        return value

    ramp_rate = pvproperty(value=0, dtype=float, name="ramp_rate", doc="ramp_rate")
    ramp_rate_rbv = pvproperty(
        dtype=float, name="ramp_rate_rbv", doc="ramp_rate readback"
    )

    @ramp_rate.putter
    async def ramp_rate(self, instance, value):
        self._temperature_controller.ramp_rate = value
        return value

    setpoint = pvproperty(
        value=100, dtype=float, name="setpoint", doc="temperature setpoint"
    )
    setpoint_rbv = pvproperty(
        dtype=float, name="setpoint_rbv", doc="temperature setpoint"
    )

    async def wait_for_completion(self):
        """
        Wait until the device is done changing the setpoint.
        """
        while True:
            if not self._temperature_controller.ramping:
                return
            await asyncio.sleep(0.1)

    @setpoint.putter
    @no_reentry
    async def setpoint(self, instance, value):
        if not instance.ev.is_set():
            await instance.ev.wait()
            return self._temperature_controller.setpoint

        instance.ev.clear()
        try:
            self._temperature_controller.setpoint = value
            await self.wait_for_completion()
        finally:
            instance.ev.set()
        return self._temperature_controller.setpoint

    @setpoint.startup
    async def setpoint(self, instance, async_lib):
        """
        This is needed to enable put completion.
        """
        instance.async_lib = async_lib
        instance.ev = async_lib.Event()
        instance.ev.set()
        await self.device_poller()

    feedback = pvproperty(
        value=100, dtype=float, name="feedback", doc="temperature feedback"
    )
    feedback_rbv = pvproperty(
        dtype=float, name="feedback_rbv", doc="temperature feedback readback"
    )

    output = pvproperty(value=100, dtype=float, name="output", doc="output value")
    output_rbv = pvproperty(dtype=float, name="output_rbv", doc="output value readback")


class Lakeshore(PVPositionerPC):
    """
    Example Ophyd device for Lakeshore that uses put completion.
    PVPositionerPC does not require a done signal like PVPositioner,
    instead it uses the setpoint put_completion.

    Example
    -------
    ls = Lakeshore('Lakeshore', name='Lakeshore', settle_time=5)
    ls.set(100).wait()

    This will wait for the ramp to be completed and also wait for
    the settle_time.
    """

    feedback = Cpt(EpicsSignalRO, ":feedback_rbv")
    output = Cpt(EpicsSignalRO, ":output_rbv")
    setpoint = Cpt(EpicsSignal, ":setpoint", put_complete=True)
    setpoint_rbv = Cpt(EpicsSignalRO, ":setpoint_rbv")
    ramp_rate = Cpt(EpicsSignal, ":ramp_rate")
    ramp_rate_rbv = Cpt(EpicsSignal, ":ramp_rate_rbv")


if __name__ == "__main__":
    ioc_options, run_options = ioc_arg_parser(
        default_prefix="Lakeshore:", desc="Lakeshore IOC"
    )
    ioc = LakeshoreIOC(**ioc_options)

    print("PVs:", list(ioc.pvdb))
    run(ioc.pvdb, **run_options)
