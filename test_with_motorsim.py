import caproto as ca
import socket
import getpass


OUR_HOSTNAME = socket.gethostname()
OUR_USERNAME = getpass.getuser()
CA_REPEATER_PORT = 5065
CA_SERVER_PORT = 5064
pv1 = "XF:31IDA-OP{Tbl-Ax:X1}Mtr.VAL"


sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
send_bcast = lambda msg: sock.sendto(bytes(msg), ('', CA_REPEATER_PORT))
recv_bcast = lambda: sock.recvfrom(4096)

# Send data
ip = socket.gethostbyname(socket.gethostname())
print('our ip', ip)
reg_command = ca.RepeaterRegisterRequest(ip)
print("Sending", reg_command)
send_bcast(reg_command)

# Receive response
print('waiting to receive')
data, address = recv_bcast()
print('received', ca.read_datagram(data, address, ca.SERVER))


sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
send_bcast = lambda msg: sock.sendto(bytes(msg), ('', CA_SERVER_PORT))
recv_bcast = lambda: sock.recvfrom(4096)

 
cli = ca.Connections(our_role=ca.CLIENT)
chan1 = cli.new_channel(pv1)
bytes_to_send = cli.send_broadcast(ca.VersionRequest(0, 13))
bytes_to_send += cli.send_broadcast(ca.SearchRequest(pv1, 0, 13))
print('searching for %s' % pv1)
send_bcast(bytes_to_send)
bytes_received, address = recv_bcast()
cli.recv_broadcast(bytes_received, address)
command = cli.next_command()
print('received', command)
command = cli.next_command()
print('received', command)

# Make a dict to hold our tcp sockets.
sockets = {}
sockets[chan1.circuit] = socket.create_connection(chan1.circuit.address)

def send(circuit, command):
    print('sending', command)
    bytes_to_send = circuit.send(command)
    sockets[circuit].send(bytes_to_send)

def recv(circuit):
    bytes_received = sockets[circuit].recv(4096)
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


send(chan1.circuit, ca.VersionRequest(priority=0, version=13))
recv(chan1.circuit)
send(chan1.circuit, ca.HostNameRequest(OUR_HOSTNAME))
send(chan1.circuit, ca.ClientNameRequest(OUR_USERNAME))
send(chan1.circuit, ca.CreateChanRequest(name=pv1, cid=chan1.cid, version=13))
recv(chan1.circuit)
try:
    send(chan1.circuit, ca.ReadNotifyRequest(data_type=2, data_count=1,
                                            sid=chan1.sid,
                                            ioid=1))
    bytes_received = sockets[chan1.circuit].recv(4096)
    raise Exception
    # recv(chan1.circuit)
    send(chan1.circuit, ca.ClearChannelRequest(chan1.sid, chan1.cid))
    recv(chan1.circuit)
finally:
    sock.close()
