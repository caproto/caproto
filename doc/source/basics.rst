**************************************
Writing Your Own Channel Access Client
**************************************

.. currentmodule:: caproto

Caproto can be used to implement both Channel Access clients and servers. To
give a flavor for how the API works, we’ll demonstrate a simple, synchronous
client.

Channel Access Basics
=====================

A Channel Access client reads and writes values to *Channels* available from
servers on its network. It locates these servers using UDP broadcasts. It
communicates with an individual server via one or more TCP connections, which
it calls *Virtual Circuits*.

In this example, our client will talk to a example IOC provided by caproto,
but this same code could talk to any Channel Access server.

.. ipython:: python
    :suppress:

    import sys
    import subprocess
    import time
    processes = []
    def run_example(module_name, *args):
        p = subprocess.Popen([sys.executable, '-m', module_name] + list(args))
        processes.append(p)  # Clean this up at the end.
        time.sleep(1)  # Give it time to start up.


.. ipython:: python
    :suppress:

    run_example('caproto.ioc_examples.random_walk')
    run_example('caproto.sync.repeater')

In a separate shell, start one of caproto's demo IOCs.

.. code-block:: bash

    $ python3 -m caproto.ioc_examples.random_walk
    PVs: ['random_walk:dt', 'random_walk:x']

In a second separate shell, start a repeater process. You may see output like
this:

.. code-block:: bash

    $ caproto-repeater
    [I 18:04:30.686 repeater:84] Repeater is listening on 0.0.0.0:5065

or this:

.. code-block:: bash

    $ caproto-repeater
    [I 18:04:08.790 repeater:189] Another repeater is already running; exiting.

Either is fine.

Registering with the Repeater
-----------------------------

To begin, we need a socket configured for UDP broadcasting. Caproto provides a
convenient utility for doing this in a way that works on all platforms.

.. ipython:: python

    import caproto
    udp_sock = caproto.bcast_socket()

A new Channel Access client is required to register itself with a Channel
Access *Repeater*.  (What a Repeater is *for* is not really important to our
story here. It's an independent process that rebroadcasts incoming server
heartbeats to all clients on our host. It exists because old systems don't
handle broadcasts properly.) To register, we must send a *request* to the
Repeater and receive a *response*.

.. ipython:: python

    bytes_to_send = b'\x00\x18\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
    udp_sock.sendto(bytes_to_send, ('127.0.0.1', 5065))

.. ipython:: python

    data, address = udp_sock.recvfrom(1024)
    data

Hurray it worked? Unless you can read Channel Access hex codes the way Neo
experiences the Matrix, you may want a better way. Caproto provides a higher
level of abstraction, *Commands*, so that we don't need to work with raw bytes.
Let's try this again using caproto.

.. note::

    Other sans-I/O libraries use the word *Event* for what we are calling a
    *Command*. "Event" is an overloaded term in Channel Access, so we're going
    our own way here.

As above, create a fresh UDP socket configured for broadcasting.

.. ipython:: python

    import caproto
    udp_sock = caproto.bcast_socket()

.. ipython:: python
    :suppress:

    import caproto
    udp_sock = caproto.bcast_socket()
    udp_sock.settimeout(2)  # should never be tripped, but it helps to debug

