import caproto as ca
import time
import socket
import getpass


CA_REPEATER_PORT = 5065
CA_SERVER_PORT = 5064
pv1 = "XF:31IDA-OP{Tbl-Ax:X1}Mtr.VAL"
ip = '127.0.0.1'

# Make a Hub and a Broadcaster.
b = ca.Broadcaster(our_role=ca.CLIENT)
b.log.setLevel('DEBUG')
cli = ca.Hub(our_role=ca.CLIENT)
cli.log.setLevel('DEBUG')


# A broadcast socket to CA Repeater and convenience functions for send/recv.
repeater_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
repeater_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
send_to_repeater = lambda msg: repeater_sock.sendto(msg, ('', CA_REPEATER_PORT))
recv_from_repeater = lambda: repeater_sock.recvfrom(4096)

# A broadcast socket to CA servers and convenience functions for send/recv.
udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
udp_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
send_bcast = lambda msg: udp_sock.sendto(msg, ('', CA_SERVER_PORT))
recv_bcast = lambda: udp_sock.recvfrom(4096)

unanswered_searches = {}
search_results = {}

# Register with the repeater.
bytes_to_send = b.send(ca.RepeaterRegisterRequest(ip))
send_to_repeater(bytes_to_send)

# Receive response
data, address = recv_from_repeater()
b.recv(data, address)
b.next_command()

# Search for pv1.
# CA requires us to send a VersionRequest and a SearchRequest bundled into
# one datagram.
bytes_to_send = b.send(ca.VersionRequest(0, 13), ca.SearchRequest(pv1, 0, 13))
send_bcast(bytes_to_send)
print('searching for %s' % pv1)
# Receive a VersionResponse and SearchResponse.
bytes_received, address = recv_bcast()
b.recv(bytes_received, address)
command = b.next_command()
assert type(command) is ca.VersionResponse
command = b.next_command()
assert type(command) is ca.SearchResponse
search_results[pv1] = ca.extract_address(command)

chan1 = cli.new_channel(name=pv1, address=search_results[pv1], priority=0)
# Make a dict to hold our tcp sockets.
sockets = {}
sockets[chan1.circuit] = socket.create_connection(chan1.circuit.address)

# Convenience functions that lump together caproto stuff with socket stuff.
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

chan1.create()

# Initialize our new TCP-based CA connection with a VersionRequest.
send(chan1.circuit, ca.VersionRequest(priority=0, version=13))
recv(chan1.circuit)
# Send info about us.
send(chan1.circuit, ca.HostNameRequest('localhost'))
send(chan1.circuit, ca.ClientNameRequest('username'))
send(chan1.circuit, ca.CreateChanRequest(name=pv1, cid=chan1.cid, version=13))
commands = recv(chan1.circuit)

# Test subscriptions.
_, event_req = chan1.subscribe()

send(chan1.circuit, event_req)
subscriptionid = event_req.subscriptionid
commands, = recv(chan1.circuit)

try:
    print('Monitoring until Ctrl-C is hit. Meanwhile, use caput to change '
          'the value and watch for commands to arrive here.')
    while True:
        commands, = recv(chan1.circuit)
except KeyboardInterrupt:
    pass


_, cancel_req = chan1.unsubscribe(subscriptionid)

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

sockets[chan1.circuit].close()
udp_sock.close()
