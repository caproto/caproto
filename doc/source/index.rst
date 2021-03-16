******************************************************
caproto: a pure-Python Channel Access protocol library
******************************************************

Caproto is an implementation of the
`EPICS <http://www.aps.anl.gov/epics/>`_ Channel Access protocol for
distributed hardware control in pure Python with a "sans-I/O" architecture.

Caproto is a toolkit for building Python programs that speak Channel Access
("EPICS"). It includes a reusable core that encodes the Channel Access
protocol. It also includes several client and server implementations built on
that core.  This layered design is inspired by the broad effort in the Python
community to write
`sans-I/O implementations of network protocols <http://sans-io.readthedocs.io/>`_.
The EPICS (Experimental Physics and Industrial Control System) Channel Access
protocol is used in laboratories and companies
`around the world <https://en.wikipedia.org/wiki/EPICS#Facilities_using_EPICS>`_
to implement distributed control systems for devices such as large telescopes,
particle accelerators, and synchrotrons. Its
`roots <http://www.aps.anl.gov/epics/docs/APS2014/01-Introduction-to-EPICS.pdf>`_
go back to a 1988 meeting funded by the Reagan-era Strategic Defense Initiative
("Star Wars").

The authors pronounce caproto "kah-proto" (not "C.A. proto"). It's fun to say.

Caproto is intended as a friendly entry-point to EPICS. It may be useful for
scientists who want to understand their hardware better, engineers learning
more about the EPICS community, and "makers" interested in using it for hobby
projects --- EPICS has been used for brewing beer and keeping bees! At the same
time, caproto is suitable for use at large experimental facilities.

Try caproto in four lines
==========================

First verify that you have Python 3.6+.

.. code-block:: bash

   python3 --version

If necessary, install it by your method of choice (apt, Homebrew, conda, etc.).
Now install caproto:

.. code-block:: bash

   python3 -m pip install -U caproto

In one terminal, start an EPICS Input-Output Controller (IOC), which is a
server.

.. code-block:: bash

   python3 -m caproto.ioc_examples.simple --list-pvs

In another, use the command-line client:

.. code-block:: bash

   caproto-put simple:A 42

This sets the value to 42. Read more about the :doc:`command-line-client` and
:doc:`iocs`.

10 Reasons To Use Caproto and 1 Big Reason Not To
=================================================

Most existing EPICS tools are built on well-established C and C++ libraries.
Why write something from scratch in Python instead of just wrapping those?

1. **Effortlessly Portable**: No required dependencies --- even numpy is
   optional. Caproto just needs Python itself. We use it on Linux, OSX,
   Windows, and RaspberryPi.
2. **Easy to Install and Use**: See "Try caproto in four lines," above.
3. **Handy for Debugging**: Programmatic access to convenient Python objects
   embodying every CA message sent and received. See the examples of verbose
   logging with the :doc:`command-line-client`.
4. **Efficient**: Data is read directly from sockets into contiguous-memory
   ctypes structures.

   * Zero-copy into ``ctypes`` and ``array.array`` or ``numpy.ndarray``.
   * Only pay a performance cost of human-friendly introspection if and when
     you use it.
5. **Batteries Included**: Includes multiple server and client implementations
   with different concurrency strategies.

   * Command-line tools (largely argument-compatible with standard epics-base
     ca*)
   * A drop-in replacement for pyepics
   * Various client and server implementations that are synchronous, threaded,
     or employing one of Python's cooperative concurrency frameworks

6. **Accessible**: Writing IOCs in pure Python is so easy, a scientist can do
   it!
7. **Reusable**: “Sans-I/O” design separates protocol interpretation from wire
   transport. See the `sans-I/O documentation
   <http://sans-io.readthedocs.io/>`_ for more on the rationale for this design
   pattern and a list of related projects.
8. **Consistent**: Server and client implementations share protocol state
   machine code.
9. **Robust**: Over 1500 unit tests verify compatibility with standard
   epics-base tools (tested against 3.14, 3.15, 3.16, R7).
10. **Succinct**: The core of the package is about the same word count as the
    CA protocol documentation.

All that said, some applications of EPICS --- such as running an accelerator
--- rely on the battle-tested reliability of EPICS' reference implementation.
We would advise those kinds of users to steer well clear of caproto. It is best
suited to applications that reward convenience, fast iteration, and
accessibility.

Some facilities do use caproto "in production" for these kinds of applications,
and we are pleased to hear that it works well. Keep in mind that caproto is
maintained primarily by two people as a hybrid work/hobby project, mostly on
evenings and weekends. At present, no facilities or funding sources have
formally committed resources to its continued support. If a facility makes a
"bet" on caproto:

1. Depending on the size of the bet and the scale of support it may require,
   the facility should commit someone to becoming a caproto core developer.

2. The facility should also maintain general EPICS (base) expertise, so that
   they have a reasonable path to back out of caproto if they need to.

What about pvAccess?
====================

Caproto offers *very* preliminary pvAccess support.  See more in the
:doc:`pva/index` section.

Vital Statistics
================

* Requirements: Python 3.6+ (no other required dependencies!)
* License: 3-clause BSD

Acknowledgement
===============

The design of this library was modeled on `h11 <https://h11.readthedocs.io/>`_,
to which caproto owes its core design principles and many of its clever tricks.
h11 is distributed under an MIT license.

And of course many resources from the EPICS developer community were
indispensable. See :doc:`references`.

Contents
========

In addition to its core "sans I/O" protocol library, caproto includes some
ready-to-use client and server implementations exploring different API choices
and networking libraries. They are organized into packages by how they handle
concurrency. Some will be maintained long-term; others may be abandoned as
learning exercises.

.. toctree::
   :maxdepth: 2

   install
   clients
   servers
   environment_variables
   shark
   loggers

.. toctree::
   :maxdepth: 2
   :caption: IOCs

   iocs
   records
   cookiecutter
   own_docs
   server_api

.. toctree::
   :maxdepth: 2
   :caption: Channel Access Sans I/O

   basics
   api

.. toctree::
   :maxdepth: 4
   :caption: pvAccess

   pva/index
   pva/clients
   pva/iocs
   pva/api

.. toctree::
   :maxdepth: 2
   :caption: Appendix

   protocol-compliance
   references
   release-notes
   containers
