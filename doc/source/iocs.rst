************************
Input-Output Controllers
************************

Simple IOC
==========

.. literalinclude:: examples/simple_ioc.py

.. code-block:: bash

    simple_ioc.py example1:

.. ipython:: python
    :suppress:

    import subprocess
    import time
    processes = []
    p = subprocess.Popen(['source/examples/simple_ioc.py', 'example1:'])
    processes.append(p)  # Clean this up later.
    time.sleep(1)  # Give it time to start up.

Now there are simple read/writable PVs named 'example1:A' and 'example1:B'.

.. ipython:: python

    from caproto.threading.client import get_pv
    get_pv('example1:A').get()
    get_pv('example1:B').get()

To run a second instance of the same IOC with a different prefix:

.. code-block:: bash

    simple_ioc.py example2:

Write to a File When a PV is Written To
=======================================

.. literalinclude:: examples/custom_write.py

Update Tallies When Each PV is Read
===================================

.. literalinclude:: examples/reading_counter.py


.. ipython:: python
    :suppress:

    # Clean up IOC processes.
    for p in processes:
        p.kill()
