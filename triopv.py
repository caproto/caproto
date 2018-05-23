import time
from caproto.trio.triothreads import PV

if True:
    pvs = [PV(name) for name in ['Py:ao1', 'Py:ao2', 'Py:ao3']]
    [pv.wait_for_connection(5) for pv in pvs]
    print([pv.get() for pv in pvs])

    def callback(pvname, value, **kwargs):
        print('callback', pvname, value)

    [pv.add_callback(callback) for pv in pvs]
    time.sleep(2)
    [pv._caproto_pv.unsubscribe(list(pv._caproto_pv._subscriptions)[0]) for pv in pvs]
else:
    pv = PV('Py:ao3')
    pv.wait_for_connection(5)
    print(pv.get())

    def callback(value, **kwargs):
        print('callback', value)

    pv.add_callback(callback)
    time.sleep(2)
    pv._caproto_pv.unsubscribe(0)
