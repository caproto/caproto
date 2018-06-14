*******************************
Input-Output Controllers (IOCs)
*******************************

EPICS Input-Output Controllers (IOCs) expose an EPICS server. Behind the
server, they may connect to a device driver, data-processing code, and/or
an EPICS client for chaining with other servers.

In this section, we will review some of the example IOCs that are included with
caproto, intended as demonstrations of what is possible.

Why Write an IOC Using Caproto?
===============================

Caproto makes it is easy to launch a protocol-compliant Channel Access server
in just a couple lines of Python. This opens up some interesting possibilities:

* In Python, it is easy to invoke standard web protocols. For example, writing
  an EPICS server around a device that speaks JSON may be easier with caproto
  than with any previously-existing tools.
* Many scientists who rely on EPICS but may not understand the details of
  EPICS already know some Python for the data analysis work. Caproto may make
  it easier for scientists and controls engineers to collaborate.
* As with its clients, caproto's servers handle a human-friendly encapsulation
  of every message sent and received, which can be valuable for development,
  logging, and debugging.

Using the IOC Examples
======================

They can be started like so:

.. code-block:: bash

    $ python3 -m caproto.ioc_examples.simple
    [I 16:51:09.751 server:93] Server starting up...
    [I 16:51:09.752 server:109] Listening on 0.0.0.0:54966
    [I 16:51:09.753 server:121] Server startup complete.

and stopped using Ctrl+C:

.. code-block:: bash

    ^C
    [I 16:51:10.828 server:129] Server task cancelled. Must shut down.
    [I 16:51:10.828 server:132] Server exiting....

Use ``--list-pvs`` to display which PVs they serve:

.. code-block:: bash

    $ python3 -m caproto.ioc_examples.simple --list-pvs
    [I 16:52:36.087 server:93] Server starting up...
    [I 16:52:36.089 server:109] Listening on 0.0.0.0:62005
    [I 16:52:36.089 server:121] Server startup complete.
    [I 16:52:36.089 server:123] PVs available:
        simple:A
        simple:B

and use ``--prefix`` to conveniently customize the PV prefix:

.. code-block:: bash

    $ python3 -m caproto.ioc_examples.simple --list-pvs --prefix my_custom_prefix:
    [I 16:54:14.528 server:93] Server starting up...
    [I 16:54:14.530 server:109] Listening on 0.0.0.0:55810
    [I 16:54:14.530 server:121] Server startup complete.
    [I 16:54:14.530 server:123] PVs available:
        my_custom_prefix:A
        my_custom_prefix:B

Type ``python3 -m caproto.ioc_examples.simple -h`` for more options.

Examples
========

Below, we will use caproto's threading client to interact with caproto IOC.

.. ipython:: python

    from caproto.threading.client import Context
    ctx = Context()  # a client Context used to explore the servers below

Of course, standard epics-base clients or other caproto clients may also be
used.

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

Simple IOC
----------

This IOC has two PVs that simply store a value.

.. literalinclude:: ../../caproto/ioc_examples/simple.py

.. ipython:: python
    :suppress:

    run_example('caproto.ioc_examples.simple')

.. code-block:: bash

    $ python3 -m caproto.ioc_examples.simple --list-pvs
    [I 18:08:47.628 server:93] Server starting up...
    [I 18:08:47.630 server:109] Listening on 0.0.0.0:56840
    [I 18:08:47.630 server:121] Server startup complete.
    [I 18:08:47.630 server:123] PVs available:
        simple:A
        simple:B

Using the threading client context we created above, we can read these values
and write to them.

.. ipython:: python

    a, b = ctx.get_pvs('simple:A', 'simple:B')
    a.read()
    b.read()
    b.write([5], wait=True)
    b.read()

Write to a File When a PV is Written To
---------------------------------------

.. literalinclude:: ../../caproto/ioc_examples/custom_write.py

.. code-block:: bash

    $ python3 -m caproto.ioc_examples.custom_write --list-pvs
    [I 18:12:07.282 server:93] Server starting up...
    [I 18:12:07.284 server:109] Listening on 0.0.0.0:57539
    [I 18:12:07.284 server:121] Server startup complete.
    [I 18:12:07.284 server:123] PVs available:
        custom_write:A
        custom_write:B

