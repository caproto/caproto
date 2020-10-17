********
Overview
********

Caproto now provides preliminary pvAccess support.

In addition to its core "sans I/O" protocol library, caproto-pva includes a
ready-to-use synchronous client and an asyncio-based server implementations.

How preliminary are we talking?
===============================

To put that statement into context, caproto itself was originally developed as
a fun side project between 3 developers and refined over the course of the past
few years.

The internals of caproto's pvAccess support, on the other hand, were developed
as a solo side-project with zero testing from (or discussion with) others, over
the course of a few months' weekends.  Given the relative complexity of
pvAccess over Channel Access, caproto's pvAccess support cannot compete with
the level of its Channel Access support.

Please don't be too discouraged by the above:

* The basics of what's needed to support PVAccess are already done.
* Like ``caproto`` for Channel Access, ``caproto-pva`` is one of the easier
  ways to go from zero-to-IOC without only a single requirement: Python itself.
* Contributing time to help testing or provide input would be *greatly*
  appreciated.


Try caproto-pva in four lines
=============================

First verify that you have Python 3.7+.

.. code-block:: bash

   python3 --version

If necessary, install it by your method of choice (apt, Homebrew, conda, etc.).
Now install caproto:

.. code-block:: bash

   python3 -m pip install -U caproto

In one terminal, start an EPICS Input-Output Controller (IOC), which is a
server.

.. code-block:: bash

   python3 -m caproto.pva.ioc_examples.normative --list-pvs

In another, use the command-line client:

.. code-block:: bash

   python3 -m caproto.pva.commandline.put caproto:pva:int 42

This sets the value to 42.
