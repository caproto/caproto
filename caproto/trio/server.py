from collections import defaultdict, deque, namedtuple
import logging
import os

import trio
from trio import socket

import caproto as ca
from caproto import (get_beacon_address_list, get_environment_variables,
                     find_available_tcp_port)
from ..server import AsyncLibraryLayer


class DisconnectedCircuit(Exception):
    ...


Subscription = namedtuple('Subscription', ('mask', 'circuit', 'channel',
                                           'data_type',
                                           'data_count', 'subscriptionid'))
SubscriptionSpec = namedtuple('SubscriptionSpec', ('db_entry', 'data_type',
                                                   'mask'))


logger = logging.getLogger(__name__)

STR_ENC = os.environ.get('CAPROTO_STRING_ENCODING', 'latin-1')


def _universal_queue(portal, max_len=1000):
    class UniversalQueue:
        def __init__(self):
            self.queue = trio.Queue(max_len)
            self.portal = portal

        async def async_put(self, value):
            await self.queue.put(value)

        def put(self, value):
            self.portal.run(self.queue.put, value)

        async def async_get(self):
            return await self.queue.get()

        def get(self):
            return self.portal.run(self.queue.get)

    return UniversalQueue


class TrioAsyncLayer(AsyncLibraryLayer):
    def __init__(self):
        self.portal = trio.BlockingTrioPortal()
        self.ThreadsafeQueue = _universal_queue(self.portal)

    name = 'trio'
    ThreadsafeQueue = None
    library = trio


