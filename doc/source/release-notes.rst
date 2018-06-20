***************
Release History
***************

Unreleased
==========

* In the threading client, process user callbacks using one threadpool *per
  circuit* instead of one threadpool for the entire context. Make the size of
  the threadpool configurable via a new
  :class:`~caproto.threading.client.Context` parameter, ``max_workers``.

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
