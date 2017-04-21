import os
import caproto as ca


def test_broadcast_address_list_from_interfaces():
    # Smoke test broadcast_address_list_from_interfaces by setting the right
    # env vars and calling get_address_list.
    env = os.environ.copy()
    try:
        os.environ['EPICS_CA_AUTO_ADDR_LIST'] = 'YES'
        ca.get_address_list()
    finally:
        os.environ = env
