from collections import defaultdict, deque, namedtuple, ChainMap, Iterable
import logging
import time
import caproto as ca
from caproto import apply_arr_filter, get_environment_variables
from .._dbr import SubscriptionType


class DisconnectedCircuit(Exception):
    ...


Subscription = namedtuple('Subscription', ('mask', 'channel_filter',
                                           'circuit', 'channel',
                                           'data_type',
                                           'data_count', 'subscriptionid',
                                           'db_entry'))
SubscriptionSpec = namedtuple('SubscriptionSpec', ('db_entry', 'data_type',
                                                   'mask', 'channel_filter'))


class VirtualCircuit:
    def __init__(self, circuit, client, context):
        self.connected = True
        self.circuit = circuit  # a caproto.VirtualCircuit
        self.log = circuit.log
        self.client = client
        self.context = context
        self.client_hostname = None
        self.client_username = None
        self.subscriptions = defaultdict(deque)

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

    async def send(self, *commands):
        """
        Process a command and tranport it over the TCP socket for this circuit.
        """
        if self.connected:
            buffers_to_send = self.circuit.send(*commands)
            # send bytes over the wire using some caproto utilities
            await ca.async_send_all(buffers_to_send, self.client.sendmsg)

    async def recv(self):
        """
        Receive bytes over TCP and cache them in this circuit's buffer.
        """
        try:
            bytes_received = await self.client.recv(4096)
        except (ConnectionResetError, ConnectionAbortedError) as ex:
            bytes_received = []

        commands, _ = self.circuit.recv(bytes_received)
        for c in commands:
            await self.command_queue.put(c)
        if not bytes_received:
            await self._on_disconnect()
            raise DisconnectedCircuit()

    async def command_queue_loop(self):
        """
        Coroutine which feeds from the circuit command queue.

        1. Dispatch and validate through caproto.VirtualCircuit.process_command
            - Upon server failure, respond to the client with
              caproto.ErrorResponse
        2. Update Channel state if applicable.
        """
        while True:
            try:
                command = await self.command_queue.get()
                self.circuit.process_command(command)
            except self.TaskCancelled:
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
                        self.log.error(
                            "Client broke the protocol in a recoverable "
                            "way, but channel disconnection of cid=%d sid=%d "
                            "failed.", cid, sid,
                            exc_info=ex)
                        break
                    else:
                        self.log.error(
                            "Client broke the protocol in a recoverable "
                            "way. Disconnected channel cid=%d sid=%d "
                            "but keeping the circuit alive.", cid, sid,
                            exc_info=ex)

                    await self._wake_new_command()
                    continue
                else:
                    self.log.error("Client broke the protocol in an "
                                   "unrecoverable way.", exc_info=ex)
                    # TODO: Kill the circuit.
                    break
            except Exception as ex:
                self.log.error('Circuit command queue evaluation failed',
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
                        self.log.error('Server error after client '
                                       'disconnection: %s', command)
                    break

                self.log.error('Server failed to process command: %s',
                               command, exc_info=ex)

                if hasattr(command, 'sid'):
                    cid = self.circuit.channels_sid[command.sid].cid

                    response_command = ca.ErrorResponse(
                        command, cid,
                        status=ca.CAStatus.ECA_INTERNAL,
                        error_message=('Python exception: {} {}'
                                       ''.format(type(ex).__name__, ex))
                    )
                    await self.send(response_command)

            await self._wake_new_command()

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
            self.context.last_dead_band.pop(sub, None)
            self.context.last_sync_edge_update.pop(sub, None)
            # Does anything else on the Context still care about sub_spec?
            # If not unsubscribe the Context's queue from the db_entry.
            if not self.context.subscriptions[sub_spec]:
                queue = self.context.subscription_queue
                await sub_spec.db_entry.unsubscribe(queue, sub_spec)
        return tuple(to_remove)

    async def _process_command(self, command):
        '''Process a command from a client, and return the server response'''
        def get_db_entry():
            chan = self.circuit.channels_sid[command.sid]
            db_entry = self.context[chan.name]
            return chan, db_entry
        if command is ca.DISCONNECTED:
            raise DisconnectedCircuit()
        elif isinstance(command, ca.VersionRequest):
            return [ca.VersionResponse(ca.DEFAULT_PROTOCOL_VERSION)]
        elif isinstance(command, ca.CreateChanRequest):
            db_entry = self.context[command.name]
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
            self.client_hostname = command.name
        elif isinstance(command, ca.ClientNameRequest):
            self.client_username = command.name
        elif isinstance(command, (ca.ReadNotifyRequest, ca.ReadRequest)):
            chan, db_entry = get_db_entry()
            metadata, data = await db_entry.auth_read(
                self.client_hostname, self.client_username,
                command.data_type, user_address=self.circuit.address)
            # This is a pass-through if arr is None.
            data = apply_arr_filter(chan.channel_filter.arr, data)
            # If the timestamp feature is active swap the timestamp.
            # Information must copied because not all clients will have the
            # timestamp filter
            if chan.channel_filter.ts and command.data_type in ca.time_types:
                time_type = type(metadata)
                now = ca.TimeStamp.from_unix_timestamp(time.time())
                metadata = time_type(**ChainMap({'stamp': now},
                                                dict((field, getattr(metadata, field))
                                                     for field, _ in time_type._fields_)))
            notify = isinstance(command, ca.ReadNotifyRequest)
            return [chan.read(data=data, data_type=command.data_type,
                              data_count=len(data), status=1,
                              ioid=command.ioid, metadata=metadata,
                              notify=notify)
                    ]
        elif isinstance(command, (ca.WriteRequest, ca.WriteNotifyRequest)):
            chan, db_entry = get_db_entry()
            client_waiting = isinstance(command, ca.WriteNotifyRequest)

            async def handle_write():
                '''Wait for an asynchronous caput to finish'''
                try:
                    write_status = await db_entry.auth_write(
                        self.client_hostname, self.client_username,
                        command.data, command.data_type, command.metadata,
                        user_address=self.circuit.address)
                except Exception as ex:
                    self.log.exception('Invalid write request by %s (%s): %r',
                                       self.client_username,
                                       self.client_hostname, command)
                    cid = self.circuit.channels_sid[command.sid].cid
                    response_command = ca.ErrorResponse(
                        command, cid,
                        status=ca.CAStatus.ECA_INTERNAL,
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

            await self._start_write_task(handle_write)
            # TODO pretty sure using the taskgroup will bog things down,
            # but it suppresses an annoying warning message, so... there
        elif isinstance(command, ca.EventAddRequest):
            chan, db_entry = get_db_entry()
            # TODO no support for deprecated low/high/to
            sub = Subscription(mask=command.mask,
                               channel_filter=chan.channel_filter,
                               channel=chan,
                               circuit=self,
                               data_type=command.data_type,
                               data_count=command.data_count,
                               subscriptionid=command.subscriptionid,
                               db_entry=db_entry)
            sub_spec = SubscriptionSpec(
                db_entry=db_entry,
                data_type=command.data_type,
                mask=command.mask,
                channel_filter=chan.channel_filter)
            self.subscriptions[sub_spec].append(sub)
            self.context.subscriptions[sub_spec].append(sub)
            await db_entry.subscribe(self.context.subscription_queue, sub_spec)
        elif isinstance(command, ca.EventCancelRequest):
            chan, db_entry = get_db_entry()
            await self._cull_subscriptions(
                db_entry,
                lambda sub: sub.subscriptionid == command.subscriptionid)
            return [chan.unsubscribe(command.subscriptionid,
                                     data_type=command.data_type)]
        elif isinstance(command, ca.ClearChannelRequest):
            chan, db_entry = get_db_entry()
            await self._cull_subscriptions(
                db_entry,
                lambda sub: sub.channel == command.sid)
            return [chan.disconnect()]
        elif isinstance(command, ca.EchoRequest):
            return [ca.EchoResponse()]


class Context:
    def __init__(self, pvdb, interfaces=None):
        if interfaces is None:
            interfaces = ca.get_server_address_list()
        self.interfaces = interfaces
        self.udp_socks = {}  # map each interface to a UDP socket for searches
        self.beacon_socks = {}  # map each interface to a UDP socket for beacons
        self.pvdb = pvdb
        self.log = logging.getLogger(f'caproto.ctx.{id(self)}')

        self.circuits = set()
        self.broadcaster = ca.Broadcaster(our_role=ca.SERVER)

        self.subscriptions = defaultdict(deque)
        # Map Subscription to {'before': last_update, 'after': last_update}
        # to silence duplicates for Subscriptions that use edge-triggered sync
        # Channel Filter.
        self.last_sync_edge_update = defaultdict(lambda: defaultdict(dict))
        self.last_dead_band = {}
        self.beacon_count = 0
        self.environ = get_environment_variables()

        ignore_addresses = self.environ['EPICS_CAS_IGNORE_ADDR_LIST']
        self.ignore_addresses = ignore_addresses.split(' ')

    async def _core_broadcaster_loop(self, udp_sock):
        while True:
            try:
                bytes_received, address = await udp_sock.recvfrom(4096 * 16)
            except ConnectionResetError:
                self.log.exception('UDP server connection reset')
                await self.async_layer.library.sleep(0.1)
                continue

            await self._broadcaster_recv_datagram(bytes_received, address)

    async def _broadcaster_recv_datagram(self, bytes_received, address):
        if bytes_received:
            commands = self.broadcaster.recv(bytes_received, address)
            await self.command_bundle_queue.put((address, commands))

    async def broadcaster_queue_loop(self):
        while True:
            try:
                addr, commands = await self.command_bundle_queue.get()
                self.broadcaster.process_commands(commands)
                if addr not in self.ignore_addresses:
                    await self._broadcaster_evaluate(addr, commands)
            except self.TaskCancelled:
                break
            except Exception as ex:
                self.log.exception('Broadcaster command queue evaluation failed',
                                   exc_info=ex)
                continue

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
        return inst

    async def _broadcaster_evaluate(self, addr, commands):
        search_replies = []
        version_requested = False
        for command in commands:
            if isinstance(command, ca.VersionRequest):
                version_requested = True
            if isinstance(command, ca.SearchRequest):
                pv_name = command.name
                try:
                    known_pv = self[pv_name] is not None
                except KeyError:
                    known_pv = False

                if known_pv:
                    # responding with an IP of `None` tells client to get IP
                    # address from the datagram.
                    search_replies.append(
                        ca.SearchResponse(self.port, None, command.cid,
                                          ca.DEFAULT_PROTOCOL_VERSION)
                    )
                else:
                    if command.reply == ca.DO_REPLY:
                        search_replies.append(
                            ca.NotFoundResponse(
                                version=ca.DEFAULT_PROTOCOL_VERSION,
                                cid=command.cid)
                        )
                    else:
                        # Not a known PV and no reply required
                        ...

        if search_replies:
            if version_requested:
                bytes_to_send = self.broadcaster.send(ca.VersionResponse(13),
                                                      *search_replies)
            else:
                bytes_to_send = self.broadcaster.send(*search_replies)

            for udp_sock in self.udp_socks.values():
                await udp_sock.sendto(bytes_to_send, addr)

    async def subscription_queue_loop(self):
        while True:
            # This queue receives updates that match the db_entry, data_type
            # and mask ("subscription spec") of one or more subscriptions.
            sub_specs, metadata, values, flags = await self.subscription_queue.get()
            subs = []
            for sub_spec in sub_specs:
                subs.extend(self.subscriptions[sub_spec])
            # Pack the data and metadata into an EventAddResponse and send it.
            # We have to make a new response for each channel because each may
            # have a different requested data_count.
            for sub in subs:
                s_flags = flags
                chan = sub.channel

                # This is a pass-through if arr is None.
                values = apply_arr_filter(sub_spec.channel_filter.arr, values)

                # If the subscription has a non-zero value respect it,
                # else default to the full length of the data.
                data_count = sub.data_count or len(values)
                if data_count != len(values):
                    values = values[:data_count]

                command = chan.subscribe(data=values,
                                         metadata=metadata,
                                         data_type=sub.data_type,
                                         data_count=data_count,
                                         subscriptionid=sub.subscriptionid,
                                         status=1)

                dbnd = sub.channel_filter.dbnd
                if dbnd is not None:
                    new = values
                    old = self.last_dead_band.get(sub)
                    if old is not None:
                        if ((not isinstance(old, Iterable) or
                             (isinstance(old, Iterable) and len(old) == 1)) and
                            (not isinstance(new, Iterable) or
                             (isinstance(new, Iterable) and len(new) == 1))):
                            if isinstance(old, Iterable):
                                old, = old
                            if isinstance(new, Iterable):
                                new, = new
                            # Cool that was fun.
                            if dbnd.m == 'rel':
                                out_of_band = dbnd.d < abs((old - new) / old)
                            else:  # must be 'abs' -- was already validated
                                out_of_band = dbnd.d < abs(old - new)
                            # We have verified that that EPICS considers DBE_LOG etc. to be
                            # an absolute (not relative) threshold.
                            abs_diff = abs(old - new)
                            if abs_diff > sub.db_entry.log_atol:
                                s_flags |= SubscriptionType.DBE_LOG
                                if abs_diff > sub.db_entry.value_atol:
                                    s_flags |= SubscriptionType.DBE_VALUE

                            if not (out_of_band and (sub.mask & s_flags)):
                                continue
                            else:
                                self.last_dead_band[sub] = new
                    else:
                        self.last_dead_band[sub] = new

                # Special-case for edge-triggered modes of the sync Channel
                # Filter (before, after, first, last). Only send the first
                # update to each channel.
                sync = sub.channel_filter.sync
                if sync is not None:
                    last_update = self.last_sync_edge_update[sub][sync.s].get(sync.m)
                    if last_update and last_update == command:
                        # This is a redundant update. Do not send.
                        continue
                    else:
                        # Stash this and then send it.
                        self.last_sync_edge_update[sub][sync.s][sync.m] = command

                # Check that the Channel did not close at some point after
                # this update started its flight.
                if chan.states[ca.SERVER] is ca.CONNECTED:
                    await sub.circuit.send(command)

    async def broadcast_beacon_loop(self):
        self.log.debug('Will send beacons to %r',
                       [f'{h}:{p}' for h, p in self.beacon_socks.keys()])
        MIN_BEACON_PERIOD = 0.02  # "RECOMMENDED" by the CA spec
        BEACON_BACKOFF = 2  # "RECOMMENDED" by the CA spec
        max_beacon_period = self.environ['EPICS_CAS_BEACON_PERIOD']
        beacon_period = MIN_BEACON_PERIOD
        while True:
            for address, (interface, sock) in self.beacon_socks.items():
                try:
                    beacon = ca.Beacon(13, self.port,
                                       self.beacon_count,
                                       interface)
                    bytes_to_send = self.broadcaster.send(beacon)
                    await sock.send(bytes_to_send)
                except IOError:
                    self.log.exception(
                        "Failed to send beacon to %r. Try setting "
                        "EPICS_CAS_AUTO_BEACON_ADDR_LIST=no and "
                        "EPICS_CAS_BEACON_ADDR_LIST=<addresses>.", address)
                    raise
            self.beacon_count += 1
            if beacon_period < max_beacon_period:
                beacon_period = min(max_beacon_period,
                                    beacon_period * BEACON_BACKOFF)
            await self.async_layer.library.sleep(beacon_period)

    async def circuit_disconnected(self, circuit):
        '''Notification from circuit that its connection has closed'''
        self.circuits.discard(circuit)

    @property
    def startup_methods(self):
        'Notify all ChannelData instances of the server startup'
        return {name: instance.server_startup
                for name, instance in self.pvdb.items()
                if hasattr(instance, 'server_startup') and
                instance.server_startup is not None}

    def _bind_tcp_sockets_with_consistent_port_number(self, make_socket):
        # Find a random port number that is free on all self.interfaces,
        # and get a bound TCP socket with that port number on each
        # interface. The argument `make_socket` is expected to be a
        # synchronous callable with the signature
        # `make_socket(interface, port)` that does whatever
        # library-specific incantation is necessary to return a bound
        # socket or raise an IOError.
        tcp_sockets = {}  # maps interface to bound socket
        stashed_ex = None
        for port in ca.random_ports(100):
            try:
                for interface in self.interfaces:
                    s = make_socket(interface, port)
                    tcp_sockets[interface] = s
            except IOError as ex:
                stashed_ex = ex
                for s in tcp_sockets.values():
                    s.close()
                tcp_sockets.clear()
            else:
                break
        else:
            raise RuntimeError('No available ports and/or bind failed') from stashed_ex
        return port, tcp_sockets

    async def tcp_handler(self, client, addr):
        '''Handler for each new TCP client to the server'''
        cavc = ca.VirtualCircuit(ca.SERVER, addr, None)
        circuit = self.CircuitClass(cavc, client, self)
        self.circuits.add(circuit)
        self.log.info('Connected to new client at %s:%d.\n'
                      'Circuits currently connected: %d', *addr,
                      len(self.circuits))

        await circuit.run()

        try:
            while True:
                try:
                    await circuit.recv()
                except DisconnectedCircuit:
                    await self.circuit_disconnected(circuit)
                    break
        except KeyboardInterrupt as ex:
            self.log.debug('TCP handler received KeyboardInterrupt')
            raise self.ServerExit() from ex
        self.log.info('Disconnected from client at %s:%d.\n'
                      'Circuits currently connected: %d', *addr,
                      len(self.circuits))
