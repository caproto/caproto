******************************************************
caproto: a pure-Python Channel Access protocol library
******************************************************

This is a "bring your own I/O" implementation of the
`EPICS <http://www.aps.anl.gov/epics/>`_ Channel Access protocol in
Python.

This project is inspired by the broad effort in the Python community to write
`sans-I/O implementations of network protocols <http://sans-io.readthedocs.io/>`_.
Caproto manages the coupled state of an EPICS Client or Server, its
VirtualCircuits, and Channels; it interprets received UDP and TCP messages and
exposes them (zero-copy) as higher-level objects;
using these same objects, it can compose valid messages to be sent. But,
crucially, it performs no I/O itself. It merely processes and validates
incoming and outgoing messsages and tracks client and server state. The
developer using caproto is in complete control over when and how bytes are
actually transmitted and received.  The transport may be synchronous, threaded,
asynchronous, etc. Caproto is unopinionated about this.

Why do this?
============

The aim is to provide a complete, reusable implementation of the Channel Access
protocol in Python which can be wrapped in whichever network library you like
best. It is not a replacement for
`pyepics <https://github.com/pyepics/pyepics>`_ or
`cothread <http://controls.diamond.ac.uk/downloads/python/cothread/>`_. Rather
it would be make libraries like pyepics or cothread easier to write in the
future. See the
`sans-I/O documentation <http://sans-io.readthedocs.io/>`_ for more on the why
and how of this idea and for a list of related projects.

This entire implementation, including copious docstrings and comments, is
shorter than official webpage documenting the Channel Access specification. The
codebase itself may serve as useful introduction to Channel Access concepts.

Vital Statistics
================

* Requirements: Python 3.5+ and (optional) numpy
* License: 3-clause BSD

How do you know it works?
=========================

* It can talk to libca as a client --- for example, reading, writing to, and
  monitoring the simulated motor ioc, motorsim.
* It can talk to libca as a server --- for example, responding correctly to
  caget, caput, camonitor.
* It passes the server test spec https://github.com/mdavidsaver/catvs (NOTE: As
  of this writing, this is not  true! It's here as a reminder to make it true
  before we publish this documentation.)
* The Python module that specifies the byte layout of each command is generated
  using Python and Jinja templates from the documentation itself to reduce
  the potential for bugs introduced by human transcription. Where we
  found errors in the documentation, we fixed them and submitted a patch
  upstream. (NOTE: Again this is a reminder to submit a patch.)

Acknowledgement
===============

The design of this library was inspired by
`h11 <https://h11.readthedocs.io/>`_, to which caproto owes its core design
principles and many of its clever tricks. h11 is distributed under an MIT
license.

And of course many resources from the EPICS developer community were
indispensible. See :doc:`references`.

.. toctree::
   :maxdepth: 2

   basics
   api
   examples
   references
