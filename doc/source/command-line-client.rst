*******************
Command-Line Client
*******************

Installing the caproto Python package places several executable command-line
utilities next to whichever ``python3`` binary was used to install caproto.
They should be available on your ``PATH``. Type ``caproto-<TAB>`` to check.

Tutorial
========

Start one of caproto's demo IOCs.

.. code-block:: bash

    $ python3 -m caproto.ioc_examples.random_walk --list-pvs
    [I 19:50:37.509 server:93] Server starting up...
    [I 19:50:37.512 server:109] Listening on 0.0.0.0:55704
    [I 19:50:37.512 server:121] Server startup complete.
    [I 19:50:37.512 server:123] PVs available:
        random_walk:dt
        random_walk:x

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

By default, the server sends no metadata. Obtain metadata by requesting a
richer data type.

.. code-block:: bash

    $ caproto-get random_walk:dt -d control --format="{response.metadata}"
    DBR_CTRL_FLOAT(status=<AlarmStatus.NO_ALARM: 0>,
    severity=<AlarmSeverity.NO_ALARM: 0>, upper_disp_limit=0.0,
    lower_disp_limit=0.0, upper_alarm_limit=0.0, upper_warning_limit=0.0,
    lower_warning_limit=0.0, lower_alarm_limit=0.0, upper_ctrl_limit=0.0,
    lower_ctrl_limit=0.0, precision=0, units=b'')

To view the list of data types, use ``--list-types``.

.. code-block:: bash

    $ caproto-get --list-types
    Request a general class of types:

    native
    status
    time
    graphic
    control

    or one of the following specific types, specified by number or by (case-insensitive) name:

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

Display multiple fields.

.. code-block:: bash

    $ caproto-get random_walk:dt -d time \
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
    [D 20:00:15.753 client:53] Registering with the Channel Access repeater.
    [D 20:00:15.755 client:60] Searching for 'random_walk:x'....
    [D 20:00:15.758 client:72] Search request sent to ('127.0.0.1', 5064).
    [D 20:00:15.758 client:72] Search request sent to ('172.27.7.255', 5064).
    [D 20:00:15.759 client:112] Found random_walk:x at ('127.0.0.1', 54388)
    [I 20:00:15.765 client:147] random_walk:x connected
    [D 20:00:15.765 client:161] Detected native data_type <ChannelType.DOUBLE: 6>.
    random_walk:x                             [0.49813506]


For extreme debugging, display all of the commands sent and received using ``-vvv``.

.. code-block:: bash

    $ caproto-get -vvv random_walk:x
    [D 20:00:47.562 repeater:214] Another repeater is already running; will not spawn one.
    [D 20:00:47.563 client:53] Registering with the Channel Access repeater.
    [D 20:00:47.563 _broadcaster:71] Serializing 1 commands into one datagram
    [D 20:00:47.564 _broadcaster:74] 1 of 1 RepeaterRegisterRequest(client_address='0.0.0.0')
    [D 20:00:47.565 client:60] Searching for 'random_walk:x'....
    [D 20:00:47.566 _broadcaster:71] Serializing 2 commands into one datagram
    [D 20:00:47.566 _broadcaster:74] 1 of 2 VersionRequest(priority=0, version=13)
    [D 20:00:47.566 _broadcaster:74] 2 of 2 SearchRequest(name='random_walk:x', cid=0, version=13)
    [D 20:00:47.567 client:72] Search request sent to ('127.0.0.1', 5064).
    [D 20:00:47.567 client:72] Search request sent to ('172.27.7.255', 5064).
    [D 20:00:47.568 _broadcaster:98] Received datagram from ('127.0.0.1', 5065) with 16 bytes.
    [D 20:00:47.568 _broadcaster:98] Received datagram from ('127.0.0.1', 5064) with 40 bytes.
    [D 20:00:47.568 client:112] Found random_walk:x at ('127.0.0.1', 54388)
    [D 20:00:47.572 _circuit:142] Serializing VersionRequest(priority=0, version=13)
    [D 20:00:47.573 _circuit:142] Serializing HostNameRequest(name='Daniels-MacBook-Air-3.local')
    [D 20:00:47.574 _circuit:142] Serializing ClientNameRequest(name='dallan')
    [D 20:00:47.574 _circuit:142] Serializing CreateChanRequest(name='random_walk:x', cid=0, version=13)
    [D 20:00:47.575 _circuit:171] Received 16 bytes.
    [D 20:00:47.575 _circuit:181] 16 bytes -> VersionResponse(version=13)
    [D 20:00:47.575 _circuit:185] 0 bytes are cached. Need more bytes to parse next command.
    [D 20:00:47.575 _circuit:171] Received 32 bytes.
    [D 20:00:47.575 _circuit:181] 16 bytes -> AccessRightsResponse(cid=0, access_rights=<AccessRights.WRITE|READ: 3>)
    [D 20:00:47.576 _circuit:181] 16 bytes -> CreateChanResponse(data_type=<ChannelType.DOUBLE: 6>, data_count=1, cid=0, sid=1)
    [D 20:00:47.576 _circuit:185] 0 bytes are cached. Need more bytes to parse next command.
    [I 20:00:47.576 client:147] random_walk:x connected
    [D 20:00:47.577 client:161] Detected native data_type <ChannelType.DOUBLE: 6>.
    [D 20:00:47.577 _circuit:142] Serializing ReadNotifyRequest(data_type=<ChannelType.DOUBLE: 6>, data_count=0, sid=1, ioid=0)
    [D 20:00:47.578 _circuit:171] Received 24 bytes.
    [D 20:00:47.578 _circuit:181] 24 bytes -> ReadNotifyResponse(data=array([5.38826246]), data_type=<ChannelType.DOUBLE: 6>, data_count=1, status=CAStatusCode(name='ECA_NORMAL', code=0, code_with_severity=1, severity=<CASeverity.SUCCESS: 1>, success=1, defunct=False, description='Normal successful completion'), ioid=0, metadata=None)
    [D 20:00:47.579 _circuit:185] 0 bytes are cached. Need more bytes to parse next command.
    [D 20:00:47.579 _circuit:142] Serializing ClearChannelRequest(sid=1, cid=0)
    random_walk:x                             [5.38826246]

For additional options, type ``caproto-get -h`` or see below.

Let us set the value to ``1``.

.. code-block:: bash

    $ caproto-put random_walk:dt 1
    random_walk:dt                            [3.]
    random_walk:dt                            [1.]

The client issues three requests:

1. Read the current value.
2. Write ``1``.
3. Read the value again.

By default it does not actually wait for confirmation that the write has been
processed by the server before moving on to the final read, so it is possible
to receive a reading that isn't up to date. Use ``-c`` to ask the server to
confirm the write's success and to wait on that confirmation before doing the
final read.

.. code-block:: bash

    $ caproto-put -c random_walk:dt 2
    random_walk:dt                            [1.]
    random_walk:dt                            [2.]

For additional options, type ``caproto-put -h`` or see below.

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
    ^C

For additional options, type ``caproto-monitor -h`` or see below.

Output Formatting Options
-------------------------

Output formatting options are changing the default format used in
``caproto-get`` and ``caproto-monitor`` for printing PV values.
The default formatting is used in the following cases:

* The format string (``--format`` argument) is not specified.

* The format string contains the field ``{response.data}``. In this case
  formatting is applied only to the field ``{response.data}``.

Formatting options applied to **floating point PV values**:

* ``-e <nr>`` - use %e format with precision of ``<nr>`` digits (e.g. ``-e5`` or ``-e 5``);
* ``-f <nr>`` - use %f format with precision of ``<nr>`` digits (e.g. ``-f5`` or ``-f 5``);
* ``-g <nr>`` - use %g format with precision of ``<nr>`` digits (e.g. ``-g5`` or ``-g 5``);
* ``-s`` - get value as string (honors server-side precision);
* ``-lx`` - round to long integer and print as hex number;
* ``-lo`` - round to long integer and print as octal number;
* ``-lb`` - round to long integer and print as binary number.

Formatting options applied to **integer PV values**:

* ``-0x`` - print as hex number;
* ``-0o`` - print as octal number;
* ``-0b`` - print as binary number.

The argument ``-F <ofs>`` replaces the default field separator (spaces) with alternate
separator ``<ofs>`` (e.g. ``-F*``, ``-F'*'``, ``-F '*'``, ``-F ' ** '``).

Some examples of output formatting:

.. code-block:: bash

    $ caproto-monitor random_walk:x -g10
    random_walk:x                             2019-04-11 20:12:45.159667 [-165.3895284]
    random_walk:x                             2019-04-11 20:12:46.160722 [-164.5046121]
    random_walk:x                             2019-04-11 20:12:47.162351 [-163.5463466]
    random_walk:x                             2019-04-11 20:12:48.164604 [-164.0319457]
    random_walk:x                             2019-04-11 20:12:49.166856 [-163.1483927]
    random_walk:x                             2019-04-11 20:12:50.169072 [-163.9358578]
    random_walk:x                             2019-04-11 20:12:51.171294 [-163.4155186]
    random_walk:x                             2019-04-11 20:12:52.173604 [-162.6590992]
    ^C

    $ caproto-monitor random_walk:x -g10 -F"  ==  "
    random_walk:x  ==  2019-04-11 20:14:41.297880  ==  [-3.811720948]
    random_walk:x  ==  2019-04-11 20:14:42.298818  ==  [-3.162919537]
    random_walk:x  ==  2019-04-11 20:14:43.301088  ==  [-3.432931988]
    random_walk:x  ==  2019-04-11 20:14:44.303375  ==  [-2.787768272]
    random_walk:x  ==  2019-04-11 20:14:45.305699  ==  [-2.024880621]
    random_walk:x  ==  2019-04-11 20:14:46.307986  ==  [-1.765013774]
    random_walk:x  ==  2019-04-11 20:14:47.310276  ==  [-1.45201324]
    random_walk:x  ==  2019-04-11 20:14:48.312575  ==  [-0.9904703683]
    ^C

    $ caproto-monitor random_walk:x -e5 --format "{timedelta} {response.data}"
    0:00:00.561498 [-6.09173e+00]
    0:00:01.001148 [-5.15495e+00]
    0:00:01.002169 [-5.64561e+00]
    0:00:01.002267 [-6.01321e+00]
    0:00:01.002256 [-5.18551e+00]
    0:00:01.002254 [-4.88171e+00]
    0:00:01.000546 [-4.47361e+00]
    ^C

    $ caproto-monitor random_walk:x -f3 -F ' ** ' --format "{timedelta} {response.data}"
    0:00:00.115265 ** [53.291]
    0:00:01.002170 ** [53.597]
    0:00:01.002251 ** [54.536]
    0:00:01.002267 ** [54.469]
    0:00:01.002254 ** [53.827]
    0:00:01.002264 ** [53.000]
    0:00:01.001584 ** [52.160]
    ^C

    $ caproto-monitor random_walk:x -lx -F ' ** ' --format "{timedelta} {response.data}"
    0:00:00.953373 ** [0x2D]
    0:00:01.000445 ** [0x2D]
    0:00:01.001918 ** [0x2E]
    0:00:01.002289 ** [0x2E]
    0:00:01.002199 ** [0x2D]
    0:00:01.002327 ** [0x2D]
    0:00:01.001610 ** [0x2C]
    ^C

API Documentation
=================

Caproto's command-line client is intended to provide a superset of the API
provided by its counterparts in EPICS' reference implementation, epics-base:
``caget``, ``caput``, ``camonitor``, and ``caRepeater``. It is our goal to make
caproto's variants safe to use as drop-in replacements. As yet, some arguments
related to string formatting are not yet implemented (`Code contributions
welcome!  <https://github.com/caproto/caproto/issues/147>`_) but similar
functionality is available via ``--format``.

caproto-get
-----------

