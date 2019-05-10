.. currentmodule:: caproto
.. _loggers:

*******
Loggers
*******

Caproto uses Python's built-in logging framework. The commandline interface,
including both the clients (e.g. ``caproto-get``) and the server modules
(``python3 -m caproto.ioc_examples.*``), accept ``-v`` and ``-vvv`` to control
log verbosity. In Python, any logger instance can accessed via its name as 
``logging.getLogger(logger_name)``. See the complete list off logger names used
by caproto, below. Because recalling the name is not always convenient, certain
objects in caproto's Python API expose a ``log`` attribute, such as ``pv.log``,
``pv.context.log`` and ``pv.circuit_manager.log``.

The flow of log event information in loggers and handlers is illustrated in the following diagram:

.. image:: https://docs.python.org/3/_images/logging_flow.png
For further reference, see the Python 3 logging howto:
https://docs.python.org/3/howto/logging.html#logging-flow


Useful snippets
===============

To get the caproto logger using Python's built-in logging framework:

.. code-block:: python

   import logging
   logger = logging.getLogger('caproto')

To add a stdout handler (i.e., one that prints messages to the standard output in your terminal) with level `DEBUG`:

.. code-block:: python

    std_handler = logging.StreamHandler()
    logger.addHandler(std_handler)
    std_handler.setLevel('DEBUG')

caproto offers a number of convenient methods for configuring logging.  The following
would replace the above code with only one line:
code above by one commmand:

.. code-block:: python

    from caproto import set_handler
    set_handler(level='DEBUG')

With this handler, you would see messages like the following:

.. code-block:: guess

    [D 15:19:14.132          client:  588] [CLIENT] Broadcaster command loop is running.
    [D 15:19:14.133          client:  719] [CLIENT] Broadcaster check for unresponsive servers loop is running.
    [D 15:19:14.134          client:  454] [CLIENT] [0.0.0.0:0] --->>> [127.0.0.1:5065] Sending 16 bytes to 127.0.0.1:5065
    [D 15:19:14.135          client:  454] [CLIENT] [0.0.0.0:0] --->>> [10.2.255.255:5065] Sending 16 bytes to 10.2.255.255:5065
    [D 15:19:14.136          client:  832] [CLIENT] Broadcaster search-retry thread has started.
    [D 15:19:14.136          client: 1079] [CLIENT] Context search-results processing loop has started.
    [D 15:19:14.137          client:  872] [CLIENT] Sending 6 SearchRequests

The logging framework is not only limited to printing to the console, of course.
For example, using Logstash - an open source tool for collecting, parsing, and
storing logs to a centralized database for future use - is also straightforward.
To send log messages to `<host>:<port>`, one might use the following:

.. code-block:: python

    import logstash
    logstash_handler = logstash.TCPLogstashHandler(<host>, <port>, version=1)
    logger.addHandler(logstash_handler)

To redirect logging output to a file, in this case `caproto.log`:

.. code-block:: python

    file_handler = logging.FileHandler('caproto.log')
    file_handler.setLevel('DEBUG')
    logger.addHandler(file_filter)

Filters
=======

Filters are where caproto's logging framework shines.
You could import thoese filters from caproto

.. code-block:: python

    from caproto import PVFilter, AddressFilter, RoleFilter

Several easy-to-use filters allow users to very specifically customize logging, based on one or more of the following:

1. `PV` names: using `PVFilter`, only PVs that match wildcard-style strings will be shown

