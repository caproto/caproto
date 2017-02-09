# State flow for successful operation


### UDP PHASE ###
import caproto as ca
cli = ca.Client()
chan1 = cli.Channel(pv1)
# chan1.circuit = {'state': (SEND_SEARCH, UNINITIALIZED)}
# srv.circuits = []
cli.send_broadcast(SearchRequest(...))
# chan1.circuit = {'state': (SEND_SEARCH, UNINITIALIZED)}
# srv.circuits = []
srv.recv_broadcast((data, address))
event = srv.next_event()  # -> SearchRequest(...)
# chan1.circuit = {'state': (AWAITING_SEARCH_RESPONSE, UNINITIALIZED)}
# srv.circuits = []
srv.send_broadcast(SearchResponse(...))
# chan1.circuit = {'state': (AWAITING_SEARCH_RESPONSE, UNINITIALIZED)}
# srv.circuits = []
cli.recv_broadcast((data, address))
event = cli.next_event()  # -> SearchResponse(...)
# chan1.circuit now has an address, which was attached to the event
# chan1.circuit = {'state': (SEND_VERSION_REQUEST, IDLE),
#                  'address': (host, port}}
# srv.circuits = []


### CIRCUIT CONNECTION PHASE ###
# cli connects over TCP
chan1.circuit.send(VersionRequest(...))
# chan1.circuit = {'state': (AWAITING_VERSION_RESPONSE, SEND_VERSION_RESPONSE)}
# srv.circuits = [{'state': (AWAITING_VERSION_RESPONSE, SEND_VERSION_RESPONE)}]
# srv accepts TCP connection
srv.circuits[0].recv(bytes_received)
event = srv.next_event()  # -> VersionRequest(...)
# chan1.circuit = {'state': (AWAITING_VERSION_RESPONSE, SEND_VERSION_RESPONSE)}
# srv.circuits = [{'state': (AWAITING_VERSION_RESPONSE, SEND_VERSION_RESPONE)}]
srv.send(VersionResponse(...))
# chan1.circuit = {'state': (AWAITING_VERSION_RESPONSE, SEND_VERSION_RESPONSE)}
# srv.circuits = [{'state': (CONNECTED, CONNECTED)}]
chan1.circuit.recv(bytes_received)
event = chan1.circuit.next_event()  # -> VersionResponse(...)
# chan1.circuit = {'state': (CONNECTED, CONNECTED)}
# srv1.circutis = [{'state': (CONNECTED, CONNECTED)}]
chan1.circuit.send(HostNameRequest(...))
# chan1.circuit = {'state': (CONNECTED, CONNECTED)}
# srv1.circutis = [{'state': (CONNECTED, CONNECTED)}]
srv.circuits[0].recv(bytes_received)
event = srv.circuits[0].next_event()  # -> HostNameRequest(...)
# chan1.circuit = {'state': (CONNECTED, CONNECTED)}
# srv1.circutis = [{'state': (CONNECTED, CONNECTED)}]
# And likewise for ClientNameRequest(...)


### CHANNEL CONNECTION PHASE ###
# chan1.state = (SEND_CREATE, UNINITIALIZED)
# srv1.circuits[0].channels = {}
chan1.send(CreateChan(pv1, ...))
# chan1.state = (AWAITING_CREATE_RESPONSE, SEND_CREATE_RESPONSE)
# srv1.circuits[0].channels = {}
srv1.circuits[0].recv(bytes_received)
event = srv1.circuits[0].next_event()  # CreateChan(...)
# chan1.state = (AWAITING_CREATE_RESPONSE, SEND_CREATE_RESPONSE)
# srv1.circuits[0].channels = {'name': {'state': (AWAITING_CREATE_RESPONSE,
#                                                 SEND_CREATE_RESPONSE)}}
srv1.circuits[0].send(CreateResponse(...))
# chan1.state = (AWAITING_CREATE_RESPONSE, SEND_CREATE_RESPONSE)
# srv1.circuits[0].channels = {'name': {'state': (READY, READY)}} 
chan1.recv(bytes_received)
chan1.next_event()
# chan1.state = (READY, READY)
# srv1.circuits[0].channels = {'name': {'state': (READY, READY)}} 


### USE ###
chan1.circuit.send(ReadNotify(...))
# or, equivalently, chan1.circuit.send(chan1.read())
srv1.circuits[0].recv(bytes_received)
event = srv1.circuits[0].next_event()  # ReadNotify(...)
# chan1.state = (READY, READY)
# srv1.circuits[0].channels = {'name': {'state': (READY, READY)}} 



