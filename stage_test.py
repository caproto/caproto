from ophyd import Device, Component as Cpt, EpicsSignal
import ophyd

# ensure using: klauer/ophyd@load_cl for this test

pe = ophyd.load_cl('pyepics', False)
ca = ophyd.load_cl('caproto', False)

class TesterPyepics(Device):
   a = Cpt(EpicsSignal, 'mtr1.OFF', cl=pe)
   b = Cpt(EpicsSignal, 'mtr2.OFF', cl=pe)

class TesterCaproto(Device):
   a = Cpt(EpicsSignal, 'mtr1.OFF', cl=ca)
   b = Cpt(EpicsSignal, 'mtr2.OFF', cl=ca)


tc = TesterCaproto('sim:', name='tc')
tc.stage_sigs['a'] = 1
tc.stage_sigs['b'] = 1

tp = TesterPyepics('sim:', name='tp')
tp.stage_sigs['a'] = 1
tp.stage_sigs['b'] = 1


if False:
    import IPython.core.getipython
    ipython = IPython.core.getipython.get_ipython()

    print('pyepics')
    ipython.magic("%timeit tp.stage(); tp.unstage()")
    print('caproto')
    ipython.magic("%timeit tc.stage(); tc.unstage()")
else:
    import logging
    # logging.getLogger('caproto').setLevel('DEBUG')
    for i in range(10):
        tc.stage(); tc.unstage()
    from caproto.threading.util import show_wait_times
    show_wait_times(0.01)
