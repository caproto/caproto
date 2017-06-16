import caproto as ca
import time
import socket


CA_REPEATER_PORT = 5065
CA_SERVER_PORT = 5064
pv1 = "XF:31IDA-OP{Tbl-Ax:X1}Mtr.VAL"
ip = '127.0.0.1'

# Make a Broadcaster.
b = ca.Broadcaster(our_role=ca.CLIENT)
b.log.setLevel('DEBUG')

# Make a dict to hold our tcp sockets.
sockets = {}


# Convenience functions that do both transport caproto validation/ingest.
def send(circuit, command):
    buffers_to_send = circuit.send(command)
    sockets[circuit].sendmsg(buffers_to_send)


def recv(circuit):
    bytes_received = sockets[circuit].recv(4096)
    circuit.recv(bytes_received)
    commands = []
    while True:
        command = circuit.next_command()
        commands.append(command)
        if circuit.backlog == 0:
            break
    return commands


def main(*, skip_monitor_section=False):
    # A broadcast socket
    udp_sock = ca.bcast_socket()

    # Register with the repeater.
    bytes_to_send = b.send(ca.RepeaterRegisterRequest('0.0.0.0'))

    # TODO: for test environment with specific hosts listed in 
    # EPICS_CA_ADDR_LIST
    if True:
        fake_reg = (('127.0.0.1', ca.EPICS_CA1_PORT),
                    [ca.RepeaterConfirmResponse(
                        repeater_address='127.0.0.1')]
                    )
        b.command_queue.put(fake_reg)
    else:
        udp_sock.sendto(bytes_to_send, ('', CA_REPEATER_PORT))

        # Receive response
        data, address = udp_sock.recvfrom(1024)
        b.recv(data, address)

    b.next_command()

    # Search for pv1.
    # CA requires us to send a VersionRequest and a SearchRequest bundled into
    # one datagram.
    bytes_to_send = b.send(ca.VersionRequest(0, 13),
                           ca.SearchRequest(pv1, 0, 13))
    for host in ca.get_address_list():
        if ':' in host:
            host, _, specified_port = host.partition(':')
            udp_sock.sendto(bytes_to_send, (host, int(specified_port)))
        else:
            udp_sock.sendto(bytes_to_send, (host, CA_SERVER_PORT))
    print('searching for %s' % pv1)
    # Receive a VersionResponse and SearchResponse.
    bytes_received, address = udp_sock.recvfrom(1024)
    b.recv(bytes_received, address)
    addr, command = b.next_command()
    assert type(command) is ca.VersionResponse
    addr, command = b.next_command()
    assert type(command) is ca.SearchResponse
    address = ca.extract_address(command)

    circuit = ca.VirtualCircuit(our_role=ca.CLIENT,
                                address=address,
                                priority=0)
    circuit.log.setLevel('DEBUG')
    chan1 = ca.ClientChannel(pv1, circuit)
    sockets[chan1.circuit] = socket.create_connection(chan1.circuit.address)

    # Initialize our new TCP-based CA connection with a VersionRequest.
    send(chan1.circuit, ca.VersionRequest(priority=0, version=13))
    recv(chan1.circuit)
    # Send info about us.
    send(chan1.circuit, ca.HostNameRequest('localhost'))
    send(chan1.circuit, ca.ClientNameRequest('username'))
    send(chan1.circuit, ca.CreateChanRequest(name=pv1, cid=chan1.cid,
                                             version=13))
    commands = recv(chan1.circuit)

    # Test subscriptions.
    assert chan1.native_data_type and chan1.native_data_count
    add_req = ca.EventAddRequest(data_type=chan1.native_data_type,
                                 data_count=chan1.native_data_count,
                                 sid=chan1.sid,
                                 subscriptionid=0,
                                 low=0, high=0, to=0, mask=1)
    send(chan1.circuit, add_req)

    commands = recv(chan1.circuit)

    if not skip_monitor_section:
        try:
            print('Monitoring until Ctrl-C is hit. Meanwhile, use caput to '
                  'change the value and watch for commands to arrive here.')
            while True:
                commands = recv(chan1.circuit)
                if commands:
                    print(commands)
        except KeyboardInterrupt:
            pass

    cancel_req = ca.EventCancelRequest(data_type=add_req.data_type,
                                       sid=add_req.sid,
                                       subscriptionid=add_req.subscriptionid)

    send(chan1.circuit, cancel_req)
    commands, = recv(chan1.circuit)

    # Test reading.
    send(chan1.circuit, ca.ReadNotifyRequest(data_type=2, data_count=1,
                                             sid=chan1.sid, ioid=12))
    commands, = recv(chan1.circuit)

    # Test writing.
    request = ca.WriteNotifyRequest(data_type=2, data_count=1,
                                    sid=chan1.sid,
                                    ioid=13, data=(4,))

    send(chan1.circuit, request)
    recv(chan1.circuit)
    time.sleep(2)
    send(chan1.circuit, ca.ReadNotifyRequest(data_type=2, data_count=1,
                                             sid=chan1.sid,
                                             ioid=14))
    recv(chan1.circuit)

    # Test "clearing" (closing) the channel.
    send(chan1.circuit, ca.ClearChannelRequest(chan1.sid, chan1.cid))
    recv(chan1.circuit)

    sockets.pop(chan1.circuit).close()
    udp_sock.close()


if __name__ == '__main__':
    main()
