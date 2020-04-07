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
        simple:C

and use ``--prefix`` to conveniently customize the PV prefix:

.. code-block:: bash

    $ python3 -m caproto.ioc_examples.simple --list-pvs --prefix my_custom_prefix:
    [I 16:54:14.528 server:93] Server starting up...
    [I 16:54:14.530 server:109] Listening on 0.0.0.0:55810
    [I 16:54:14.530 server:121] Server startup complete.
    [I 16:54:14.530 server:123] PVs available:
        my_custom_prefix:A
        my_custom_prefix:B
        my_custom_prefix:C

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
        simple:C

Using the threading client context we created above, we can read these values
and write to them.

.. ipython:: python

    a, b, c = ctx.get_pvs('simple:A', 'simple:B', 'simple:C')
    a.read()
    b.read()
    c.read()
    b.write(5)
    b.read()
    c.write([4, 5, 6])
    c.read()

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

On the machine where the server resides, we will see files update whenever any
client writes.

.. ipython:: python

    a, b = ctx.get_pvs('custom_write:A', 'custom_write:B')
    a.write(5)
    print(open('/tmp/A').read())
    a.write(10)
    print(open('/tmp/A').read())

It is easy to imagine extending this example to write a socket or a serial
device rather than a file.

Random Walk
-----------

This example contains a PV ``random_walk:x`` that takes random steps at an
update rate controlled by a second PV, ``random_walk:dt``.

.. literalinclude:: ../../caproto/ioc_examples/random_walk.py

.. note::

   **What is async_lib.library.sleep?**

   As caproto supports three different async libraries, we have an "async
   layer" class that gives compatible async versions of commonly-used
   synchronization primitives. The attribute ``async_lib.library`` would be either
   the Python module ``asyncio`` (default), ``trio``, or ``curio``, depending on how
   the server is run.  It happens that all three of these modules have a ``sleep``
   function at the top level, so ``async_lib.library.sleep`` accesses the
   appropriate sleep function for each library.

   **Why not use time.sleep?**

   The gist is that ``asyncio.sleep`` doesn't hold up your entire thread /
   event loop, but gives back control to the event loop to run other tasks while
   sleeping. The function ``time.sleep``, on the other hand, would cause
   noticeable delays and problems.

   This is a fundamental consideration in concurrent programming generally,
   not specific to caproto. See for example
   `this StackOverflow post <https://stackoverflow.com/questions/46207991/what-does-yield-from-asyncio-sleepdelay-do>`_
   for more information.


I/O Interrupt
-------------

This example listens for key presses.

.. literalinclude:: ../../caproto/ioc_examples/io_interrupt.py

.. code-block:: bash

    $ python -m caproto.ioc_examples.io_interrupt --list-pvs
    [I 10:18:57.643 server:132] Server starting up...
    [I 10:18:57.644 server:145] Listening on 0.0.0.0:54583
    [I 10:18:57.646 server:218] Server startup complete.
    [I 10:18:57.646 server:220] PVs available:
        io:keypress
    * keypress method called at server startup
    Started monitoring the keyboard outside of the async library

Typing causes updates to be sent to any client subscribed to ``io:keypress``.
If we monitoring using the commandline-client like so:

.. code-block:: bash

    $ caproto-monitor io:keypress

and go back to the server and type some keys:

.. code-block:: bash

    New keypress: 'a'
    Saw new value on async side: 'a'
    New keypress: 'b'
    Saw new value on async side: 'b'
    New keypress: 'c'
    Saw new value on async side: 'c'
    New keypress: 'd'
    Saw new value on async side: 'd'

the client will receive the updates:

.. code-block:: bash

    io:keypress                               2018-06-14 10:19:04 [b'd']
    io:keypress                               2018-06-14 10:20:26 [b'a']
    io:keypress                               2018-06-14 10:20:26 [b's']
    io:keypress                               2018-06-14 10:20:26 [b'd']

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

Subgroups
---------

The PVGroup is designed to be nested, which provides a nice path toward future
capability: IOCs that are natively "V7", encoding semantic structure for PV
Access clients and decomposing into flat PVs for Channel Access clients.

.. literalinclude:: ../../caproto/ioc_examples/subgroups.py

