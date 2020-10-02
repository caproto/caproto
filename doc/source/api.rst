.. currentmodule:: caproto

**********************
Core API Documentation
**********************

.. contents::

Commands
========

Caproto lets you work with Channel Access communication in terms of *Commands*
instead of thinking in terms of bytes.

Take :class:`VersionRequest` as an example.

.. ipython:: python

    import caproto
    com = caproto.VersionRequest(version=13, priority=0)

A Command has a useful ``__repr__()``:

.. ipython:: python

    com

Every Command has a :data:`header` and a :data:`payload`. The data in them
fully describe the Command. The :data:`header` has generically-named fields
provided by the Channel Access specification.

.. ipython:: python

    com.header

These names are rather opaque, but each Command provides views on this same
data through type-specific attributes with more obvious names. These are the
same names used in the Command's ``__repr__()`` and ``__init__`` arguments.

.. ipython:: python

    com.version
    com.priority

This is a complete list of the Commands. They are sorted in Command ID order,
designated by the Channel Access specification.

.. autoclass:: VersionRequest
.. autoclass:: VersionResponse
.. autoclass:: SearchRequest
.. autoclass:: SearchResponse
.. autoclass:: NotFoundResponse
.. autoclass:: EchoRequest
.. autoclass:: EchoResponse
.. autoclass:: Beacon
.. autoclass:: RepeaterRegisterRequest
.. autoclass:: RepeaterConfirmResponse
.. autoclass:: EventAddRequest
.. autoclass:: EventAddResponse
.. autoclass:: EventCancelRequest
.. autoclass:: EventCancelResponse
.. autoclass:: ReadRequest
.. autoclass:: ReadResponse
.. autoclass:: WriteRequest
.. autoclass:: EventsOffRequest
.. autoclass:: EventsOnRequest
.. autoclass:: ReadSyncRequest
.. autoclass:: ErrorResponse
.. autoclass:: ClearChannelRequest
.. autoclass:: ClearChannelResponse
.. autoclass:: ReadNotifyRequest
.. autoclass:: ReadNotifyResponse
.. autoclass:: WriteNotifyRequest
.. autoclass:: WriteNotifyResponse
.. autoclass:: ClientNameRequest
.. autoclass:: HostNameRequest
.. autoclass:: AccessRightsResponse
.. autoclass:: CreateChFailResponse
.. autoclass:: ServerDisconnResponse

The State Machine
=================

To validate commands being sent and received, the caproto VirtualCircuit object
maintains several state machines. It keeps track of what the client is doing
and what server is doing, whether it is playing the role of the client or
server.

A single VirtualCircuit maintains:

* exactly one client-side circuit state machine
* exactly one server-side circuit state machine
* one client-side channel state machine *per channel*
* one server-side channel *per channel*

The basic interaction looks like this:

* Client specifies the priority and protocol version of a new Virtual Circuit.
* Server confirms.
* Client (optionally) provides its host name and client name.
* Client requests the creation of a new Channel.
* Server announces access rights for this Channel and confirms Channel
  creation.

With the Channel open, the client may send unlimited requests to read, write,
or subscribe. The Server responds. The server or the client may initiate
closing the Channel.

The state machines look like this. Click on each to expand.

.. ipython:: python
   :suppress:

   import sys
   import subprocess
   subprocess.check_call([sys.executable,
                          sys._caproto_hack_docs_source_path
                          + "/../gen_graphs.py"])

.. |channel-client| image:: _static/command_triggered_channel_transitions_client.png
      :target: _static/command_triggered_channel_transitions_client.png
      :width: 100%
.. |channel-server| image:: _static/command_triggered_channel_transitions_server.png
      :target: _static/command_triggered_channel_transitions_server.png
      :width: 100%
.. |circuit-client| image:: _static/command_triggered_circuit_transitions_client.png
      :target: _static/command_triggered_circuit_transitions_client.png
      :width: 100%
.. |circuit-server| image:: _static/command_triggered_circuit_transitions_server.png
      :target: _static/command_triggered_circuit_transitions_server.png
      :width: 100%