.. code-block:: bash

    $ caproto-get -h
    usage: caproto-get [-h] [--verbose] [--format FORMAT] [--timeout TIMEOUT]
                    [--notify] [--priority PRIORITY]
                    [--terse | --wide | -d DATA_TYPE] [--list-types] [-n]
                    [--no-color] [--no-repeater] [--version] [-e <nr>]
                    [-f <nr>] [-g <nr>] [-s] [-lx] [-lo] [-lb] [-0x] [-0o]
                    [-0b] [-F <ofs>]
                    pv_names [pv_names ...]

    Read the value of a PV.

    positional arguments:
    pv_names              PV (channel) name(s) separated by spaces

    optional arguments:
    -h, --help            show this help message and exit
    --verbose, -v         Show more log messages. (Use -vvv for even more.)
    --format FORMAT       Python format string. Available tokens are {pv_name}
                            and {response}. Additionally, if this data type
                            includes time, {timestamp} and usages like
                            {timestamp:%Y-%m-%d %H:%M:%S} are supported. If the
                            format string is specified, --terse and --wide options
                            have no effect on the output formatting.
    --timeout TIMEOUT, -w TIMEOUT
                            Timeout ('wait') in seconds for server responses.
    --notify, -c          This is a vestigial argument that now has no effect in
                            caget but is provided for for backward-compatibility
                            with caget invocations.
    --priority PRIORITY, -p PRIORITY
                            Channel Access Virtual Circuit priority. Lowest is 0;
                            highest is 99.
    --terse, -t           Display data only. Unpack scalars: [3.] -> 3.
    --wide, -a, -l        Wide mode, showing 'name timestamp value
                            status'(implies -d 'time')
    -d DATA_TYPE          Request a class of data type (native, status, time,
                            graphic, control) or a specific type. Accepts numeric
                            code ('3') or case-insensitive string ('enum'). See
                            --list-types.
    --list-types          List allowed values for -d and exit.
    -n                    Retrieve enums as integers (default is strings).
    --no-color            Suppress ANSI color codes in log messages.
    --no-repeater         Do not spawn a Channel Access repeater daemon process.
    --version, -V         Show caproto version and exit.

    Floating point type format:
    If --format is set, the following arguments change formatting of the
    {response.data} field if floating point value is displayed. The default
    format is %g.

    -e <nr>               Use %e format with precision of <nr> digits (e.g. -e5
                            or -e 5)
    -f <nr>               Use %f format with precision of <nr> digits (e.g. -f5
                            or -f 5)
    -g <nr>               Use %g format with precision of <nr> digits (e.g. -g5
                            or -g 5)
    -s                    Get value as string (honors server-side precision)
    -lx                   Round to long integer and print as hex number
    -lo                   Round to long integer and print as octal number
    -lb                   Round to long integer and print as binary number

    Integer number format:
    If --format is set, the following arguments change formatting of the
    {response.data} field if integer value is displayed. Decimal number is
    displayed by default.

    -0x                   Print as hex number
    -0o                   Print as octal number
    -0b                   Print as binary number

    Custom output field separator:
    -F <ofs>              Use <ofs> as an alternate output field separator (e.g.
                            -F*, -F'*', -F '*', -F ' ** ')

caproto-put
-----------

.. code-block:: bash

    $ caproto-put -h
    usage: caproto-put [-h] [--verbose] [--format FORMAT] [--timeout TIMEOUT]
                    [--notify] [--priority PRIORITY] [--terse] [--wide] [-n]
                    [--array] [--array-pad ARRAY_PAD] [--no-color]
                    [--no-repeater]
                    pv_name data

    Write a value to a PV.

    positional arguments:
    pv_name               PV (channel) name
    data                  Value or values to write.

    optional arguments:
    -h, --help            show this help message and exit
    --verbose, -v         Show more log messages. (Use -vvv for even more.)
    --format FORMAT       Python format string. Available tokens are {pv_name},
                            {response} and {which} (Old/New).Additionally, this
                            data type includes time, {timestamp} and usages like
                            {timestamp:%Y-%m-%d %H:%M:%S} are supported.
    --timeout TIMEOUT, -w TIMEOUT
                            Timeout ('wait') in seconds for server responses.
    --notify, -c          Request notification of completion, and wait for it.
    --priority PRIORITY, -p PRIORITY
                            Channel Access Virtual Circuit priority. Lowest is 0;
                            highest is 99.
    --terse, -t           Display data only. Unpack scalars: [3.] -> 3.
    --wide, -l            Wide mode, showing 'name timestamp value
                            status'(implies -d 'time')
    -n                    Retrieve enums as integers (default is strings).
    --array, -a           Interprets `data` as an array, delimited by space
    --array-pad ARRAY_PAD
                            Pad the array up to a specified length
    --no-color            Suppress ANSI color codes in log messages.
    --no-repeater         Do not spawn a Channel Access repeater daemon process.


