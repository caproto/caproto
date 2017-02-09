import socket
import getpass
import caproto as ca

PV1 = 'pv1'
SERVER_HOST = 'localhost'
SERVER_PORT = 6000
PROTOCOL_VERSION = 13


cli = ca.Connections(our_role=ca.CLIENT)
chan1 = cli.new_channel(PV1)
print('chan1 state:', chan1._state.states)
print('Send SearchRequest')
cli.send_broadcast(ca.SearchRequest(PV1, 0, 13))
print('chan1 state:', chan1._state.states)

print('Receive and process SearchResponse')
response = bytes(ca.SearchResponse(SERVER_PORT, 0, 0, PROTOCOL_VERSION))
address = (SERVER_HOST, SERVER_PORT)
cli.recv_broadcast(response, address)
command = cli.next_command()
print(command)
print('chan1 state:', chan1._state.states)

print("--- Circuit Phase ---")
print('chan1.circuit state:', chan1.circuit._state.states)
print("Send VersionRequest")
chan1.circuit.send(ca.VersionRequest(1, PROTOCOL_VERSION))
print('chan1.circuit state:', chan1.circuit._state.states)

print('Receive and process VersionResponse')
response = bytes(ca.VersionResponse(PROTOCOL_VERSION))
chan1.circuit.recv(response)
command = chan1.circuit.next_command()
print(command)
print('chan1.circuit state:', chan1.circuit._state.states)

print("Send HostNameRequest")
chan1.circuit.send(ca.HostNameRequest(socket.gethostname()))
print('chan1.circuit state:', chan1.circuit._state.states)

print("Send ClientNameRequest")
chan1.circuit.send(ca.ClientNameRequest(getpass.getuser()))
print('chan1.circuit state:', chan1.circuit._state.states)

print("--- Channel Phase ---")
# This cid and sid came from the SearchResponse! Capture that state.
print('chan1 state:', chan1._state.states)
chan1.circuit.send(ca.CreateChanRequest(PV1, 0, PROTOCOL_VERSION))
print('chan1 state:', chan1._state.states)

print('Receive and process CreateChanResponse')
response = bytes(ca.CreateChanResponse(ca.DBR_INT.DBR_ID, 1, 0, 0))
chan1.circuit.recv(response)
command = chan1.circuit.next_command()
print(command)
print('chan1 state:', chan1._state.states)
