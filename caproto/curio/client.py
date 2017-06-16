# This is a channel access client implemented using curio.

# It builds on the abstractions used in caproto, adding transport and some
# caches for matching requests with responses.
#
# VirtualCircuit: has a caproto.VirtualCircuit, a socket, and some caches.
# Channel: has a VirtualCircuit and a caproto.ClientChannel.
# Context: has a caproto.Broadcaster, a UDP socket, a cache of
#          search results and a cache of VirtualCircuits.
#
import logging
import caproto as ca
import curio
from curio import socket


logger = logging.getLogger(__name__)


class ChannelReadError(Exception):
    ...


class VirtualCircuit:
    "Wraps a caproto.VirtualCircuit and adds transport."
    def __init__(self, circuit):
        self.circuit = circuit  # a caproto.VirtualCircuit
        self.channels = {}  # map cid to Channel
        self.ioids = {}  # map ioid to Channel
        self.ioid_data = {}  # map ioid to server response
        self.subscriptionids = {}  # map subscriptionid to Channel
        self.socket = None
        self.new_command_condition = curio.Condition()
        self._socket_lock = curio.Lock()

    async def create_connection(self):
        self.socket = await socket.create_connection(self.circuit.address)
        await self._socket_lock.release()

        while True:
            bytes_received = await self.socket.recv(32768)
            if not len(bytes_received):
                self.circuit.disconnect()
                break
            self.circuit.recv(bytes_received)

    async def _command_queue_loop(self):
        while True:
            try:
                command = await self.circuit.async_next_command()
            except curio.TaskCancelled:
                break
            except Exception as ex:
                logger.error('Command queue evaluation failed: {!r}'
                             ''.format(command), exc_info=ex)
                continue

            if isinstance(command, (ca.ReadNotifyResponse,
                                    ca.WriteNotifyResponse)):
                user_event = self.ioids.pop(command.ioid)
                self.ioid_data[command.ioid] = command
                await user_event.set()
            elif isinstance(command, ca.EventAddResponse):
                user_queue = self.subscriptionids[command.subscriptionid]
                await user_queue.put(command)
            elif isinstance(command, ca.EventCancelResponse):
                self.subscriptionids.pop(command.subscriptionid)
            elif isinstance(command, ca.ErrorResponse):
                original_req = command.original_request
                cmd_class = ca.get_command_class(ca.CLIENT, original_req)
                if cmd_class in (ca.ReadNotifyRequest, ca.WriteNotifyRequest):
                    ioid = original_req.parameter2
                    user_event = self.ioids.pop(ioid)
                    self.ioid_data[ioid] = command
                    await user_event.set()

            async with self.new_command_condition:
                await self.new_command_condition.notify_all()

    async def send(self, *commands):
        """
        Process a command and tranport it over the TCP socket for this circuit.
        """
        buffers_to_send = self.circuit.send(*commands)
        async with self._socket_lock:
            if self.socket is None:
                raise RuntimeError('socket connection failed')
            await self.socket.sendmsg(buffers_to_send)


