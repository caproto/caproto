****************************
Shark (pcap/tcpdump parsing)
****************************

Caproto includes a Python function for parsing and analyzing Channel Access
network traffic in Python. It consumes pcap format, as produced by ``tcpdump``.
This functionality is also accessible though a CLI, ``caproto-shark``.

.. important::

   This feature of caproto uses an external Python library
   `dpkt <https://dpkt.readthedocs.io/en/latest/>`_ to parse the pcap format
   output by ``tcpdump``. A "minimal" installation of caproto---as in
   ``pip install caproto``---does not include ``dpkt``. Any of the following
   will install it:

   .. code-block:: bash

      # Any one of these is sufficient:
      pip install dpkt  # just dpkt
      pip install caproto[standard]  # all of caproto's network-related extras
      pip install caproto[complete]  # all of caproto's extras

Caproto and tcpdump
===================

Capture network traffic to a using ``tcpdump`` like so:

.. code-block:: bash

   sudo tcpdump -w some_network_traffic.pcap

You may need to specify a particular network interface. For example, if the
IOCs of interest are on the local machine, use ``lo`` for local loopback.

.. code-block:: bash

   sudo tcpdump -i lo -w some_network_traffic.pcap

On Linux and Mac, use ``ifconfig`` to list the available interfaces.

Extract the information in Python using caproto:

.. code-block:: python

   from caproto.sync.shark import shark

   with open('some_network_traffic.pcap', 'rb') as file:
       parsed = shark(file)
       # Loop through the items in parsed and do things....

The result, ``parsed``, is a generator. Each item is a ``SimpleNamespace`` that
contains:

* ``timestamp``
* ``command`` caproto ``Message`` object respresenting CA command
* ``transport`` -- bundle of transport-layer (TCP or UDP) information
* ``ip`` --- bundle of IP-layer information
* ``ethernet`` --- bundle of Ethernet-layer information
* ``src`` and ``dst``, which are ``ip.src`` and ``ip.dst`` decoded into
  numbers-and-dots form

Example item:

.. code-block:: python

   namespace(
       timestamp=1550524419.962509,
       command=VersionRequest(priority=0, version=13),
       src='192.168.86.21',
       dst='255.255.255.255',
       transport=UDP(sport=41600, dport=5064, ulen=56, sum=21249, data=b'\x00\x00\x00\x00\x00\x00\x00\r\x00\x00\x00\x00\x00\x00\x00\x00\x00\x06\x00\x10\x00\x05\x00\r\x00\x00\xe0\xdb\x00\x00\xe0\xdbrpi:color\x00\x00\x00\x00\x00\x00\x00'),
       ethernet=Ethernet(dst=b'\xff\xff\xff\xff\xff\xff', src=b'tp\xfd\xf2K?', data=IP(len=76, id=10227, off=16384, p=17, sum=64496, src=b'\xc0\xa8V\x15', dst=b'\xff\xff\xff\xff', opts=b'', data=UDP(sport=41600, dport=5064, ulen=56, sum=21249, data=b'\x00\x00\x00\x00\x00\x00\x00\r\x00\x00\x00\x00\x00\x00\x00\x00\x00\x06\x00\x10\x00\x05\x00\r\x00\x00\xe0\xdb\x00\x00\xe0\xdbrpi:color\x00\x00\x00\x00\x00\x00\x00'))),
       ip=IP(len=76, id=10227, off=16384, p=17, sum=64496, src=b'\xc0\xa8V\x15', dst=b'\xff\xff\xff\xff', opts=b'', data=UDP(sport=41600, dport=5064, ulen=56, sum=21249, data=b'\x00\x00\x00\x00\x00\x00\x00\r\x00\x00\x00\x00\x00\x00\x00\x00\x00\x06\x00\x10\x00\x05\x00\r\x00\x00\xe0\xdb\x00\x00\xe0\xdbrpi:color\x00\x00\x00\x00\x00\x00\x00')))

This data can be used, for example, to perform statistical analysis of IOC
connection performance.

.. literalinclude:: ../../caproto/examples/benchmark_connections.py

This feature is also accessible through a CLI:

.. code-block:: bash

   $ caproto-shark -h
   usage: caproto-shark [-h] [--format FORMAT] [--version]

   Parse pcap (tcpdump) output and pretty-print CA commands.

   optional arguments:
     -h, --help       show this help message and exit
     --format FORMAT  Python format string. Available tokens are {timestamp},
                      {ethernet}, {ip}, {transport}, {command} and {src} and
                      {dst}, which are {ip.src} and {ip.dst} decoded into
                      numbers-and-dots form.
     --version, -V    Show caproto version and exit.

