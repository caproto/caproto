********************
Asynchronous Clients
********************

Developers interested in exploring the prototype asyncio client can poke around
the module :mod:`caproto.asyncio.client`. The design is analogous to the
threading client but using asyncio.

While this asyncio client is full-featured as compared to the threading client,
it has had minimal testing, usage, or review.

With that in mind, please let us know if it works for you, or you have feedback
for us.

For those that are looking for information about curio or trio clients, their
prototype implementations have been removed.

.. currentmodule:: caproto.asyncio.client

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

Tutorial
========

.. ipython:: python
    :suppress:

    run_example('caproto.ioc_examples.random_walk')

In a separate shell, start one of caproto's demo IOCs.

.. code-block:: bash

    $ python3 -m caproto.ioc_examples.random_walk --list-pvs
    [I 10:37:48.827       server:  133] Asyncio server starting up...
    [I 10:37:48.827       server:  146] Listening on 0.0.0.0:65442
    [I 10:37:48.829       server:  205] Server startup complete.
    [I 10:37:48.829       server:  207] PVs available:
        random_walk:dt
        random_walk:x


Connect
-------

.. note::

    To do this interactively, you will need a newer version of IPython >= 7
    that supports ``%autoawait``.

In Python we will talk to it using caproto's asyncio client. Start by enabling
``%autoawait``.

.. ipython:: python

    %autoawait on

Now, create a :class:`Context`.  A requirement for the asyncio client is that
the context must be created within the asyncio loop that will be using it, thus
it must be created in a coroutine.

.. ipython:: python

    from caproto.asyncio.client import Context

    async def new_context():
        return Context()

    ctx = await new_context()

The :class:`Context` object caches connections, manages automatic
re-connection, and tracks the state of connections in progress.  We can use it
to request new connections. Formulating requests for many PVs in a large batch
is efficient. In this example we'll just ask for two PVs.

.. ipython:: python

    x, dt = await ctx.get_pvs('random_walk:x', 'random_walk:dt')

:meth:`Context.get_pvs`  accepts an arbitrary number of PV names and
immediately returns a collection of :class:`PV` objects representing each name.
In a background task, the Context searches for an EPICS server that provides
that PV name and then connects to it. The PV object displays its connection
state:

.. ipython:: python

    dt

The Context displays aggregate information about the state of all connections.

.. ipython:: python

    ctx

Read
----

Now, to read a PV:

.. ipython:: python

    res = await dt.read()
    res

This object is a human-friendly representation of the server's response. The
raw bytes of that response are:

.. ipython:: python

    bytes(res)

Access particular fields in the response using attribute ("dot") access on ``res``.

.. ipython:: python

    res.data

By default, the client does not request any metadata

.. ipython:: python

   res.metadata

Use the ``data_type`` parameter to request a richer data type.

.. ipython:: python


   richer_res = await dt.read(data_type='time')
   richer_res.metadata
   richer_res.metadata.timestamp
   richer_res.metadata.stamp.as_datetime()  # a convenience method

See :meth:`PV.read` for more information on the values accepted by the
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

    await dt.write([1])

By default, we send ``WriteNotifyResponse``, wait for a response, and return
it. There are a couple other ways we can handle writes:

* Return immediately, not asking for or waiting for a response.

    .. code-block:: python

        await dt.write([1], wait=False)

* Return immediately, not waiting for a response, but handing the response
  (when it arrived) to some callback function, processed in the background.
  Coroutines and regular functions are supported as callbacks.

    .. code-block:: python

        async def f(response):
            print('got a response:', response)

        await dt.write([1], wait=False, callback=f)

See the :meth:`PV.write` for more.

Subscribe ("Monitor")
---------------------

Let us now monitor a channel. The server updates the ``random_walk:x`` channel
periodically at some period set by ``random_walk:dt``. We can subscribe to
updates and fan them out to one or more user-defined callback functions.
First, we define a :class:`Subscription`.

.. ipython:: python

    sub = x.subscribe()

Next, we define a callback function, a function that will be called whenever
the server sends an update. It must accept two positional arguments.

.. ipython:: python

    responses = []
    def f(sub, response):
        print('Received response from', sub.pv.name)
        responses.append(response)

This user-defined function ``f`` has access to the full response from the
server, which includes data and any metadata. The server's response does not
include the name of the PV involved (it identifies it indirectly via a
"subscription ID" code) so caproto provides the function with ``sub`` as well,
from which you can obtain the pertinent PV ``sub.pv`` and its name
``sub.pv.name`` as illustrated above. This is useful for distinguishing
responses when the same function is added to multiple subscriptions.

We register this function with ``sub``.

