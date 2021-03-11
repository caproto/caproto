#!/usr/bin/env python3
import logging
import time

from caproto.server import PVGroup, ioc_arg_parser, pvproperty, run

logger = logging.getLogger('caproto')


class ScanRateIOC(PVGroup):
    # This pvproperty mocks an analog input (ai) record.
    scanned = pvproperty(
        value=0.0,
        record='ai',
        doc="An analog input with customizable scan rate."
    )

    # The mocked record also happens to have the standard fields normally
    # associated with an EPICS record.  This is used here to tie in the
    # scanned.SCAN field with the period of the following loop:
    @scanned.scan(period=1, use_scan_field=True)
    async def scanned(self, instance, async_lib):
        if hasattr(self, 'last_time'):
            elapsed = time.time() - self.last_time
            print('Elapsed time since last scan:', elapsed)
            await instance.write(elapsed)
        self.last_time = time.time()

    # To try this example, use:
    #    $ caput periodic:scanned.SCAN '.5 second'
    #    $ camonitor periodic:scanned
    # This record should hold the time difference between consecutive calls due
    # to the `write` call above.  The timestamps shown by camonitor should be
    # close to this value, but not exact. To compare these, you can also try:
    #    $ camonitor -tsi periodic:scanned

    # As of caproto v0.7.2, you may also include a "startup" method along
    # with a "scan" method:
    @scanned.startup
    async def scanned(self, instance, async_lib):
        print(f"{instance.name} startup called.")


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='periodic:',
        desc='Use the .SCAN field of a record',
        macros=dict(macro='expanded'))

    ioc = ScanRateIOC(**ioc_options)
    run(ioc.pvdb, **run_options)
