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

Useful snippets
===============

To turn on maximal logging (usually way too much information!) use

.. code-block:: python

    import logging
    logging.getLogger('caproto').setLevel('DEBUG')

To log (non-batch) read/write requests and read/write/event responses in the
threading and pyepics-compat clients:

.. code-block:: python

   import logging
   logging.getLogger('caproto.ch').setLevel('DEBUG')

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

.. code-block:: python

    caproto.set_handler(color=False)

.. autofunction:: caproto.set_handler
