************************
Input-Output Controllers
************************

Simple IOC
==========

.. ipython:: python
    :suppress:

    import subprocess
    import time
    processes = []
    def run_example(*args):
        p = subprocess.Popen(args)
        processes.append(p)  # Clean this up at the end.
        time.sleep(1)  # Give it time to start up.

.. literalinclude:: examples/simple_ioc.py

.. ipython:: python
    :suppress:

    run_example('source/examples/simple_ioc.py', 'example1:')

.. code-block:: bash

    $ simple_ioc.py example1:
    PVs: ['example1:A', 'example1:B']

Now there are simple read/writable PVs named 'example1:A' and 'example1:B'.

.. ipython:: python

    from caproto.threading.client import get_pv
    get_pv('example1:A').get()
    get_pv('example1:B').get()

To run a second instance of the same IOC with a different prefix:

.. code-block:: bash

    $ simple_ioc.py example2:
    PVs: ['example2:A', 'example2:B']

Write to a File When a PV is Written To
=======================================

.. literalinclude:: examples/custom_write.py

.. code-block:: bash

    $ custom_write.py example3:
    PVs: ['example3:A', 'example3:B']

.. ipython:: python
    :suppress:

    run_example('source/examples/custom_write.py', 'example3:')

Update Tallies When Each PV is Read
===================================

.. literalinclude:: examples/reading_counter.py

.. code-block:: bash

    $ reading_counter.py example4:
    PVs: ['example4:A', 'example4:B']

.. ipython:: python
    :suppress:

    run_example('source/examples/reading_counter.py', 'example4:')

.. ipython:: python
    :suppress:

    # Clean up IOC processes.
    for p in processes:
        p.terminate()
    for p in processes:
        p.wait()
