import time
import threading

from caproto.server import PVGroup, ioc_arg_parser, pvproperty, run
from simple_pid import PID


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
    def __init__(self, get_feedback, set_output, ramp_rate=None,
                 setpoint=150,
                 *args, **kwargs):
        self._setpoint = setpoint
        self.ramp_rate = ramp_rate
        super().__init__(setpoint=setpoint, *args, **kwargs)
        self._get_feedback = get_feedback
        self._set_output = set_output
        self._feedback = None
        self._output = None
        self._run = True
        self._ramping = False
        self.history = {"output": [], "feedback": [], "setpoint": [], "timestamp": []}
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
        self._setpoint_target = value
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
            remaining = (self._setpoint_target - self.setpoint)
            if isinstance(self.ramp_rate, (int, float)):
                if remaining > 0:
                    self._setpoint += min(self.ramp_rate*iteration_time, abs(remaining))
                    self._ramping = True
                elif remaining < 0:
                    self._setpoint -= min(self.ramp_rate*iteration_time, abs(remaining))
                    self._ramping = True
                elif remaining == 0:
                    self._ramping = False
            elif self.ramp_rate is None and remaining != 0:
                self._setpoint = self._setpoint_target

            time.sleep(iteration_time)


"""
# Temperature Controller Example Code

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from caproto.ioc_examples.lakeshore import PIDController, ThermalMaterial

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


def no_reentry(func):
    @functools.wraps(func)
    async def inner(*args, **kwargs):
        if internal_process.get():
            return
        try:
            internal_process.set(True)
            return (await func(*args, **kwargs))
        finally:
            internal_process.set(False)

    return inner


class Lakeshore336Sim(PVGroup):
    """
    Simulated Lakeshore IOC.
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

    Kp = pvproperty(value=0, dtype=float, name="Kp", doc="PID parameter Kp")

    @Kp.getter
    async def Kp(self, instance):
        return self._temperature_controller.Kp

    @Kp.putter
    async def Kp(self, instance, value):
        self._temperature_controller.Kp = value
        return value

    Ki = pvproperty(value=0, dtype=float, name="Ki", doc="PID parameter Ki")

    @Ki.getter
    async def Ki(self, instance):
        return self._temperature_controller.Ki

    @Ki.putter
    async def Ki(self, instance, value):
        self._temperature_controller.Ki = value
        return value

    Kd = pvproperty(value=0, dtype=float, name="Kd", doc="PID parameter Kd")

    @Kd.getter
    async def Kd(self, instance):
        return self._temperature_controller.Kd

    @Kd.putter
    async def Kd(self, instance, value):
        self._temperature_controller.Kd = value
        return value

    setpoint = pvproperty(
        value=100, dtype=float, name="setpoint", doc="temperature setpoint"
    )

    async def wait_for_completion(self):
        while True:
            old_ramping = self._temperature_controller.ramping
            await asyncio.sleep(0.1)
            ramping = self._temperature_controller.ramping
            if old_ramping and not ramping:
                return

    @setpoint.getter
    async def setpoint(self, instance):
        return self._temperature_controller.setpoint

    @setpoint.putter
    @no_reentry
    async def setpoint(self, instance, value):

        if not instance.ev.is_set():
            await instance.ev.wait()
            return self._temperature_controller.setpoint

        instance.ev.clear()
        try:
            self._temperature_controller.setpoint = value
            await wait_for_completion()
        finally:
            instance.ev.set()
        return self._temperature_controller.setpoint

    @setpoint.startup
    async def setpoint(self, instance, async_lib):
        instance.async_lib = async_lib
        instance.ev = async_lib.Event()
        instance.ev.set()

    feedback = pvproperty(
        value=100, dtype=float, name="feedback", doc="temperature feedback"
    )

    @feedback.getter
    async def feedback(self, instance):
        return self._temperature_controller.feedback

    output = pvproperty(value=100, dtype=float, name="output", doc="output value")

    @output.getter
    async def output(self, instance):
        return self._temperature_controller.output


if __name__ == "__main__":
    ioc_options, run_options = ioc_arg_parser(
        default_prefix="Lakeshore336Sim:", desc="Lakeshore336Sim IOC"
    )
    ioc = Lakeshore336Sim(**ioc_options)
    print("PVs:", list(ioc.pvdb))
    run(ioc.pvdb, **run_options)
