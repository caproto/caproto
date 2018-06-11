********************
Asynchronous Clients
********************

The asynchronous clients are arguably the most interesting implementations in
caproto, or at least the most original. However, they are still very
experimental. They have some known issues, and they lack feature parity with
the threading client. They will be heavily revised in a future release of
caproto.

Developers interested in exploring them can poke around the modules
``caproto.curio.client`` and ``caproto.trio.client``. The conceptual design is
analogous to the threading client, but using the respective async frameworks,
curio and trio.
