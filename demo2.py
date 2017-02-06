import socket
import os
import getpass


host = os.environ['DOCKER0_IP']
sock = socket.create_connection((host, 5064))

# Send CA_PROTO_VERSION and listen for the server's reply.
CLIENT_VERSION = 13
req = CA_PROTO_VERSION_REQ(priority=1, version=CLIENT_VERSION)
print(sock.sendall(bytes(req)))
response = MessageHeader()
sock.recv_into(response)
print('Server protocol version:', response.data_count)

# Announce hostname and username.
hostname = socket.gethostname()
header = bytes(CA_PROTO_HOST_NAME_REQ(len(hostname)))
payload = bytes(DBR_STRING(hostname.encode()))
print(sock.sendall(header + payload))
# There is no response.
username = getpass.getuser()
header = bytes(CA_PROTO_CLIENT_NAME_REQ(len(hostname)))
payload = bytes(DBR_STRING(hostname.encode()))
print(sock.sendall(header + payload))
# There is no response.

# Create a new channel
cid = 9
pv = "XF:31IDA-OP{Tbl-Ax:X1}Mtr"
header = CA_PROTO_SEARCH_REQ(25 * 8, 10, CLIENT_VERSION, 4)
# header = CA_PROTO_CREATE_CHAN_REQ(25 * 8, cid, CLIENT_VERSION)
payload = DBR_STRING(pv.encode())
print(header.command)
msg = bytes(header) + bytes(payload)
print(msg)
sock.sendall(msg)
print(sock.recv(1024))
