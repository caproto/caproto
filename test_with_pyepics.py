import caproto as ca
import epics
import time
import socket
import getpass


OUR_HOSTNAME = socket.gethostname()
OUR_USERNAME = getpass.getuser()
our_ip = socket.gethostbyname(socket.gethostname())
print('our_ip', our_ip)
CA_REPEATER_PORT = 5065
CA_SERVER_PORT = 5064
pv1 = "XF:31IDA-FAKE-PV"

udp_address = ('192.168.1.255', CA_SERVER_PORT)  # obtained via tshark
tcp_address = (our_ip, CA_SERVER_PORT)
# Create a UDP socket
sock2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock2.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock2.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(udp_address)

sock3 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock3.bind(tcp_address)

srv = ca.Hub(our_role=ca.SERVER)

print('\nwaiting to receive message')
data, client_udp_address = sock.recvfrom(1024)

print('received %s bytes from %s' % (len(data), client_udp_address))
print(data)
srv.recv_broadcast(data, client_udp_address)
print('datagram', data, client_udp_address)
command = srv.next_command()
print('received', command)
command = srv.next_command()
print('received', command)

res1 = ca.VersionResponse(0)
h, p = tcp_address
print("HOST", h)
response = ca.SearchResponse(CA_SERVER_PORT, h, command.cid,
                             ca.DEFAULT_PROTOCOL_VERSION)
bytes_to_send = srv.send_broadcast(res1, response)
sent = sock2.sendto(bytes_to_send, client_udp_address)
print('sent %s bytes back to %s' % (sent, client_udp_address))

print('waiting to accept')
sock3.listen(1)
connection, client_address = sock3.accept()
print('accepted')


# # Make a dict to hold our tcp sockets.
sockets = {}
def send(proxy, command):
    print('sending', command)
    bytes_to_send = circuit.send(command)
    connection.sendall(bytes_to_send)

def recv(proxy):
    circuit = proxy.circuit
    bytes_received = connection.recv(4096)
    print('received', len(bytes_received), 'bytes')
    circuit.recv(bytes_received)
    commands = []
    while True:
        command = circuit.next_command()
        if type(command) is ca.NEED_DATA:
            break
        print('parsed', command)
        commands.append(command)
    return commands

# First receive directly into the proxy.
print('initial receipt')
bytes_received = connection.recv(4096)
print('received', len(bytes_received), 'bytes')
print(bytes_received)
# TODO Unify VirtualCircuit Client/Server.
proxy = ca.ServerVirtualCircuitProxy(srv, client_address[0])
proxy.recv(bytes_received)
ver_com = proxy.next_command()
print('parsed', ver_com)
assert type(ver_com) is ca.VersionRequest
bytes_to_send = proxy.send(ca.VersionResponse(13))
connection.sendall(bytes_to_send)

print(proxy.bound)
print('parsed', proxy.next_command())
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
    print("HELLO")
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
print('will send response', read_res)
bytes_to_send = proxy.send(read_res)
connection.sendall(bytes_to_send)
print('sent')
recv(proxy)
