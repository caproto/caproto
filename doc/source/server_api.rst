**********
Server API
**********


Data Containers
===============

Core
----

The following are the underlying, lowest-level classes for holding data which
can be sent over an EPICS V3 channel in caproto.

Numeric Data
^^^^^^^^^^^^

.. inheritance-diagram::
    caproto.ChannelData
    caproto.ChannelDouble
    caproto.ChannelFloat
    caproto.ChannelInteger
    caproto.ChannelShort
    :parts: 1

.. autosummary::
    :toctree: generated

    caproto.ChannelData
    caproto.ChannelDouble
    caproto.ChannelFloat
    caproto.ChannelInteger
    caproto.ChannelShort

String or Byte Data
^^^^^^^^^^^^^^^^^^^

.. inheritance-diagram::
    caproto.ChannelByte
    caproto.ChannelChar
    caproto.ChannelEnum
    caproto.ChannelString
    :parts: 1

.. autosummary::
    :toctree: generated

    caproto.ChannelByte
    caproto.ChannelChar
    caproto.ChannelEnum
    caproto.ChannelString
    :parts: 1

Base Class
^^^^^^^^^^

The above share methods from their common (internal) base class
:class:`~caproto._data.ChannelData`.

.. autosummary::
    :toctree: generated

    ~caproto._data.ChannelData


PvpropertyData
--------------

pvproperty builds on top of ChannelData with the following classes, separated
by whether or not they are read-only.

.. autosummary::
    :toctree: generated

    caproto.server.PvpropertyData


Read/write
^^^^^^^^^^

.. inheritance-diagram::
    caproto.server.PvpropertyBoolEnum
    caproto.server.PvpropertyByte
    caproto.server.PvpropertyChar
    caproto.server.PvpropertyData
    caproto.server.PvpropertyDouble
    caproto.server.PvpropertyEnum
    caproto.server.PvpropertyString
    :top-classes: caproto._data.ChannelData,caproto._data.ChannelDouble,caproto._data.ChannelFloat,caproto._data.ChannelInteger,caproto._data.ChannelShort,caproto._data.ChannelByte,caproto._data.ChannelChar,caproto._data.ChannelEnum,caproto._data.ChannelString
    :parts: 1

.. autosummary::
    :toctree: generated

    caproto.server.PvpropertyBoolEnum
    caproto.server.PvpropertyByte
    caproto.server.PvpropertyChar
    caproto.server.PvpropertyDouble
    caproto.server.PvpropertyEnum
    caproto.server.PvpropertyFloat
    caproto.server.PvpropertyInteger
    caproto.server.PvpropertyReadOnlyData
    caproto.server.PvpropertyShort
    caproto.server.PvpropertyString

Read-only
^^^^^^^^^

Read-only data classes mix in with
:class:`~caproto.server.PvpropertyReadOnlyData`.

.. inheritance-diagram::
    caproto.server.PvpropertyBoolEnumRO
    caproto.server.PvpropertyByteRO
    caproto.server.PvpropertyCharRO
    caproto.server.PvpropertyData
    caproto.server.PvpropertyDoubleRO
    caproto.server.PvpropertyEnumRO
    caproto.server.PvpropertyStringRO
    :top-classes: caproto._data.ChannelData,caproto._data.ChannelDouble,caproto._data.ChannelFloat,caproto._data.ChannelInteger,caproto._data.ChannelShort,caproto._data.ChannelByte,caproto._data.ChannelChar,caproto._data.ChannelEnum,caproto._data.ChannelString
    :parts: 1

.. autosummary::
    :toctree: generated

    caproto.server.PvpropertyBoolEnumRO
    caproto.server.PvpropertyByteRO
    caproto.server.PvpropertyCharRO
    caproto.server.PvpropertyDoubleRO
    caproto.server.PvpropertyEnumRO
    caproto.server.PvpropertyFloatRO
    caproto.server.PvpropertyIntegerRO
    caproto.server.PvpropertyShortRO
    caproto.server.PvpropertyStringRO


High-level API / pvproperty magic
=================================

.. autosummary::
    :toctree: generated

    caproto.server.PVSpec
    caproto.server.expand_macros


.. autosummary::
    :toctree: generated

    caproto.server.PVGroup
    caproto.server.pvproperty
    caproto.server.PvpropertyData
    caproto.server.SubGroup
    caproto.server.pvfunction
    caproto.server.expand_macros
    caproto.server.get_pv_pair_wrapper
    caproto.server.scan_wrapper

Command-line Helpers
--------------------

Tools for helping to generate command-line argument parsers for use with
IOCs.

.. autosummary::
    :toctree: generated

    caproto.server.template_arg_parser
    caproto.server.ioc_arg_parser
    caproto.server.run

Advanced / Internal
-------------------

The following are related to the internal mechanisms that PVGroup and
pvproperty rely on.

.. autosummary::
    :toctree: generated

    caproto.server.server.FieldProxy
    caproto.server.server.FieldSpec
    caproto.server.server.NestedPvproperty
    caproto.server.server.PVGroupMeta


Library-agnostic server core
============================

Core Classes
------------

These are mostly as-is by all server implementations.

.. autosummary::
    :toctree: generated

    caproto.server.AsyncLibraryLayer
    caproto.server.common.Subscription
    caproto.server.common.SubscriptionSpec


Base Classes
------------

These are intended to be subclassed to implement support for a new async
library.

.. autosummary::
    :toctree: generated

    caproto.server.common.Context
    caproto.server.common.VirtualCircuit

Exceptions
----------

.. autosummary::
    :toctree: generated

    caproto.server.common.DisconnectedCircuit
    caproto.server.common.LoopExit


asyncio server
==============

Implementation classes
----------------------

Classes built on top of the library-agnostic core, used to implement asyncio
functionality.

.. autosummary::
    :toctree: generated

    caproto.asyncio.server.AsyncioAsyncLayer
    caproto.asyncio.server.Context
    caproto.asyncio.server.Event
    caproto.asyncio.server.ServerExit
    caproto.asyncio.server.VirtualCircuit

Helper functions
----------------

.. autosummary::
    :toctree: generated

    caproto.asyncio.server.run
    caproto.asyncio.server.start_server

Curio server
============


Implementation classes
----------------------

Classes built on top of the library-agnostic core, used to implement asyncio
functionality.

.. inheritance-diagram::
    caproto.curio.server.Context
    caproto.curio.server.VirtualCircuit

.. autosummary::
    :toctree: generated

    caproto.curio.server.CurioAsyncLayer
    caproto.curio.server.Context
    caproto.curio.server.Event
    caproto.curio.server.ServerExit
    caproto.curio.server.VirtualCircuit

Helper functions
----------------

.. autosummary::
    :toctree: generated

    caproto.curio.server.run
    caproto.curio.server.start_server

Miscellaneous
--------------

.. autosummary::
    :toctree: generated

    caproto.curio.server.QueueWithFullError
    caproto.curio.server.QueueFull
    caproto.curio.server.UniversalQueue

Trio server
===========

Implementation classes
----------------------

Classes built on top of the library-agnostic core, used to implement asyncio
functionality.

.. inheritance-diagram::
    caproto.trio.server.Context
    caproto.trio.server.VirtualCircuit

.. autosummary::
    :toctree: generated

    caproto.trio.server.TrioAsyncLayer
    caproto.trio.server.Context
    caproto.trio.server.Event
    caproto.trio.server.ServerExit
    caproto.trio.server.VirtualCircuit

Helper functions
----------------

.. autosummary::
    :toctree: generated

    caproto.trio.server.run
    caproto.trio.server.start_server
