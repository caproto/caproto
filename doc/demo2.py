from caproto import *
import time
import socket
import os
import getpass
import math

def padded_len(s):
    return 8 * math.ceil(len(s) / 8)
    

host = 'localhost'
port = 5064
sock = socket.create_connection((host, port))

# Send CA_PROTO_VERSION and listen for the server's reply.
CLIENT_VERSION = 13
req = VersionRequest(priority=1, version=CLIENT_VERSION)
print(sock.sendall(bytes(req)))
response1 = MessageHeader()
sock.recv_into(response1)
print('Server protocol version:', response1.data_count)

# Announce hostname and username.
hostname = socket.gethostname()
pl = padded_len(hostname)
header = bytes(HostNameRequestHeader(pl))
payload = bytes(DBR_STRING(hostname.encode()))[:pl]
print(sock.sendall(header + payload))
# There is no response.
username = getpass.getuser()
header = bytes(ClientNameRequestHeader(pl))
pl = padded_len(hostname)
payload = bytes(DBR_STRING(hostname.encode()))[:pl]
print(sock.sendall(header + payload))
# There is no response.

# Create a new channel
try:
    cid += 1
except NameError:
    cid = 1
pv = "XF:31IDA-OP{Tbl-Ax:X1}Mtr.VAL"
pl = padded_len(pv)
header = SearchRequestHeader(pl, 10, CLIENT_VERSION, cid)
payload = DBR_STRING(pv.encode())
msg = bytes(header) + bytes(payload)[:pl]
sock.sendall(msg)
response2 = MessageHeader()
sock.recv_into(response2)
print('response command:', response2.command)

print(cid == response2.parameter2)
# sample payload as previous
header = CreateChanRequestHeader(pl, cid, CLIENT_VERSION)
msg = bytes(header) + bytes(payload)[:pl]
print(msg)
sock.sendall(msg)
response3 = MessageHeader()
sock.recv_into(response3)
print('response command:', response3.command)
response4 = MessageHeader()
sock.recv_into(response4)
print('response command:', response4.command)
sid = response4.parameter2

try:
    ioid += ioid
except NameError:
    ioid = 1

print('sid', sid)
header = ReadNotifyRequestHeader(DBR_FLOAT.DBR_ID, 1, sid, ioid)
sock.sendall(header)
response5 = MessageHeader()
sock.recv_into(response5)
print(response5.command)
res_payload5 = DBR_FLOAT()
sock.recv_into(res_payload5)
print(res_payload5.value)
