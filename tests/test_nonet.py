import logging
from multiprocessing import Process
import caproto as ca
import os
import time
import socket
import getpass


pv1 = "synctest1"
cli_addr = ('127.0.0.1', 6666)
repeater_addr = ('127.0.0.1', 5065)

# Make a Broadcaster for the client and one for the server.
cli_b = ca.Broadcaster(our_role=ca.CLIENT)
srv_b = ca.Broadcaster(our_role=ca.SERVER)
cli_b.log.setLevel('DEBUG')
srv_b.log.setLevel('DEBUG')

req_cache = bytearray()
res_cache = bytearray()

def srv_send(circuit, command):
    buffers_to_send = circuit.send(command)
    for buffer in buffers_to_send:
        res_cache.extend(bytes(buffer))


def srv_recv(circuit):
    bytes_received = bytes(req_cache)
    req_cache.clear()
    circuit.recv(bytes_received)
    commands = []
    while True:
        command = circuit.next_command()
        if type(command) is ca.NEED_DATA:
            break
        commands.append(command)
    return commands


def cli_send(circuit, command):
    buffers_to_send = circuit.send(command)
    for buffer in buffers_to_send:
        req_cache.extend(bytes(buffer))


def cli_recv(circuit):
    bytes_received = bytes(res_cache)
    res_cache.clear()
    circuit.recv(bytes_received)
    commands = []
    while True:
        command = circuit.next_command()
        if type(command) is ca.NEED_DATA:
            break
        commands.append(command)
    return commands


def test_nonet():
    # Register with the repeater.
    bytes_to_send = cli_b.send(ca.RepeaterRegisterRequest('0.0.0.0'))

    # Receive response
    data = bytes(ca.RepeaterConfirmResponse('127.0.0.1'))
    cli_b.recv(data, cli_addr)
    cli_b.next_command()

    # Search for pv1.
    # CA requires us to send a VersionRequest and a SearchRequest bundled into
    # one datagram.
    bytes_to_send = cli_b.send(ca.VersionRequest(0, 13),
                               ca.SearchRequest(pv1, 0, 13))

    
    srv_b.recv(bytes_to_send, cli_addr)
    ver_req = srv_b.next_command()
    search_req = srv_b.next_command()
    bytes_to_send = srv_b.send(ca.VersionResponse(13),
                               ca.SearchResponse(5064, None,
                                                 search_req.cid, 13))

    # Receive a VersionResponse and SearchResponse.
    cli_b.recv(bytes_to_send, cli_addr)
    command = cli_b.next_command()
    assert type(command) is ca.VersionResponse
    command = cli_b.next_command()
    assert type(command) is ca.SearchResponse
    address = ca.extract_address(command)

    circuit = ca.VirtualCircuit(our_role=ca.CLIENT,
                                address=address,
                                priority=0)
    circuit.log.setLevel('DEBUG')
    chan1 = ca.ClientChannel(pv1, circuit)

    srv_circuit = ca.VirtualCircuit(our_role=ca.SERVER,
                                    address=address, priority=None)

    cli_send(chan1.circuit, ca.VersionRequest(priority=0, version=13))
    srv_recv(srv_circuit)
    srv_send(srv_circuit, ca.VersionResponse(version=13))
    cli_recv(chan1.circuit)
    cli_send(chan1.circuit, ca.HostNameRequest('localhost'))
    cli_send(chan1.circuit, ca.ClientNameRequest('username'))
    cli_send(chan1.circuit, ca.CreateChanRequest(name=pv1, cid=chan1.cid,
                                                 version=13))
    srv_recv(srv_circuit)
    srv_send(srv_circuit, ca.CreateChanResponse(cid=chan1.cid, sid=1,
                                                data_type=5, data_count=1))
    cli_recv(chan1.circuit)

    # Test subscriptions.
    assert chan1.native_data_type and chan1.native_data_count
    add_req = ca.EventAddRequest(data_type=chan1.native_data_type,
                                 data_count=chan1.native_data_count,
                                 sid=chan1.sid,
                                 subscriptionid=0,
                                 low=0, high=0, to=0, mask=1)
    cli_send(chan1.circuit, add_req)
    srv_recv(srv_circuit)
    subscriptionid = add_req.subscriptionid
    add_res = ca.EventAddResponse(data=(3,),
                                  data_type=chan1.native_data_type,
                                  data_count=chan1.native_data_count,
                                  subscriptionid=0,
                                  status_code=1)

    srv_send(srv_circuit, add_res)
    cli_recv(chan1.circuit)

    cancel_req = ca.EventCancelRequest(data_type=add_req.data_type,
                                       sid=add_req.sid,
                                       subscriptionid=add_req.subscriptionid)

    cli_send(chan1.circuit, cancel_req)
    srv_recv(srv_circuit)
    cli_recv(chan1.circuit)

    # Test reading.
    cli_send(chan1.circuit, ca.ReadNotifyRequest(data_type=5, data_count=1,
                                            sid=chan1.sid,
                                            ioid=12))
    srv_recv(srv_circuit)
    srv_send(srv_circuit, ca.ReadNotifyResponse(data=(3,),
                                                data_type=5, data_count=1,
                                                ioid=12, status=1))
    commands, = cli_recv(chan1.circuit)

    # Test writing.
    request = ca.WriteNotifyRequest(data_type=2, data_count=1,
                                    sid=chan1.sid,
                                    ioid=13, data=(4,))

    cli_send(chan1.circuit, request)
    srv_recv(srv_circuit)
    srv_send(srv_circuit, ca.WriteNotifyResponse(data_type=5, data_count=1,
                                                 ioid=13, status=1))
    cli_recv(chan1.circuit)

    # Test "clearing" (closing) the channel.
    cli_send(chan1.circuit, ca.ClearChannelRequest(chan1.sid, chan1.cid))
    srv_recv(chan1.circuit)

