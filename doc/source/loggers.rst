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

You could find python logging flow here.
https://docs.python.org/2/_images/logging_flow.png


Useful snippets
===============

Make sure you understand how level control loggging in logger.
and handler. Both has method setLevel(...) which allow you do logger.setLevel(...) or
handler.setLevel(...). You may only have one logger in your package. But, mutiple
handlers could be added to one logger. Logger's level influence all handler. So the
effective level is the intersection of logger's level and handler's level.


Here INFO will effect

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

.. code-block:: python

    This is info message
    This is warn message

Here WARNING will effect

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

.. code-block:: python

    This is warn message

To avoid confused level setting, we recommend leave logger's level 'NOTSET' and use
handler's level domain independently.

To log (non-batch) read/write requests and read/write/event responses in the
threading and pyepics-compat clients:

.. code-block:: python

   import logging
   logger = logging.getLogger('caproto')

To add a stdout handler with level, default level is WARNING

.. code-block:: python

    from caproto._log import set_handler
    std_handler = set_handler(level='DEBUG')
    logger.addHandler(std_handler)

To add logstash handler, this will pipe log message to elasticsearch to kibana on cmb03

.. code-block:: python

    import logstash
    logstash_handler = logstash.TCPLogstashHandler(<host>, <port>, version=1)
    logger.addHandler(logstash_handler)

To add file handler

.. code-block:: python

    file_handler = logging.FileHandler('caproto.log')
    file_handler.setLevel('DEBUG')
    logger.addHandler(file_filter)

To add filter

.. code-block:: python

    from caproto._log import PVFilter, AddressFilter, RoleFilter
    std_handler.addFilter(PVFilter(['complex:*', 'simple:B'], level='DEBUG', exclusive=False))
    std_handler.addFilter(AddressFilter(['10.2.227.105']))
    std_handler.addFilter(RoleFilter('Client', level = 'DEBUG'))

For example, ``PVFilter(['complex:*', 'simple:B'], level='DEBUG', exclusive=False)`` meaning
You want to block any message below level=DEBUG level except it related complex:* or simple:B and
keep the env, config or misc message by exclusive=False

In caproto, you almost never want to addFilter to logger even you could.
See :ref:`threading_loggers` for more handy examples.

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

.. autofunction:: caproto.set_handler
