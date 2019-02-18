from dpkt.pcap import Reader
from dpkt.ethernet import Ethernet
from dpkt.tcp import TCP
from dpkt.udp import UDP
from socket import inet_ntoa
import sys
from types import SimpleNamespace


from .. import NEED_DATA, CLIENT, SERVER
from .._commands import read_from_bytestream, read_datagram


def shark(file):
    """
    Parse tcpdump output.::

        sudo tcpdump -U -w - port <PORT> | caproto-shark

    """
    while True:
        for timestamp, buffer in Reader(file):
            ethernet = Ethernet(buffer)
            ip = ethernet.data
            transport = ip.data
            if isinstance(transport, TCP):
                if transport.dport == 5064:
                    role = CLIENT
                else:
                    role = SERVER
                print('role', role)
                data = bytearray(transport.data)
                while True:
                    data, command, _ = read_from_bytestream(data, role)
                    if command is NEED_DATA:
                        break
                    yield SimpleNamespace(timestamp=timestamp,
                                          ethernet=ethernet,
                                          src=inet_ntoa(ip.src),
                                          dst=inet_ntoa(ip.dst),
                                          ip=ip,
                                          transport=transport,
                                          role=role,
                                          command=command)
            if isinstance(transport, UDP):
                if transport.dport == 5064:
                    role = CLIENT
                else:
                    role = SERVER
                address = inet_ntoa(ip.src)
                for command in read_datagram(transport.data, address, role):
                    yield SimpleNamespace(timestamp=timestamp,
                                            ethernet=ethernet,
                                            src=inet_ntoa(ip.src),
                                            dst=inet_ntoa(ip.dst),
                                            ip=ip,
                                            transport=transport,
                                            role=role,
                                            command=command)
