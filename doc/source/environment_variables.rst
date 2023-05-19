*********************
Environment Variables
*********************


.. list-table:: Client Environment Variables
   :header-rows: 1

   * - Variable
     - Default
     - Description
   * - CAPROTO_DEFAULT_TIMEOUT
     - 2.0
     - The default timeout to use for client connections and reading.
   * - CAPROTO_STRING_ENCODING
     - "latin-1"
     - The default string encoding to use.
   * - CAPROTO_CLIENT_AUTOMONITOR_MAXLENGTH
      - 65536
      - Toggle automatic monitoring of PVs based on this.
   * - CAPROTO_CLIENT_BEACON_MARGIN
      - 1
      - The margin after EPICS_CA_CONN_TMO for beacons to arrive (seconds).
   * - CAPROTO_CLIENT_EVENT_ADD_BATCH_MAX_BYTES
     - 2**16 = 65536
     - Requests are batched when sent on the wire if they are under this
       threshold.
   * - CAPROTO_CLIENT_MAX_RETRY_SEARCHES_INTERVAL
     - 5
     - Retry searches for PVs at this interval.
   * - CAPROTO_CLIENT_MIN_RETRY_SEARCHES_INTERVAL
     - 0.03
     - Minimum interval for retrying searches.
   * - CAPROTO_CLIENT_RESTART_SUBS_PERIOD
     - 0.1
     - After a circuit reconnection, wait this number of seconds and then re-activate
       previous subscriptions.
   * - CAPROTO_CLIENT_RETRY_RETIRED_SEARCHES_INTERVAL
     - 60
     - For the searches older than SEARCH_RETIREMENT_AGE, we adopt a slower
       period to minimize network traffic. We only resend every
       RETRY_RETIRED_SEARCHES_INTERVAL or, again, whenever new searches are
       added.
   * - CAPROTO_CLIENT_SEARCH_RETIREMENT_AGE
     - 480
     - We then frequently retry the unanswered searches that are younger than
       SEARCH_RETIREMENT_AGE, backing off from an interval of
       MIN_RETRY_SEARCHES_INTERVAL to MAX_RETRY_SEARCHES_INTERVAL. The interval
       is reset to MIN_RETRY_SEARCHES_INTERVAL each time new searches are
       added.
   * - EPICS_CA_ADDR_LIST
     - ''
     - The client address list.
   * - EPICS_CA_AUTO_ADDR_LIST
     - 'YES'
     - Whether or not to automatically determine the address list.
   * - EPICS_CA_CONN_TMO
     - 30.0
     - Connection timeout.
   * - EPICS_CA_BEACON_PERIOD
     - 15.0
     - Beacon broadcast period.
   * - EPICS_CA_REPEATER_PORT
     - 5065
     - Port for the repeater.
   * - EPICS_CA_SERVER_PORT
     - 5064
     - Default port for the server.
   * - EPICS_CA_MAX_ARRAY_BYTES
     - 16384
     - Max bytes as a client. Caproto does not support this.
   * - EPICS_CA_MAX_SEARCH_PERIOD
     - 300
     - Maximum search period.
   * - EPICS_TS_MIN_WEST
     - 360
     - Caproto does not support this.

.. list-table:: Server Environment Variables
   :header-rows: 1

   * - Variable
     - Default
     - Description
   * - EPICS_CAS_SERVER_PORT
     - 5064
     - Default server port.
   * - EPICS_CAS_AUTO_BEACON_ADDR_LIST
     - 'YES'
     - Automatically determine beacon address lists.
   * - EPICS_CAS_BEACON_ADDR_LIST
     - ''
     - Manual beacon address list.
   * - EPICS_CAS_BEACON_PERIOD
     - 15.0
     - Beacon broadcast period.
   * - EPICS_CAS_BEACON_PORT
     - 5065
     - Beacon UDP port.
   * - EPICS_CAS_INTF_ADDR_LIST
     - ''
     - Interfaces to listen on.
   * - EPICS_CAS_IGNORE_ADDR_LIST
     - ''
     - Interfaces to ignore.
   * - CAPROTO_SERVER_HIGH_LOAD_TIMEOUT
     - 0.01
     - Tuning this parameters will affect the server's performance under high
       load. If the queue of subscriptions to has a new update ready within
       this timeout, we consider ourselves under high load and trade accept
       some latency for some efficiency.
   * - CAPROTO_SERVER_HIGH_LOAD_EVENT_TIME_THRESHOLD
     - 0.1
     - If events are toggled by the client, subscriptions values get garbage-
       collected.  It's not a high load situation.  Let's warn only if we're
       relatively sure that it wasn't due to recent event toggling.  You
       probably shouldn't need to change this.
   * - CAPROTO_SERVER_HIGH_LOAD_WARN_LATENCY_SEC
     - 0.03
     - Warn the user if packets are delayed by more than this amount: 30ms.
       Set to 0 to disable the warning entirely.
   * - CAPROTO_SERVER_SUB_BATCH_THRESH
     - 2 ** 16
     - When a batch of subscription updates has this many bytes or more, send
       it.
   * - CAPROTO_SERVER_MAX_LATENCY
     - 1
     - Tune this to change the max time between packets. If it's too high, the
       client will experience long gaps when the server is under load. If it's
       too low, the *overall* latency will be higher because the server will
       have to waste time bundling many small packets.
   * - CAPROTO_SERVER_WRITE_LOCK_TIMEOUT
     - 0.001
     - If a Read[Notify]Request or EventAddRequest is received, wait for up to
       this long for the currently-processing Write[Notify]Request to finish.

.. list-table:: IOC Helper Environment Variables
   :header-rows: 1

   * - Variable
     - Default
     - Description
   * - ENGINEER
     - ""
     - The engineer to report as owner of the IOC.
   * - LOCATION
     - ""
     - The location to report in IOC stats.
