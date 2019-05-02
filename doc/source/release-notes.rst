***************
Release History
***************

v0.3.4 (2019-05-02)
===================

Fixes
-----
* Several fixes and documentation for the commandline utilities' formatting
  parameters added in v0.3.3.
* Put an upper limit on how quickly a given search result may be reissued.
* Documentation fix in server help string.

v0.3.3 (2019-04-11)
===================

This release improves the commandline utilities' parity to their counterparts
in the reference implementation by supporting formatting parameters for
integers and floats. It also includes some important fixes.

Fixes
-----

* When optional dependency ``netifaces`` is installed, clients search on all
  broadcast interfaces, not just ``255.255.255.255``. This reverts an erroneous
  change made in v0.2.3.
* ``caproto-shark`` does a better job ignoring non-CA packets (instead of
  erroring out).

v0.3.2 (2019-03-06)
===================

This release inclues just one minor fix to :doc:`caproto-shark <shark>`,
enabling it to more reliably skip over irrelevant network traffic (i.e. traffic
that is not Channel Access messages).

v0.3.1 (2019-03-05)
===================

This is a bug-fix release addressing issues related to empty (zero-length)
channel data.

Fixes
-----

* Fix servers' support for empty (zero-length) data.
* Assume the *maximum* length of a channel initialized with empty data is one
  (i.e. assume it is scalar).
* Address an ambiguity in the Channel Access protocol: a subscription update
  (``EventAddResponse``) indicating empty data and a confirmation of a request
  to cancel the subscription (``EventCancelResponse``) serialize identically,
  and so the client must make a best effort to interpret based on context which
  of the two is intended.

v0.3.0 (2019-02-20)
===================

This release introduces :doc:`caproto-shark <shark>` and other convenient
improvements. It also contains many bug-fixes, some critical.

Features
--------

* Add :doc:`shark`.
* Add server "healthcheck" methods to the threading client, which expose
  information collected about how recently each server has communicated with
  the client. See :ref:`server_health_check`.
* Add a new example IOC who PVs are dynamic (change during runtime). Include a
  "waveform" (array) PV in the simple example.
* Make the default timeout configurable per Context and per PV, in addition to
  per a given operation. This makes it possible to adjust all the timeouts in
  one place during debugging.
* Use a random starting ID for message identifiers as an extra layer of
  protections against collisions, especially in the context of CI testing where
  many clients and servers are started up in rapid succession.

Bug Fixes
---------

* Only attempt to use ``SO_REUSEPORT`` socket option if support for it has been
  compiled into Python.
* A critical bug only affecting Windows had broken asyncio servers on Windows
  in a previous release.
* The threading client was wrongly issuing warnings if it received multiple
  responses to a search for a PV from *the same server*.
* Add missing user_offset pvproperty to MotorFields.
* Fix several race conditions in the threading client.
* Improve cleanup of resources: ensure sockets are explicitly closed and
  threads explicitly joined. (More work is needed, but progress was made.)
* Fix "leak" of ioids (IO message identifiers).
* Handle setting empty lists as values through the pyepics-compat client.
* In the trio-backed server, remove usage of deprecated ``trio.Queue``.
* Many other small fixes and safeguards.

v0.2.3 (2019-01-02)
===================

Usability Improvements
-----------------------

* A new function :func:`~caproto.set_handler` provides a convenient way to make
  common customizations to caproto's default logging handler, such as writing
  to a file instead of the stdout.
* In the threading client, store the current access rights level on the PV
  object as ``pv.access_rights``. It was previously only accessible when it
  *changed*, via a callback, and had to be stashed/tracked by user code.
* Display the version of caproto in the output of ``--help``/``-h`` in the
  commandline utilities. Add a new commandline argument ``--version``/``-V``
  that outputs the version and exits.
* In the threading client, DEBUG-log *all* read/write requests and
  read/write/event responses. (When these log messages were first introduced in
  v0.2.1, batched requests and their responses were not logged, and write
  responses were not logged when ``notify=True`` but ``wait=False``.)

Bug Fixes
---------

