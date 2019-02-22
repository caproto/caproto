# This is a channel access client implemented using asyncio.

# It builds on the abstractions used in caproto, adding transport and some
# caches for matching requests with responses.
#
# VirtualCircuit: has a caproto.VirtualCircuit, a socket, and some caches.
# Channel: has a VirtualCircuit and a caproto.ClientChannel.
# Context: has a caproto.Broadcaster, a UDP socket, a cache of
#          search results and a cache of VirtualCircuits.
#
import getpass
import logging

import caproto as ca

from collections import OrderedDict
import socket
import asyncio

from ..client.common import (VirtualCircuit as _VirtualCircuit)
from .utils import _get_asyncio_queue


class ChannelReadError(Exception):
    ...


class VirtualCircuit(_VirtualCircuit):
    "Wraps a caproto.VirtualCircuit and adds transport."
    def __init__(self, circuit, *, loop=None):
        # do loopy stuff up front
        if loop is None:
            loop = asyncio.get_event_loop()
        self.loop = loop

        super().__init__(circuit)
        self.command_queue = _get_asyncio_queue(loop)
        self.new_command_condition = asyncio.Condition(loop=self.loop)
        self._socket_lock = asyncio.Lock()

        self.tasks = {}

    async def _connect(self):
        # very confused
        ...
