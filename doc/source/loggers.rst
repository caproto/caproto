.. currentmodule:: caproto
.. _loggers:

*******
Logging
*******

.. versionchanged:: 0.4.0

   Caproto's use of Python logging framework has been completely reworked to
   follow Python's own guidelines for best practices.

Caproto uses Python's logging framework, following Python's own guidelines for
best practices. Users with a sophisticated knowledge of that framework may wish
to skip ahead to :ref:`logger_api`. Convenience functions are provided to
streamline simple cases.

Command-line tools
==================

Caproto's commandline tools, including both the clients (e.g.  ``caproto-get``)
and the server modules (``python3 -m caproto.ioc_examples.*``), accept ``-v``
and ``-vvv`` to control log verbosity.

Basic Examples
==============

In scripts or interactive sessions, the convenience function
:func:`set_handler` can address common use cases succinctly. An equivalent
configuration can be achieved using the standard Python logging interafce.

Log warnings
------------

This is the recommended standard setup.

.. code-block:: python

   from caproto import set_handler
   set_handler()

It will display log records of ``WARNING`` level or higher in the terminal
(standard out) with a formatting tailored to caproto.

Maximum verbosity
-----------------

This will display all Channel Access commands sent or received, comprising a
complete account of the Channel Access traffic handled by caproto.

.. code-block:: python

   from caproto import set_handler
   set_handler(level='DEBUG')

.. important::

   We strongly recommend setting levels on *handlers* not on *loggers*.
   In previous versions of caproto, we recommended adjusting the level on the
   *logger*, as in ``some_pv.log.setLevel('DEBUG')``. We now recommended
   that you *avoid* setting levels on loggers because it would affect all
   handlers downstream, potentially inhibiting some other part of the program
   from collecting the records it wants to collect.

Log to a file
-------------

This will direct all log messages to a file, instaed to the terminal (standard
out).

.. code-block:: python

    from caproto import set_handler
    set_handler(file='/tmp/caproto.log', level='DEBUG')

Filter by PV, Address, or Role
------------------------------

To debug a particular issue, it is often convenient to focus on log records
related to a specific PV, address, or role (CLIENT or SERVER). To add filters,
you will need a reference to a handler. Typically, you will want to set the
handler to ``'DEBUG'`` or ``'INFO'``. Capture its return value in a variable.

.. code-block:: python

   handler = set_handler(level='INFO')

You can later access the current caproto global handler at any point by using
:func:`get_handler`.

.. code-block:: python

   from caproto import get_handler
   handler = get_handler()

Several easy-to-use filters allow users to very specifically customize logging,
based on one or more of the following:

#. Show only records related to specific PVs---or partial PVs with a ``*``
   wildcard.

   .. code-block:: python

       from caproto import PVFilter

       handler.addFilter(PVFilter(['random_walk:*', 'simple:B'])

#. Show only records related to specific hosts or addresses.

   .. code-block:: python

      from caproto import AddressFilter

      # Multiple ways to specify:
      handler.addFilter(AddressFilter(['10.2.227.105']))  # host (all ports)
      handler.addFilter(AddressFilter(['10.2.227.105:59384']))  # host:port
      handler.addFilter(AddressFilter(('10.2.227.105', 59384))  # equivalent

#. In special situations (usually testing) one process may be acting as client
   and server, and it may be useful to filter by role (``'CLIENT'`` or
   ``'SERVER'``).

   .. code-block:: python

      from caproto import RoleFilter

      handler.addFilter(RoleFilter('CLIENT'))

Note that if multiple filters are added to the same handler, they are composed
using "logical AND" by Python's logging framework. See the section on
:ref:`logging_filters` below for more information or composing filters or
writing complex filters.

.. important::

   In the examples above we add filters to handlers, as in
   ``handler.addFilter(...)``. The Python logging framework also allows filters
   to be added to *loggers*, as in ``some_pv.log.addFilter(...)``. But we
   recommend that you *avoid* adding filters to loggers because it would affect
   all handlers downstream, potentially inhibiting some other part of the
   program from collecting the records it wants to collect.

See :ref:`threading_loggers` for more handy examples.

.. _logger_api:

Caproto's Logging-Related API
=============================

Loggers
-------

Here is the complete list of loggers used by caproto.

* ``'caproto'`` --- the logger to which all caproto messages propagate
* ``'caproto.ch'`` --- INFO-logs changes to channel connection state on all
  channels; DEBUG-logs read/write requests and read/write/event responses for
  the threading client (other async clients TODO)
* ``'caproto.circ'`` --- DEBUG-logs commands sent and received over TCP
* ``'caproto.bcast'`` --- logs command sent and received over UDP
* ``'caproto.bcast.search'`` --- logs seach-related commands
* ``'caproto.ctx'`` -- logs updates from Contexts, such (on the client side)
  how many search requests are still awaiting replies and (on the server side)
  the number of connected clients and performance metrics when under load

Certain objects in the caproto API, including Context, VirtualCircuits,
Broadcasters, and PVs, have a ``log`` attribute, referencing a
:py:class:`logging.Logger` or a :py:class:`logging.LoggerAdapter`` that
encapsulates one of the loggers above with some context-specific information,
enumerated below.

Extra Context in LogRecords
---------------------------

The records issued by caproto's loggers may have some or all of the following
attributes, as applicable:

* ``pv`` --- PV name
* ``our_address`` --- local interface, given as ``(host, port)``
* ``their_address`` --- address of peer, given as ``(host, port)``
* ``direction`` --- indicating whether the message is being sent or received
* ``role`` --- ``'CLIENT'`` or ``'SERVER'``

.. _logging_filters:

Filters
-------

Python's logging framework supports using simple functions as filters, as in:

.. code-block:: python

   def my_filter(record):
       if hasattr(record, 'pv'):
           return record.pv == 'simple:A'
       return False

   handler.add_filter(my_filter)

An *ad hoc* function such as the above is the best approach for complex
filtering. But for simple filtering by PV, address, or role, caproto provides
built-in filters. Note the functionality of the ``level`` and ``exclusive``
arguments, explained the docstrings below, which aim to support composition of
multiple filters.:

.. autoclass:: PVFilter
.. autoclass:: AddressFilter
.. autoclass:: RoleFilter

Formatter
---------

.. autoclass:: LogFormatter

Global Handler
---------------

By default, following Python's recommendation, caproto does not install any
handlers, but it provides a function to install a suitable handler in one line.

The convenience function :func:`set_handler` may be used to write records at a
specific level of verbosity to the terminal (standard out) or a file. It is
designed to streamline common use cases without interfering with more
sophisticated use cases.

.. autofunction:: set_handler
.. autofunction:: get_handler

Python Logging Illustration
===========================

The flow of log event information in loggers and handlers is illustrated in the following diagram:

.. image:: https://docs.python.org/3/_images/logging_flow.png

For further reference, see the Python 3 logging howto:
https://docs.python.org/3/howto/logging.html#logging-flow

As an illustrative example, we will outline how a specific logging call from
inside caproto works it way through this system.

Suppose we set up a handler aimed at a file:

.. code-block:: python

    file_handler = logging.FileHandler('caproto.log')
    file_handler.setLevel('DEBUG')
    logger.addHandler(file_filter)

And another aimed at `Logstash <https://www.elastic.co/products/logstash>`_:

.. code-block:: python

    import logstash  # requires python-logstash package
    logstash_handler = logstash.TCPLogstashHandler(<host>, <port>, version=1)
    logger.addHandler(logstash_handler)

TODO: Discuss ``logging.disable``, ``getEffectiveLevel``, etc.
