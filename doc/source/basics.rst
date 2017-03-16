*******************************************************
Getting Started: Writing Your Own Channel Access Client
*******************************************************

Caproto can be used to implement both Channel Access clients and servers. To
give a flavor for how the API works, we’ll demonstrate a small client.

Channel Access Basics
=====================

A Channel Access client reads and writes values to *Channels* available from
servers on its network. It locates these servers using UDP broadcasts. It
communicates with an individual server via one or more TCP connections, which
is calls *Virtual Circuits*.

In this example, our client will talk to 
`EPICS motorsim <github.com/danielballan/motorsim>`_, which provides a
collection of simulated motors we can read and move. But this same code could
talk to any Channel Access server, including one implemented in caproto itself.

Registering with the Repeater
-----------------------------

To begin, we need a UDP socket.

.. ipython:: python

    import socket
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    udp_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)

A new Channel Access client is required to register itself with a *Repeater*,
an independent process that rebroadcasts all UDP traffic on a given host. To
register, we must send a *request* to the Repeater and recive a *response*.
At the lowest level, we simply need to send the right bytes over the network.
This is effective, but no very readable:

.. ipython:: python

    bytes_to_send = b'\x00\x18\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
    udp_sock.sendto(bytes_to_send, ('', 5065))

.. ipython:: python

    data, address = udp_sock.recvfrom(1024)
    data

Hurray it worked? Caproto provides a higher level of abstraction, *Commands*,
so that we don't need to work with raw bytes. Let's try this again using
caproto.

.. note::

    Other sans-I/O libraries use the word *Event* for what we are calling a
    *Command*. "Event" is an overloaded term in Channel Access, so we're going
    our own way here.

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

When we call :meth:`~Broadcaster.send` or :meth:`~Broadcaster.next_command`,
two things happen. The broadcaster translates between low-level bytes and a
high-level *Command*. The broadcaster also updates its internal state machine
encoding the rules of the protocol. It tracks the state of both the client and
server (it can serve as either). If, as the client, you send an illegal
command, it will raise :class:`LocalProtocolError`. If, as the client, you
receive bytes from the server that constitute an illegal command, it will raise
:class:`RemoteProtocolError`.

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
    udp_sock.sendto(bytes_to_send, ('', 5064))

Our answer will arrive in a single datagram with multiple commands in it.

.. ipython:: python

    bytes_received, address = udp_sock.recvfrom(1024)
    b.recv(bytes_received, address)
    b.next_command()
    b.next_command()
    address

Now we have the address of a server that has the channel we're interested in.
Next, we'll set aside the broadcaster and initiate TCP communication with this
particular server.

Creating a Channel
------------------

Create a TCP connection with the server at the ``address`` we found above.

.. ipython:: python

    sock = socket.create_connection(address)


A :class:`caproto.VirtualCircuit` plays the same for a TCP connection as the
:class:`caproto.Broadcaster` played for UDP: we'll use it to interpret received
bytes as Commands and to ensure that incoming and outgoing bytes abide by the
protocol.

.. ipython:: python

    circuit = caproto.VirtualCircuit(our_role=caproto.CLIENT, address=address, priority=0)

We'll use these two convenience functions for what follows.

.. code-block:: python

    def send(command):
        "Process a Command in the VirtualCircuit and then transmit its bytes."
        bytes_to_send = circuit.send(command)  # Update state machine.
        sock.send(bytes_to_send)  # Actually transmit bytes.

    def recv():
        "Receive some bytes and parse all the Commands in them."
        bytes_received = sock.recv(4096)
        circuit.recv(bytes_received)  # Cache bytes.
        commands = []
        while True:
            command = circuit.next_command()  # Parsing happens here.
            if type(command) is caproto.NEED_DATA:
                break  # Not enough bytes to parse any more commands.
            commands.append(command)
        return commands

.. ipython:: python
    :suppress:

    def send(command):
        bytes_to_send = circuit.send(command)
        sock.send(bytes_to_send)
    def recv():
        bytes_received = sock.recv(4096)
        circuit.recv(bytes_received)
        commands = []
        while True:
            command = circuit.next_command()
            if type(command) is caproto.NEED_DATA:
                break
            commands.append(command)
        return commands

.. ipython:: python

    send(caproto.VersionRequest(priority=0, version=13))
    recv()
    send(caproto.HostNameRequest('localhost'))
    send(caproto.ClientNameRequest('user'))
    cid = 1  # a client-specific unique ID for this Channel
    send(caproto.CreateChanRequest(name=name, cid=cid, version=13))
    access_response, create_chan_response = recv()
    access_response, create_chan_response

Success! We now have a connection to the ``XF:31IDA-OP{Tbl-Ax:X1}Mtr.VAL``
channel. Next we'll read and write values.

Incidentally, we reuse this same ``circuit`` and ``socket`` to connect to
other channels on the same server. In the commands that follow, we'll use the
integer IDs ``cid`` (specified by our client in ``CreateChanRequest``) and
``sid`` (specified by the server in its ``CreateChanResponse``) to specify
which channel we mean.

.. ipython:: python

    sid = create_chan_response.sid

