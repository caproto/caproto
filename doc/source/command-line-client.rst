*******************
Command-Line Client
*******************


Installing the caproto Python package places several executable command-line
utilities next to whichever ``python3`` binary was used to install caproto.
They should be available on your ``PATH``.

Type ``caproto-<TAB>`` to check:

.. code-block:: bash

   $ caproto-
   caproto-example-ioc  caproto-monitor      caproto-repeater
   caproto-get          caproto-put

Tutorial
========

Start one of caproto's demo IOCs.

.. code-block:: bash

    $ python3 -m caproto.ioc_examples.random_walk
    PVs: ['random_walk:dt', 'random_walk:x']

Now, in a separate shell, we will talk to it using caproto's command-line
client:

.. code-block:: bash

    $ caproto-get random_walk:dt
    random_walk:dt                       [3.]

By default, ``caproto-get`` displays the name and the current value.  For
comprehensive access to the server's response, use ``--format``.

.. code-block:: bash

    $ caproto-get random_walk:dt --format="{response}"
    ReadNotifyResponse(data=array([3.]), data_type=<ChannelType.DOUBLE: 6>,
    data_count=1, status=CAStatusCode(name='ECA_NORMAL', code=0,
    code_with_severity=1, severity=<CASeverity.SUCCESS: 1>, success=1,
    defunct=False, description='Normal successful completion'), ioid=0,
    metadata=None)

Access particular fields in the response using attribute ("dot") access.

.. code-block:: bash

    $ caproto-get random_walk:dt --format="{response.data}"
    [3.]

    $ caproto-get random_walk:dt --format="{response.status.description}"
    Normal successful completion

    $ caproto-get random_walk:dt --format="{response.metadata}"
    None

By default, the server sends no metadata. Obtain metadata by specifically
requesting a richer data type.

.. code-block:: bash

    $ caproto-get random_walk:dt -d CTRL_FLOAT --format="{response.metadata}"
    DBR_CTRL_FLOAT(status=<AlarmStatus.NO_ALARM: 0>,
    severity=<AlarmSeverity.NO_ALARM: 0>, upper_disp_limit=0.0,
    lower_disp_limit=0.0, upper_alarm_limit=0.0, upper_warning_limit=0.0,
    lower_warning_limit=0.0, lower_alarm_limit=0.0, upper_ctrl_limit=0.0,
    lower_ctrl_limit=0.0, precision=0, units=b'')

To view the list of data types, use ``-list-types``. The ``-d`` parameter used
above accepts a data type's name or its numerical code.

.. code-block:: bash

    $ caproto-get --list-types
    0  STRING
    1  INT
    2  FLOAT
    3  ENUM
    4  CHAR
    5  LONG
    6  DOUBLE
    <...snipped...>
    34 CTRL_DOUBLE
    35 PUT_ACKT
    36 PUT_ACKS
    37 STSACK_STRING
    38 CLASS_NAME

Access multiple fields.

.. code-block:: bash

    $ caproto-get random_walk:dt -d TIME_FLOAT \
      --format="{response.metadata.timestamp}   {response.data}"
    1527708484.417967   [3.]

Query multiple PVs in one command and label the results.

.. code-block:: bash

    caproto-get random_walk:dt random_walk:x --format="{pv_name} {response.data}"
    random_walk:dt [3.]
    random_walk:x [15.03687]

For debugging purposes, display some log messages using ``-v`` or ``--verbose``.
On supported terminals, this output is color-coded and somewhat easier to
visually parse.

.. code-block:: bash

    $ caproto-get -v random_walk:x
    [D 19:27:02.523 client:167] Spawning caproto-repeater process....
    [D 19:27:03.221 repeater:184] Checking for another repeater....
    [I 19:27:03.221 repeater:84] Repeater is listening on 0.0.0.0:5065
    [D 19:27:02.527 client:61] Registering with the Channel Access repeater.
    [D 19:27:02.529 client:68] Searching for 'random_walk:x'....
    [D 19:27:02.531 client:80] Search request sent to ('127.0.0.1', 5064).
    [D 19:27:02.531 client:80] Search request sent to ('192.168.86.255', 5064).
    [D 19:27:02.543 client:154] Channel created.
    [D 19:27:02.543 client:320] Detected native data_type <ChannelType.DOUBLE: 6>.
    random_walk:x                             [2.95033725]