.. ipython:: python

    token = sub.add_callback(f)

The ``token`` is just an integer which we can use to remove ``f`` later. We can
define a second callback:

.. ipython:: python

    values = []
    def g(sub, response):
        values.append(response.data[0])

and add it to the same subscription, putting no additional load on the network.

.. ipython:: python

    sub.add_callback(g)

After some time has passed, we will have accumulated some responses.  The only
caveat here is that asyncio tasks will not be running in the background until
we start interacting with it.  Let's sleep for a few seconds - letting asyncio
take control - and see what we get.

.. ipython:: python

    import asyncio

    await asyncio.sleep(5)

.. ipython:: python

    len(responses)
    values

An alternative syntax is a bit more convenient here:

.. ipython:: python

    async for value in sub:
        print('Received value', value)
        break

At any point we can remove a specific callback function:

.. ipython:: python

    await sub.remove_callback(token)

or clear all the callbacks on a subscription:

.. ipython:: python

    await sub.clear()

In order to minimize load on the network, a :class:`Subscription` waits to
request updates from the server until the first user callback is added. Thus,
the first callback added by the user is guaranteed to get the first response
received from the server. If all user callbacks are later removed, either
explicitly (via ``remove_callback`` or ``clear``) or implicitly via Python
garbage collection, the Subscription automatically cancels future updates from
the server.  If a callback is then later added, the Subscription silently
re-initiates updates. All of this is transparent to the user.

.. warning::

    The callback registry in :class:`Subscription`  only holds weak references
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

    This pitfall does not apply to callbacks passed to :meth:`PV.read` and
    :meth:`PV.write` because those are single-shot callbacks that do not
    persist beyond their first use.

Go Idle
-------

Once created, PVs are cached for the lifetime of the :class:`Context` and
returned again to the user if a PV with the same name and priority is
requested. In order to reduce the load on the network, a PV can be temporarily
made "idle" (disconnected). It will silently, automatically reconnect the next
time it is used.

.. ipython:: python

    x
    await x.go_idle()
    x
    await x.read()
    x

Notice that when the PV was read it automatically reconnected, requiring no
action from the user.

The ``go_idle()`` method is merely a *request* and is not guaranteed to have
any effect. If a PV has active subscriptions, it will ignore the request: it
must stay active to continue servicing user callbacks. Therefore, it is safe
call ``go_idle()`` on any PV at any time, knowing that the PV will decline to
disconnect if it is being actively used and that, if it is currently unused, it
will transparently reconnect the next time it is used.

Canceling Searches
------------------

All unanswered searches are retried repeatedly, with decreasing frequency,
forever. Each new call to :meth:`~Context.get_pvs` causes all unanswered
searches to be retried at least once immediately. This can generate unwanted
network traffic. To fully cancel a search that is never expected to complete,
access the method :class:`SharedBroadcaster.cancel`.

.. code-block:: python

   ctx.broadcaster.cancel('some typo-ed PV name, for example')

As the name suggests, it is possible to construct multiple Contexts that
share one SharedBroadcaster. In that scenario, notice that canceling the
search will affect all contexts using the SharedBroadcaster.

Events Off and On
-----------------

If a given circuit produces updates faster than a client can process them, the
client can suspend subscriptions on that circuit. This will causes the server
to discard all backlogged updates and all new updates during the period of
supsension. When the client reactives subscriptions, it will immediate receive
the most recent update and then any future updates.

.. code-block:: python

   await x.circuit_manager.events_off()
   ...
   await x.circuit_manager.events_on()


Server Health Check
-------------------

To check how much time has passed (in seconds) since each known server was last
heard from, use:

.. code-block:: python

   ctx.broadcaster.time_since_last_heard()

As a convenience, check on the server connected to a specific PV using:

.. code-block:: python

   x.time_since_last_heard()

See the :meth:`SharedBroadcaster.time_since_last_heard` API documentation below
for details.

.. _asyncio_client_loggers:

Logs for Debugging
------------------

Caproto uses Python's logging framework, which enables sophisticated log
management. For more information and copy/paste-able examples, see
:ref:`loggers`.

.. ipython:: python
    :suppress:

    # Clean up IOC processes.
    for p in processes:
        p.terminate()
    for p in processes:
        p.wait()

API Documentation
=================

.. autoclass:: Context

    .. automethod:: get_pvs

.. autoclass:: PV
   :members:

.. autoclass:: Subscription

    .. automethod:: add_callback
    .. automethod:: clear
    .. automethod:: remove_callback

The following are internal components. There API may change in the future.

.. autoclass:: VirtualCircuitManager
   :members:

.. autoclass:: SharedBroadcaster
   :members:
