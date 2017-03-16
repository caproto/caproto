******************************************************
caproto: a pure-Python Channel Access protocol library
******************************************************

This is a "bring your own I/O" implementation of the
`EPICS <http://www.aps.anl.gov/epics/>`_ Channel Access protocol in
Python.

This project is inspired by the broad effort in the Python community to write
`sans-I/O implementations of network protocols <http://sans-io.readthedocs.io/>`_.
Caproto parses and validates incoming and outgoing bytes, keeping track
the state of an EPICS Client, Server, Virtual Circuits, and Channels. But,
crucially, it performs no I/O itself: handling sockets and transport is
completely up the caller. Caproto is a toolkit for building programs that speak
EPICS.

Why do this?
============

The aim is to provide a complete, reusable implementation of the Channel Access
protocol in Python which can be wrapped in whichever network library you like
best. It is not a replacement for
`pyepics <https://github.com/pyepics/pyepics>`_,
`cothread <http://controls.diamond.ac.uk/downloads/python/cothread/>`_, or
`pcaspy <https://pcaspy.readthedocs.io>`_. It's a pure-Python implementation
of *libca* that makes libraries like these easier to write in the
future. See the `sans-I/O documentation <http://sans-io.readthedocs.io/>`_ for
more on the why and how of this idea and for a list of related projects.

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
* The Python module that specifies the byte layout of each command is generated
  using Python and Jinja templates from the documentation itself to reduce
  the potential for bugs introduced by human transcription. Where we
  found errors in the documentation, we fixed them and submitted a patch
  upstream. (NOTE: This is a reminder to submit a patch.)
* It passes the server test spec https://github.com/mdavidsaver/catvs (NOTE: As
  of this writing, this is not true! It's here as a reminder to make it true
  before we publish this documentation.)
* The byte sizes of the DBR types compare exactly to those in pyepics.

So should I use it?
===================

That depends. Probably not. It's a very young project, and the primary author
(hi!) is fairly new to EPICS. For important work, one of the more battle-tested
projects linked above would be a better choice.

But by all means, take it for a test drive. Use it to understand EPICS better
or to play with the growing family of asynchronous libraries in Python.

How's the performance?
======================

No idea yet! That's high on the list of things we'd like to know. Caproto gets
some important basics right, like reading bytes directly from sockets into C
structs with no extra copies. Time will tell if there are any major
bottlenecks we haven't anticipated.

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
   examples/index
   references
   release-notes