Use this, for example, to stream ``tcpdump`` to the standard out, and pipe it
to ``caproto-shark``.

.. code-block:: bash

   sudo tcpdump -U -w - | caproto-shark

Example output:

.. code-block:: bash

   $ sudo tcpdump -U -w - | caproto-shark
   tcpdump: listening on wlp59s0, link-type EN10MB (Ethernet), capture size 262144 bytes
   1550679067.619182 192.168.86.21:55928->255.255.255.255:5065 RepeaterRegisterRequest(client_address='0.0.0.0')
   1550679069.309346 192.168.86.21:55928->255.255.255.255:5064 VersionRequest(priority=0, version=13)
   1550679069.309346 192.168.86.21:55928->255.255.255.255:5064 SearchRequest(name='rpi:color', cid=24593, version=13, reply=5)
   1550679069.339563 192.168.86.21:55928->255.255.255.255:5064 VersionRequest(priority=0, version=13)
   1550679069.339563 192.168.86.21:55928->255.255.255.255:5064 SearchRequest(name='rpi:color', cid=24593, version=13, reply=5)
   1550679069.381939 192.168.86.245:5064->192.168.86.21:55928 VersionResponse(version=13)
   1550679069.381939 192.168.86.245:5064->192.168.86.21:55928 SearchResponse(port=50421, ip='255.255.255.255', cid=24593, version=13)
   1550679069.398823 192.168.86.21:57522->192.168.86.245:50421 VersionRequest(priority=0, version=13)
   1550679069.398823 192.168.86.21:57522->192.168.86.245:50421 HostNameRequest(name='pop-os')
   1550679069.398823 192.168.86.21:57522->192.168.86.245:50421 ClientNameRequest(name='dallan')
   1550679069.423308 192.168.86.245:5064->192.168.86.21:55928 VersionResponse(version=13)
   1550679069.423308 192.168.86.245:5064->192.168.86.21:55928 SearchResponse(port=50421, ip='255.255.255.255', cid=24593, version=13)
   1550679069.481746 192.168.86.245:50421->192.168.86.21:57522 VersionResponse(version=13)
   1550679069.482269 192.168.86.21:57522->192.168.86.245:50421 CreateChanRequest(name='rpi:color', cid=0, version=13)
   1550679069.541407 192.168.86.245:50421->192.168.86.21:57522 AccessRightsResponse(cid=0, access_rights=<AccessRights.WRITE|READ: 3>)
   1550679069.541407 192.168.86.245:50421->192.168.86.21:57522 CreateChanResponse(data_type=<ChannelType.STRING: 0>, data_count=1, cid=0, sid=1)
   1550679076.427868 192.168.86.21:57522->192.168.86.245:50421 ReadNotifyRequest(data_type=<ChannelType.STRING: 0>, data_count=0, sid=1, ioid=0)
   1550679076.488508 192.168.86.245:50421->192.168.86.21:57522 ReadNotifyResponse(data=[b'000000'], data_type=<ChannelType.STRING: 0>, data_count=1, status=CAStatusCode(name='ECA_NORMAL', code=0, code_with_severity=1, severity=<CASeverity.SUCCESS: 1>, success=1, defunct=False, description='Normal successful completion'), ioid=0, metadata=None)

Windows
=======

The Windows program `WinDump <https://www.winpcap.org/windump/>`_ provides
similar functionality to ``tcpdump``. List the available network interfaces
like so:

.. code-block:: bash

   WinDump.exe -D

And then use it similarly to ``tcpdump``:

.. code-block:: bash

   WinDump.exe -i <INTERFACE> -U -w - | caproto-shark

Why not just use wireshark?
===========================

There is already a
`wireshark plugin for CA <https://github.com/mdavidsaver/cashark>`_. In fact,
we used it to help write caproto itself, and we have had a link to it in our
:doc:`references` section from the start. Who needs ``caproto-shark``? There
are situations where using wireshark is a better choice. However:

* Caproto's implementation enables in-depth analysis of traffic in Python
  (making timing plots in Matplotlib, etc.)
* The output from ``caproto-shark`` is more descriptive in some areas as a
  natural consequence of reusing the same command objects that back caproto's
  clients and servers.
* It's handy to bundle pcap analysis with caproto---batteries included, nothing
  else to install.
