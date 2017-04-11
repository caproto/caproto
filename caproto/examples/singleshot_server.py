import caproto as ca
import epics
import time
import socket
import getpass


OUR_HOSTNAME = socket.gethostname()
OUR_USERNAME = getpass.getuser()
CA_REPEATER_PORT = 5065
CA_SERVER_PORT = 5064
pv1 = "XF:31IDA-FAKE-PV"

b = ca.Broadcaster(our_role=ca.SERVER)
b.log.setLevel('DEBUG')

tcp_address = ('0.0.0.0', CA_SERVER_PORT)
# Create a UDP socket
udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
udp_sock.bind(('0.0.0.0', 5064))

sock3 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock3.bind(tcp_address)

print('Waiting to receive message')
data, client_udp_address = udp_sock.recvfrom(1024)

b.recv(data, client_udp_address)
command = b.next_command()
assert type(command) is ca.VersionRequest
command = b.next_command()
assert type(command) is ca.SearchRequest

res1 = ca.VersionResponse(13)
h, p = tcp_address
response = ca.SearchResponse(CA_SERVER_PORT, '255.255.255.255', 1, 13)
bytes_to_send = b.send(res1, response)
sent = udp_sock.sendto(bytes_to_send, client_udp_address)

print('Waiting to accept TCP')
sock3.listen(1)
connection, client_address = sock3.accept()
print('Accepted TCP')

sock3.close()

# # Make a dict to hold our tcp sockets.
sockets = {}
def send(circuit, command):
    bytes_to_send = circuit.send(command)
    connection.sendall(bytes_to_send)

def recv(circuit):
    bytes_received = connection.recv(4096)
    circuit.recv(bytes_received)
    commands = []
    while True:
        command = circuit.next_command()
        if type(command) is ca.NEED_DATA:
            break
        commands.append(command)
    return commands

# First receive directly into the circuit.
print('initial receipt')
bytes_received = connection.recv(4096)
circuit = ca.VirtualCircuit(our_role=ca.SERVER,
                         address=client_address,
                         priority=None)
circuit.log.setLevel('DEBUG')
circuit.recv(bytes_received)
circuit.next_command()
circuit.next_command()
circuit.next_command()
circuit.next_command()
print('normal operation')
bytes_to_send = circuit.send(ca.VersionResponse(13),
                           ca.AccessRightsResponse(cid=1, access_rights=3),
                           ca.CreateChanResponse(data_type=2, data_count=1, cid=1, sid=1))
connection.sendall(bytes_to_send)
recv(circuit)
circuit.next_command()
send(circuit, ca.ReadNotifyResponse((3.14,), 2, 1, 1, 1))
recv(circuit)
print(circuit.next_command())
send(circuit, ca.ClearChannelResponse(1, 1))
