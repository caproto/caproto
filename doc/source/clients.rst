*******
Clients
*******

Caproto implements several clients, all built on the same core. This page aims
to help you choose which one is best for your application.

The :doc:`sync-client` is simplistic but functional, easy to read and
understand what happens with a single operation. It is perfectly fine to
use directly, but should generally not be used to build larger programs. It
opts for simplicity over performance.

The :doc:`threading-client` is a high-performance client and the one with the
most features and testing behind it. We generally recommend this one.

The :doc:`pyepics-compat-client` should only be used if you want to have
compatibility with some existing pyepics-based code.

Use the :doc:`async-clients` if you wish to write client code that takes
advantage of cooperative multitasking with asyncio.

The :doc:`command-line-client` provides commandline tools (``caproto-get``,
``caproto-put``, ...) that are drop-in replacements for their analogues in
EPICS' reference implementation (``caget``, ``caput``, ...). They are backed by
the synchronous client.

.. toctree::
   :maxdepth: 2

   command-line-client
   sync-client
   threading-client
   pyepics-compat-client
   async-clients
