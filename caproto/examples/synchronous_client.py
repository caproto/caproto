import caproto as ca
import os
import time
import socket
import getpass


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
    bytes_to_send = circuit.send(command)
    sockets[circuit].send(bytes_to_send)

def recv(circuit):
    bytes_received = sockets[circuit].recv(4096)
    circuit.recv(bytes_received)
    commands = []
    while True:
        command = circuit.next_command()
        if type(command) is ca.NEED_DATA:
            break
        commands.append(command)
    return commands

def main():
    # A broadcast socket
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    # Register with the repeater.
    bytes_to_send = b.send(ca.RepeaterRegisterRequest('0.0.0.0'))
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
        udp_sock.sendto(bytes_to_send, (host, CA_SERVER_PORT))
    print('searching for %s' % pv1)
    # Receive a VersionResponse and SearchResponse.
    bytes_received, address = udp_sock.recvfrom(1024)
    b.recv(bytes_received, address)
    command = b.next_command()
    assert type(command) is ca.VersionResponse
    command = b.next_command()
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
    commands = []
    commands = recv(chan1.circuit)

    # Test subscriptions.
    assert chan1.native_data_type and chan1.native_data_count
    add_req = ca.EventAddRequest(data_type=chan1.native_data_type,
                                 data_count=chan1.native_data_count,
                                 sid=chan1.sid,
                                 subscriptionid=0,
                                 low=0, high=0, to=0, mask=1)
    send(chan1.circuit, add_req)
    subscriptionid = add_req.subscriptionid

    try:
        print('Monitoring until Ctrl-C is hit. Meanwhile, use caput to change '
              'the value and watch for commands to arrive here.')
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
                                            sid=chan1.sid,
                                            ioid=12))
    commands, = recv(chan1.circuit)

    # Test writing.
    request = ca.WriteNotifyRequest(data_type=2, data_count=1,
                                    sid=chan1.sid,
                                    ioid=13, values=(4,))

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
