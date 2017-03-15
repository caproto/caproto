.. currentmodule:: caproto

*****************
API Documentation
*****************

.. contents::

Components
==========

.. autoclass:: Hub

    .. automethod:: new_circuit
    .. automethod:: get_circuit
    .. automethod:: new_channel

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

Commands
========

.. automodule:: caproto._commands

The State Machine
=================

Headers
=======

.. automodule:: caproto._headers

DBR Structs
===========

.. automodule:: caproto._dbr

Exceptions
==========
