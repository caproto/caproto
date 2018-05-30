******************
Synchronous Client
******************

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
performance. This has its uses, but for high-performance applications one of
the other clients should be used.

Tutorial
========

.. ipython:: python
    :suppress:

    run_example('caproto.ioc_examples.random_walk')

In a separate shell, start one of caproto's demo IOCs.

.. code-block:: bash

    $ python3 -m caproto.ioc_examples.random_walk
    PVs: ['random_walk:delta_t', 'random_walk:x']

Now, in Python we will talk to it using caproto's synchronous client:

.. ipython:: python

    from caproto.sync.client import get, put, monitor
    res = get('random_walk:delta_t')
    res

This object is a human-friendly representation of the server's response. The
raw bytes of that response are:

.. ipython:: python

    bytes(res)

Access particular fields in the response through attributes access on ``res``.

.. ipython:: python

    res.data

Let us set the value to ``1``.

.. ipython:: python

    before, after = put('random_walk:delta_t', 1)
    before.data
    after.data

The synchronous client issues three requests:

1. Read the current value.
2. Write ``1``.
3. Read the value again.

This behavior is particular to caproto's *synchronous* client. The other, more
sophisticated clients leave it up to the caller when and whether to request
readings.

Let us now monitor a channel. The server updates the ``random_walk:x`` channel
periodically. (The period is set by ``random_walk:delta_t``.) We can subscribe
to updates.

.. ipython:: python

   responses = []
   def f(name, response):
       "On each update, print the data and cache the full response."
       responses.append(response)
       print(response.data)

This call to :func:`monitor` blocks indefinitely, passing responses to ``f`` as
they arrive. When we are satisfied, we can interrupted it with Ctrl+C.
   
.. ipython::
   :verbatim:

   In [12]: monitor('random_walk:x', callback=f)
   [24.51439201]
   [24.6344612]
   [24.7142318]
   [25.54776527]
   [25.67713186]
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

.. currentmodule:: caproto.sync.client
.. autofunction:: get
.. autofunction:: put
.. autofunction:: monitor