In the event of high traffic clogging the network, we can open up *multiple*
TCP connections to the same server, each with its own VirtualCircuit, and
designate them with different *priority* (specified in our ``VersionRequest``).
This why we need the concept of a VirtualCircuit: there can be multiple
VirtualCircuits between peers.

Reading and Writing Values
--------------------------

Read:

.. ipython:: python

    send(caproto.ReadNotifyRequest(data_type=2, data_count=1, sid=sid, ioid=1))
    recv()

Write:

.. ipython:: python
    
    send(caproto.WriteNotifyRequest(values=(4,), data_type=2, data_count=1, sid=sid, ioid=2))
    recv()

Why is the value given as a tuple? Channel Access has its own sprawling data
type system. Many of its types bundle a value with metadata like a timestamp
and various "limits". At the lowest level, caproto reads values into C structs
that match byte layouts in the canonical implementation of Channel Access,
libca. At a higher level, the user may interact with values as named tuples
with an element for each field in the struct. The elements in the tuple are
built-in Python types (strings, floats, integers). If the value is an array (in
Channel Access parlance, a "waveform") it is given as a numpy arrays if numpy
is available.

Subscribing to "Events" (Updates)
---------------------------------

Ask the server to send responses every time the value of the Channel changes.
We can request a particular data type and element count; in the case we'll
just ask for the "native" data type and count that the server reported in its
``CreateChanResponse`` above.

.. ipython:: python

    req = caproto.EventAddRequest(data_type=create_chan_response.data_type,
                                  data_count=create_chan_response.data_count,
                                  sid=sid,
                                  subscriptionid=0,
                                  low=0, high=0, to=0, mask=1)
    send(req)

The server always sends at least one response with the current value at
subscription time.

.. ipython:: python

    recv()

If the value changes, additional responses will come in. If multiple
subscriptions are in play at once over this circuit, we can use the
``subscriptionid`` to match them to the right channel. We also use it to end
the subscription:
    
.. ipython:: python

    send(caproto.EventCancelRequest(data_type=req.data_type,
                                    sid=req.sid,
                                    subscriptionid=req.subscriptionid))
    recv()

Closing the Channel
-------------------

To clean up, close the Channel.

.. ipython:: python

    send(caproto.ClearChannelRequest(sid, cid))
    recv()

If we are done with the circuit, close the socket too.

.. ipython:: python

    sock.close()

Simplify Bookkeepinig with Channels
===================================

In the example above, we handled a ``VirtualCircuit`` and several different
commands. The ``VirtualCircuit`` policed our adherence to the
Channel Access protocol by watching incoming and outgoing commands and tracking
the state of the circuit itself and the state(s) of the channel(s) on the
circuit.  To facilitate this, it creates a ``ClientChannel`` object for each
channel to encapsulate its state and stash bookkeeping details like ``cid`` and
``sid``.

Using these objects directly can help us juggle IDs and generate valid commands
more succintly. This API is purely optional, and using it does not affect
the state machines.

See how much more succinct our example becomes:

.. code-block:: python

    ### Create
    chan = caproto.ClientChannel(name, circuit)
    send(chan.version())
    recv()
    send(chan.host_name('localhost'), chan.client_name('user'), chan.create())
    recv()

    ### Read and Write
    send(chan.read())
    recv()
    send(chan.write((4,)))
    recv()

    ### Subscribe and Unsubscribe
    send(chan.subscribe())
    recv()
    send(chan.unsubscribe(0))
    recv()

    ### Clear
    send(chan.clear())
    recv()

Here is the equivalent, a condensed copy of our work from previous sections:

.. code-block:: python

    ### Create
    send(caproto.VersionRequest(priority=0, version=13))
    recv()
    send(caproto.HostNameRequest('localhost'))
    send(caproto.ClientNameRequest('user'))
    cid = 1  # a client-specific unique ID for this Channel
    send(caproto.CreateChanRequest(name=name, cid=cid, version=13))
    access_response, create_chan_response = recv()
    access_response, create_chan_response

    ### Read and Write
    send(caproto.ReadNotifyRequest(data_type=2, data_count=1, sid=sid, ioid=1))
    recv()
    send(caproto.WriteNotifyRequest(values=(4,), data_type=2, data_count=1, sid=sid, ioid=2))
    recv()
    
    ### Subscribe and Unsubscribe
    req = caproto.EventAddRequest(data_type=create_chan_response.data_type,
                                  data_count=create_chan_response.data_count,
                                  sid=sid,
                                  subscriptionid=0,
                                  low=0, high=0, to=0, mask=1)
    send(req)
    recv()
    send(caproto.EventCancelRequest(data_type=req.data_type,
                                    sid=req.sid,
                                    subscriptionid=req.subscriptionid))
    recv()

    ### Clear
    send(caproto.ClearChannelRequest(sid, cid))
    recv()

Notice that the channel convenience methods like ``chan.create()`` don't
actually *do* anything. We still have to ``send`` the command into the
VirtualCircuit and then send it over the socket. These are just easy ways to
generate valid commands --- with auto-generated unique IDs filled in --- which
you may or may not then choose to send. The state machines are not updated
until (unless) the command is actually sent.
