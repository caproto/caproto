***************
Release History
***************

v0.2.1 (2018-10-29)
===================

This release tunes server performance under high load and fixes several subtle
bugs in the server identified via
`acctst <https://epics.anl.gov/base/R3-16/2-docs/CAref.html#acctst>`_,
the server acceptance test that ships with ``epics-base``.

Bug Fixes
---------

* When a new Subscription is added, send the most recent value immediately but
  only to the *new* Subscription. Previous releases sent redundant messages
  to *all* Subscriptions that had similar parameters.
* Reduce the maximum size of a datagram of search requests to match the typical
  Maximum Transmission Unit seen in the wild.
* Fix a bug in the pyepics-compatibility layer that caused the connection
  callbacks never to be called when underlying ``caproto.threading.client.PV``s were reused.
* Fix a typo in the PV names in the ``spoof_beamline`` IOC.
* Never send an ``EventAddResponse`` after a matching ``EventCancelResponse``
  has been sent.
* Always send a response to a failed write, and include the correct error code.
* If a circuit has an oversized backlog of received commands to process, log a
  WARNING before disconnecting.

Server Performance Tuning
-------------------------

* Increase the max backlog of subscription updates queued up to send (both
  updates per specific Subscription and total updates per circuit) by a factor
  of 10. Likewise for the max backlog of received commands queued up to
  process.
* When under sustained high load of subscription updates to send, iteratively
  double the latency between packets up to at most 1 second to achieve higher
  overall throughput (more commands per packet, less overhead).
* When a ``Read[Notify]Request`` arrives on the heels of a
  ``Write[Notify]Request``, wait for up to 0.001 seconds for the write to
  process before reading the current value. If the write happens to complete
  in less than 0.001 seconds, the read will reflect the new value. This
  behavior is in the spirit of, but distinct from, EPICS' "synchronous writes."
  EPICS allows a device to block while writing if it promises to finish quickly
  (< 0.1 miliseconds). We take a different approach, making all writes
  asynchronous. This ensures that an accidentally-slow write cannot lock up the
  server. It adds latency to some reads, up to a hard maximum of 1 milisecond,
  giving the effect of synchronous write whenever the write finishes fast.

The release also includes one small new feature: in the threading client,
DEBUG-level logging of channels/PVs ``caproto.ch`` now logs (non-batch)
read/write requests and read/write/event responses. Related --- there is
expanded documentation on :doc:`loggers`.

v0.2.0 (2018-10-17)
===================

This release improves compliance with the protocol and server performance under
high load.

Features
--------

* Under high load (with many subscription updates queued up to send) servers
  batch subscriptions into blocks, trading a little latency for efficiency.
  Under low load, servers prioritize low latency.
* The servers' medium-verbose setting (``-v``) displays current load and
  latency.
* In the threading client, process user callbacks using one threadpool *per
  circuit* instead of one threadpool for the entire context. Make the size of
  the threadpool configurable via a new
  :class:`~caproto.threading.client.Context` parameter, ``max_workers``.
* We now test the servers against a
  `Python 3-compatible fork <https://github.com/klauer/catvs/tree/py3k>`_ of
  Michael Davidsaver's utility for testing Channel Access servers,
  `catvs <https://github.com/mdavidsaver/catvs>`_. This has generated several
  fixes improving protocol compliance, list a section below. There are a small
  number of known failures wherein the best/correct behavior is arguable; see
  `caproto#327 on GitHub <https://github.com/NSLS-II/caproto/pull/327>`_ for
  discussion. There may be more progress on these in future releases of
  caproto.
* Added ``pvproperty.scan``. See
  the `mini_beamline example IOC <https://github.com/NSLS-II/caproto/blob/master/caproto/ioc_examples/mini_beamline.py>`_
  for a usage example.
* Add a server-side data source for ``ChannelType.INT`` (a.k.a SHORT) data.
* The default printed output of the ``caproto-monitor`` CLI utility now
  includes microseconds.
* There are several new `IOC examples <https://github.com/NSLS-II/caproto/tree/master/caproto/ioc_examples>`_.

Breaking Changes
----------------

* The expected signature of the ``access_rights_callback`` passed to
  :class:`~caproto.threading.client.Context` has been changed from
  ``f(access_rights)`` to ``f(pv, access_rights)``. This makes it consistent
  with the ``connection_callback``.
* If a beacon fails to send, do not kill the server; just log the failure,
  along with a suggestion on how to fix the environment to omit the failed
  address, and continue to run.
* In the high-level server, implemented with ``pvproperty``, PV values can be
  defined as scalars. The accessor ``pvproperty.value`` now returns a scalar
  instead of a length-1 list (API break), while ``write()`` accepts either list
  or scalar.

Bug Fixes
---------

* A critical bug CHAR-type payload serialization which made caproto clients
  unusable with CHAR-type channels has been fixed.
* The asyncio server now executes its cleanup code when interrupted with SIGINT
  (Ctrl+C).
* All three servers were relying on the operating system to clean up their
  sockets when the process exited. They now close their sockets explicitly when
  the server task exits. This fixes the runaway usage of file descriptors when
  the tests are run.

Improved Protocol Compliance
----------------------------

* The servers send :class:`~caproto.CreateChFailResponse` when the client
  requests a channel name that does not exist on the server. They previously
  did not respond.
* The servers reply to :class:`~caproto.SearchRequest` messages sent over TCP.
  (UDP is more common, but TCP is allowed.) They previously did not respond.
* The :class:`~caproto.EventCancelResponse` message includes a ``data_count``.
* The servers respect the ``data_count`` requested by the client.
* Servers enforce quota per subscription to avoid one prolific subscription (or
  slow client) from drowning out others.
* Servers respect ``EventsOn`` and ``EventsOff`` requests.
* Servers differentiate between *current* length and *maximum* length of an
  array, and they properly declare the *maximum* length in
  :class:`~caproto.CreateChanResponse`. They formerly declared the *current*
  length, which was not correct.
* The ``caproto-put`` commandline utility now supports ``-a`` for arrays.

v0.1.2 (2018-08-31)
===================

This is a bug-fix release fixing some critical bugs. We recommend that all
users ugprade.

* Fix critical typo in threading client's search functionality that could cause
  it to conflate addresses from different search responses and then attempt to
  connect to the wrong server.
* Fix handshake with servers and clients speaking Version 11 (or older) of the
  protocol.

v0.1.1 (2018-06-17)
===================

This is a bug-fix release following closely on the initial release. We
recommend that all users update.

* Fix straightforward but important bug in the synchronous client that broke
  monitoring of multiple channels concurrently.
* In servers, abide by the spec's recommendation that beacons should be issued
  quickly at startup before backing off to a slower, steady rate.
* Fix a bug that broke the array ("arr") channel filter if numpy was not
  installed.
* Add a new section to the documentation detailing caproto's compliance with
  the Channel Access protocol and the feature parity of caproto's clients and
  servers with respect to the reference implementations in epics-base.

v0.1.0 (2018-06-14)
===================

This initial release contains some fairly stable components and some very
experimental ones.

* The core protocol code, the synchronous client, the threading client, and the
  pyepics-compatible client are fairly stable.
* The high-level interface to IOCs has no known issues but could in a future
  release of caproto, as we gain experience from its use.
* The three server implementations are thoroughly tested, but their low level
  API is likely to change in a future release.
* The asynchronous client implementations (trio client and curio client) are
  highly experimental. They lack feature-parity with the other clients and have
  some known bugs. They may be heavily revised or removed in a future release
  of caproto.