class TrioVirtualCircuit:
    "Wraps a caproto.VirtualCircuit with a trio client."
    def __init__(self, circuit, client, context):
        self.nursery = context.nursery
        self.connected = True
        self.circuit = circuit  # a caproto.VirtualCircuit
        self.client = client
        self.context = context
        self.client_hostname = None
        self.client_username = None
        self.command_queue = trio.Queue(1000)
        self.new_command_condition = trio.Condition()
        self.subscriptions = defaultdict(deque)

    async def run(self):
        await self.nursery.start(self.command_queue_loop)

    async def _on_disconnect(self):
        """Executed when disconnection detected"""
        if not self.connected:
            return

        self.connected = False
        queue = self.context.subscription_queue
        for sub_spec, subs in self.subscriptions.items():
            for sub in subs:
                self.context.subscriptions[sub_spec].remove(sub)
            # Does anything else on the Context still care about this sub_spec?
            # If not unsubscribe the Context's queue from the db_entry.
            if not self.context.subscriptions[sub_spec]:
                await sub_spec.db_entry.unsubscribe(queue, sub_spec)
        self.subscriptions.clear()

        # TODO this may cancel some caputs in progress, need to rethink it
        # await self.pending_tasks.cancel_remaining()
        print('client connection closed')
        self.client.close()

    async def send(self, *commands):
        """
        Process a command and tranport it over the TCP socket for this circuit.
        """
        if self.connected:
            buffers_to_send = self.circuit.send(*commands)
            await ca.async_send_all(buffers_to_send, self.client.sendmsg)

    async def recv(self):
        """
        Receive bytes over TCP and cache them in this circuit's buffer.
        """
        try:
            bytes_received = await self.client.recv(4096)
        except ConnectionResetError:
            bytes_received = []

        commands, _ = self.circuit.recv(bytes_received)
        for c in commands:
            await self.command_queue.put(c)
        if not bytes_received:
            await self._on_disconnect()
            raise DisconnectedCircuit()

    async def command_queue_loop(self, task_status):
        """
        Coroutine which feeds from the circuit command queue.

        1. Dispatch and validate through caproto.VirtualCircuit.process_command
            - Upon server failure, respond to the client with
              caproto.ErrorResponse
        2. Update Channel state if applicable.
        """
        task_status.started()
        while True:
            try:
                command = await self.command_queue.get()
                self.circuit.process_command(command)
            except trio.Cancelled:
                break
            except ca.RemoteProtocolError as ex:
                if hasattr(command, 'sid'):
                    sid = command.sid
                    cid = self.circuit.channels_sid[sid].cid
                elif hasattr(command, 'cid'):
                    cid = command.cid
                    sid = self.circuit.channels[cid].sid

                else:
                    cid, sid = None, None

                if cid is not None:
                    try:
                        await self.send(ca.ServerDisconnResponse(cid=cid))
                    except Exception:
                        logger.error(
                            "Client broke the protocol in a recoverable "
                            "way, but channel disconnection of cid=%d sid=%d "
                            "failed.", cid, sid,
                            exc_info=ex)
                        break
                    else:
                        logger.error(
                            "Client broke the protocol in a recoverable "
                            "way. Disconnected channel cid=%d sid=%d "
                            "but keeping the circuit alive.", cid, sid,
                            exc_info=ex)

                    async with self.new_command_condition:
                        await self.new_command_condition.notify_all()
                    continue
                else:
                    logger.error("Client broke the protocol in an "
                                 "unrecoverable way.", exc_info=ex)
                    # TODO: Kill the circuit.
                    break
            except Exception as ex:
                logger.error('Circuit command queue evaluation failed',
                             exc_info=ex)
                continue

            try:
                response_command = await self._process_command(command)
                if response_command is not None:
                    await self.send(*response_command)
            except DisconnectedCircuit:
                await self._on_disconnect()
                self.circuit.disconnect()
                await self.context.circuit_disconnected(self)
                break
            except Exception as ex:
                if not self.connected:
                    if not isinstance(command, ca.ClearChannelRequest):
                        logger.error('Trio server error after client '
                                     'disconnection: %s', command)
                    break

                logger.error('Trio server failed to process command: %s',
                             command, exc_info=ex)

                if hasattr(command, 'sid'):
                    cid = self.circuit.channels_sid[command.sid].cid

                    response_command = ca.ErrorResponse(
                        command, cid,
                        status_code=ca.ECA_INTERNAL.code_with_severity,
                        error_message=('Python exception: {} {}'
                                       ''.format(type(ex).__name__, ex))
                    )
                    await self.send(response_command)

            async with self.new_command_condition:
                self.new_command_condition.notify_all()

    async def _process_command(self, command):
        '''Process a command from a client, and return the server response'''
        def get_db_entry():
            chan = self.circuit.channels_sid[command.sid]
            db_entry = self.context[chan.name.decode(STR_ENC)]
            return chan, db_entry

        if command is ca.DISCONNECTED:
            raise DisconnectedCircuit()
        elif isinstance(command, ca.VersionRequest):
            return [ca.VersionResponse(13)]
        elif isinstance(command, ca.CreateChanRequest):
            db_entry = self.context[command.name.decode(STR_ENC)]
            access = db_entry.check_access(self.client_hostname,
                                           self.client_username)

            return [ca.AccessRightsResponse(cid=command.cid,
                                            access_rights=access),
                    ca.CreateChanResponse(data_type=db_entry.data_type,
                                          data_count=len(db_entry),
                                          cid=command.cid,
                                          sid=self.circuit.new_channel_id()),
                    ]
        elif isinstance(command, ca.HostNameRequest):
            self.client_hostname = command.name.decode(STR_ENC)
        elif isinstance(command, ca.ClientNameRequest):
            self.client_username = command.name.decode(STR_ENC)
        elif isinstance(command, ca.ReadNotifyRequest):
            chan, db_entry = get_db_entry()
            metadata, data = await db_entry.auth_read(
                self.client_hostname, self.client_username,
                command.data_type)
            return [chan.read(data=data, data_type=command.data_type,
                              data_count=len(data), status=1,
                              ioid=command.ioid, metadata=metadata)
                    ]
        elif isinstance(command, (ca.WriteRequest, ca.WriteNotifyRequest)):
            chan, db_entry = get_db_entry()
            client_waiting = isinstance(command, ca.WriteNotifyRequest)

            async def handle_write():
                '''Wait for an asynchronous caput to finish'''
                try:
                    write_status = await db_entry.auth_write(
                        self.client_hostname, self.client_username,
                        command.data, command.data_type, command.metadata)
                except Exception as ex:
                    logger.exception('Invalid write request by %s (%s): %r',
                                     self.client_username,
                                     self.client_hostname, command)
                    cid = self.circuit.channels_sid[command.sid].cid
                    response_command = ca.ErrorResponse(
                        command, cid,
                        status_code=ca.ECA_INTERNAL.code_with_severity,
                        error_message=('Python exception: {} {}'
                                       ''.format(type(ex).__name__, ex))
                    )
                else:
                    if write_status is None:
                        # errors can be passed back by exceptions, and
                        # returning none for write_status can just be
                        # considered laziness
                        write_status = True
                    response_command = chan.write(ioid=command.ioid,
                                                  status=write_status)

                if client_waiting:
                    await self.send(response_command)

            self.nursery.start_soon(handle_write)
            # TODO pretty sure using the taskgroup will bog things down,
            # but it suppresses an annoying warning message, so... there
        elif isinstance(command, ca.EventAddRequest):
            chan, db_entry = get_db_entry()
            # TODO no support for deprecated low/high/to
            sub = Subscription(mask=command.mask,
                               channel=chan,
                               circuit=self,
                               data_type=command.data_type,
                               data_count=command.data_count,
                               subscriptionid=command.subscriptionid)
            sub_spec = SubscriptionSpec(db_entry=db_entry,
                                        data_type=command.data_type,
                                        mask=command.mask)
            self.subscriptions[sub_spec].append(sub)
            self.context.subscriptions[sub_spec].append(sub)
            await db_entry.subscribe(self.context.subscription_queue, sub_spec)
        elif isinstance(command, ca.EventCancelRequest):
            chan, db_entry = get_db_entry()
            await self._cull_subscriptions(
                db_entry,
                lambda sub: sub.subscriptionid == command.subscriptionid)
            return [chan.unsubscribe(command.subscriptionid)]
        elif isinstance(command, ca.ClearChannelRequest):
            chan, db_entry = get_db_entry()
            await self._cull_subscriptions(
                db_entry,
                lambda sub: sub.channel == command.sid)
            return [chan.disconnect()]
        elif isinstance(command, ca.EchoRequest):
            return [ca.EchoResponse()]

    async def _cull_subscriptions(self, db_entry, func):
        # Iterate through each Subscription, passing each one to func(sub).
        # Collect a list of (SubscriptionSpec, Subscription) for which
        # func(sub) is True.
        #
        # Remove any matching Subscriptions, and then remove any empty
        # SubsciprtionSpecs. Return the list of matching pairs.
        to_remove = []
        for sub_spec, subs in self.subscriptions.items():
            for sub in subs:
                if func(sub):
                    to_remove.append((sub_spec, sub))
        for sub_spec, sub in to_remove:
            self.subscriptions[sub_spec].remove(sub)
            self.context.subscriptions[sub_spec].remove(sub)
            # Does anything else on the Context still care about sub_spec?
            # If not unsubscribe the Context's queue from the db_entry.
            if not self.context.subscriptions[sub_spec]:
                queue = self.context.subscription_queue
                await sub_spec.db_entry.unsubscribe(queue, sub_spec)
        return tuple(to_remove)