* Fix critical bug in synchronous client that broke monitoring of multiple PVs.
* Fix default ("AUTO") broadcast address list (should always be
  ``255.255.255.255``). Removed internal utility function
  :func:`broadcast_address_list_from_interfaces`.
* In pyepics-compatible client, set default mask to
  ``SubscriptionType.DBE_VALUE | SubscriptionType.DBE_ALARM``, consistent with
  pyepics.
* Prevent subscriptions for being processed for all channels that share an
  alarm if the alarm state has not actually changed.

Updated Pyepics Compatibility
-----------------------------

* Added new method ``PV.get_with_metadata``, which was added in pyepics 3.3.1.

Deprecations
------------

* The :func:`~caproto.color_logs` convenience function has been deprecated in
  favor of :func:`~caproto.set_handler`.

Internal Changes
----------------

* Enable ``-vvv`` ("very verbose") option when running example IOCs in test
  suite.

v0.2.2 (2018-11-15)
===================

The release improves the performance of the threading client and adds support
for value-based alarms. Additionally, it provides more control over search and
implements back-off in a way more consistent with (but not yet fully consistent
with) EPICS' reference implementation.

More Control Over Search
------------------------

The threading client---and, thereby, the pyepics-compatible shim---have
greater feature parity with epics-base.

* In previous releases, the client resent any unanswered ``SearchRequests`` at
  a fast regular rate forever. Now, it backs off from that initial rate and
  rests at a slow interval to avoid creating too much wasteful network traffic.
  There is a new method,
  :meth:`~caproto.threading.client.SharedBroadcaster.cancel`, for manually
  canceling some requests altogether if a response is never expected (e.g. a
  typo). There is also a new method for manually resending all unanswered
  search requests,
  :meth:`~caproto.threading.client.SharedBroadcaster.search_now`,
  primarily for debugging. All unanswered search requests are automatically
  resent when the user searches for a new PV or when a new server appears on
  the network (see next point).
* The client monitors server beacons to notice changes in the CA servers on the
  network. When a new server appears, all standing unanswered search requests
  are given a fresh start and immediately resent. If a server does not send a
  beacon within the expected interval and has also not sent any TCP packets
  related to user activity during that interval, the client silently initiates
  an Echo. If the server still does not respond, it is deemed unresponsive. The
  client logs a warning and disconnects all circuits from that server so that
  their PVs can begin attempting to reconnect to a responsive server.


Improved Alarm Support
----------------------

* Value-based alarms are supported by all servers.
* LOLO, LO, HI, and HIHI alarm status fields of mocked records are respected.
* Channel limit metadata (upper_alarm_limit, upper_warning_limit, etc.) is now
  integrated with alarms.

Bug Fixes and Performance Improvements
--------------------------------------

* The socket settings ``SO_KEEPALIVE`` and ``TCP_NODELAY`` are used in the
  threading client TCP sockets, making it consistent with epics-base and removing a 40ms
  overhead that can occur when sending small packets.
* Some unnecessary locking was removed from the threading client, resolving
  a deadlock observed in ophyd and improving performance.
* The ``spoof_beamline`` IOC is aware of more components of Area Detector and
  defaults to float-type channels instead of integer-type.
* A rare but possible race condition that caused a subscription to be activated
  twice (thus getting two responses for each update) has been resolved.
* The ``ChannelData`` objects are serializable with pickle.
* A bug in length-checking that affected zero-length data has been fixed.

The detail and consistency of the exceptions raised by the clients has also
been improved.

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
  callbacks never to be called when underlying ``caproto.threading.client.PV``'s were reused.
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
  (< 0.1 milliseconds). We take a different approach, making all writes
  asynchronous. This ensures that an accidentally-slow write cannot lock up the
  server. It adds latency to some reads, up to a hard maximum of 1 millisecond,
  giving the effect of synchronous write whenever the write finishes fast.

The release also includes one small new feature: in the threading client,
DEBUG-level logging of channels/PVs ``caproto.ch`` now logs (non-batch)
read/write requests and read/write/event responses. [Update: In v0.2.3,
this feature was extended to include batched requests and their responses.]
Related --- there is expanded documentation on :doc:`loggers`.

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
users upgrade.

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
