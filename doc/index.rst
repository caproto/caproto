******************************************************
caproto: a pure-Python Channel Access protocol library
******************************************************

This is a "bring your own I/O" implementation of the Channel Access protocol in
Python.

This project is inspired by the broad effort in the Python community to write
`sans-I/O implementations of network protocols <http://sans-io.readthedocs.io/>`_.
Caproto manages the coupled state of an EPICS Client or Server, its
VirtualCircuits, and Channels; it interprets received packets; and it can
compose valid packets to be sent. But, crucially, it performs no I/O itself.
The developer using caproto is in complete control over when and how
bytes are actually transmitted and received. The networking may be synchronous,
threaded, asynchronous, etc. Cothread is unopinionated about how the bytes are
moved around.

Why do this?
============`

The aim is to provide a complete, reusable implementation of the Channel Access
protocol in Python which can be wrapped in whichever network library you like
best. It is not a replacement for `pyepics
<https://github.com/pyepics/pyepics>` or
`cothread <http://controls.diamond.ac.uk/downloads/python/cothread/>`_. Rather
it would be make libraries like pyepics or cothread easier to write in the
future. See the
`sans-I/O documentation <http://sans-io.readthedocs.io/>`_ for more on the why
and how of this idea and for a list of related projects.

Additionally, the codebase itself may serve as a useful introduction to Channel
Access concepts. In fact, this entire working implementation, including
copious docstrings and comments, is shorter than official webpage documenting
the specification.

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
* It passes the server test spec https://github.com/mdavidsaver/catvs
* The Python module that specifies the byte layout of each command is generated
  using Python and Jinja templates from the documentation itself. Where we
  found errors in the documentation, we fixed them and submitted a patch
  upstream.
