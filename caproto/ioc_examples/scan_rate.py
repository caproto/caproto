#!/usr/bin/env python3
import time
import logging
from caproto.server import pvproperty, PVGroup, ioc_arg_parser, run


logger = logging.getLogger('caproto')


class MyPVGroup(PVGroup):
    # This pvproperty mocks an analog input (ai) record.
    scanned = pvproperty(value=[0.0], mock_record='ai')

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


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='periodic:',
        desc='Use the .SCAN field of a record',
        macros=dict(macro='expanded'))

    ioc = MyPVGroup(**ioc_options)
    run(ioc.pvdb, **run_options)