caproto-monitor
---------------

.. code-block:: bash

    $ caproto-monitor -h
    usage: caproto-monitor [-h] [--format FORMAT] [--verbose]
                        [--duration DURATION | --maximum MAXIMUM]
                        [--timeout TIMEOUT] [-m MASK] [--priority PRIORITY]
                        [-n] [--no-color] [--no-repeater] [--version] [-e <nr>]
                        [-f <nr>] [-g <nr>] [-s] [-lx] [-lo] [-lb] [-0x] [-0o]
                        [-0b] [-F <ofs>]
                        pv_names [pv_names ...]

    Read the value of a PV.

    positional arguments:
    pv_names              PV (channel) name

    optional arguments:
    -h, --help            show this help message and exit
    --format FORMAT       Python format string. Available tokens are {pv_name},
                            {response}, {callback_count}. Additionally, if this
                            data type includes time, {timestamp}, {timedelta} and
                            usages like {timestamp:%Y-%m-%d %H:%M:%S} are
                            supported.
    --verbose, -v         Show more log messages. (Use -vvv for even more.)
    --duration DURATION   Maximum number seconds to run before exiting. Runs
                            indefinitely by default.
    --maximum MAXIMUM     Maximum number of monitor events to process exiting.
                            Unlimited by default.
    --timeout TIMEOUT, -w TIMEOUT
                            Timeout ('wait') in seconds for server responses.
    -m MASK               Channel Access mask. Any combination of 'v' (value),
                            'a' (alarm), 'l' (log/archive), 'p' (property).
                            Default is 'va'.
    --priority PRIORITY, -p PRIORITY
                            Channel Access Virtual Circuit priority. Lowest is 0;
                            highest is 99.
    -n                    Retrieve enums as integers (default is strings).
    --no-color            Suppress ANSI color codes in log messages.
    --no-repeater         Do not spawn a Channel Access repeater daemon process.
    --version, -V         Show caproto version and exit.

    Floating point type format:
    If --format is set, the following arguments change formatting of the
    {response.data} field if floating point value is displayed. The default
    format is %g.

    -e <nr>               Use %e format with precision of <nr> digits (e.g. -e5
                            or -e 5)
    -f <nr>               Use %f format with precision of <nr> digits (e.g. -f5
                            or -f 5)
    -g <nr>               Use %g format with precision of <nr> digits (e.g. -g5
                            or -g 5)
    -s                    Get value as string (honors server-side precision)
    -lx                   Round to long integer and print as hex number
    -lo                   Round to long integer and print as octal number
    -lb                   Round to long integer and print as binary number

    Integer number format:
    If --format is set, the following arguments change formatting of the
    {response.data} field if integer value is displayed. Decimal number is
    displayed by default.

    -0x                   Print as hex number
    -0o                   Print as octal number
    -0b                   Print as binary number

    Custom output field separator:
    -F <ofs>              Use <ofs> as an alternate output field separator (e.g.
                            -F*, -F'*', -F '*', -F ' ** ')





caproto-repeater
----------------

.. code-block:: bash

    $ caproto-repeater -h
    usage: caproto-repeater [-h] [-q | -v] [--no-color]

    Run a Channel Access Repeater. If the Repeater port is already in use, assume
    a Repeater is already running and exit. That port number is set by the
    environment variable EPICS_CA_REPEATER_PORT. It defaults to the standard 5065.
    The current value is 5065.

    optional arguments:
    -h, --help     show this help message and exit
    -q, --quiet    Suppress INFO log messages. (Still show WARNING or higher.)
    -v, --verbose  Verbose mode. (Use -vvv for more.)
    --no-color     Suppress ANSI color codes in log messages.
