******************
Synchronous Client
******************

.. currentmodule:: caproto.sync.client

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

The synchronous client optimizes for simplicity of implementation over
performance. This has its uses but for high-performance applications one of
the other clients, such as the :doc:`threading-client`, should be used.

Tutorial
========

.. ipython:: python
    :suppress:

    run_example('caproto.ioc_examples.random_walk')

In a separate shell, start one of caproto's demo IOCs.

.. code-block:: bash

    $ python3 -m caproto.ioc_examples.random_walk
    PVs: ['random_walk:dt', 'random_walk:x']

Now, in Python we will talk to it using caproto's synchronous client:

.. ipython:: python

    from caproto.sync.client import read
    res = read('random_walk:dt')
    res

This object is a human-friendly representation of the server's response. The
raw bytes of that response are:

.. ipython:: python

    bytes(res)

Access particular fields in the response using attribute ("dot") access on
``res``.

.. ipython:: python

    res.data

.. note::

    **Performance Note**

    The underlying metadata and data are stored in efficient, contiguous-memory
    data structures.

    .. ipython:: python

        res.header  # a ctypes.BigEndianStructure
        res.buffers  # a collection of one or more buffers

    They were received directly from the socket into these structure with no
    intermediate copies. Accessing the ``res.data`` --- which returns a
    ``numpy.ndarray`` or ``array.array`` --- provides a view onto that same
    memory with no copying (if the data was received from the socket all at
    once) or one copy (if the data bridged multiple receipts).

Let us set the value to ``1``.

.. ipython:: python

    from caproto.sync.client import write 
    write('random_walk:dt', 1)

The function returns immediately and returns ``None``. To wait for confirmation
that the write has been successfully processed by the server, use the
``notify`` keyword argument:

.. ipython:: python

    from caproto.sync.client import write 
    write('random_walk:dt', 1, notify=True)

Let us now monitor a channel. The server updates the ``random_walk:x`` channel
periodically. (The period is set by ``random_walk:dt``.) We can subscribe
to updates. First, we define a :class:`Subscription`.

.. ipython:: python

    from caproto.sync.client import subscribe
    sub = subscribe('random_walk:x')

Next, we a function that will be called whenever the server send an update.

.. ipython:: python

   responses = []
   def f(response):
       "On each update, print the data and cache the full response."
       responses.append(response)
       print(response.data)

We register this function with ``sub``.

.. ipython:: python

    sub.add_callback(f)

We can register multiple such function is we wish.

Because this is a *synchronous* client, processing subscriptions is a blocking
operation,. (See the :doc:`threading-client` to process subscriptions on a
separate, background thread.) To activate the subscription, call
``sub.block()``.

.. ipython::
    :verbatim:

    In [1]: sub.block()
    [14.14272394]
    [14.94322537]
    [15.35695388]
    [15.74301991]
    ^C

This call to ``sub.block()`` blocks indefinitely, passing responses to ``f`` as
they arrive. When we are satisfied, we can interrupt it with Ctrl+C (or by
calling ``sub.interrupt()`` from another thread).

Equivalently, use the top-level function :func:`block`, which can be used to
process multiple subscriptions concurrently:

.. ipython::
    :verbatim:

    In [1]: from caproto.sync.client import block

    In [2]: sub_dt = subscribe('random_walk:dt')

    In [3]: sub_x = subscribe('random_walk:x')

    In [4]: sub_dt.add_callback(f)
    Out[4]: 0

    In [5]: sub_x.add_callback(f)
    Out[5]: 0

    In [6]: block(sub_x, sub_dt)
    [63.34866867]
    [1.]
    [63.53448681]
    [64.30532391]
    ^C

.. ipython:: python
    :suppress:

    # Clean up IOC processes.
    for p in processes:
        p.terminate()
    for p in processes:
        p.wait()

API Documentation
=================

.. autofunction:: read
.. autofunction:: write
.. autofunction:: subscribe
.. autofunction:: block
.. autofunction:: interrupt
.. autofunction:: read_write_read
.. autoclass:: Subscription
   :members:

