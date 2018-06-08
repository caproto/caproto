"""
Test that the pytest fixtures themselves are functioning.
"""
from caproto.sync.client import read


def test_ioc(ioc):
    print(f'This is a {ioc.type} IOC. Process={ioc.process}')
    print(f'Name: {ioc.name}')
    print(f'Available PVs: {ioc.pvs.items()}')
    if ioc.type == 'epics-base':
        read(f'{ioc.prefix}ao1')  # test a PV from the pyepics 'debug' IOC
