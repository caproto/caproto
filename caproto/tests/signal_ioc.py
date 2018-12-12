#!/usr/bin/env python3
from caproto.server import pvproperty, PVGroup, ioc_arg_parser, run


class SignalTestIOC(PVGroup):
    read_only = pvproperty(value=0.0, read_only=True, alarm_group='alarm_a')
    read_write = pvproperty(value=0.0,
                            lower_ctrl_limit=-100.0,
                            upper_ctrl_limit=100.0,
                            alarm_group='alarm_a')

    pair_rbv = pvproperty(value=0.0, read_only=True, alarm_group='alarm_a')
    pair_set = pvproperty(value=0.0,
                          lower_ctrl_limit=-100.0,
                          upper_ctrl_limit=100.0,
                          alarm_group='alarm_a')

    @pair_set.putter
    async def pair_set(self, instance, value):
        await self.pair_rbv.write(value=value)

    waveform = pvproperty(value=[ord('a'), ord('b'), ord('c')], read_only=True,
                          alarm_group='alarm_a')
    bool_enum = pvproperty(value=True, alarm_group='alarm_a')
    alarm_status = pvproperty(value=0)
    set_severity = pvproperty(value=0)

    @set_severity.putter
    async def set_severity(self, instance, severity):
        await self.read_only.alarm.write(
            severity=severity, status=self.alarm_status.value)


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='signal_tests:',
        desc="ophyd.tests.test_signal test IOC")
    ioc = SignalTestIOC(**ioc_options)
    run(ioc.pvdb, **run_options)
