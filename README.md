# caproto

a bring-your-own-IO implementation of the EPICS Channel Access protocol

This is nowhere near a working prototype. It is a hobby project.

This project is inspired by the broad effort in the Python community to write
[sans-I/O implementations of network protocols](http://sans-io.readthedocs.io/).
It manages the coupled state of EPICS Clients, VirtualCircuits, and Channels; it
interprets received packets; and it composes valid packets to be sent. But,
crucially, it performs no I/O itself. The developer is using this library is
in complete control over when and how bytes are actually transmitted and
received. The networking may be synchronous, threaded, asynchronous.

The aim is to provide a complete, reusable implementation of the Channel Access
protocol in Python which can be wrapped in whichever network library you like
best.
