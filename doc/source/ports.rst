*************************************
Configuration of Interfaces and Ports
*************************************

Servers
=======

UDP
---

* Servers bind a UDP socket to ``EPICS_CA1_PORT`` (``5064`` --- not
  configurable).
* Servers listen for ``SearchResponse`` commands and may reply to the address
  of the sender.
* Servers periodically broadcast ``RsrvIsUp`` commands to the hosts defined by
  ``EPICS_CA_ATO_BEACON_ADDR_LIST`` or if ``EPICS_CAS_BEACON_ADDR_LIST`` is not
  ``'no'``, to all broadcast interfaces. The port used is
  ``EPICS_CAS_BEACON_PORT`` (default ``5065``).

TCP
---

* Servers start a TCP server, listening on all interface ``0.0.0.0`` or or the
  list of interfaces defined by ``EPICS_CAS_INTF_ADDR_LIST``, if set. The
  addresses in the list may include a port or not. If not, ???

Clients
=======

UDP
---

TCP
---


Repeater
========

The CA Repeater is basically a UDP proxy server. Its only role is to forward
server beacons (a.k.a ``RsrvIsUp`` commands) to all clients on a host. It
exists to cope with older system that do not broadcast correctly, failing to
fan out the message to all clients reliably.

Operation:
1. Try to bind to 0.0.0.0 on the ``EPICS_CA_REPEATER_PORT`` (default ``5065``).
2. If binding fails, assume a CA Repeater is already running. Exit.
3. When a UDP datagram is received from an unknown port:
   - Check that the source host is localhost. If it is not, ignore it.
   - The datagram data may be a ``RegisterRepeaterRequest`` (recent versions of
     Channel Access) or blank (old versions of Channel Access).
   - Stash the source port number.
   - Send a ``RepeaterConfirmResponse`` to that source port.
   - Send an empty datagram to any other ports we have stashed.
   - Forward all subsequent messages to all ports we know about.