For extreme debugging, display all of the commands sent and received using ``-vvv``.

.. code-block:: bash

    $ caproto-get -vvv random_walk:x
    [D 19:27:08.557 client:167] Spawning caproto-repeater process....
    [D 19:27:08.561 client:61] Registering with the Channel Access repeater.
    [D 19:27:08.561 _broadcaster:68] Serializing 1 commands into one datagram
    [D 19:27:08.562 _broadcaster:71] 1 of 1 RepeaterRegisterRequest(client_address='0.0.0.0')
    [D 19:27:08.565 client:68] Searching for 'random_walk:x'....
    [D 19:27:08.566 _broadcaster:68] Serializing 2 commands into one datagram
    [D 19:27:08.566 _broadcaster:71] 1 of 2 VersionRequest(priority=0, version=13)
    [D 19:27:08.567 _broadcaster:71] 2 of 2 SearchRequest(name=b'random_walk:x', cid=0, version=13)
    [D 19:27:08.567 repeater:131] New client ('127.0.0.1', 60442)
    [D 19:27:08.569 client:80] Search request sent to ('127.0.0.1', 5064).
    [D 19:27:08.569 client:80] Search request sent to ('192.168.86.255', 5064).
    [D 19:27:08.570 _broadcaster:95] Received datagram from ('127.0.0.1', 5065) with 16 bytes.
    [D 19:27:08.584 _broadcaster:95] Received datagram from ('127.0.0.1', 5064) with 40 bytes.
    [D 19:27:08.598 _circuit:133] Serializing VersionRequest(priority=0, version=13)
    [D 19:27:08.598 _circuit:133] Serializing HostNameRequest(name=b'daniels-air-3.lan')
    [D 19:27:08.599 _circuit:133] Serializing ClientNameRequest(name=b'dallan')
    [D 19:27:08.600 _circuit:133] Serializing CreateChanRequest(name=b'random_walk:x', cid=0, version=13)
    [D 19:27:09.191 _circuit:162] Received 16 bytes.
    [D 19:27:09.191 _circuit:172] 16 bytes -> VersionResponse(version=13)
    [D 19:27:09.192 _circuit:176] 0 bytes are cached. Need more bytes to parse next command.
    [D 19:27:09.192 _circuit:162] Received 32 bytes.
    [D 19:27:09.192 _circuit:172] 16 bytes -> AccessRightsResponse(cid=0, access_rights=<AccessRights.WRITE|READ: 3>)
    [D 19:27:09.193 _circuit:172] 16 bytes -> CreateChanResponse(data_type=<ChannelType.DOUBLE: 6>, data_count=1, cid=0, sid=1)
    [D 19:27:09.193 _circuit:176] 0 bytes are cached. Need more bytes to parse next command.
    [D 19:27:09.193 client:154] Channel created.
    [D 19:27:09.193 client:320] Detected native data_type <ChannelType.DOUBLE: 6>.
    [D 19:27:09.195 _circuit:133] Serializing ReadNotifyRequest(data_type=<ChannelType.DOUBLE: 6>, data_count=0, sid=1, ioid=0)
    [D 19:27:09.198 _circuit:162] Received 24 bytes.
    [D 19:27:09.208 _circuit:172] 24 bytes -> ReadNotifyResponse(data=array([4.10904623]), data_type=<ChannelType.DOUBLE: 6>, data_count=1, status=CAStatusCode(name='ECA_NORMAL', code=0, code_with_severity=1, severity=<CASeverity.SUCCESS: 1>, success=1, defunct=False, description='Normal successful completion'), ioid=0, metadata=None)
    [D 19:27:09.274 _circuit:176] 0 bytes are cached. Need more bytes to parse next command.
    [D 19:27:09.274 _circuit:133] Serializing ClearChannelRequest(sid=1, cid=0)
    random_walk:x                             [4.10904623]
    [D 19:27:09.690 repeater:184] Checking for another repeater....
    [I 19:27:09.691 repeater:189] Another repeater is already running; exiting.

