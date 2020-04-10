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
performance. This has its uses, as described below. But for high-performance
applications, use one of caproto's other clients such as the
:doc:`threading-client`.

Tutorial
========

.. ipython:: python
    :suppress:

    run_example('caproto.ioc_examples.random_walk')

In a separate shell, start one of caproto's demo IOCs.

.. code-block:: bash

    $ python3 -m caproto.ioc_examples.random_walk
    PVs: ['random_walk:dt', 'random_walk:x']

Now, in Python we will talk to it using caproto's synchronous client.

Read
----

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

By default, the client does not request any metadata

.. ipython:: python

   res.metadata

Use the ``data_type`` parameter to request a richer data type.

.. ipython:: python

   richer_res = read('random_walk:dt', data_type='time')
   richer_res.metadata
   richer_res.metadata.timestamp
   richer_res.metadata.stamp.as_datetime()  # a convenience method

See :func:`read` for more information on the values accepted by the
``data_type`` parameter.

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

Write
-----

Let us set the value to ``1``.

.. ipython:: python

    from caproto.sync.client import write
    write('random_walk:dt', 1)

The function returns ``None`` immediately. To wait for confirmation that the
write has been successfully processed by the server, use the ``notify`` keyword
argument. (This is not guaranteed to be supported by an EPICS server; it may
result in an ``ErrorResponse``.)

.. ipython:: python

    from caproto.sync.client import write
    write('random_walk:dt', 1, notify=True)

Subscribe ("Monitor")
---------------------

Let us now monitor a channel. The server updates the ``random_walk:x`` channel
periodically at some period set by ``random_walk:dt``. We can subscribe
to updates and fan them out to one or more user-defined callback functions.
First, we define a :class:`Subscription`.

.. ipython:: python

    from caproto.sync.client import subscribe
    sub = subscribe('random_walk:x')

Next, we define a callback function, a function that will be called whenever
the server sends an update. It must accept one positional argument.

.. ipython:: python

   responses = []
   def f(sub, response):
       """
       On each update, print the PV name and data
       Cache the full response in a list.
       """
       responses.append(response)
       print(sub.pv_name, response.data)

We register this function with ``sub``. We can register multiple such functions
is we wish.

.. ipython:: python

    token = sub.add_callback(f)

The ``token`` is just an integer which we can use to remove ``f`` later.

Because this is a *synchronous* client, processing subscriptions is a blocking
operation,. (See the :doc:`threading-client` to process subscriptions on a
separate, background thread.) To activate the subscription, call
``sub.block()``.

.. ipython::
    :verbatim:

    In [1]: sub.block()
    random_walk:x [14.14272394]
    random_walk:x [14.94322537]
    random_walk:x [15.35695388]
    random_walk:x [15.74301991]
    ^C

This call to ``sub.block()`` blocks indefinitely, sending a message to the
server to request future updates and then passing its responses to ``f`` as
they arrive. The server always sends at least one response immediately. When we
are satisfied, we can interrupt it with Ctrl+C (or by calling
``sub.interrupt()`` from another thread). The subscription may later be
reactivated by calling ``sub.block()`` again.

Recall that the user-defined function ``f`` printed the data from each response
and accumulated the response objects in a list. Indeed, we have captured four
responses.

.. ipython::
    :verbatim:

    In [2]: len(responses)
    Out[2]: 4

At any point we can remove a specific callback function:

.. ipython:: python

    sub.remove_callback(token)

or clear all the callbacks on a subscription:

.. ipython:: python

    sub.clear()

To activate multiple subscriptions concurrently, use the top-level function
:func:`block`, which accepts any number of :class:`Subscription` objects as
arguments. Again, use Ctrl+C to interrupt (or call :func:`interrupt` from
another thread).

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
    random_walk:x [63.34866867]
    random_walk:dt [1.]
    random_walk:x [63.53448681]
    random_walk:x [64.30532391]
    ^C

.. versionchanged:: 0.5.0

   The expected signature of the callback function was changed from
   ``f(response)`` to ``f(sub, response)``. For backward compatibility,
   functions with signature ``f(response)`` are still accepted, but caproto
   will issue a warning that a future release may require the new signature,
   ``f(sub, response)``.

.. warning::

    The callback registry in :class:`Subscription` only holds weak references
    to the user callback functions. If there are no other references to the
    function, it will be silently garbage collected and removed. Therefore,
    constructions like this do not work:

    .. code-block:: python

        sub.add_callback(lambda sub, response: print(response.data))

    The lambda function will be promptly garbage collected by Python and
    removed from ``sub`` by caproto. To avoid that, make a reference before
    passing the function to :meth:`Subscription.add_callback`.

    .. code-block:: python

        cb = lambda sub, response: print(response.data)
        sub.add_callback(cb)

    This can be surprising, but it is a standard approach for avoiding the
    accidental costly accumulation of abandoned callbacks.

Stateless Connection Handling
-----------------------------

As noted at the top, the synchronous client is optimized for simplicity of
implementation. While the other caproto clients use the notion of a *context*
to cache connections, the synchronous client creates a fresh connection for
each function call. This stateless design is sufficient to support the
:doc:`command-line interface <command-line-client>` and it can be useful for
debugging, but it is very inefficient for performing multiple operations on the
same channel.

For the common use case "read / write a new value / read again," the
synchronous client provides :func:`read_write_read`, which uses one connection
for all three operations. For anything more complicated than that, upgrade to
one of the other clients.

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
