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

.. literalinclude:: ../../ioc_examples/simple.py

.. ipython:: python
    :suppress:

    run_example('../../examples/simple.py', 'example1:')

.. code-block:: bash

    $ simple.py example1:
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

.. literalinclude:: ../../ioc_examples/custom_write.py

.. code-block:: bash

    $ custom_write.py example3:
    PVs: ['example3:A', 'example3:B']

.. ipython:: python
    :suppress:

    run_example('../../ioc_examples/custom_write.py', 'example3:')

Update Tallies When Each PV is Read
===================================

.. literalinclude:: examples/reading_counter.py

.. code-block:: bash

    $ reading_counter.py example4:
    PVs: ['example4:A', 'example4:B']

.. ipython:: python
    :suppress:

    run_example('../../ioc_examples/reading_counter.py', 'example4:')

Macros for PV names
===================

.. literalinclude:: ../../ioc_examples/macros.py

.. code-block:: bash

    $ macros.py example5: XF11ID detector
    PVs: ['example5:XF11ID:detector.VAL', 'example5:XF11ID:detector.RBV']

.. ipython:: python
    :suppress:

    run_example('../../ioc_examples/macros.py', 'example5:', 'XF11ID', 'detector')

Observe that the command line arguments fill in the PV names.

"Inline" Style Read and Write Customization
===========================================

.. literalinclude:: ../../ioc_examples/inline_style.py

.. ipython:: python
    :suppress:

    run_example('../../ioc_examples/inline_style.py', 'example6:')

.. code-block:: bash

    $ inline_style.py example6:
    PVs: ['example6:random_int', 'example6:random_str', 'example6:A']


.. code-block:: bash

    $ caproto-get example6:random_int
    example6:random                           87
    $ caproto-get example6:random_int
    example6:random                           92
    $ caproto-get example6:random_str
    example6:random_str                       b'b'
    $ caproto-get example6:random_str
    example6:random_str                       b'a'

.. ipython:: python
    :suppress:

    # Clean up IOC processes.
    for p in processes:
        p.terminate()
    for p in processes:
        p.wait()
