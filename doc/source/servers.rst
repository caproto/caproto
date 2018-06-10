=======
Servers
=======

Caproto includes three implementations of a Channel Access server for three
different Python concurrency libraries:

* asyncio (built in to Python)
* curio
* trio

The :doc:`IOC code <iocs>` abstracts out the particular server implementation,
so IOC authors do not need to interact with the server API directly. The
low-level server API is still experimental and subject to change, and it is not
yet documented here. We refer interested developers to the source code in
``caproto.asyncio.server``, ``caproto.curio.server``, and
``caproto.trio.server``.