.. code-block:: bash

    $ python -m caproto.ioc_examples.subgroups --list-pvs
    random using the descriptor getter is: <caproto.server.server.PvpropertyInteger object at 0x10928ffd0>
    subgroup4 is: <__main__.MyPVGroup.group4.subgroup4 object at 0x10928fe10>
    subgroup4.random is: <caproto.server.server.PvpropertyInteger object at 0x10928fef0>
    [I 11:08:35.074 server:132] Server starting up...
    [I 11:08:35.074 server:145] Listening on 0.0.0.0:63336
    [I 11:08:35.076 server:218] Server startup complete.
    [I 11:08:35.077 server:220] PVs available:
        subgroups:random
        subgroups:RECORD_LIKE1.RTYP
        subgroups:RECORD_LIKE1.VAL
        subgroups:RECORD_LIKE1.DESC
        subgroups:recordlike2.RTYP
        subgroups:recordlike2.VAL
        subgroups:recordlike2.DESC
        subgroups:group1:random
        subgroups:group2-random
        subgroups:group3_prefix:random
        subgroups:group4:subgroup4:random

.. _mocking_records_example:

Mocking Records
---------------

See :doc:`mock-records`.

.. literalinclude:: ../../caproto/ioc_examples/mocking_records.py

.. code-block:: bash

    python -m caproto.ioc_examples.mocking_records --list-pvs
    PVs: ['mock:A', 'mock:B']
    Fields of B: ['ACKS', 'ACKT', 'ASG', 'DESC', 'DISA', 'DISP', 'DISS', 'DISV', 'DTYP', 'EVNT', 'FLNK', 'LCNT', 'NAME', 'NSEV', 'NSTA', 'PACT', 'PHAS', 'PINI', 'PRIO', 'PROC', 'PUTF', 'RPRO', 'SCAN', 'SDIS', 'SEVR', 'TPRO', 'TSE', 'TSEL', 'UDF', 'RTYP', 'STAT', 'RVAL', 'INIT', 'MLST', 'LALM', 'ALST', 'LBRK', 'ORAW', 'ROFF', 'SIMM', 'SVAL', 'HYST', 'HIGH', 'HSV', 'HIHI', 'HHSV', 'LOLO', 'LLSV', 'LOW', 'LSV', 'AOFF', 'ASLO', 'EGUF', 'EGUL', 'LINR', 'EOFF', 'ESLO', 'SMOO', 'ADEL', 'PREC', 'EGU', 'HOPR', 'LOPR', 'MDEL', 'INP', 'SIOL', 'SIML', 'SIMS']
    [I 11:07:48.635 server:132] Server starting up...
    [I 11:07:48.636 server:145] Listening on 0.0.0.0:49637
    [I 11:07:48.638 server:218] Server startup complete.
    [I 11:07:48.638 server:220] PVs available:
        mock:A
        mock:B

RPC Server from Python Function
-------------------------------

This automatically generates a SubGroup. In the future, this could be used to
spin up a PVA RPC service. As is, for Channel Access, this provides an RPC
function for single-user access.

.. literalinclude:: ../../caproto/ioc_examples/rpc_function.py

.. code-block:: bash

 $ python -m caproto.ioc_examples.rpc_function --list-pvs

    fixed_random using the descriptor getter is: <caproto.server.server.PvpropertyInteger object at 0x1041672b0>
    get_random using the descriptor getter is: <caproto.server.server.get_random object at 0x1041675f8>
    get_random is an autogenerated subgroup with PVs:
        ('rpc:get_random:low', <caproto.server.server.PvpropertyInteger object at 0x104167358>)
        ('rpc:get_random:high', <caproto.server.server.PvpropertyInteger object at 0x104167588>)
        ('rpc:get_random:Status', <caproto.server.server.PvpropertyStringRO object at 0x104167320>)
        ('rpc:get_random:Retval', <caproto.server.server.PvpropertyIntegerRO object at 0x104167550>)
        ('rpc:get_random:Process', <caproto.server.server.PvpropertyInteger object at 0x1041672e8>)
    OrderedDict([('rpc:fixed_random',
                <caproto.server.server.PvpropertyInteger object at 0x1041672b0>),
                ('rpc:get_random:low',
                <caproto.server.server.PvpropertyInteger object at 0x104167358>),
                ('rpc:get_random:high',
                <caproto.server.server.PvpropertyInteger object at 0x104167588>),
                ('rpc:get_random:Status',
                <caproto.server.server.PvpropertyStringRO object at 0x104167320>),
                ('rpc:get_random:Retval',
                <caproto.server.server.PvpropertyIntegerRO object at 0x104167550>),
                ('rpc:get_random:Process',
                <caproto.server.server.PvpropertyInteger object at 0x1041672e8>)])

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

More...
-------

Take a look around
`the ioc_examples subpackage <https://github.com/caproto/caproto/tree/master/caproto/ioc_examples>`_ for more examples not covered here.

.. ipython:: python
    :suppress:

    # Clean up IOC processes.
    for p in processes:
        p.terminate()
    for p in processes:
        p.wait()
