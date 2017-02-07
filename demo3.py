# This is not an actual demo so much as an aspirational demo, sorting out an
# API that could actually work.


import socket
import os
import caproto as ca


### SETUP ###

HOST = os.environ['DOCKER0_IP']  # if using klauer/epics-docker
TCP_PORT = 5064
CA_REPEATER_PORT = 5065

pv1 = "XF:31IDA-OP{Tbl-Ax:X1}Mtr.VAL"
pv2 = "XF:31IDA-OP{Tbl-Ax:X2}Mtr.VAL"
pv2 = "XF:31IDA-OP{Tbl-Ax:X3}Mtr.VAL"

udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


### REGISTER WITH A CA REPEATER ###

bytes_to_send = ca.repeater_register(OUR_IP)  # a CA_REPEATER_REGISTER command
udp_sock.sendto('localhost', CA_REPEATER_PORT)
bytes_received, _ = udp_sock.recv(1024)
# The function below should does one of the following:
# - receives CA_REPEATER_CONFIRM and returns the IP (0.0.0.0 or 127.0.0.1)
# - does not receive a reply and returns None, indicating client should set up
#   a REPEATER of their own
repeater_ip = ca.repeater_confirm(bytes_received)


### CREATE SOME CHANNELS ###

chan1 = ca.Channel(pv1)
chan2 = ca.Channel(pv2)
chan3 = ca.Channel(pv3)
# chan1.state == chan2.state == chan3.state == ca.BROADCAST_SEARCH
# chan1.circuit is chan2.circuit is chan3.circuit is None

# The method `Channel.broadcast()` encodes CA_PROTO_SERACH.
bytes_to_broadcast = chan1.broadcast() + chan2.broadcast() + chan3.broadcast()
# chan1.state == chan2.state == chan3.state == ca.NEEDS_BROADCAST_SEARCH_REPLY
# chan1.circuit is chan2.circuit is chan3.circuit is None

udp_sock.sendto(bytes_to_broadcast, (repeater_ip, CA_REPEATER_PORT))
addr, bytes_received = udp_sock.recv(1024)
# We may get an answer from 0 or more servers for each channel. The answers do
# not necessarily arrive in order or at all.

ca.recv_broadcast(addr, bytes_received)  # parses bytes, updates some state
# Suppose we received replies regarding chan1 and chan3 and that they are on
# the same host, HOST_A.
# chan1.state == chan3.state == ca.CONNECT_CIRCUIT
# chan2.state == ca.NEEDS_BROADCAST_SEARCH_REPLY
# chan1.circuit is chan3.circuit is <VirtualCircuit on 'HOST A'>

 # We can't read or write or monitor it yet:
chan1.read()   # raises UninitializedCircuitError

# A 'VirtualCircuit' is a notion from EPICS, a mapping of hosts to channels
# (PVs) with an associated 'priority'. A module level singleton keeps track of
# them:
# ca._VIRTUAL_CIRCUITS == [{'host': 'HOST_A', 'state': 'UNINITALIZED'}]
# ca._CHANNELS = {<chan1>: <vc1>, <chan3>: <vc1>}

# The method `VirtualCircuit.connect()` encodes CA_PROTO_VERSION,
# CA_PROTO_HOST_NAME, and CA_PROTO_CLIENT_NAME.
host, bytes_to_send = chan1.circuit.connect()  # ('HOST_A', <bytes>)

# Because chan1 and chan3 are on the same circuit, we only need to do this
# once, as we can verify by checking the channels' state.
# chan1.state == chan3.state == ca.NEEDS_CONNECT_CIRCUIT_REPLY

# Create a TCP socket for this host.
tcp_sock1 = socket.create_connection((host, TCP_PORT))

# Caproto manages the mapping between hosts and channels, but it's up to the
# user to manage the mapping between hosts and sockets. Something like this
# is convenient for our purposes, but again this part is ocmpletely up to the
# user:
sockets = {'HOST_A', tcp_sock1}
send = lambda host, bytes_to_send: sockets[host].sendall(bytes_to_send)
recv = lambda host, byte_count: return sockets[host].recv(byte_count)
send(host, bytes_to_send)
ca.recv(recv(host, 1024))

# Having received confirmation from the host, now:
# ca._VIRTUAL_CIRCUITS == [{'host': 'HOST_A', 'state': 'CONNECTED'}]
# chan1.state == chan3.state == ca.CREATE_CHANNEL

# The method `Channel.create` encodes CA_PROTO_CREATE_CHAN.
send(*chan1.create())
send(*chan3.create())
# chan1.state == chan3.state == ca.NEEDS_CREATE_CHANNEL_REPLY

ca.recv(recv(chan1.host, 1024))
# chan1.state == chan3.state == ca.READY


### USE THE CHANNELS ###

# The method Channel.read() encodes CA_PROTO_READ_NOTIFY.
send(*chan1.read(ca.DBR_FLOAT, 1))  # desired data type and count
send(*chan2.read(ca.DBR_FLOAT, 1))
# chan1.state == chan2.state == ca.READY
# chan1.unanswered_ioids == [1]
# chan2.unanswered_ioids == [2]
ca.recv(recv(chan1.host, 1024))
# chan1.unanswered_ioids == chan2.unanswered_ioids == []
data1 = chan1.value
data2 = chan2.value

# The method Channel.write() encodes CA_PROTO_WRITE_NOTIFY.
send(*chan1.write(ca.DBR_FLOAT(3.14)))
# chan1.state == ca.READY
# chan1.unanswered_ioids == [3]
ca.recv(recv(chan1.host, 1024))
# chan1.unanswered_ioids == []
write_status = chan1.write_status

# The method Channel.monitor() encodes CA_PROTO_EVENT_ADD
send(*chan1.monitor(ca.DBR_FLOAT, 1))  # desired data type and count
# chan1.state == ca.MONITORING
# chan1.subscription_id == 1
ca.recv(recv(chan1.host, 1024))
send(*chan1.unmonitor())
# chan1.state = ca.READY
# chan1.subscription_id = None

# Notice that because all replies are routed through the global function
# `ca.recv` it's OK if unrelated messages from monitoring one channel are
# interspersed messages from reading or writing to another from the same host.

# In the event that a connection is dropped, the state about VirtualCircuits
# allows us to notify all relevant channels.
