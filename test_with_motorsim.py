import caproto as ca
import socket


CA_REPEATER_PORT = 5065
pv1 = "XF:31IDA-OP{Tbl-Ax:X1}Mtr"


sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
send_bcast = lambda msg: sock.sendto(bytes(msg), ('', CA_REPEATER_PORT))
recv_bcast = lambda: sock.recvfrom(4096)

# Send data
# ip = socket.gethostbyname(socket.gethostname())
ip = '127.0.0.1'
reg_command = ca.RepeaterRegisterRequest(ip)
print("Sending", reg_command)
send_bcast(reg_command)

# Receive response
print('waiting to receive')
data, address = recv_bcast()
print('received "%s"' % data)


cli = ca.Connections(our_role=ca.CLIENT)
chan1 = cli.new_channel(pv1)
bytes_to_send = cli.send_broadcast(ca.VersionRequest(0, 12))
bytes_to_send += cli.send_broadcast(ca.SearchRequest(pv1, 0, 12))
send_bcast(bytes_to_send)
print('searching for %s' % pv1)
send_bcast(bytes_to_send)
bytes_received, address = recv_bcast()
cli.recv_broadcast(bytes_received, address)
command = cli.next_command()
print('received', command)
