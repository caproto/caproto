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
     - Interfaces to igonre.

.. list-table:: pvAccess Environment Variables
   :header-rows: 1

   * - Variable
     - Default
     - Description
   * - EPICS_PVA_DEBUG
     - 0
     - Caproto does not support this; use logger levels.
   * - EPICS_PVA_ADDR_LIST
     - ''
     - Client address list.
   * - EPICS_PVA_AUTO_ADDR_LIST
     - 'YES'
     - Automatically determine client address list.
   * - EPICS_PVA_CONN_TMO
     - 30.0
     - Connection timeout.
   * - EPICS_PVA_BEACON_PERIOD
     - 15.0
     - Beacon period.
   * - EPICS_PVA_BROADCAST_PORT
     - 5076
     - Port used for broadcast requests.
   * - EPICS_PVA_MAX_ARRAY_BYTES
     - 16384
     - Maximum array bytes. Caproto does not use this.
   * - EPICS_PVA_SERVER_PORT
     - 5075
     - Default server port.

.. list-table:: pvAccess Server Environment Variables
   :header-rows: 1

   * - Variable
     - Default
     - Description
   * - EPICS_PVAS_BEACON_ADDR_LIST
     - ''
     - Beacon address list.
   * - EPICS_PVAS_AUTO_BEACON_ADDR_LIST
     - 'YES'
     - Automatically determine beacon address list.
   * - EPICS_PVAS_BEACON_PERIOD
     - 15.0
     - Beacon broadcast period.
   * - EPICS_PVAS_SERVER_PORT
     - 5075
     - Default server port.
   * - EPICS_PVAS_BROADCAST_PORT
     - 5076
     - Default broadcast port.
   * - EPICS_PVAS_MAX_ARRAY_BYTES
     - 16384
     - Maximum array bytes. Caproto ignores this.
   * - EPICS_PVAS_PROVIDER_NAMES
     - 'local'
     - Unsupported.
   * - EPICS_PVAS_INTF_ADDR_LIST
     - ''
     - Interface list to listen on.
   * - EPICS_PVA_PROVIDER_NAMES
     - 'local'
     - Unsupported.

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
