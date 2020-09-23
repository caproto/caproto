********************
Asynchronous Clients
********************

Developers interested in exploring the prototype asyncio client can poke around
the module :mod:`caproto.asyncio.client`. The design is analogous to the
threading client but using asyncio.

While this asyncio client is full-featured as compared to the threading client,
it has had minimal testing, usage, or review.

With that in mind, please let us know if it works for you, or you have feedback
for us.

For those that are looking for information about curio or trio clients, their
prototype implementations have been removed.
