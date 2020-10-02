from pathlib import Path
import pytest

pytest.importorskip('dpkt')


data_dir = Path(__file__).parent / 'data'

# Smoke tests that push pcap data captured during search, create, read, write,
# subscribe, cancel, and clear.


def test_tcp_traffic():
    from ..sync.shark import shark

    # tcpdump -U -w example_tcp_data.pcap port <TCP PORT>
    with open(data_dir / 'example_tcp_data.pcap', 'rb') as file:
        list(shark(file))


def test_udp_traffic():
    from ..sync.shark import shark
    # tcpdump -U -w example_udp_data.pcap port 5064
    with open(data_dir / 'example_udp_data.pcap', 'rb') as file:
        list(shark(file))