.. ipython:: python
    :suppress:

    run_example('caproto.ioc_examples.custom_write')

On the machine where the server redies, we will see files update whenever any
client writes.

.. ipython:: python

    a, b = ctx.get_pvs('custom_write:A', 'custom_write:B')
    a.write([5], wait=True)
    print(open('/tmp/A').read())
    a.write([10], wait=True)
    print(open('/tmp/A').read())

It is easy to imagine extending this example to write a socket or a serial
device rather than a file.

Update Tallies When Each PV is Read
-----------------------------------

Above, we hooked into the IOC's writing behavior to customize it. Here, we
customize its reading behavior.

.. literalinclude:: ../../caproto/ioc_examples/reading_counter.py

.. code-block:: bash

    $ python3 -m caproto.ioc_examples.reading_counter --list-pvs
    [I 18:26:38.169 server:93] Server starting up...
    [I 18:26:38.170 server:109] Listening on 0.0.0.0:52687
    [I 18:26:38.171 server:121] Server startup complete.
    [I 18:26:38.171 server:123] PVs available:
        reading_counter:A
        reading_counter:B

.. ipython:: python
    :suppress:

    run_example('caproto.ioc_examples.reading_counter')

.. ipython:: python

    a, b = ctx.get_pvs('reading_counter:A', 'reading_counter:B')
    a.read().data
    a.read().data
    a.read().data

Macros for PV names
-------------------

.. literalinclude:: ../../caproto/ioc_examples/macros.py

The help string for this IOC contains two extra entries at the bottom:

.. code-block:: bash

    $ python3 -m caproto.ioc_examples.macros -h
    usage: macros.py [-h] [--prefix PREFIX] [-q | -v] [--list-pvs]
                    [--async-lib {asyncio,curio,trio}]
                    [--interfaces INTERFACES [INTERFACES ...]]
                    [--beamline BEAMLINE] [--thing THING]

    Run an IOC with PVs that have macro-ified names.

    optional arguments:

    <...snipped...>

    --beamline BEAMLINE   Macro substitution, optional
    --thing THING         Macro substitution, optional

.. code-block:: bash

    $ python3 -m caproto.ioc_examples.macros --beamline XF31ID --thing detector --list-pvs
    [I 18:44:39.528 server:93] Server starting up...
    [I 18:44:39.530 server:109] Listening on 0.0.0.0:56365
    [I 18:44:39.531 server:121] Server startup complete.
    [I 18:44:39.531 server:123] PVs available:
        macros:XF31ID:detector.VAL
        macros:XF31ID:detector.RBV

.. ipython:: python
    :suppress:

    run_example('caproto.ioc_examples.macros', '--beamline', 'XF31ID', '--thing', 'detector')

.. ipython:: python

    pv, = ctx.get_pvs('macros:XF31ID:detector.VAL')
    pv.read()

Observe that the command line arguments fill in the PV names.

"Inline" Style Read and Write Customization
-------------------------------------------

This example shows custom write and read behavior similar to what we have seen
before, but implemented "inline" rather than siloed into a separate method.
This may be useful, from a readability point of view, for implementing one-off
behavior.

.. literalinclude:: ../../caproto/ioc_examples/inline_style.py

.. ipython:: python
    :suppress:

    run_example('caproto.ioc_examples.inline_style')

.. code-block:: bash

    $ python3 -m caproto.ioc_examples.inline_style --list-pvs
    [I 18:47:05.344 server:93] Server starting up...
    [I 18:47:05.346 server:109] Listening on 0.0.0.0:64443
    [I 18:47:05.346 server:121] Server startup complete.
    [I 18:47:05.346 server:123] PVs available:
        inline_style:random_int
        inline_style:random_str
        inline_style:A

.. ipython:: python

    randint, randstr = ctx.get_pvs('inline_style:random_int', 'inline_style:random_str')
    randint.read()
    randint.read()
    randint.read()
    randstr.read()
    randstr.read()
    randstr.read()

.. ipython:: python
    :suppress:

    # Clean up IOC processes.
    for p in processes:
        p.terminate()
    for p in processes:
        p.wait()
