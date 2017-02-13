import caproto as ca
import epics
import time
import socket
import getpass


OUR_HOSTNAME = socket.gethostname()
OUR_USERNAME = getpass.getuser()
OUR_IP = our_ip = '10.2.229.216'
CA_REPEATER_PORT = 5065
CA_SERVER_PORT = 5064
pv1 = "XF:31IDA-FAKE-PV"

tcp_address = ('0.0.0.0', CA_SERVER_PORT)
# Create a UDP socket
udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
udp_sock.bind(('0.0.0.0', 5064))

sock3 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock3.bind(tcp_address)

srv = ca.Hub(our_role=ca.SERVER)
srv.log.setLevel('DEBUG')

print('Waiting to receive message')
data, client_udp_address = udp_sock.recvfrom(1024)

srv.recv_broadcast(data, client_udp_address)
command = srv.next_command()
command = srv.next_command()

res1 = ca.VersionResponse(13)
h, p = tcp_address
response = ca.SearchResponse(CA_SERVER_PORT, OUR_IP, 1,
                             ca.DEFAULT_PROTOCOL_VERSION)
bytes_to_send = srv.send_broadcast(res1, response)
sent = udp_sock.sendto(bytes_to_send, client_udp_address)

print('Waiting to accept TCP')
sock3.listen(1)
connection, client_address = sock3.accept()
print('Accepted TCP')


# # Make a dict to hold our tcp sockets.
sockets = {}
def send(proxy, command):
    bytes_to_send = circuit.send(command)
    connection.sendall(bytes_to_send)

def recv(proxy):
    circuit = proxy.circuit
    bytes_received = connection.recv(4096)
    circuit.recv(bytes_received)
    commands = []
    while True:
        command = circuit.next_command()
        if type(command) is ca.NEED_DATA:
            break
        commands.append(command)
    return commands

# First receive directly into the proxy.
print('initial receipt')
bytes_received = connection.recv(4096)
# TODO Unify VirtualCircuit Client/Server.
proxy = ca.ServerVirtualCircuitProxy(srv, client_address[0])
proxy.recv(bytes_received)
ver_com = proxy.next_command()
assert type(ver_com) is ca.VersionRequest
bytes_to_send = proxy.send(ca.VersionResponse(13))
connection.sendall(bytes_to_send)

print(proxy.bound)
proxy.next_command()
print('normal operation')
bytes_to_send = proxy.send(ca.AccessRightsResponse(cid=1, access_rights=3))
connection.sendall(bytes_to_send)
bytes_to_send = proxy.send(ca.CreateChanResponse(data_type=1, data_count=1,
                                                 cid=1, sid=1))
connection.sendall(bytes_to_send)
#assert type(recv(proxy)[0]) is ca.ReadSyncRequest
#assert type(recv(proxy)[0]) is ca.ReadNotifyRequest
done = False
while not done:
    commands = recv(proxy)
    print(commands)
    for command in commands:
        print(command)
        if type(command) is ca.ReadNotifyRequest:
            done = True
            break
    if done:
        break
p = (19, 1, 1, 1, 0, 15)  # DBR_TIME_INT args
read_res = ca.ReadNotifyResponse(p, 15, 1, 1, 1)
bytes_to_send = proxy.send(read_res)
connection.sendall(bytes_to_send)
recv(proxy)
