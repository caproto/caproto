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

It also uses special constants to represent which role a peer is playing,

.. data:: CLIENT
          SERVER

to represent the nature of a command,

.. data:: RESPONSE
          REQUEST

and as a sentinel "Command" indicating that more data needs to be received
before any new Commands can be parsed.

.. data:: NEED_DATA

Borrowing a trick from the h11 project, these sentinels are *instances of
themselves*. This can be useful if you have some object ``obj`` that might be a
Command or might be a sentinel (e.g. :data:`NEED_DATA`). You can always call
``type(obj)`` and get something useful.

The VirtualCircuit object
=========================

.. autoclass:: VirtualCircuit

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

.. autoclass:: Hub

    .. automethod:: new_circuit
    .. automethod:: get_circuit
    .. automethod:: new_channel

Channel convenience objects
===========================

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


..
    Headers
    =======
    .. automodule:: caproto._headers
        :members:

DBR
===

.. automodule:: caproto._dbr
    :members:

Exceptions
==========

All exceptions directly raised by caproto inherit from :class:`CaprotoError`.

Errors like :class:`CaprotoKeyError` inherit from both :class:`CaprotoError`
and the built-in Python `KeyError`.

The only special exceptions raised by caproto are :class:`LocalProtocolError`
and :class:`RemoteProtocolError`. These inherit from
:class:`ChannelAccessProtocolError`.
