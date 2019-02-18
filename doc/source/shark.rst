****************************
Shark (pcap/tcpdump parsing)
****************************

Caproto includes a Python function for parsing and analyzing Channel Access
network traffic in Python. It consumes pcap format, as produced by ``tcpdump``.
This functionality is also accessible though a CLI, ``caproto-shark``.

.. info::

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

Capture network traffic to a using ``tcpdump`` like so:

.. code-block:: bash

   sudo tcpdump -w some_network_traffic.pcap port 5064

Extract the information in Python using caproto:

.. code-block:: python

   from caproto.sync.shark import shark

   file = open('some_network_traffic.pcap', 'rb')
   parsed = shark(file)

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

Use this, for example, to stream ``tcpdump`` unbuffered to the standard out,
and pipe it to ``caproto-shark``.

.. code-block:: bash

   sudo tcpdump -U -w - port 5064 | caproto-shark

Example output:

.. code-block:: bash

   $ sudo tcpdump -U -w - port 5064 | caproto-shark
   tcpdump: listening on wlp59s0, link-type EN10MB (Ethernet), capture size 262144 bytes
   1550523983.54872 192.168.86.21:54763->255.255.255.255:5064 VersionRequest(priority=0, version=13)
   1550523983.54872 192.168.86.21:54763->255.255.255.255:5064 SearchRequest(name='rpi:color', cid=50928, version=13, reply=5)
   1550523983.57894 192.168.86.21:54763->255.255.255.255:5064 VersionRequest(priority=0, version=13)
   1550523983.57894 192.168.86.21:54763->255.255.255.255:5064 SearchRequest(name='rpi:color', cid=50928, version=13, reply=5)
   1550523983.639661 192.168.86.21:54763->255.255.255.255:5064 VersionRequest(priority=0, version=13)
   1550523983.639661 192.168.86.21:54763->255.255.255.255:5064 SearchRequest(name='rpi:color', cid=50928, version=13, reply=5)
   1550523983.653664 192.168.86.245:5064->192.168.86.21:54763 VersionResponse(version=13)
   1550523983.653664 192.168.86.245:5064->192.168.86.21:54763 SearchResponse(port=50421, ip='255.255.255.255', cid=50928, version=13)
   1550523983.695755 192.168.86.245:5064->192.168.86.21:54763 VersionResponse(version=13)
   1550523983.695755 192.168.86.245:5064->192.168.86.21:54763 SearchResponse(port=50421, ip='255.255.255.255', cid=50928, version=13)

And an example from a capture of TCP traffic:

.. code-block:: bash

   $ sudo tcpdump -U -w - port 50421 | caproto-shark
   tcpdump: listening on wlp59s0, link-type EN10MB (Ethernet), capture size 262144 bytes
   1550523362.981695 192.168.86.21:46212->192.168.86.245:50421 VersionRequest(priority=0, version=13)
   1550523362.981695 192.168.86.21:46212->192.168.86.245:50421 HostNameRequest(name='pop-os')
   1550523362.981695 192.168.86.21:46212->192.168.86.245:50421 ClientNameRequest(name='dallan')
   1550523363.120444 192.168.86.245:50421->192.168.86.21:46212 VersionResponse(version=13)
   1550523363.121993 192.168.86.21:46212->192.168.86.245:50421 CreateChanRequest(name='rpi:color', cid=0, version=13)
   1550523363.170899 192.168.86.245:50421->192.168.86.21:46212 AccessRightsResponse(cid=0, access_rights=<AccessRights.WRITE|READ: 3>)
   1550523363.170899 192.168.86.245:50421->192.168.86.21:46212 CreateChanResponse(data_type=<ChannelType.STRING: 0>, data_count=1, cid=0, sid=1)
   1550523369.251882 192.168.86.21:46212->192.168.86.245:50421 ReadNotifyRequest(data_type=<ChannelType.STRING: 0>, data_count=0, sid=1, ioid=0)
   1550523369.298866 192.168.86.245:50421->192.168.86.21:46212 ReadNotifyResponse(data=[b'000000'], data_type=<ChannelType.STRING: 0>, data_count=1, status=CAStatusCode(name='ECA_NORMAL', code=0, code_with_severity=1, severity=<CASeverity.SUCCESS: 1>, success=1, defunct=False, description='Normal successful completion'), ioid=0, metadata=None)
   1550523374.317729 192.168.86.21:46212->192.168.86.245:50421 WriteNotifyRequest(data=[b'ff0000'], data_type=<ChannelType.STRING: 0>, data_count=1, sid=1, ioid=1, metadata=None)
   1550523374.366062 192.168.86.245:50421->192.168.86.21:46212 WriteNotifyResponse(data_type=<ChannelType.STRING: 0>, data_count=0, status=CAStatusCode(name='ECA_NORMAL', code=0, code_with_severity=1, severity=<CASeverity.SUCCESS: 1>, success=1, defunct=False, description='Normal successful completion'), ioid=1)
   1550523386.739346 192.168.86.21:46212->192.168.86.245:50421 ReadNotifyRequest(data_type=<ChannelType.TIME_STRING: 14>, data_count=0, sid=1, ioid=2)
   1550523386.811133 192.168.86.245:50421->192.168.86.21:46212 ReadNotifyResponse(data=[b'000000'], data_type=<ChannelType.TIME_STRING: 14>, data_count=1, status=CAStatusCode(name='ECA_NORMAL', code=0, code_with_severity=1, severity=<CASeverity.SUCCESS: 1>, success=1, defunct=False, description='Normal successful completion'), ioid=2, metadata=DBR_TIME_STRING(status=<AlarmStatus.NO_ALARM: 0>, severity=<AlarmSeverity.NO_ALARM: 0>, timestamp=1550523385.868129))
   1550523418.232482 192.168.86.21:46212->192.168.86.245:50421 EchoRequestOrResponse()
   1550523418.336746 192.168.86.245:50421->192.168.86.21:46212 EchoRequestOrResponse()
   1550523429.690765 192.168.86.21:46212->192.168.86.245:50421 EventAddRequestOrResponse(data_type=<ChannelType.STRING: 0>, data_count=0, sid=1, subscriptionid=0, low=0.0, high=0.0, to=0.0, mask=13)
   1550523429.743627 192.168.86.245:50421->192.168.86.21:46212 EventAddResponse(data=[b'000000'], data_type=<ChannelType.STRING: 0>, data_count=1, status=CAStatusCode(name='ECA_NORMAL', code=0, code_with_severity=1, severity=<CASeverity.SUCCESS: 1>, success=1, defunct=False, description='Normal successful completion'), subscriptionid=0, metadata=None)
   1550523449.254619 192.168.86.21:46212->192.168.86.245:50421 EventCancelRequest(data_type=<ChannelType.STRING: 0>, sid=1, subscriptionid=0)
   1550523449.320692 192.168.86.245:50421->192.168.86.21:46212 EventCancelResponse(data_type=<ChannelType.STRING: 0>, sid=1, subscriptionid=0, data_count=0)
