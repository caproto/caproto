******************************************************
caproto: a pure-Python Channel Access protocol library
******************************************************

Caproto is a implementation of the
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

Try caproto in three lines
==========================

.. code-block:: bash

   python3 -m pip install caproto[complete]  # install caproto (and its optional dependencies)
   python3 -m caproto.ioc_examples.simple &  # background a demo server
   caproto-put simple:A 42  # run a command-line client

11 Reasons This Isn't As Crazy as It Sounds
===========================================

Most existing EPICS tools are built on a well-established C library, *libca*.
Why rewrite it from scratch in Python instead of just wrapping C?

1. **Effortlessly Portable**: No required dependencies —-- even numpy is
   optional. Caproto just needs Python itself.
2. **Easy to Install and Use**: See "Try caproto in three lines," above.
3. **Handy for Debugging**: Programmatic access to convenient Python objects
   embodying every CA message sent and received.
4. **Efficient**: Data is read directly from sockets into contiguous-memory
   ctypes structures.

   * Zero-copy into ``ctypes`` and ``array.array`` or ``numpy.ndarray``.
   * Only pay a performance cost of human-friendly introspection if and when
     you use it.

   For hard numbers, see the
   `benchmarks <https://nsls-ii.github.io/caproto/bench/#/summarylist>`_.
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
9. **Robust**: Over 1000 unit tests verify compatibility with standard
   epics-base tools (tested against 3.14, 3.15, 3.16, R7).
10. **Succinct**: The core of the package is about the same word count as the
    CA protocol documentation.

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
   :caption: EPICS Clients and Servers

   command-line-client
   sync-client
   threading-client
   pyepics-compat-client
   trio-client
   curio-client
   iocs
   servers

.. toctree::
   :maxdepth: 2
   :caption: Channel Access Sans I/O

   basics
   api
   Performance Benchmarks <https://nsls-ii.github.io/caproto/bench/#/summarylist>
   references
   release-notes