.. code-block:: python

    std_handler.addFilter(PVFilter(['complex:*', 'simple:B'])

2. Addresses: using `AddressFilter`, only PVs on specific IP addresses (and optionally ports) will be displayed

.. code-block:: python

    std_handler.addFilter(AddressFilter(['10.2.227.105']))

3. Client/server roles: caproto provides both clients and servers - limit messages to one or the other.

.. code-block:: python

    std_handler.addFilter(RoleFilter('Client'))

For example, ``PVFilter(['complex:*', 'simple:B'], level='DEBUG', exclusive=False)`` meaning
You want to block any message below ``DEBUG`` level except it related ``complex:*`` or ``simple:B``, and
keep the env, config or misc message by ``exclusive=False``. Check API section of this page for more details

See :ref:`threading_loggers` for more handy examples.

Logger's level vs handler's level
=================================

Make sure you understand how level control loggging in logger and handler.
Both has method setLevel(...) which allow you do logger.setLevel(...) or handler.setLevel(...).
You may only have one logger in your package. But, mutiple handlers could be added to one logger.
Logger's level influence all handler. So the effective level is the intersection of logger's level
and handler's level.


Here, with a handler level of `INFO` and a logger level of `DEBUG`:

.. code-block:: python

    import logging
    logger = logging.getLogger('caproto')
    logger.setLevel('DEBUG')
    handler = logging.StreamHandler()
    handler.setLevel('INFO')
    logger.addHandler(handler)
    logger.debug('This is debug message')
    logger.info('This is info message')
    logger.warning('This is warn message')


The following log messages will be shown:

.. code-block:: python

    This is info message
    This is warn message

Whereas with a logger level of `WARNING`:

.. code-block:: python

    import logging
    logger = logging.getLogger('caproto')
    logger.setLevel('WARNING')
    handler = logging.StreamHandler()
    handler.setLevel('INFO')
    logger.addHandler(handler)
    logger.debug('This is debug message')
    logger.info('This is info message')
    logger.warning('This is warn message')


The following log messages will be displayed:

.. code-block:: python

    This is warn message

To avoid confused level setting, we recommend leave logger's level 'NOTSET' and use
handler's level domain independently.
DO NOT USE
.. code-block:: python
  logger.setLevel(...)

In caproto, you almost never want to addFilter to logger even you could. Because
there are always multiple(at least one by set_handler) handlers added to logger.
Logger level flow control will influence all handlers. If there is only one handler,
everything you want to be filtered on logger level could be filtered on handler level.
In conclusion, handler level filter is recommended.

Logger names
============

Here is the complete list of loggers used by caproto.

* ``'caproto'`` --- the logger to which all caproto messages propagate
* ``'caproto.ch'`` --- INFO-logs changes to channel connection state on all
  channels; DEBUG-logs read/write requests and read/write/event responses for
  the threading client (other async clients TODO)
* ``'caproto.ch.<name>'`` --- narrows to channel(s) with a given PV name, as in
  ``'caproto.ch.random_walk:x'``
* ``'caproto.ch.<name>.<priority>'`` --- narrows one channel with a given PV
  name and priority, as in ``'caproto.ch.random_walk:x.0'``
* ``'caproto.circ'`` --- DEBUG-logs commands sent and received over TCP
* ``'caproto.circ.<addr>'`` -- narrows to circuits connected to the address
  ``<addr>``, as in ``'caproto.circ.127.0.0.1:49384'``
* ``'caproto.circ.<addr>.<priority>'`` -- specifies example one circuit with a
  certain address and priority, as in ``'caproto.circ.127.0.0.1:49384.0'``
* ``'caproto.bcast'`` --- logs command sent and received over UDP
* ``'caproto.ctx'`` -- logs updates from Contexts, such (on the client side)
  how many search requests are still awaiting replies and (on the server side)
  the number of connected clients and performance metrics when under load
* ``'caproto.ctx.<id>'`` -- narrows to one specific Context instance ``ctx``
  where ``<id>`` ``str(id(ctx))``

Logging Handlers
================

By default, caproto prints log messages to the standard out by adding a
:class:`logging.StreamHandler` to the ``'caproto'`` logger at import time. You
can, of course, configure the handlers manually in the standard fashion
supported by Python. But a convenience function :func:`caproto.set_handler`,
makes it easy to address to common cases.

See the Examples section below.

API
===
.. autofunction:: caproto.set_handler
.. autoclass:: PVFilter
.. autoclass:: AddressFilter
.. autoclass:: RoleFilter