class Channel:
    """Wraps a VirtualCircuit and a caproto.ClientChannel."""
    def __init__(self, circuit, channel):
        self.circuit = circuit  # a VirtualCircuit
        self.channel = channel  # a caproto.ClientChannel
        self.last_reading = None
        self.monitoring_tasks = {}  # maps subscriptionid to curio.Task
        self._callback = None  # user func to call when subscriptions are run

    def register_user_callback(self, func):
        """
        Func to be called when a subscription receives a new EventAdd command.

        This function will be called by a Task in the main thread. If ``func``
        needs to do CPU-intensive or I/O-related work, it should execute that
        work in a separate thread of process.
        """
        self._callback = func

    def process_subscription(self, event_add_command):
        if self._callback is None:
            return
        else:
            self._callback(event_add_command)

    async def wait_for_connection(self):
        """Wait for this Channel to be connected, ready to use.

        The method ``Context.create_channel`` spawns an asynchronous task to
        initialize the connection in the fist place. This method waits for it
        to complete.
        """
        while not self.channel.states[ca.CLIENT] is ca.CONNECTED:
            await self.wait_on_new_command()

    async def disconnect(self):
        "Disconnect this Channel."
        await self.circuit.send(self.channel.disconnect())
        while self.channel.states[ca.CLIENT] is ca.MUST_CLOSE:
            await self.wait_on_new_command()

    async def read(self, *args, **kwargs):
        """Request a fresh reading, wait for it, return it and stash it.

        The most recent reading is always available in the ``last_reading``
        attribute.
        """
        command = self.channel.read(*args, **kwargs)
        # Stash the ioid to match the response to the request.
        ioid = command.ioid
        # TODO this could be implemented as a concurrent.Future and use
        #      curio.traps._future_wait. A Future is really what we want here,
        #      but it doesn't seem like curio provides such a primitive for us
        ioid = command.ioid
        event = curio.Event()
        self.circuit.ioids[ioid] = event
        await self.circuit.send(command)
        await event.wait()

        reading = self.circuit.ioid_data.pop(ioid)
        if isinstance(reading, ca.ReadNotifyResponse):
            self.last_reading = reading
            return self.last_reading
        else:
            raise ChannelReadError(str(reading))

    async def write(self, *args, **kwargs):
        "Write a new value and await confirmation from the server."
        command = self.channel.write(*args, **kwargs)
        # Stash the ioid to match the response to the request.
        ioid = command.ioid
        event = curio.Event()
        self.circuit.ioids[ioid] = event
        await self.circuit.send(command)
        await event.wait()
        return self.circuit.ioid_data.pop(ioid)

    async def subscribe(self, *args, **kwargs):
        "Start a new subscription and spawn an async task to receive readings."
        command = self.channel.subscribe(*args, **kwargs)
        # Stash the subscriptionid to match the response to the request.
        queue = curio.Queue()
        self.circuit.subscriptionids[command.subscriptionid] = queue
        await self.circuit.send(command)

        async def _queue_loop():
            command = await queue.get()
            self.process_subscription(command)

        task = await curio.spawn(_queue_loop, daemon=True)
        self.monitoring_tasks[command.subscriptionid] = task

    async def unsubscribe(self, subscriptionid, *args, **kwargs):
        "Cancel a subscription and await confirmation from the server."
        await self.circuit.send(self.channel.unsubscribe(subscriptionid))
        while subscriptionid in self.circuit.subscriptionids:
            await self.wait_on_new_command()
        task = self.monitoring_tasks.pop(subscriptionid)
        await task.cancel()

    async def wait_on_new_command(self):
        '''Wait for a new command to come in'''
        async with self.circuit.new_command_condition:
            await self.circuit.new_command_condition.wait()


class SharedBroadcaster:
    def __init__(self, *, log_level='ERROR'):
        self.log_level = log_level
        self.broadcaster = ca.Broadcaster(our_role=ca.CLIENT,
                                          queue_class=curio.UniversalQueue)
        self.broadcaster.log.setLevel(self.log_level)
        self.broadcaster_command_condition = curio.Condition()

        # UDP socket broadcasting to CA servers
        self.udp_sock = ca.bcast_socket(socket)
        self.registered = False  # refers to RepeaterRegisterRequest
        self.unanswered_searches = {}  # map search id (cid) to name
        self.search_results = {}  # map name to address

    async def send(self, port, *commands):
        """
        Process a command and tranport it over the UDP socket.
        """
        bytes_to_send = self.broadcaster.send(*commands)
        for host in ca.get_address_list():
            if ':' in host:
                host, _, specified_port = host.partition(':')
                is_register = isinstance(commands[0],
                                         ca.RepeaterRegisterRequest)
                if not self.registered and is_register:
                    logger.debug('Specific IOC host/port designated in address'
                                 'list: %s:%s.  Repeater registration '
                                 'requirement ignored', host, specified_port)
                    async with self.broadcaster_command_condition:
                        # TODO how does this work with multiple addresses
                        # listed?
                        response = (('127.0.0.1', ca.EPICS_CA1_PORT),
                                    [ca.RepeaterConfirmResponse(
                                        repeater_address='127.0.0.1')]
                                    )
                        await self.broadcaster.command_queue.put(response)
                        await self.broadcaster_command_condition.notify_all()
                    continue
                await self.udp_sock.sendto(bytes_to_send,
                                           (host, int(specified_port)))
            else:
                await self.udp_sock.sendto(bytes_to_send, (host, port))

    async def register(self):
        "Register this client with the CA Repeater."
        await curio.spawn(self._broadcaster_queue_loop(), daemon=True)

        while not self.registered:
            async with self.broadcaster_command_condition:
                await self.broadcaster_command_condition.wait()

    async def _broadcaster_recv_loop(self):
        # TODO: broadcaster info should be shared application-wide if possible,
        # as they are not really tied to a context in any way?
        # also: these coroutines could probably be merged intelligently
        # somehow, but isn't the point rather that you can break it up into
        # these readable co-friendly routines?

        while True:
            bytes_received, address = await self.udp_sock.recvfrom(4096)
            self.broadcaster.recv(bytes_received, address)

    async def _broadcaster_queue_loop(self):
        await curio.spawn(self._broadcaster_recv_loop(), daemon=True)
        command = self.broadcaster.register('127.0.0.1')
        await self.send(ca.EPICS_CA2_PORT, command)

        while True:
            try:
                addr, commands = await self.broadcaster.async_next_command()
            except curio.TaskCancelled:
                break
            except Exception as ex:
                logger.error('Broadcaster command queue evaluation '
                             'failed: {!r}'.format(commands), exc_info=ex)
                continue

            for command in commands:
                if isinstance(command, ca.RepeaterConfirmResponse):
                    self.registered = True
                if isinstance(command, ca.VersionResponse):
                    # Check that the server version is one we can talk to.
                    assert command.version > 11
                if isinstance(command, ca.SearchResponse):
                    name = self.unanswered_searches.pop(command.cid, None)
                    if name is not None:
                        self.search_results[name] = ca.extract_address(command)
                    else:
                        # This is a redundant response, which the spec tell us
                        # we must ignore.
                        pass

                async with self.broadcaster_command_condition:
                    await self.broadcaster_command_condition.notify_all()

    async def search(self, name):
        "Generate, process, and transport a search request."
        # Discard any old search result for this name.
        self.search_results.pop(name, None)
        ver_command, search_command = self.broadcaster.search(name)
        # Stash the search ID for recognizes the SearchResponse later.
        self.unanswered_searches[search_command.cid] = name
        await self.send(ca.EPICS_CA1_PORT, ver_command, search_command)
        # Wait for the SearchResponse.
        while search_command.cid in self.unanswered_searches:
            await self.wait_on_new_command()

    async def wait_on_new_command(self):
        '''Wait for a new broadcaster command to come in'''
        async with self.broadcaster_command_condition:
            await self.broadcaster_command_condition.wait()


