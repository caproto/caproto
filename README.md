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

## TO DO

* [x] Read and write to motorsim
* [x] Subscribe to motorsim (EventAdd, EventCancel) and finish
  ``Channel.subscribe`` convenience method.
* [x] Fix the socket logic at the top of `test_with_motorsim.py` to talk to
  CARepeater over TCP.
  libca installed.
* [x] Use caproto as a server that responds to caget/pyepics.
  without limiting user control.
* [x] Once "caproto as a server" works, revisit `_state.py` and simplify.
* [x] Refactor state machine that Circuit state reaches out and updates Channel
  state if a state-based transition applies.
* [x] Sphinx docs
* [x] graphviz of state machines (TODO improve)
* [x] Accessing values as ``dbr_instance.value`` is clumsy. Change the API for
  simple types.
* [x] Make DBR <-> Python type conversion as automatic and smooth as possible
* [ ] Add tests that exercise subscribe/unsubscribe on the server side in
  test_server.py.
* [ ] Test read/write of every DBR type.
* [ ] Write a standalone script that acts as a CARepeater so we can test without
  libca.
* [ ] Write an example implementation of a client.
* [ ] Write an example implementation of a server.
* [ ] Set up Travis CI.
* [ ] Publish documentation.
