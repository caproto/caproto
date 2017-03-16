*******************************************************
Getting Started: Writing Your Own Channel Access Client
*******************************************************

Caproto can be used to implement both EPICS clients and servers. To give a
flavor for how the API works, we’ll demonstrate a small client.

Channel Access Basics
=====================

Registering with the Repeater
-----------------------------

A Channel Access client locates servers on its network using UDP broadcasts. It
communicates with each individual server via one or more TCP connections. Why
have multiple TCP connections to the same server? They can be designated
different *priority* to cope with high traffic. Channel Access calls each
individual connection a *Virtual Circuit*.

To begin, we need a UDP socket.

.. ipython:: python

    import socket
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    udp_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)

A new Channel Access client is required to register itself with a *Repeater*,
an independent process that rebroadcasts all UDP traffic. We must send a
*request* and receive a *response* from the Repeater. At the lowest level, we
merely need to send the right bytes over the network. This is effective, but no
very readable:

.. ipython:: python

    bytes_to_send = b'\x00\x18\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
    udp_sock.sendto(bytes_to_send, ('', 5065))

.. ipython:: python

    data, address = udp_sock.recvfrom(1024)
    data

Hurray it worked? Caproto provides a higher level of abstraction, *Commands*,
so that we don't need to with raw bytes. Let's try this again using caproto.

Set up the socket, exactly as above. Additionally, import :mod:`caproto` and
make a :class:`caproto.Broadcaster`.

.. ipython:: python

    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    udp_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    import caproto
    b = caproto.Broadcaster(our_role=caproto.CLIENT)

Make the command we want to send.

.. ipython:: python

    command = caproto.RepeaterRegisterRequest('0.0.0.0')

Pass the command to our broadcaster's :meth:`~Connection.send`send`` method,
which translates the command to bytes.

.. ipython:: python

    bytes_to_send = b.send(command)

Transport those bytes over the wire.

.. ipython:: python

    udp_sock.sendto(bytes_to_send, ('', 5065))

These bytes are same bytes we assembled manually before:

.. ipython:: python

    bytes_to_send
    
.. ipython:: python

    udp_sock.sendto(bytes_to_send, ('', 5065))

Why we need two steps here? Why doesn't caproto just send the bytes for us?
Because it's designed to support any socket API you might want to use ---
synchronous (like this example), asynchronous, etc. Caproto does not care how
you send and receive that bytes. It's job is to make it easier to compose
outgoing messages, interpret incoming ones, and verify that the rules of the
protocol are obeyed.

Recall that we are in the process of registering our client with a *Repeater*
and that we are expecting a response. As with sending, receiving is a
two-step process. First we read bytes from the socket and pass them to the
broadcaster.

.. ipython:: python

    bytes_received, address = udp_sock.recvfrom(1024)
    b.recv(bytes_received, address)

The bytes have been cached but not yet parsed. The :class:`~Broadcaster`
converst the bytes into *Commands* one at time.

.. ipython:: python

    b.next_command()

When there aren't enough bytes cached to interpret another complete Command,
:meth:`~Broadcaster.next_command` returns the special constant
:data:`NEED_DATA`.

.. ipython:: python

    b.next_command()

Searching for a Channel
-----------------------

Say we're looking for a channel ("Process Variable") with a vintage EPICS name
like :data:`"XF:31IDA-OP{Tbl-Ax:X1}Mtr.VAL"`. It just flows off the tongue!

We need to broadcast a search request to the servers on our network and recive
any responses. We follow the same pattern as above, still using our broadcaster
``b`` our socket ``udp_sock`` and some new caproto commands.

We need to announce which version of the protocol we are using in the same UDP
datagram as our search request.

.. ipython:: python

    name  = "XF:31IDA-OP{Tbl-Ax:X1}Mtr.VAL"
    bytes_to_send = b.send(caproto.VersionRequest(priority=0, version=13),
                           caproto.SearchRequest(name=name, cid=0, version=13))
    udp_sock.sendto(bytes_to_send, ('', CA_SERVER_PORT))

Our answer will arrive in a single datagram with multiple commands in it.

.. ipython:: python

    bytes_received, address = udp_sock.recvfrom(1024)
    b.recv(bytes_received, address)
    b.next_command()
    b.next_command()

Now we have the address of a server that has the channel we're interested in.

    
    circuit = caproto.VirtualCircuit(our_role=caproto.CLIENT, address=address, priority=0)
    chan1 = caproto.ClientChannel(circuit, name)
    socket = socket.create_connection(chan1.circuit.address)
    
    # Initialize our new TCP-based CA connection with a VersionRequest.
    send(chan1.circuit, ca.VersionRequest(priority=0, version=13))
    bytes_to_send = chan1.circuit.send(command)
    socket.send(bytes_to_send)
    recv(chan1.circuit)
    # Send info about us.
    send(chan1.circuit, ca.HostNameRequest('localhost'))
    send(chan1.circuit, ca.ClientNameRequest('username'))
    send(chan1.circuit, ca.CreateChanRequest(name=pv1, cid=chan1.cid, version=13))
    commands = recv(chan1.circuit)

TODO This is not true. It's only true of circuits.

When we call :meth:`~Broadcaster.send` or :meth:`~Broadcaster.next_command`,
two things happen. The broadcaster translates between low-level bytes and a
high-level *Command*. The broadcaster also updates its internal state machine
encoding the rules of the protocol. It tracks the state of both the client and
server (it can serve as either). If, as the client, you send an illegal
command, it will raise :class:`LocalProtocolError`. If, as the client, you
receive bytes from the server that constitute an illegal command, it will raise
:class:`RemoteProtocolError`.