class Context:
    "Wraps a caproto.Broadcaster, a UDP socket, and cache of VirtualCircuits."
    def __init__(self, broadcaster, *, log_level='ERROR'):
        self.log_level = log_level
        self.circuits = []  # list of VirtualCircuits
        self.broadcaster = broadcaster

    def get_circuit(self, address, priority):
        """
        Return a VirtualCircuit with this address, priority.

        Make a new one if necessary.
        """
        for circuit in self.circuits:
            if (circuit.circuit.address == address and
                    circuit.circuit.priority == priority):
                return circuit

        ca_circuit = ca.VirtualCircuit(our_role=ca.CLIENT, address=address,
                                       priority=priority,
                                       queue_class=curio.UniversalQueue)
        circuit = VirtualCircuit(ca_circuit)
        circuit.circuit.log.setLevel(self.log_level)
        self.circuits.append(circuit)
        return circuit

    async def search(self, name):
        "Generate, process, transport a search request with the broadcaster"
        return await self.broadcaster.search(name)

    async def create_channel(self, name, priority=0):
        """
        Create a new channel.
        """
        address = self.broadcaster.search_results[name]
        circuit = self.get_circuit(address, priority)
        chan = ca.ClientChannel(name, circuit.circuit)

        if chan.circuit.states[ca.SERVER] is ca.IDLE:
            await circuit._socket_lock.acquire()  # wrong primitive
            await curio.spawn(circuit.create_connection(), daemon=True)
            await curio.spawn(circuit._command_queue_loop(), daemon=True)
            await circuit.send(chan.version())
            await circuit.send(chan.host_name())
            await circuit.send(chan.client_name())

        await circuit.send(chan.create())
        return Channel(circuit, chan)


async def main():
    logger.setLevel('DEBUG')
    logging.basicConfig()

    # this universalqueue is evil and genius
    # ca.set_default_queue_class(curio.UniversalQueue)

    # Connect to two motorsim PVs. Test reading, writing, and subscribing.
    pv1 = "XF:31IDA-OP{Tbl-Ax:X1}Mtr.VAL"
    pv2 = "XF:31IDA-OP{Tbl-Ax:X2}Mtr.VAL"

    # Some user function to call when subscriptions receive data.
    called = []

    def user_callback(command):
        print("Subscription has received data: {}".format(command))
        called.append(True)

    broadcaster = SharedBroadcaster()
    await broadcaster.register()

    ctx = Context(broadcaster)
    await ctx.search(pv1)
    await ctx.search(pv2)
    # Send out connection requests without waiting for responses...
    chan1 = await ctx.create_channel(pv1)
    chan2 = await ctx.create_channel(pv2)
    # Set up a function to call when subscriptions are received.
    chan1.register_user_callback(user_callback)
    # ...and then wait for all the responses.
    await chan1.wait_for_connection()
    await chan2.wait_for_connection()
    reading = await chan1.read()
    print('reading:', reading)
    await chan1.subscribe()
    await chan2.read()
    await chan1.unsubscribe(0)
    await chan1.write((5,))
    reading = await chan1.read()
    print('reading:', reading)
    await chan1.write((6,))
    reading = await chan1.read()
    print('reading:', reading)
    await chan2.disconnect()
    await chan1.disconnect()
    assert called
    print('Done')


if __name__ == '__main__':
    curio.run(main())