For additional options, see ``caproto-get -h`` or the documentation below.

Let us set the value to ``1``.

.. code-block:: bash

    $ caproto-put random_walk:dt 1
    random_walk:dt                            [3.]
    random_walk:dt                            [1.]

The client issues three requests:

1. Read the current value.
2. Write ``1``.
3. Read the value again.

This behavior is particular to caproto's *synchronous* client, on which this
command-line interface relies. The other, more sophisticated clients leave it
up to the caller when and whether to request readings.

For additional options, see ``caproto-put -h`` or the documentation below.

Let us now monitor a channel. The server updates the ``random_walk:x`` channel
periodically. (The period is set by ``random_walk:dt``.) We can subscribe
to updates. Use Ctrl+C to escape.

.. code-block:: bash

    $ caproto-monitor random_walk:x
    random_walk:x                             2018-05-30 16:05:14 [3.21691947]
    random_walk:x                             2018-05-30 16:05:17 [4.06274315]
    random_walk:x                             2018-05-30 16:05:18 [4.66485147]
    random_walk:x                             2018-05-30 16:05:19 [5.37846743]
    random_walk:x                             2018-05-30 16:05:20 [5.91004514]
    random_walk:x                             2018-05-30 16:05:21 [6.73980869]
    random_walk:x                             2018-05-30 16:05:22 [7.32833931]
    random_walk:x                             2018-05-30 16:05:23 [7.34338441]
    random_walk:x                             2018-05-30 16:05:24 [7.54504445]
    random_walk:x                             2018-05-30 16:05:25 [7.97174939]
    random_walk:x                             2018-05-30 16:05:26 [8.54049119]

Since monitoring involves a time series of multiple readings, the ``--format``
argument for ``caproto-monitor`` provides additional tokens, ``{timestamp}``
and ``{timedelta}``. We can show the hours, minutes, and seconds of each reading:

.. code-block:: bash

    $ caproto-monitor random_walk:x --format "{timestamp:%H:%M:%S} {response.data}"
    16:13:00 [239.95707401]
    16:13:01 [240.49112986]
    16:13:02 [241.46992348]
    16:13:03 [241.93483515]
    16:13:04 [242.39478219]
    ^C

and the time-spacing between readings:

.. code-block:: bash

    $ caproto-monitor random_walk:x --format "{timedelta} {response.data}"
    0:00:00.821489 [216.31247919]
    0:00:01.001850 [216.87041785]
    0:00:01.002946 [217.64755049]
    0:00:01.003341 [218.41384969]
    0:00:01.004499 [219.30221942]
    0:00:01.004556 [220.2028958]
    ^C

For additional options, see ``caproto-monitor -h`` or the documentation below.

API Documentation
=================

These are intended to provide a superset of the API provided by their standard
counterparts in epics-base, ``caget``, ``caput``, ``camonitor``, and
``caRepeater`` so that they can be safely used as drop-in replacements. Some of
``caget``'s arguments related to string formatting are not yet implemented
(`Code contributions welcome!  <https://github.com/NSLS-II/caproto/issues/147>`_)
but similar functionality is available via ``--format``.

caproto-get
-----------

