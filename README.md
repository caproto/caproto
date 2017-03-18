# caproto

a bring-your-own-IO implementation of the EPICS Channel Access protocol

[![Build Status](https://travis-ci.org/danielballan/caproto.svg?branch=master)](https://travis-ci.org/danielballan/caproto)

[**Documentation**](https://github.com/danielballan/caproto)


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
* [x] Add tests that exercise subscribe/unsubscribe on the server side in
  test_server.py.
* [x] Set up Travis CI.
* [x] Write a standalone script that acts as a CARepeater so we can test without
  libca.
* [x] Publish documentation.
* [x] Write an example implementation of a client.
* [x] Write an example implementation of a server.
* [ ] Write pytest tests to exercise examples.
* [ ] Test read/write of every DBR type.
* [ ] Benchmark!
* [ ] Submit patch to upstream EPICS spec documentation.
* [ ] Test against catvs.
