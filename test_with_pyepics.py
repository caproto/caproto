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
proxy = ca.ServerVirtualCircuitProxy(srv, client_address[0])
proxy.recv(bytes_received)
print('parsed', proxy.next_command())
print('normal operation')
recv(proxy)
recv(proxy)
recv(proxy)

#
# sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
# sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
# send_bcast = lambda msg: sock.sendto(bytes(msg), ('', CA_SERVER_PORT))
# recv_bcast = lambda: sock.recvfrom(4096)
#
# # Send data
# ip = socket.gethostbyname(socket.gethostname())
# print('our ip', ip)
# reg_command = ca.RepeaterRegisterRequest(ip)
# print("Sending", reg_command)
# send_bcast(reg_command)
#
# # Receive response
# print('waiting to receive')
# data, address = recv_bcast()
# print('received', ca.read_datagram(data, address, ca.SERVER))
# sock.close()
#
#
# sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
# sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
# send_bcast = lambda msg: sock.sendto(bytes(msg), ('', CA_SERVER_PORT))
# recv_bcast = lambda: sock.recvfrom(4096)
#
#
# cli = ca.Hub(our_role=ca.CLIENT)
# chan1 = cli.new_channel(pv1)
# bytes_to_send = cli.send_broadcast(ca.VersionRequest(0, 13))
# bytes_to_send += cli.send_broadcast(ca.SearchRequest(pv1, 0, 13))
# print('searching for %s' % pv1)
# send_bcast(bytes_to_send)
# bytes_received, address = recv_bcast()
# cli.recv_broadcast(bytes_received, address)
# command = cli.next_command()
# print('received', command)
# command = cli.next_command()
# print('received', command)
#
#
# send(chan1.circuit, ca.VersionRequest(priority=0, version=13))
# recv(chan1.circuit)
# send(chan1.circuit, ca.HostNameRequest(OUR_HOSTNAME))
# send(chan1.circuit, ca.ClientNameRequest(OUR_USERNAME))
# send(chan1.circuit, ca.CreateChanRequest(name=pv1, cid=chan1.cid, version=13))
# recv(chan1.circuit)
# send(chan1.circuit, ca.ReadNotifyRequest(data_type=2, data_count=1,
#                                         sid=chan1.sid,
#                                         ioid=12))
# commands, = recv(chan1.circuit)
# print(commands.values.value)
# request = ca.WriteNotifyRequest(data_type=2, data_count=1,
#                                 sid=chan1.sid,
#                                 ioid=13, values=3)
#
# send(chan1.circuit, request)
# recv(chan1.circuit)
# time.sleep(2)
# send(chan1.circuit, ca.ReadNotifyRequest(data_type=2, data_count=1,
#                                          sid=chan1.sid,
#                                          ioid=14))
# recv(chan1.circuit)
# print(commands.values.value)
# send(chan1.circuit, ca.ClearChannelRequest(chan1.sid, chan1.cid))
# recv(chan1.circuit)
#
# sockets[chan1.circuit].close()
# sock.close()
