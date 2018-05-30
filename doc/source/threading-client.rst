****************
Threading Client
****************

.. currentmodule:: caproto.threading.client

.. ipython:: python
    :suppress:
    
    import sys
    import subprocess
    import time
    processes = []
    def run_example(module_name, *args):
        p = subprocess.Popen([sys.executable, '-m', module_name] + list(args))
        processes.append(p)  # Clean this up at the end.
        time.sleep(1)  # Give it time to start up.

The threading client is a high-performance client that uses Python built-in
threading module to manage concurrency.

Tutorial
========

.. ipython:: python
    :suppress:

    run_example('caproto.ioc_examples.random_walk')

In a separate shell, start one of caproto's demo IOCs.

.. code-block:: bash

    $ python3 -m caproto.ioc_examples.random_walk
    PVs: ['random_walk:dt', 'random_walk:x']

Now, in Python we will talk to it using caproto's threading client. Start by
creating a :class:`Context`.

.. ipython:: python

    from caproto.threading.client import Context, SharedBroadcaster
    ctx = Context(SharedBroadcaster())

The :class:`Context` object tracks the state of connections in progress.
We can use it to request new connections.

.. ipython:: python

    x, dt = ctx.get_pvs('random_walk:x', 'random_walk:dt')

:meth:`Context.get_pvs`  accepts an arbitrary number of PV names and
immediately returns a collection of :class:`PV` objects representing each name.
In a background thread, the Context searches for an EPICS server that provides
that PV name and then connects to it. The PV object displays its connection
state:

.. ipython:: python

    dt

The Context displays aggregate information about the state of all connections.

.. ipython:: python

    ctx

With these preliminaries done, let's finally read the PV.

.. ipython:: python

    res = dt.read()
    res

This object is a human-friendly representation of the server's response. The
raw bytes of that response are:

.. ipython:: python

    bytes(res)

Access particular fields in the response using attribute ("dot") access on ``res``.

.. ipython:: python

    res.data

Let us set the value to ``1``.

.. ipython:: python

    dt.write([1])

Let us now monitor a channel. The server updates the ``random_walk:x`` channel
periodically. (The period is set by ``random_walk:dt``.) We can subscribe
to updates.

.. ipython:: python
    :suppress:

    # Clean up IOC processes.
    for p in processes:
        p.terminate()
    for p in processes:
        p.wait()

API Documentation
=================

.. autoclass:: SharedBroadcaster
.. autoclass:: Context
