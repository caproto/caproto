***************
Release History
***************

Unreleased
==========

Features
--------

* In the threading client, process user callbacks using one threadpool *per
  circuit* instead of one threadpool for the entire context. Make the size of
  the threadpool configurable via a new
  :class:`~caproto.threading.client.Context` parameter, ``max_workers``.
* We now test the servers against a
  `Python 3-compatible fork <https://github.com/klauer/catvs/tree/py3k>`_ of
  Michael Davidsaver's utility for testing Channel Access servers,
  `catvs <https://github.com/mdavidsaver/catvs>`_. This has generated several
  bug fixes, included in the list below. There are a small number of known
  failures wherein the best/correct behavior is arguable; see
  `caproto#327 on GitHub <https://github.com/NSLS-II/caproto/pull/327>`_ for
  discussion. There may be more progress on these in future releases of
  caproto.
* Added ``pvproperty.scan``. See
  the `mini_beamline example IOC <https://github.com/NSLS-II/caproto/blob/master/caproto/ioc_examples/mini_beamline.py>`_
  for a usage example.
* Support 'Short' an as alias for 'Int' in sever and data modules.
* The default printed output of the ``caproto-monitor`` CLI utility now
  includes microseconds.

Breaking Changes
----------------

* The expected signature of the ``access_rights_callback`` passed to
  :class:`~caproto.threading.client.Context` has been changed from
  ``f(access_rights)`` to ``f(pv, access_rights)``. This makes it consistent
  with the ``connection_callback``.
* If a beacon fails to send, do not kill the server; just log the failure,
  along with a suggestion on how to fix the environment to omit the failed
  address, and continue to run.

Bug Fixes
---------

* The asyncio server now executes its cleanup code when interrupted with SIGINT
  (Ctrl+C).
* All three servers were relying on the operating system to clean up their
  sockets when the process exited. They now close their sockets explicitly when
  the server task exits. This fixes the runaway usage of file descriptors when
  the tests are run.
* The servers send :class:`~caproto.CreateChFailResponse` when the client
  requests a channel name that does not exist on the server. They previously
  did not respond.
* The servers reply to :class:`~caproto.SearchRequest` messages sent over TCP.
  (UDP is more common, but TCP is allowed.) They previously did not respond.
* The :class:`~caproto.EventCancelResponse` message includes a ``data_count``.
* The servers respect the ``data_count`` requested by the client.

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
