import caproto as ca
import time
import socket
import getpass


OUR_HOSTNAME = socket.gethostname()
OUR_USERNAME = getpass.getuser()
CA_REPEATER_PORT = 5065
CA_SERVER_PORT = 5064

# Broadcaster and Hub
b = ca.Broadcaster(our_role=ca.CLIENT)
b.log.setLevel('DEBUG')
cli = ca.Hub(our_role=ca.CLIENT)
cli.log.setLevel('DEBUG')

# UDP socket to CA repeater
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
send_bcast = lambda msg: sock.sendto(bytes(msg), ('', CA_REPEATER_PORT))
recv_bcast = lambda: sock.recvfrom(4096)

# Send data
command = b.register()
bytes_to_send = b.send(command)
send_bcast(bytes_to_send)

# Receive response
bytes_received, address = recv_bcast()
b.recv(bytes_received, address)
command = b.next_command()
assert type(command) is ca.RepeaterConfirmResponse
sock.close()

# UDP socket broadcasting to CA servers
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
send_bcast = lambda msg: sock.sendto(bytes(msg), ('', CA_SERVER_PORT))
recv_bcast = lambda: sock.recvfrom(4096)

# Search
pv1 = "XF:31IDA-OP{Tbl-Ax:X1}Mtr.VAL"
commands = b.search(pv1)
bytes_to_send = b.send(*commands)
send_bcast(bytes_to_send)
bytes_received, address = recv_bcast()
b.recv(bytes_received, address)
command = b.next_command()
assert type(command) is ca.VersionResponse
command = b.next_command()
assert type(command) is ca.SearchResponse

# Create an Channel. This implicitly creates a VirtualCircuit too.
chan1 = cli.new_channel(pv1, address=ca.extract_address(command), priority=0)

# Make a dict to hold our TCP sockets.
sockets = {}  # maps (address, priority) to a socket

def send(circuit, command):
    """
    Combine the caproto processing with the socket I/O.
    """
    bytes_to_send = circuit.send(command)
    key = circuit.key
    # circuit.key is (address, priority), which uniquely identifies a Channel
    # Access 'VirtualCircuit'. We have to open one socket per VirtualCircuit.
    if key not in sockets:
        sockets[key] = socket.create_connection(circuit.address)
    sockets[key].send(bytes_to_send)

def recv(circuit):
    """Combine the caproto processing with the socket I/O."""
    bytes_received = sockets[circuit.key].recv(4096)
    circuit.recv(bytes_received)


send(*chan1.version())
recv(chan1.circuit)
command = chan1.circuit.next_command()
assert type(command) is ca.VersionResponse
send(*chan1.host_name())
send(*chan1.client_name())
send(*chan1.create())
recv(chan1.circuit)
command = chan1.circuit.next_command()
assert type(command) is ca.AccessRightsResponse
command = chan1.circuit.next_command()
assert type(command) is ca.CreateChanResponse

_, event_req = chan1.subscribe()

send(chan1.circuit, event_req)
subscriptionid = event_req.subscriptionid
recv(chan1.circuit)
command = chan1.circuit.next_command()
assert type(command) is ca.EventAddResponse

try:
    print('Monitoring until Ctrl-C is hit')
    while True:
        recv(chan1.circuit)
        command = chan1.circuit.next_command()
        assert type(command) is ca.EventAddResponse
except KeyboardInterrupt:
    pass


_, cancel_req = chan1.unsubscribe(subscriptionid)

send(chan1.circuit, cancel_req)
recv(chan1.circuit)
command = chan1.circuit.next_command()
assert type(command) is ca.EventAddResponse

send(*chan1.read(data_count=3, data_type=15))
recv(chan1.circuit)
command = chan1.circuit.next_command()
assert type(command) is ca.ReadNotifyResponse
print(repr(ca.to_builtin(command.values, command.data_type,
                         command.data_count)))
send(*chan1.write((3,)))
recv(chan1.circuit)
command = chan1.circuit.next_command()
assert type(command) is ca.WriteNotifyResponse
time.sleep(2)
send(*chan1.read())
recv(chan1.circuit)
command = chan1.circuit.next_command()
assert type(command) is ca.ReadNotifyResponse
send(*chan1.clear())
recv(chan1.circuit)

for sock in sockets.values():
    sock.close()
