import caproto.caproto as ca

PV1 = 'pv1'
SERVER_HOST = 'localhost'
SERVER_PORT = 6000


cli = ca.Client()
chan1 = cli.new_channel(PV1)
print(chan1._state.states)
print('Send SearchRequest')
cli.send_broadcast(ca.SearchRequest(PV1, 0, 13))
print(chan1._state.states)

print('Receive and process SearchResponse')
response = bytes(ca.SearchResponse(SERVER_PORT, 0, 0, 13))
address = (SERVER_HOST, SERVER_PORT)
cli.recv_broadcast(response, address)
command = cli.next_command()
print(command)
print(chan1._state.states)
