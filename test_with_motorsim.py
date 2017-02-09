import caproto as ca
import socket


CA_REPEATER_PORT = 5065
pv = "XF:31IDA-OP{Tbl-Ax:X1}Mtr"


sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
send_bcast = lambda msg: sock.sendto(bytes(msg), ('', CA_REPEATER_PORT))
recv_bcast = lambda: sock.recvfrom(4096)

# Send data
ip = socket.gethostbyname(socket.gethostname())
reg_command = ca.RepeaterRegisterRequest(ip)
print("Sending", reg_command)
send_bcast(reg_command)

# Receive response
print('waiting to receive')
data, address = recv_bcast()
print('received "%s"' % data)
