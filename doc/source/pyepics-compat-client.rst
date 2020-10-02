*************************
Pyepics-Compatible Client
*************************

.. currentmodule:: caproto.threading.pyepics_compat

What is This?
=============

`Pyepics <http://cars9.uchicago.edu/software/python/pyepics3/>`_ is a
well-established Python wrapper of libca. Caproto includes a client that is a
drop-in replacement for pyepics. It is implemented as a shim on top of
caproto's main :doc:`threading-client`.  Caproto's pyepics-compatible client is
tested against a representative sample of the pyepics test suite.

Why would you ever want to use caproto's pyepics instead of actual pyepics?  It
may be advantageous to run existing user code written for pyepics on top of
caproto --- for example, to leverage caproto's verbose logging or portability.

Why are there two threading clients in caproto instead of just one
pyepics-compatible one? Caproto's main threading client makes different design
choices, consistent with the rest of caproto:

1. Caproto's threading client provides a lower-level API, handing the user
   objects encapsulating the complete response from the server as opposed to
   just the value.
2. Caproto pulls apart the subscription process into two steps---specifying a
   subscription and adding a user callback function to one---whereas pyepics
   elides them.

Caproto is speed-competitive with pyepics. Because it controls the
entire network stack, rather than calling out to libca, it can batch requests
into UDP datagrams and TCP packets more efficiently, leading to a ~250X speedup
in connecting a large number of channels in bulk.

The authors of caproto are heavy pyepics users and occasional contributors.
This module is intended as a friendly bridge to pyepics.

Demonstration
=============

For full documentation on pyepics usage, see the
`pyepics doucmentation <http://cars9.uchicago.edu/software/python/pyepics3/>`_.
This is a brief demonstration of caproto's pyepics-compat client.

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

.. ipython:: python
    :suppress:

    run_example('caproto.ioc_examples.random_walk')

In a separate shell, start one of caproto's demo IOCs.

.. code-block:: bash

    $ python3 -m caproto.ioc_examples.random_walk
    PVs: ['random_walk:dt', 'random_walk:x']

Now, in Python we will talk to it using caproto's pyepics-compatible client.
Get and put to ``random_walk:dt``:

.. ipython:: python

    import caproto.threading.pyepics_compat as epics
    pv_name = 'random_walk:dt'
    epics.caget(pv_name)
    epics.caput(pv_name, 2)
    pv = epics.get_pv(pv_name)
    pv.get()
    pv.put(1)
    pv.get()

Subscribe a user-defined callback function to ``random_walk:x``:

.. ipython:: python

    def f(value, **kwargs):
        print('received value' , value)

Note that pyepics recommends using ``epics.get_pv(...)`` instead of
``epics.PV(...)`` and so do we, but both usages are supported.

.. ipython:: python

    x_pv = epics.PV('random_walk:x')
    x_pv.add_callback(f)
    import time; time.sleep(5)  # give some time for responses to come in
    x_pv.clear_callbacks()

The underlying caproto PV and Context objects from caproto's main
:doc:`threading-client`. are accessible:

.. ipython:: python

    pv._caproto_pv
    pv._caproto_pv.context

This brief demonstration has not exercised every aspect of the pyepics API, but
caproto's test suite is more comprehensive.

.. ipython:: python
    :suppress:

    # Clean up IOC processes.
    for p in processes:
        p.terminate()
        p.kill()
    for p in processes:
        p.wait()
