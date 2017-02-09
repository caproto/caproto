import socket


CA_REPEATER_PORT = 5065
pv = "XF:31IDA-OP{Tbl-Ax:X1}Mtr"


sbcast_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,
                            socket.IPPROTO_UDP)
sbcast_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
send_bcast = lambda msg: sock.sendto(msg, ('', CA_REPEATER_PORT))

rbcast_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,
                            socket.IPPROTO_UDP)
rbcast_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
rbcast_sock.bind(('', CA_REPEATER_PORT))
mreq = struct.pack("4sl", socket.inet_aton(MCAST_GRP), socket.INADDR_ANY)
rbcast_sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

recv_bcast = lambda: rbcast_sock.recv(10240)