+------------------+------------------+
| Channel (Client) | Channel (Server) |
|                  |                  |
| |channel-client| | |channel-server| |
+------------------+------------------+
| Circuit (Client) | Circuit (Server) |
|                  |                  |
| |circuit-client| | |circuit-server| |
+------------------+------------------+

Special Constants
=================

Caproto uses special constants to represent the states of the state machine:

.. data:: SEND_SEARCH_REQUEST
          AWAIT_SEARCH_RESPONSE
          SEND_SEARCH_RESPONSE
          SEND_VERSION_REQUEST
          AWAIT_VERSION_RESPONSE
          SEND_VERSION_RESPONSE
          SEND_CREATE_CHAN_REQUEST
          AWAIT_CREATE_CHAN_RESPONSE
          SEND_CREATE_CHAN_RESPONSE
          CONNECTED
          MUST_CLOSE
          CLOSED
          DISCONNECTED
          IDLE
          FAILED

For example, a new VirtualCiruit starts with these states:

.. ipython:: python

    circuit = caproto.VirtualCircuit(our_role=caproto.CLIENT,
                                     address=('0.0.0.0', 5555),
                                     priority=0)
    circuit.states

When a :class:`VersionRequest` is sent through the VirtualCircuit, both the
client and the server state update.

.. ipython:: python

    circuit.send(caproto.VersionRequest(version=13, priority=0));
    circuit.states

And we can test the current state using constants like
:class:`SEND_VERSION_RESPONSE`.

.. ipython:: python

    circuit.states[caproto.SERVER] is caproto.SEND_VERSION_RESPONSE

Notice the special constants to represent which role a peer is playing.

.. data:: CLIENT
          SERVER

Special constants are also used to represent the "direction" of a command.

.. data:: RESPONSE
          REQUEST

Another special constant serves as a sentinel "Command" returned by
:func:`read_from_bytestream` when more data needs to be received before any new
Commands can be parsed.

.. data:: NEED_DATA

Similarly, the sentinel :class:`DISCONNECTED` is re-used as a "Command"
allowing for consistent handling of disconnection events through the command
queues.

.. data:: DISCONNECTED
   :noindex:

The VirtualCircuit object
=========================

.. autoclass:: VirtualCircuit

    .. attribute:: our_role

        :class:`caproto.CLIENT` or :class:`caproto.SERVER`

    .. attribute:: log

        Python logger instance

    .. attribute:: host

        peer host name

    .. attribute:: port

        peer port number

    .. attribute:: key

        a unique identifer for this instance: :data:`((host, port), priority)`

    .. automethod:: send
    .. automethod:: recv
    .. automethod:: process_command
    .. automethod:: disconnect
    .. automethod:: new_channel_id
    .. automethod:: new_subscriptionid
    .. automethod:: new_ioid

The Broadcaster object
======================

.. autoclass:: Broadcaster

    .. attribute:: our_role

        :class:`caproto.CLIENT` or :class:`caproto.SERVER`

    .. attribute:: log

        Python logger instance

    .. automethod:: send
    .. automethod:: recv
    .. automethod:: process_commands
    .. automethod:: register

Channel objects
===============

These objects are used internally by :class:`VirtualCircuit` to track the state
of individual channels. The user can optionally use them as a convenience for
generating valid commands.

.. autoclass:: ClientChannel

    .. automethod:: version
    .. automethod:: host_name
    .. automethod:: client_name
    .. automethod:: create
    .. automethod:: read
    .. automethod:: write
    .. automethod:: subscribe
    .. automethod:: unsubscribe
    .. automethod:: clear

.. autoclass:: ServerChannel

    .. automethod:: version
    .. automethod:: create
    .. automethod:: create_fail
    .. automethod:: read
    .. automethod:: write
    .. automethod:: subscribe
    .. automethod:: unsubscribe
    .. automethod:: clear
    .. automethod:: disconnect

.. _payload_data_types:

Payload Data Types
==================

Channel Access implements a system of data structures ("Database Records") that
encode metadata like time, alarm status, and control limits with the data
value(s). Each Channel Access data type has an integer ID, encoded by caproto
in the :class:`ChannelType` enum:

.. autoclass:: ChannelType

    .. attribute:: STRING = 0
    .. attribute:: INT = 1
    .. attribute:: FLOAT = 2
    .. attribute:: ENUM = 3
    .. attribute:: CHAR = 4
    .. attribute:: LONG = 5
    .. attribute:: DOUBLE = 6

    .. attribute:: STS_STRING = 7
    .. attribute:: STS_INT = 8
    .. attribute:: STS_FLOAT = 9
    .. attribute:: STS_ENUM = 10
    .. attribute:: STS_CHAR = 11
    .. attribute:: STS_LONG = 12
    .. attribute:: STS_DOUBLE = 13

    .. attribute:: TIME_STRING = 14
    .. attribute:: TIME_INT = 15
    .. attribute:: TIME_FLOAT = 16
    .. attribute:: TIME_ENUM = 17
    .. attribute:: TIME_CHAR = 18
    .. attribute:: TIME_LONG = 19
    .. attribute:: TIME_DOUBLE = 20

    .. attribute:: GR_STRING = 21
    .. attribute:: GR_INT = 22
    .. attribute:: GR_FLOAT = 23
    .. attribute:: GR_ENUM = 24
    .. attribute:: GR_CHAR = 25
    .. attribute:: GR_LONG = 26
    .. attribute:: GR_DOUBLE = 27

    .. attribute:: CTRL_STRING = 28
    .. attribute:: CTRL_INT = 29
    .. attribute:: CTRL_FLOAT = 30
    .. attribute:: CTRL_ENUM = 31
    .. attribute:: CTRL_CHAR = 32
    .. attribute:: CTRL_LONG = 33
    .. attribute:: CTRL_DOUBLE = 34

    .. attribute:: STSACK_STRING = 37
    .. attribute:: CLASS_NAME = 38


All commands that accept a ``data_type`` argument expect one of these
:class:`ChannelType` attributes or the corresponding integer. Here some valid
examples using the simple "native" types.

.. code-block:: python

    import caproto as ca

    ReadNotifyResponse(data_type=ca.ChannelType.FLOAT,
                       data_count=3,
                       data=(3.2, 5.3, 10.6),
                       metadata=None)

    ReadNotifyResponse(data_type=2,  # 2 is equivalent to ChannelType.FLOAT
                       data_count=3,
                       data=(3.2, 5.3, 10.6),
                       metadata=None)

    ReadNotifyResponse(data_type=ca.ChannelType.FLOAT,
                       data_count=1,
                       data=(3.1,),  # scalars must be given inside an iterable
                       metadata=None)

    ReadNotifyResponse(data_type=ca.ChannelType.INT,
                       data_count=5,
                       data=numpy.array([7, 21, 2, 4, 5], dtype='i2'),
                       metadata=None)

And here are some examples using the compound types that include metadata. The
metadata is packed into a ``ctypes.BigEndianStructure`` with the appropriate
fields. The caller can handle the struct directly and pass it in:

.. code-block:: python

    metadata = ca.DBR_TIME_DOUBLE(1, 0, 3, 5)
    ReadNotifyResponse(data_type=ca.ChannelType.TIME_DOUBLE,
                       data_count=1,
                       data=(7,),
                       metadata=metadata)

or the caller can pass the values as a tuple and let caproto fill in the
struct:

.. code-block:: python

    ReadNotifyResponse(data_type=ca.ChannelType.TIME_DOUBLE,
                       data_count=5,
                       data=(7,),
                       metadata=(1, 0, 3, 5))

Exceptions
==========

All exceptions directly raised by caproto inherit from :class:`CaprotoError`.

Errors like :class:`CaprotoKeyError` inherit from both :class:`CaprotoError`
and the built-in Python :class:`KeyError`.

The only special exceptions raised by caproto are :class:`LocalProtocolError`
and :class:`RemoteProtocolError`. These inherit from
:class:`ProtocolError`.

.. autoclass:: LocalProtocolError
.. autoclass:: RemoteProtocolError