class Context:
    def __init__(self, host, port, pvdb, *, log_level='ERROR'):
        self.nursery = None
        self.host = host
        self.port = port
        self.pvdb = pvdb

        self.circuits = set()
        self.log_level = log_level
        self.broadcaster = ca.Broadcaster(our_role=ca.SERVER)
        self.broadcaster.log.setLevel(self.log_level)
        self.command_bundle_queue = trio.Queue(1000)

        self.subscriptions = defaultdict(deque)
        self.subscription_queue = trio.Queue(1000)
        self.beacon_count = 0
        self.environ = get_environment_variables()

        ignore_addresses = self.environ['EPICS_CAS_IGNORE_ADDR_LIST']
        self.ignore_addresses = ignore_addresses.split(' ')

    async def broadcaster_udp_server_loop(self, task_status):
        self.udp_sock = ca.bcast_socket(socket)
        try:
            await self.udp_sock.bind((self.host, ca.EPICS_CA1_PORT))
        except Exception:
            logger.exception('[server] udp bind failure!')
            raise

        task_status.started()

        while True:
            bytes_received, address = await self.udp_sock.recvfrom(4096)
            if bytes_received:
                commands = self.broadcaster.recv(bytes_received, address)
                await self.command_bundle_queue.put((address, commands))

    def __iter__(self):
        # Implemented to support __getitem__ below
        return iter(self.pvdb)

    def __getitem__(self, pvname):
        try:
            return self.pvdb[pvname]
        except KeyError as ex:
            try:
                (rec_field, rec, field, mods) = ca.parse_record_field(pvname)
            except ValueError:
                raise ex

            if not field and not mods:
                # No field or modifiers, so there's nothing left to check
                raise

        # Without the modifiers, try 'record[.field]'
        try:
            inst = self.pvdb[rec_field]
        except KeyError:
            # Finally, access 'record', see if it has 'field'
            try:
                inst = self.pvdb[rec]
            except KeyError:
                raise KeyError(f'Neither record nor field exists: '
                               f'{rec_field}')

            try:
                inst = inst.get_field(field)
            except (AttributeError, KeyError):
                raise KeyError(f'Neither record nor field exists: '
                               f'{rec_field}')

            # Cache record.FIELD for later usage
            self.pvdb[rec_field] = inst

        # Finally, handle the modifiers
        if not mods:
            return inst

        # filter check
        # TODO: filter API? wrap somehow?
        return inst.filtered(mods)

    async def _broadcaster_evaluate(self, addr, commands):
        responses = []
        for command in commands:
            if isinstance(command, ca.VersionRequest):
                responses.append(ca.VersionResponse(13))
            if isinstance(command, ca.SearchRequest):
                pv_name = command.name.decode(STR_ENC)
                try:
                    known_pv = self[pv_name] is not None
                except KeyError:
                    known_pv = False

                if (not known_pv) and command.reply == ca.NO_REPLY:
                    responses.clear()
                    break  # Do not send any repsonse to this datagram.

                # responding with an IP of `None` tells client to get IP
                # address from packet
                responses.append(
                    ca.SearchResponse(self.port, None, command.cid, 13)
                )
        if responses:
            bytes_to_send = self.broadcaster.send(*responses)
            await self.udp_sock.sendto(bytes_to_send, addr)

    async def broadcaster_queue_loop(self, task_status):
        task_status.started()
        while True:
            try:
                addr, commands = await self.command_bundle_queue.get()
                self.broadcaster.process_commands(commands)
                if addr not in self.ignore_addresses:
                    await self._broadcaster_evaluate(addr, commands)
            except trio.Cancelled:
                break
            except Exception as ex:
                logger.error('Broadcaster command queue evaluation failed',
                             exc_info=ex)
                continue

    async def tcp_handler(self, client, addr):
        '''Handler for each new TCP client to the server'''
        cavc = ca.VirtualCircuit(ca.SERVER, addr, None)
        circuit = TrioVirtualCircuit(cavc, client, self)
        self.circuits.add(circuit)

        circuit.circuit.log.setLevel(self.log_level)

        await circuit.run()

        while True:
            try:
                await circuit.recv()
            except DisconnectedCircuit:
                break

    async def circuit_disconnected(self, circuit):
        '''Notification from circuit that its connection has closed'''
        self.circuits.remove(circuit)

    async def subscription_queue_loop(self, task_status):
        task_status.started()
        while True:
            # This queue receives updates that match the db_entry, data_type
            # and mask ("subscription spec") of one or more subscriptions.
            sub_specs, metadata, values = await self.subscription_queue.get()
            subs = []
            for sub_spec in sub_specs:
                subs.extend(self.subscriptions[sub_spec])
            # Pack the data and metadata into an EventAddResponse and send it.
            # We have to make a new response for each channel because each may
            # have a different requested data_count.
            for sub in subs:
                chan = sub.channel
                # if the subscription has a non-zero value respect it,
                # else default to the full length of the data
                data_count = sub.data_count or len(values)
                command = chan.subscribe(data=values,
                                         metadata=metadata,
                                         data_type=sub.data_type,
                                         data_count=data_count,
                                         subscriptionid=sub.subscriptionid,
                                         status_code=1)
                await sub.circuit.send(command)

    async def broadcast_beacon_loop(self, task_status):
        beacon_period = self.environ['EPICS_CAS_BEACON_PERIOD']
        addresses = get_beacon_address_list()

        task_status.started()

        while True:
            beacon = ca.RsrvIsUpResponse(13, self.port, self.beacon_count,
                                         self.host)
            bytes_to_send = self.broadcaster.send(beacon)
            for addr_port in addresses:
                try:
                    await self.udp_sock.sendto(bytes_to_send, addr_port)
                except IOError:
                    logger.exception("Failed to send beacon to %r. Try "
                                     "setting "
                                     "EPICS_CAS_BEACON_AUTO_ADDR_LIST=no and "
                                     "EPICS_CAS_BEACON_ADDR_LIST=<addresses>.",
                                     addr_port)
                    raise
            self.beacon_count += 1
            await trio.sleep(beacon_period)

    async def server_accept_loop(self, addr, port, *, task_status):
        with trio.socket.socket() as listen_sock:
            logger.debug('Listening on %s:%d', addr, port)
            await listen_sock.bind((addr, port))
            listen_sock.listen()

            task_status.started()

            while True:
                client_sock, addr = await listen_sock.accept()
                self.nursery.start_soon(self.tcp_handler, client_sock, addr)

    @property
    def startup_methods(self):
        'Notify all ChannelData instances of the server startup'
        return [instance.server_startup
                for name, instance in self.pvdb.items()
                if hasattr(instance, 'server_startup') and
                instance.server_startup is not None]

    async def run(self):
        'Start the server'
        try:
            async with trio.open_nursery() as self.nursery:
                for addr, port in ca.get_server_address_list(self.port):
                    await self.nursery.start(self.server_accept_loop,
                                             addr, port)
                await self.nursery.start(self.broadcaster_udp_server_loop)
                await self.nursery.start(self.broadcaster_queue_loop)
                await self.nursery.start(self.subscription_queue_loop)
                await self.nursery.start(self.broadcast_beacon_loop)

                async_lib = TrioAsyncLayer()
                for method in self.startup_methods:
                    logger.debug('Calling startup method %r', method)

                    async def startup(task_status):
                        task_status.started()
                        await method(async_lib)

                    await self.nursery.start(startup)
        except trio.Cancelled:
            logger.info('Server task cancelled')

    async def stop(self):
        'Stop the server'
        nursery = self.nursery
        if nursery is None:
            return

        nursery.cancel_scope.cancel()


async def start_server(pvdb, log_level='DEBUG', *, bind_addr='0.0.0.0'):
    '''Start a trio server with a given PV database'''
    logger.setLevel(log_level)
    ctx = Context(bind_addr, find_available_tcp_port(), pvdb,
                  log_level=log_level)
    logger.info('Server starting up on %s:%d', ctx.host, ctx.port)
    return await ctx.run()
