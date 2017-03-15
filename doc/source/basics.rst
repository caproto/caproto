*******************************************************
Getting Started: Writing Your Own Channel Access Client
*******************************************************

Caproto can be used to implement both EPICS clients and servers. To give a
flavor for how the API works, we’ll demonstrate a small client.

Channel Access Basics
=====================

A Channel Access client locates servers on its network using UDP broadcasts. It
communicates with each individual server via one or more TCP connections. (Why
have multiple TCP connections to the same server? They can be designated
different *priority* to cope with high traffic. Channel Access calls each
individual connection a *Virtual Circuit*.)

To begin, we need a UDP socket.

.. ipython:: python

    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    udp_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)



    bytes_to_send = b.send(ca.RepeaterRegisterRequest('0.0.0.0'))
    udp_sock.sendto(bytes_to_send, ('', 5065))



* Set up sockets.
* Send bytes, raw.
* Use commands to build bytes.

The Hub object
==============

* Introduce Hub

Channels
========

* Introduce Chnnales.

Virtual Circuits
================