# This is not an actual demo so much as an aspirational demo, sorting out an
# API that could actually work.


import socket
import os
import caproto as ca


### SETUP ###

HOST = os.environ['DOCKER0_IP']  # if using klauer/epics-docker
TCP_PORT = 5064
CA_REPEATER_PORT = 5065
OUR_IP = 'localhost'

pv1 = "XF:31IDA-OP{Tbl-Ax:X1}Mtr.VAL"
pv2 = "XF:31IDA-OP{Tbl-Ax:X2}Mtr.VAL"
pv2 = "XF:31IDA-OP{Tbl-Ax:X3}Mtr.VAL"

udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

cli = caproto.Client()

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

chan1 = ctx.Channel(pv1)
chan2 = ctx.Channel(pv2)
chan3 = ctx.Channel(pv3)
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

ctx.recv_broadcast(addr, bytes_received)  # parses bytes, updates some state
# Suppose we received replies regarding chan1 and chan3 and that they are on
# the same host, HOST_A.
# chan1.state == chan3.state == ca.CONNECT_CIRCUIT
# chan2.state == ca.NEEDS_BROADCAST_SEARCH_REPLY
# chan1.circuit is chan3.circuit is <VirtualCircuit on 'HOST A'>

 # We can't read or write or monitor it yet:
chan1.read()   # raises UninitializedCircuitError

# A 'VirtualCircuit' is a notion from EPICS, a mapping of hosts to channels
# (PVs) with an associated 'priority'. The Context `ctx` keeps track of
# them:
# ctx._VIRTUAL_CIRCUITS == [{'host': 'HOST_A', 'state': 'UNINITALIZED'}]
# ctx._CHANNELS = {<chan1>: <vc1>, <chan3>: <vc1>}

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
sockets = {'HOST_A': tcp_sock1}
send = lambda host, bytes_to_send: sockets[host].sendall(bytes_to_send)
recv = lambda host, byte_count: sockets[host].recv(byte_count)
send(host, bytes_to_send)
ctx.recv(recv(host, 1024))

# Having received confirmation from the host, now:
# ctx._VIRTUAL_CIRCUITS == [{'host': 'HOST_A', 'state': 'CONNECTED'}]
# chan1.state == chan3.state == ca.CREATE_CHANNEL

# The method `Channel.create` encodes CA_PROTO_CREATE_CHAN.
send(*chan1.create())
send(*chan3.create())
# chan1.state == chan3.state == ca.NEEDS_CREATE_CHANNEL_REPLY

ctx.recv(recv(chan1.host, 1024))
# chan1._sid == <server-generated id>
# chan2._sid == <server-generated id>
# chan1.state == chan3.state == ca.READY


### USE THE CHANNELS ###

# The method Channel.read() encodes CA_PROTO_READ_NOTIFY.
send(*chan1.read(ca.DBR_FLOAT, 1))  # desired data type and count
send(*chan3.read(ca.DBR_FLOAT, 1))
# chan1.state == chan3.state == ca.READY
# A CA_PROTO_READ_NOTIFY command includes a client-generated "IOID" that will
# be echoed by the server in its reply. `Channel.read()` stashes it in state.
# chan1.unanswered_ioids == [1]
# chan3.unanswered_ioids == [2]
ctx.recv(recv(chan1.host, 1024))
# chan1.unanswered_ioids == chan3.unanswered_ioids == []
data1 = chan1.value
data3 = chan3.value

# The method Channel.write() encodes CA_PROTO_WRITE_NOTIFY.
send(*chan1.write(ctx.DBR_FLOAT(3.14)))
# chan1.state == ca.READY
# chan1.unanswered_ioids == [3]
ctx.recv(recv(chan1.host, 1024))
# chan1.unanswered_ioids == []
write_status = chan1.write_status

# The method Channel.monitor() encodes CA_PROTO_EVENT_ADD
send(*chan1.monitor(ca.DBR_FLOAT, 1))  # desired data type and count
# chan1.state == ca.MONITORING
# chan1.subscription_id == 1
ctx.recv(recv(chan1.host, 1024))
send(*chan1.unmonitor())
# chan1.state = ca.READY
# chan1.subscription_id = None

# Notice that because all replies are routed through the Context, as in
# `ctx.recv`, it's OK if unrelated messages from monitoring one channel are
# interspersed messages from reading or writing to another from the same host.

# In the event that a connection is dropped, the state about VirtualCircuits
# allows us to notify all relevant channels.
