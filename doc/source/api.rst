.. currentmodule:: caproto

*****************
API Documentation
*****************

.. contents::

Commands
========

Caproto lets you work with Channel Access communication in terms of *Commands*
instead of thinking in terms of bytes.

Take :class:`VersionRequest` as an example.

.. ipython:: python

    import caproto
    com = caproto.VersionRequest(version=13, priority=0)

A Command has a useful repr:

.. ipython:: python

    com

Every Command has a :data:`header` and a :data:`payload`. The data in them
fully describe the Command. The :data:`header` has generically-named fields
provided by the Channel Access specification.

.. ipython:: python

    com.header

These names are rather opaque, but each Command provides accessors its data
with more obvious names, corresponding to the names in the repr.

.. ipython:: python

    com.version
    com.priority

This is a complete list of the Commands. (They are sorted in Command ID order,
designated by the Channel Access spec.)

.. autoclass:: VersionRequest
.. autoclass:: VersionResponse
.. autoclass:: SearchRequest
.. autoclass:: SearchResponse
.. autoclass:: NotFoundResponse
.. autoclass:: EchoRequest
.. autoclass:: EchoResponse
.. autoclass:: RsrvIsUpResponse
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
| |channel-client| | |channel-server| |
+------------------+------------------+
| |circuit-client| | |circuit-server| |
+------------------+------------------+

Special Constants
=================

Caproto uses special constants to represent the states of the state machine:

.. data:: SEND_SEARCH_REQUEST
          AWAIT_SEARCH_RESPONSE
          SEND_SEARCH_RESPONSE
          NEED_CIRCUIT
          SEND_VERSION_REQUEST
          AWAIT_VERSION_RESPONSE
          SEND_VERSION_RESPONSE
          SEND_CREATE_CHAN_REQUEST
          AWAIT_CREATE_CHAN_RESPONSE
          SEND_CREATE_CHAN_RESPONSE
          CONNECTED
          MUST_CLOSE
          CLOSED
          IDLE
          ERROR

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

Notice the special constants to represent which role a peer is playing,

.. data:: CLIENT
          SERVER

Special constants are also used to represent the nature of a command

.. data:: RESPONSE
          REQUEST

and as a sentinel "Command" returned by :meth:`Broadcaster.next_command` and
:meth:`VirtualCircuit.next_command` when more data needs to be received
before any new Commands can be parsed.

.. data:: NEED_DATA

Borrowing a trick (one of many!) from the h11 project, these special constants
are modeled after ``None``: they’re singletons, their ``__repr__()`` is
their name, and you compare them with ``is``.  They are also *instances of
themselves*. This can be useful if you have some object ``obj`` that might be a
Command or might be a sentinel (e.g. :data:`NEED_DATA`). You can always call
``type(obj)`` and get something useful.

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
    .. automethod:: next_command
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
    .. automethod:: next_command
    .. automethod:: new_search_id
    .. automethod:: search
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
    .. automethod:: clear
    .. automethod:: read
    .. automethod:: write
    .. automethod:: subscribe
    .. automethod:: unsubscribe

.. autoclass:: ServerChannel

    .. automethod:: version
    .. automethod:: create
    .. automethod:: clear
    .. automethod:: read
    .. automethod:: write
    .. automethod:: subscribe
    .. automethod:: unsubscribe

Payload Data Types
==================

(Implemented but not yet documented.)

Exceptions
==========

All exceptions directly raised by caproto inherit from :class:`CaprotoError`.

Errors like :class:`CaprotoKeyError` inherit from both :class:`CaprotoError`
and the built-in Python `KeyError`.

The only special exceptions raised by caproto are :class:`LocalProtocolError`
and :class:`RemoteProtocolError`. These inherit from
:class:`ProtocolError`.

.. autoclass:: LocalProtocolError
.. autoclass:: RemoteProtocolError
