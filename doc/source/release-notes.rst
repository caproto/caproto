***************
Release History
***************

v1.0.1 (2023-03-29)
===================

Added / Fixed
-------------

* Timeout no longer ignored in pyepics_compat's caget_many (@mcnanneyd, #806)
* New example: Lakeshore temperature controller (@gwbischof, #809)


v1.0.0 (2022-09-01)
===================

Breaking Changes
----------------

- Python 3.6 and Python 3.7 support has been dropped. Python 3.8 through Python
  3.10 are now targeted for support.
- PVAccess support has been removed, and caproto returns to being solely an
  EPICS Channel Access library.
- Top-level utility functions for accessing pvAccess environment variables
  are now deprecated and will be reverted to pre-pvAccess (no protocol argument
  allowed) signatures in a future release.

Added / Fixed
-------------

- Fixes for all Windows clients, servers, and the repeater relating to PV
  searches. ``recvfrom`` was occasionally raising ``ConnectionResetError``,
  which on Windows only means that: "... a previous send operation resulted in
  an ICMP Port Unreachable message."  This is not fatal in caproto's case and
  can safely be ignored (or worked around, in the case of asyncio).
  https://docs.microsoft.com/en-us/windows/win32/api/winsock/nf-winsock-recvfrom
- Fixed pickle/copy for ChannelData subclasses
- Fixed synchronous repeater bind address to INADDR_ANY ("0.0.0.0").  Binding
  to a specific interface meant that on Windows the repeater could not use
  its client-is-alive detection mechanism by binding to the client port as
  the bind would always succeed.
- Updated method ``get_data_class()`` in PVSpec so that type maps are correct for
  read-only.
- Use RotatingFileManager filename when restoring autosave.
- Provide defaults for user limits in motor record simulation.
- pvproperty no longer broken when decorating methods with docstring.
- Type annotations have been added to ``caproto.server.server``.
    - ``pvproperty`` and ``PVSpec`` may now use the data class directly, instead of
      requiring an internal mapping of data type to class. For example,
      ``pvproperty(..., dtype=PvpropertyInteger)`` is allowed alongside the
      existing and less explicit ``pvproperty(..., dtype=int)``.
    - Using such classes directly comes with the added benefit of type
      inference with your IDE's language server / static analyzer. pyright and
      similar should be much happier with caproto IOCs that use ``pvproperty``
      such that linting of attributes on pvproperty instances, features as "Go
      to source", and code completion are now possible.

Development
-----------

- Adjusted continuous integration jobs to reflect new supported versions.
- Improved test suite reliability on continuous integration.
- Removed buffer-slicing tools and tests in a refactor to avoid ``sendmsg`` on
  all platforms and async libraries.
- Removed some old windows compatibility patches in
  ``caproto._windows_compat``, and avoided monkey-patching for curio by moving
  its Windows-facing ``curio.run`` modification to
  ``caproto.curio.utils.curio_run``.
- Test suite has some built-in timeout-handling functionality on a
  per-async-library basis, avoiding exiting the entire test suite on Windows
  (due to limitations of ``pytest-timeout``).
- Trio socket handling has been updated to follow better practices for recent
  trio versions.

v0.8.1 (2021-06-03)
===================

Fixed
-----

- pyepics compatibility layer should no longer leak a byte string ``value``
  through for DBR_STRING ``PV`` instances.  (#710, #763)

Added
-----

- Added support for raw EPICS timestamps in ``ChannelData`` instances, allowing
  for lossless representation and transmission of facility-specific beam
  fiducials, pulse IDs, and such.  This feature is not intended to replace the
  current usage of POSIX (``time.time()``) timestamps, but rather extend what
  is considered to be acceptable input.


v0.8.0 (2021-03-18)
===================

Fixed
-----

- pyepics compatibility layer ``char_value`` and ``enum_strs`` handling with
  ``PV`` instances and ``caget_many`` should now behave better.  (#732)
- Windows compatibility has been improved, especially with respect to
  the more recent ProactorEventLoop (#720, #707)
- The environment variable ``CAPROTO_DEFAULT_TIMEOUT`` is no longer erroneously
  interpreted as a string.  All clients should now mostly respect this value.
  (#727)
- Previously only either ``scan`` or ``startup`` hooks were allowed
  per-``pvproperty``.  Both may be used simultaneously now. (#729)
- Threading client ``SharedBroadcaster`` should no longer attempt
  re-registration after it is disconnected.  (#732)
- RecordFieldGroup subclasses may now customize common fields without
  intefering with other classes. (#736)
- Supports the numpy array interface to remove a significant ``O(n)``
  bottleneck when pre-processing numpy arrays for ``ChannelByte`` instances.
  To avoid an additional copy on immutable data, set ``value.flags.writeable``
  to ``False`` when using compatible numpy arrays.  (#731)
- ``safe_getsockname`` was stashing references to sockets and not allowing
  them to be garbage collected. (#739)
- ``data_type`` values are now validated against ``ChannelType`` when used in
  commands. (#742)
- Raise ``RemoteProtocolError`` with more user-friendly messages when invalid
  packets or those with invalid command IDs are received. (#743)
- Synchronous client search erroneously used the same search ID for multiple
  requests. (#754)

Added
-----

- An example indicating how to analyze IOCs response times for channel creation
  was added in #725.
- A ``value_write_hook`` is now supported when updating a value in records.
  This means that if the user updates ``.VAL``, other fields will have the
  chance to update their state. (#734)
- Added preliminary support of the ``raw_value`` (``.RVAL``) field for bi, bo,
  mbbi, and mbbo records.  (#734)
- Added ``sleep`` to AsyncLibraryLayer. (#739)
- Added ``startup_hook`` to ``caproto.server.run()`` (with support in asyncio,
  curio, trio).  By convention, consider using ``__ainit__`` for this hook.
  (#739)
- Added ``monitor`` helper to the asyncio client. (#739)
- Now using GitHub actions for automated testing on Windows and macOS,
  with fixed documentation building and releasing to PyPI.  This was defunct
  since Travis CI changed its payment model. (#749, #754)

Changed
-------

- The ``mock_record=`` keyword argument for ``pvproperty``, deprecated in
  v0.5.0, has been removed.  Please change any remaining references to
  ``record=`` when upgrading to v0.8.0.
- Efforts have been made to allow ``PVSpec`` to be used in a standalone
  fashion - i.e., without ``pvproperty``.  See the ``no_pvproperty`` IOC
  example (``ioc_examples/advanced``) for further details.
- asyncio-based transports have mostly been removed in favor of using a
  higher-level API provided by asyncio. This should allow for more precise
  and informative exception tracebacks.  This is now used for all asyncio
  servers and clients supported by caproto. (#720)
- The method for generating record field ``PVGroup`` classes has been changed
  to better split auto-generated code with user-customizable field-handling
  code. (#734)
- Improved hook method signature checker to include source code filename,
  line number, and suggested signature.  (#736)
- Reworked IOC documentation and corresponding examples.
- Old and bad form example ``all_in_one`` moved to testing area.
- Old and bad form example ``inline_style`` moved to testing area.
- Example using ChannelData ``type_varieties`` moved to "advanced"
- On-class-definition validation of ``PvpropertyData`` keyword arguments was
  removed to reduce complexity.  ``CaprotoRuntimeError`` will be raised on
  instantiation for pvproperties with bad keyword arguments, indicating
  the cause and full ``PVSpec`` information. (#741)
- Warning messages when old CA clients are detected have been removed.  The
  reasoning behind the message was likely flawed and will require further
  investigation.  In the meantime, this will reduce log spam.  (#757, #761)


v0.7.1 (2020-01-13)
===================

Fixed
-----

- For ``pvproperty``, avoid multiple passes of macro expansion, so
  {% raw %}``{{``{% endraw %} is now sufficient to escape curly brackets in PV
  names.
- The server implementation will now catch when `socket.recv` raises `OSError`.
- Broken entrypoints have been fixed for the pathological examples,
  ``defaultdict_server`` and ``spoof_beamline``.

Added
-----

- Show default values for optional macro substitution for IOCs using the
  template parser.

Changed
-------

- Travis CI configuration has been removed from the repository.


v0.7.0 (2020-12-08)
===================

Fixed
-----

- Eliminate memory leak on run-longing servers were we remembered
  every search request we saw but did not service
- ``WaitForPlugins`` and additional PVs for compatibility were added in
  the fancy ``spoof_beamline`` example.
- Many more libraries are now entirely optional in the test suite.
- ``get_pv_pair_wrapper`` now supports keyword arguments to the generated
  ``pvproperty`` instances.

Added
-----

- Added documentation notes on multi-tenant soft IOCs.
- Added helper tools for easily auto-generating ``PVGroup``-based IOC
  documentation with sphinx-autosummary.
- A fake motor record IOC example, with the most common fields implemented.
- Added iocStats-like helpers for caproto-based IOCs, which include CPU/memory
  usage information, tools for finding memory leaks, and so on.
- Add support for ``-#`` arguments in ``caproto-get`` and ``caproto-monitor``
  command-line tools.
- ``IntEnum`` values are now supported for ``pvproperty``, simplifying
  declarations of enum PVs.
- Added preliminary pvAccess support, including examples and documentation.
- Added a shared memory IOC example.
- Added a gamepad IOC example.
- Added an IOC which generates PVs based on a formula string.
- Added an escape hatch for pvproperty putters to skip further processing, the
  ``SkipWrite`` exception.

Changed
-------

- The search related API was removed from :class:`ca.Broadcaster`, all
  of the search request accounting is handled in the client code.  The
  code that is used on the servers can not do this book keeping
  because we can not know what other servers are out there and if the
  SearchRequest actually got serviced (as that goes back uni-cast).
- Removed curio and trio client implementations.  These may reappear
  in the future, based on the new asyncio client.
- Removed unused dependency ``asks``, which was part of the full installation.
- Documentation is now versioned on GitHub pages thanks to doctr-versions-menu.
- Automated benchmarking code which was previously part of the test suite, has
  been removed.
- Unmaintained prototype-level clients based on ``trio`` and ``curio`` have
  been removed.  The full-featured ``asyncio`` client from v0.6.0 is the
  suggested migration path.
- IOC examples have been reorganized.
- Updated continuous integration to use conda-forge epics-base.


v0.6.0 (2020-07-31)
===================

Fixed
-----

- Fixed server PVGroup logger names.  It was erroneously using the exact string
  '{base}.{log_name}', and now will be correctly expanded to be based on either
  the module name or the parent PVGroup's logger name.
- Fields defined in the :class:`caproto.server.records.RecordFieldGroup` may
  now be customized using, for example, ``@prop.fields.process_record.putter``.
- :class:`caproto.ChannelByte` and :class:`caproto.ChannelChar` with
  ``max_length=1`` now accept scalar integer values, whereas they were
  previously failing due to expecting byte strings (or strings).  This arose
  primarily in the case of record fields which attempt to reflect the actual
  data types found in epics-base.

Added
-----

- Added a new (experimental) asyncio client with features comparable to the
  threading client.
- Allow :class:`caproto.server.SubGroup` instances to accept keyword arguments.
- Added autosave-like tools and an example.
- Now using ``doctr-versions-menu`` for documentation.

Changed
-------

- Significantly refactored task handling in the asyncio server.  This improves
  the performance of write request handling and overall task cleanup.
- Some asyncio server utilities were relocated such that the server and new
  client can both utilize them.
- Accessing a :class:`caproto.server.pvproperty` directly from the
  :class:`caproto.server.PVGroup` class will no longer return a
  :class:`caproto.server.PVSpec` instance, but the
  :class:`caproto.server.pvproperty` itself.


v0.5.2 (2020-06-18)
===================

Fixed
-----

- Fixed a packaging issue introduced in 0.5.1 where some files were missing
  in the ``sdist`` source distribution package.
- Prevent an error from occurring when trying to subscribe, with a callback,
  to a PV that is not yet connected. The subscription will now succeed and
  become active once the PV is fully connected.
- Avoid duplicate registration of callbacks in ``Context.get_pvs()``.

v0.5.1 (2020-06-12)
===================

Changed
-------

* Replaced usage of deprecated trio features with recommended approaches.
* Updated curio-based server for compatibility with recent versions of curio.
  It is now incompatible with curio < 1.2.

Added
-----

* Added ``vel`` and ``mtr_tick_rate`` pvproperties to ``PinHole``, ``Edge``
  and ``Slit`` motors on mini beamline example, to provide control over the
  speed of the motors.
* Added documentation on how to build and run caproto containers using
  ``buildah`` and ``podman``.
* Add a new ``test`` pip selector, as in ``pip install caproto[test]``, which
  installs ``caproto[complete]`` plus the requirements for running the tests.

v0.5.0 (2020-05-01)
===================

Changed
-------

* In the threading client, the expected signature of Subscription callbacks has
  changed from ``f(response)`` to ``f(sub, response)`` where ``sub`` is the
  pertinent :class:`caproto.threading.client.Subscription`.
  This change has been made in a backward-compatible way. Callbacks with the
  old signature, ``f(response)``, will still work but caproto will issue a
  warning. Support for the old signature may be removed in the future.
  By giving the callback ``f`` access to ``sub``, we enable usages like

  .. code-block:: python

     def f(sub, response):
         # Print the name of the pertinent PV.
         print('Received response from', sub.pv.name)

     def f(sub, response):
         if ...:
             sub.remove_callback(f)

* In the synchronous client, the expected signature of subscription callbacks
  has changed from ``f(response)`` to ``f(pv_name, response)``. As with the
  similar change to the threading client described above, this change was made
  an a backward-compatible way: the old signature is still accepted but a
  warning is issued.
* The detail and formatting of the log messages has been improved.
* The ``mock_record`` keyword argument to :class:`caproto.server.pvproperty`
  has been deprecated, in favor of the simpler ``record``.
* EPICS record field support has been regenerated with a new database
  definition source.  This reference ``.dbd`` file can be found in a separate
  repository `here <https://github.com/caproto/reference-dbd>`_. These fields
  should now be more accurate than previous releases, including some initial
  values and better enum values, and also with basic round-trip tests verifying
  protocol compliance for each field.

Added
-----

* Added IOC server support for long string PVs.
    - Channel Access maximum string length is 40 characters
    - However, appending ``$`` to ``DBF_STRING`` fields (e.g.,
      ``MY:RECORD.DESC$``) changes the request to ``DBF_CHAR``, allowing for
      effectively unlimited length of strings.
    - This is supported for :class:`caproto.server.pvproperty` instances which
      are initialized with a string value (or specify
      ``caproto.ChannelType.STRING`` as the data type).
    - This is supported internally by way of
      :class:`caproto._data.ChannelString`, which adds an init keyword argument
      ``long_string_max_length``.
* Added documentation for fields of all supported record types.
* Tools for automatically regenerating record fields and menus via a Jinja
  template are now included. See
  :func:`caproto.server.conversion.generate_all_records_jinja` and
  :func:`caproto.server.conversion.generate_all_menus_jinja` and the related
  jinja templates in ``caproto/server``.

Fixed
-----

* On OSX, the creating a :class:`threading.client.Context` pinned a CPU due to
  a busy socket selector loop.
* When ``EPICS_CA_ADDR_LIST`` is set and nonempty and
  ``EPICS_CA_AUTO_ADDR_LIST=YES``, the auto-detected addresses should be used
  *in addition to* the manually specified one. They were being used *instead*
  (with a warning issued).

v0.4.4 (2020-03-26)
===================

Fixed
-----

* The fix for Python asyncio's servers released in 0.4.3 had the accidental
  side-effect of preventing multiple servers from running on the same machine
  (or, to be precise, on the same network interface). This release fixes that
  regression.
* Fix bug in ``caproto-put`` which made it impossible to set ENUM-type PVs.
* Ensure that caproto servers respect the limits on the number of enum members
  and the length of enum streams.

v0.4.3 (2020-01-29)
===================

Python releases 3.6.10, 3.7.6, and 3.8.1 made a breaking change for security
reasons that happens to break caproto's asyncio-based server (the default one)
on all platforms. This release adjusts for that change. See
:meth:`asyncio.loop.create_datagram_endpoint` for details about this change in
Python.

This release also fixes a bug introduced in v0.4.0 affecting Windows only that
made caproto clients and servers unusuable on Windows.

v0.4.2 (2019-11-13)
===================

This release contains some important bug fixes and some minor new features.

Features
--------
* Make the default timeout for the threading client configurable via the
  environment variable ``CAPROTO_DEFAULT_TIMEOUT``. It was previously
  hard-coded to ``2`` (seconds).
* Add ``--file`` argument to ``caproto-put``, which obtains the value to be put
  from reading a file.
* Link ZNAM and ONAM fields to the parent enum_strings.
* Automatically populate ``pvproperty`` DESC using doc keyword argument.

Bug Fixes
---------
* Fix a critical race condition wherein data could be written into a buffer as
  it was being sent.
* Propagate timeout specific to pyepics-compatible client to the next layer
  down.
* Correctly handle reconnection if the server dies.
* Allow asyncio server to do cleanup in all cases. (Previously,
  ``KeyboardInterrupt`` was erroneously exempted from cleanup.)
* Let the server's ``write`` method provide the timestamp. This is significant
  if the putter takes significant time to process or does any internal writes.

v0.4.1 (2019-10-06)
===================

This release adds some small improvements and updates to address deprecations
in Python and caproto's optional dependencies.

Features
--------
* Added support for ``-S`` argument in the ``caproto-put`` commandline tool.
* Added support for using ``Event`` synchronization primitives in servers, used
  in the new example ``caproto.ioc_examples.worker_thread_pc``.

v0.4.0 (2019-06-06)
===================

Features
--------
* Rewrite approach to logging. See :doc:`loggers` for details.
* Add precision to motor_ph in mini_beamline example IOC.

Bug Fixes
---------
* Fix bug in `scan_rate` that raised errors when it was written to
* Respond correctly when channel filter is set but empty.

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
  `caproto#327 on GitHub <https://github.com/caproto/caproto/pull/327>`_ for
  discussion. There may be more progress on these in future releases of
  caproto.
* Added ``pvproperty.scan``. See
  the `mini_beamline example IOC <https://github.com/caproto/caproto/blob/master/caproto/ioc_examples/mini_beamline.py>`_
  for a usage example.
* Add a server-side data source for ``ChannelType.INT`` (a.k.a SHORT) data.
* The default printed output of the ``caproto-monitor`` CLI utility now
  includes microseconds.
* There are several new `IOC examples <https://github.com/caproto/caproto/tree/master/caproto/ioc_examples>`_.

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