.. code-block:: bash

    $ caproto-get -h
    usage: caproto-get [-h] [-d DATA_TYPE] [--format FORMAT] [--list-types] [-n]
                    [--no-repeater] [--priority PRIORITY] [--terse]
                    [--timeout TIMEOUT] [--verbose]
                    pv_names [pv_names ...]

    Read the value of a PV.

    positional arguments:
    pv_names              PV (channel) name(s) separated by spaces

    optional arguments:
    -h, --help            show this help message and exit
    -d DATA_TYPE          Request a certain data type. Accepts numeric code
                          ('3') or case-insensitive string ('enum'). See --list-
                          types
    --format FORMAT       Python format string. Available tokens are {pv_name}
                          and {response}. Additionally, if this data type
                          includes time, {timestamp} and usages like
                          {timestamp:%Y-%m-%d %H:%M:%S} are supported.
    --list-types          List allowed values for -d and exit.
    -n                    Retrieve enums as integers (default is strings).
    --no-repeater         Do not spawn a Channel Access repeater daemon process.
    --priority PRIORITY, -p PRIORITY
                          Channel Access Virtual Circuit priority. Lowest is 0;
                          highest is 99.
    --terse, -t           Display data only. Unpack scalars: [3.] -> 3.
    --timeout TIMEOUT, -w TIMEOUT
                          Timeout ('wait') in seconds for server responses.
    --verbose, -v         Verbose mode. (Use -vvv for more.)

caproto-put
-----------

.. code-block:: bash

    $ caproto-put -h
    usage: caproto-put [-h] [--format FORMAT] [--no-repeater]
                    [--priority PRIORITY] [--terse] [--timeout TIMEOUT]
                    [--verbose]
                    pv_name data

    Write a value to a PV.

    positional arguments:
    pv_name               PV (channel) name
    data                  Value or values to write.

    optional arguments:
    -h, --help            show this help message and exit
    --format FORMAT       Python format string. Available tokens are {pv_name}
                          and {response}. Additionally, this data type includes
                          time, {timestamp} and usages like {timestamp:%Y-%m-%d
                          %H:%M:%S} are supported.
    --no-repeater         Do not spawn a Channel Access repeater daemon process.
    --priority PRIORITY, -p PRIORITY
                          Channel Access Virtual Circuit priority. Lowest is 0;
                          highest is 99.
    --terse, -t           Display data only. Unpack scalars: [3.] -> 3.
    --timeout TIMEOUT, -w TIMEOUT
                          Timeout ('wait') in seconds for server responses.
    --verbose, -v         Verbose mode. (Use -vvv for more.)

caproto-monitor
---------------

.. code-block:: bash

    $ caproto-monitor -h
    usage: caproto-monitor [-h] [--format FORMAT] [-m MASK] [-n] [--no-repeater]
                        [--priority PRIORITY] [--timeout TIMEOUT] [--verbose]
                        pv_names [pv_names ...]

    Read the value of a PV.

    positional arguments:
    pv_names              PV (channel) name

    optional arguments:
    -h, --help            show this help message and exit
    --format FORMAT       Python format string. Available tokens are {pv_name}
                          and {response}. Additionally, if this data type
                          includes time, {timestamp}, {timedelta} and usages
                          like {timestamp:%Y-%m-%d %H:%M:%S} are supported.
    -m MASK               Channel Access mask. Any combination of 'v' (value),
                          'a' (alarm), 'l' (log/archive), 'p' (property).
                          Default is 'va'.
    -n                    Retrieve enums as integers (default is strings).
    --no-repeater         Do not spawn a Channel Access repeater daemon process.
    --priority PRIORITY, -p PRIORITY
                          Channel Access Virtual Circuit priority. Lowest is 0;
                          highest is 99.
    --timeout TIMEOUT, -w TIMEOUT
                          Timeout ('wait') in seconds for server responses.
    --verbose, -v         Verbose mode. (Use -vvv for more.)


caproto-repeater
----------------

.. code-block:: bash

    $ caproto-repeater -h
    usage: caproto-repeater [-h] [-q | -v]

    Run a Channel Access Repeater. If the Repeater port is already in use, assume
    a Repeater is already running and exit. That port number is set by the
    environment variable EPICS_CA_REPEATER_PORT. It defaults to the standard 5065.
    The current value is 5065.

    optional arguments:
    -h, --help     show this help message and exit
    -q, --quiet    Suppress INFO log messages. (Still show WARNING or higher.)
    -v, --verbose  Verbose mode. (Use -vvv for more.)
