=======
Servers
=======

.. note::

    If your goal is to write IOCs, see :doc:`iocs`.

Caproto includes three implementations of a Channel Access server for three
different Python concurrency libraries:

* asyncio (built in to Python)
* curio
* trio

To learn more about concurrency in Python (and in general) we recommend these
introductory resources, suggested by a caproto user:

* `Speed up your Python program with concurrency <https://realpython.com/python-concurrency/>`_
* `Async IO in Python: A Complete Walkthrough <https://realpython.com/async-io-python/>`_

The :doc:`IOC code <iocs>` abstracts out the particular server implementation,
so IOC authors do not need to interact with the server API directly. The
low-level server API is still experimental and subject to change, and it is not
yet documented here. We refer interested developers to the source code in
``caproto.asyncio.server``, ``caproto.curio.server``, and
``caproto.trio.server``.
