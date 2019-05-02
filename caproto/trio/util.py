import collections
import trio


TrioMemoryChannelPair = collections.namedtuple('TrioMemoryChannelPair',
                                               'send receive')


def open_memory_channel(max_items):
    '''Wrapper around trio.open_memory_channel, which patches the send channel
    for queue-like compatibility'''
    send, recv = trio.open_memory_channel(max_items)
    # monkey-patch here for compatibility with a regular queue:
    send.put = send.send
    return TrioMemoryChannelPair(send, recv)
