"""
Test that the pytest fixtures themselves are functioning.
"""


def test_ioc(ioc):
    print(f'This is a {ioc.type} IOC. Process={ioc.process}')
    print(f'Name: {ioc.name}')
    print(f'Available PVs: {ioc.pvs.items()}')