Instantiate a caproto :class:`Broadcaster` and a command to broadcast --- a
:class:`RepeaterRegisterRequest`.`

.. ipython:: python

    b = caproto.Broadcaster(our_role=caproto.CLIENT)
    command = caproto.RepeaterRegisterRequest('0.0.0.0')

Pass the command to our broadcaster's :meth:`Broadcaster.send` method, which
does two things. It translates command objects into bytes, and it checks
them against the rules of the Channel Access protocol. The rules are encoded in
the Broadcaster's internal state machine, which tracks the state of both the
client and the server. (It can serve as either.) If you try to send an illegal
command, it will raise :class:`LocalProtocolError`.

.. ipython:: python

    bytes_to_send = b.send(command)
    bytes_to_send

Transport those bytes over the wire, using the same ``udp_sock`` we configured
above.  A quick comparison will show that these bytes are the same bytes we
spelled out manually before.

.. ipython:: python

    udp_sock.sendto(bytes_to_send, ('127.0.0.1', 5065))

Why do we need two steps here? Why doesn't caproto just send the bytes for us?
Because it's designed to support any socket API you might want to use ---
synchronous (like this example), asynchronous, etc. Caproto does not care how
or when you send and receive the bytes. Its job is to make it easier to
compose outgoing messages, interpret incoming ones, and verify that the rules
of the protocol are obeyed by both peers.

Recall that we are in the process of registering our client with a Channel
Access Repeater and that we are expecting a response. As with sending,
receiving is a two-step process. First we read bytes from the socket and pass
them to the broadcaster.

.. ipython:: python

    bytes_received, address = udp_sock.recvfrom(1024)
    commands = b.recv(bytes_received, address)

The bytes have been parsed into command objects. Next, check them against the
Channel Access protocol.

.. ipython:: python

    b.process_commands(commands)

When we call :meth:`Broadcaster.process_commands`, the Broadcaster does the
same thing is did for :meth:`Broadcaster.send` in reverse: if one of the
received commands is illegal, it raises :class:`RemoteProtocolError`.

Searching for a Channel
-----------------------

Say we're looking for a channel ("Process Variable") with a typically lyrical
EPICS name like :data:`"random_walk:dt"`. Some server on our
network provides this channel.

The range of IP addresses to search is conventionally controlled by the
environment variables ``EPICS_CA_ADDR_LIST`` (a space-separated list of IP
addresses) and ``EPICS_CA_AUTO_ADDR_LIST`` (``yes`` or ``no``). Caproto
provides a convenience function :func:`get_address_list` for parsing these
variables, checking the available network interfaces if necessary, and
returning a list.

.. ipython:: python

    import caproto
    hosts = caproto.get_address_list()  # example: ['172.17.255.255']

We need to broadcast a search request to the servers on our network and receive
a response. (In the event that multiple responses arrive, Channel Access
specifies that all but the first response should be ignored.) We follow the
same pattern as above, still using our broadcaster ``b``, our socket
``udp_sock``, and some new caproto commands.

We need to announce which version of the protocol we are using and the name of
the channel we are seraching for. These two commands must be sent in the same
broadcast (UDP datagram), so we pass them to :meth:`Broadcaster.send` together.

.. ipython:: python

    name  = "random_walk:dt"
    bytes_to_send = b.send(caproto.VersionRequest(priority=0, version=13),
                           caproto.SearchRequest(name=name, cid=0, version=13))
    bytes_to_send
    for host in hosts:
        udp_sock.sendto(bytes_to_send, (host, 5064))

Our answer will arrive in a single datagram with multiple commands in it.

.. ipython:: python

    bytes_received, recv_address = udp_sock.recvfrom(1024)
    commands = b.recv(bytes_received, recv_address)
    version_response, search_response = commands
    version_response
    search_response
    address = caproto.extract_address(search_response)
    address

Now we have the address of a server that has the channel we're interested in.
Next, we'll set aside the broadcaster and initiate TCP communication with this
particular server.

Creating a Channel
------------------

Create a TCP connection with the server at the ``address`` we found above.

.. ipython:: python

    import socket
    sock = socket.create_connection(address)


A :class:`VirtualCircuit` plays the same role for a TCP connection as
the :class:`Broadcaster` played for UDP: we'll use it to interpret
received bytes as commands and to ensure that incoming and outgoing bytes abide
by the protocol.

.. ipython:: python

    circuit = caproto.VirtualCircuit(our_role=caproto.CLIENT, address=address,
                                     priority=0)

We'll use these convenience functions for what follows.

.. ipython:: python

    def send(command):
        "Process a command in the VirtualCircuit and then transmit its bytes."
        buffers_to_send = circuit.send(command)
        sock.sendmsg(buffers_to_send)

.. ipython:: python

    def recv():
        "Receive bytes; parse commands; process them in the VirtualCircuit."
        bytes_received = sock.recv(4096)
        commands, _ = circuit.recv(bytes_received)
        for command in commands:
            circuit.process_command(command)
        return commands

We initialize the circuit by specifying our protocol version.

.. ipython:: python

    send(caproto.VersionRequest(priority=0, version=13))
    recv()

Optionally provide the host name and "client" name, which the server may use
to determine our read/write permissions on channels. (There is no
authentication in Channel Access; security has to be provided at the network
level.)

.. ipython:: python

    send(caproto.HostNameRequest('localhost'))
    send(caproto.ClientNameRequest('user'))

Finally, create the channel and look at the responses.

.. ipython:: python

    cid = 1  # a client-specified unique ID for this Channel
    send(caproto.CreateChanRequest(name=name, cid=cid, version=13))
    commands = recv()
    access_response, create_chan_response = commands
    access_response
    create_chan_response

Success! We now have a connection to the ``random_walk:dt`` channel. Next we'll
read and write values.

Incidentally, we can reuse this same ``circuit`` and ``sock`` to connect to
other channels on the same server. In the commands that follow, we'll use the
integer IDs ``cid`` (specified by our client in :class:`CreateChanRequest`) and
``sid`` (specified by the server in its :class:`CreateChanResponse`) to specify
which channel we mean.

.. ipython:: python

    sid = create_chan_response.sid

In the event of high traffic clogging the network, we can open up *multiple*
TCP connections to the same server, each with its own VirtualCircuit, and
designate them with different *priority* (specified in our
:class:`VersionRequest`). This why we need the concept of a VirtualCircuit:
there can be multiple VirtualCircuits between peers.

Reading and Writing Values
--------------------------

Read:

.. ipython:: python

    send(caproto.ReadNotifyRequest(data_type=create_chan_response.data_type,
                                   data_count=create_chan_response.data_count,
                                   sid=sid,
                                   ioid=1))
    recv()

We may request a particular data type and element count; in the case we just
asked for the "native" data type and count that the server reported in its
:class:`CreateChanResponse` above.

Write:

.. ipython:: python

    send(caproto.WriteNotifyRequest(data=(4,),
                                    data_type=create_chan_response.data_type,
                                    data_count=create_chan_response.data_count,
                                    sid=sid,
                                    ioid=2))
    recv()

The ``data`` may be given as one of the following types:

* ``tuple``
* ``numpy.ndarray`` (if numpy is installed)
* big-endian ``array.array`` (the somewhat rarely-used builtin array library)
* big-endian bytes-like (``bytes``, ``bytearray``, ``memoryview``)

The command also accepts a ``metadata`` parameter for data types that include
metadata. See :ref:`payload_data_types` for details.

Subscribing to "Events" (Updates)
---------------------------------

Ask the server to send responses every time the value of the Channel changes.
As with reading, above, we have the option of requesting a specific data type
or element count, but we'll use the "native" parameters.

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

Simplify Bookkeeping with Channels
===================================

In the example above, we handled a :class:`VirtualCircuit` and several
different commands. The :class:`VirtualCircuit` policed our adherence to the
Channel Access protocol by watching incoming and outgoing commands and tracking
the state of the circuit itself and the state(s) of the channel(s) on the
circuit. Internally, to facilitate this, it creates a :class:`ClientChannel`
object for each channel to encapsulate its state and stash bookkeeping details
like ``cid`` and ``sid``.

Using these objects directly can help us juggle IDs and generate valid commands
more succinctly. This API is purely optional, and using it does not affect
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
    cid = 1  # a client-specified unique ID for this Channel
    send(caproto.CreateChanRequest(name=name, cid=cid, version=13))
    commands = recv()
    access_response, create_chan_response = commands

    ### Read and Write
    send(caproto.ReadNotifyRequest(data_type=2, data_count=1, sid=sid, ioid=1))
    recv()
    send(caproto.WriteNotifyRequest(data=(4,), data_type=2, data_count=1, sid=sid, ioid=2))
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

.. ipython:: python
    :suppress:

    # Clean up IOC processes.
    for p in processes:
        p.terminate()
    for p in processes:
        p.wait()
