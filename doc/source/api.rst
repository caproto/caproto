.. currentmodule:: caproto

*****************
API Documentation
*****************

.. contents::

Commands
========

Caproto lets you work with Channel Access communication in terms of *Commands*
instead of thinking in terms of bytes.

Every Command has a :data:`header` fields and a :data:`payload` field.

The :data:`header` has generically-named fields provided by the Channel Access
specification.

Each Command provides additional properties specific to that Command type.
These are merely aliases to the content in :data:`header` and :data:`payload`.

Their names match names of the Command's arguments and are used to generate a
nice repr.

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
.. autoclass:: RepeaterRegisterResponse
.. autoclass:: EventAddRequest
.. autoclass:: EventAddResponse
.. autoclass:: EventCancelRequest
.. autoclass:: EventCancelResponse
.. autoclass:: ReadRequest
.. autoclass:: ReadResponse
.. autoclass:: WriteRequest
.. autoclass:: WriteResponse
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
    .. automethod:: new_subscription_id
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


Headers
=======

.. automodule:: caproto._headers

DBR Structs
===========

.. automodule:: caproto._dbr

Exceptions
==========
