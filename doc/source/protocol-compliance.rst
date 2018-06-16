***********************************************
Details of our Protocol Compliance for CA Nerds
***********************************************

This is a summary of caproto's compliance with the Channel Access protocol and
the feature parity of caproto's clients and servers with the reference
implementations in epics-base. We aim for 100% compliance and feature parity.

For more details, see our
`issue tracker on GitHub <https://github.com/NSLS-II/caproto/issues>`_

Core protocol support
=====================

Supported:

* Every DBR data type
* Every message type
* Tested against epics-based versions 3.14, 3.15, 3.16, R7 and protocol
  versions as old as 12

TO DO:

* There are possible issues with the ``ReadResponse`` message, but this message
  has been deprecated since epics-base version 3.13.

Threading Client
================

Supported:

* Respects all ``EPICS_CA*`` environment variables, correctly configuring
  interfaces and ports.
* Connection caching
* Automatic reconnection
* Batching of requests for efficiency

TO DO:

* Back-off of unanswered search requests
* "Flow control" --- automatic temporary suspension of subscriptions when
  under high load using ``EventsOn`` and ``EventsOff``

Synchronous Client and Command-Line Client
==========================================

Supported:

* Respects all ``EPICS_CA*`` environment variables, correctly configuring
  interfaces and ports.
* Most of the command-line arguments that ``caget``, ``caput``, ``camonitor``
  take work the same on ``caproto-get``, ``caproto-put``, ``caproto-monitor``
* Monitoring of multiple channel concurrently using a selector

TO DO:

* Complete coverage of all command-line arguments
* Automatic reconnection

Servers
=======

Supported:

* Respects all ``EPICS_CAS*`` environment variables, correctly configuring
  interfaces and ports.
* Channel Access filters (arr, dbnd, ts, sync) including their "shorthand"
  syntax
* DBE mask specification

TO DO:

* Enforcing quotas per subscription to avoid one prolific subscription (or slow
  client) from drowning out others
* Respecting ``EventsOn`` and ``EventsOff``
* Deprecated mask specification (low, high, to)
