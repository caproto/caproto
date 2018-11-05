from collections import defaultdict, deque, namedtuple, ChainMap, Iterable
import copy
import logging
import sys
import time
import weakref
import caproto as ca
from caproto import (apply_arr_filter, get_environment_variables,
                     RemoteProtocolError, CaprotoKeyError, CaprotoRuntimeError,
                     CaprotoNetworkError)
from .._dbr import SubscriptionType


# ** Tuning this parameters will affect the servers' performance **
# ** under high load. **
# If the queue of subscriptions to has a new update ready within this timeout,
# we consider ourselves under high load and trade accept some latency for some
# efficiency.
HIGH_LOAD_TIMEOUT = 0.01
# When a batch of subscription updates has this many bytes or more, send it.
SUB_BATCH_THRESH = 2**16
# Tune this to change the max time between packets. If it's too high, the
# client will experience long gaps when the server is under load. If it's too
# low, the *overall* latency will be higher because the server will have to
# waste time bundling many small packets.
MAX_LATENCY = 1
# If a Read[Notify]Request or EventAddRequest is received, wait for up to this
# long for the currently-processing Write[Notify]Request to finish.
WRITE_LOCK_TIMEOUT = 0.001


class DisconnectedCircuit(Exception):
    ...


Subscription = namedtuple('Subscription', ('mask', 'channel_filter',
                                           'circuit', 'channel',
                                           'data_type',
                                           'data_count', 'subscriptionid',
                                           'db_entry'))
SubscriptionSpec = namedtuple('SubscriptionSpec', ('db_entry', 'data_type',
                                                   'mask', 'channel_filter'))

host_endian = ('>' if sys.byteorder == 'big' else '<')


class VirtualCircuit:
    def __init__(self, circuit, client, context):
        self.connected = True
        self.circuit = circuit  # a caproto.VirtualCircuit
        self.log = circuit.log
        self.client = client
        self.context = context
        self.client_hostname = None
        self.client_username = None
        # The structure of self.subscriptions is:
        # {SubscriptionSpec: deque([Subscription, Subscription, ...]), ...}
        self.subscriptions = defaultdict(deque)
        self.unexpired_updates = defaultdict(
            lambda: deque(maxlen=ca.MAX_SUBSCRIPTION_BACKLOG))
        self.most_recent_updates = {}
        # Subclasses are expected to define:
        # self.QueueFull = ...
        # self.command_queue = ...
        # self.new_command_condition = ...
        # self.subscription_queue = ...
        # self.get_from_sub_queue_with_timeout = ...
        # self.events_on = ...
        # self.write_event = ...

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
        except (ConnectionResetError, ConnectionAbortedError):
            bytes_received = []

        commands, _ = self.circuit.recv(bytes_received)
        for c in commands:
            try:
                await self.command_queue.put(c)
            except self.QueueFull:
                # This client is fast and we are not keeping up. Better to kill
                # the circuit (and let the client try again) than to let the
                # whole server be OOM-ed.
                self.log.warning(f"Circuit {self!r} has a large backlog of "
                                 f"received commands, evidently cannot keep "
                                 f"with a fast client. Disconnecting circuit "
                                 f"to avoid letting consume all available "
                                 f"memory.")
                await self._on_disconnect()
                raise DisconnectedCircuit()
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
        # The write_event will be cleared when a write is scheduled and set
        # when one completes.
        maybe_awaitable = self.write_event.set()
        # The curio backend makes this an awaitable thing.
        if maybe_awaitable is not None:
            await maybe_awaitable
        while True:
            try:
                command = await self.command_queue.get()
                self.circuit.process_command(command)
                if command is ca.DISCONNECTED:
                    break
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
            except Exception:
                self.log.exception('Circuit command queue evaluation failed')
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

                self.log.exception('Server failed to process command: %s',
                                   command)

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

    async def subscription_queue_loop(self):
        maybe_awaitable = self.events_on.set()
        # The curio backend makes this an awaitable thing.
        if maybe_awaitable is not None:
            await maybe_awaitable
        commands = deque()
        latency_limit = HIGH_LOAD_TIMEOUT
        while True:
            send_now = False
            commands.clear()
            commands_bytes = 0
            num_expired = 0
            try:
                # We are covering two regimes of operation here. In the "slow
                # producer" regime, the server is only occasionally sending
                # updates, and it should optimize for low latency. In the "fast
                # producer" regime, the server is flooded with updates that it
                # needs to get out onto the wire as efficiently as possible,
                # and it should sacrifice some latency in order to batch
                # requests efficiently.
                while True:
                    ref = await self.get_from_sub_queue_with_timeout(HIGH_LOAD_TIMEOUT)
                    if ref is None:
                        # We have caught up with the producer. Stop batching,
                        # and optimize for low latency.
                        send_now = True
                        if commands:
                            # We have accumulated commands while previously in
                            # the "fast producer" regime. Short-circuit and
                            # send them.
                            break

                        # Block here until we have something to send...
                        ref = await self.subscription_queue.get()

                        # And, since we are in "slow producer" mode, reset the
                        # limit in preparation for the next time we enter "fast
                        # producer" mode.
                        latency_limit = HIGH_LOAD_TIMEOUT

                    command = ref()
                    if command is None:
                        # Quota for this subscription has been exceeded.  This
                        # client is a slow consumer. To avoid letting it get
                        # behind, drop this message on the floor and move on.
                        # We are dropping "old news" in favor of prioritizing
                        # getting the "latest news" out. Note that the
                        # reference implementation in epics-base, rsrv, does
                        # the opposite: it drops the new news and sends the old
                        # news. Jeff Hill has stated clearly that this should
                        # be considered an implementation detail, not part of
                        # the specification. The C++ implementation can save
                        # some memory by discarding the latest updates, but it
                        # is more useful to discard the oldest updates. Python
                        # might as well do the more useful thing, given that
                        # its baseline memory usage is high.
                        num_expired += 1
                        continue
                    # Accumulate commands into a batch.
                    commands.append(command)
                    commands_bytes += len(command)
                    now = time.monotonic()
                    if len(commands) == 1:
                        # Set a dealine by which will must send this oldest
                        # command in the batch, effecitvely a limit of latency.
                        deadline = now + latency_limit
                    elif deadline < now:
                        send_now = True
                    if commands_bytes > SUB_BATCH_THRESH:
                        send_now = True
                    # Send the batch if we are in low-latency / slow producer
                    # mode, or if the high-latency deadline has passed, or if
                    # the batch has reached max size.  But be sure _not_ to
                    # send it if it is empty (because all the would-be contents
                    # were expired.)
                    if commands and send_now:
                        break
            except self.TaskCancelled:
                break
            try:
                len_commands = len(commands)
                if num_expired:
                    self.log.warning("High load. Dropped %d responses.", num_expired)
                if len_commands > 1:
                    self.log.info(
                        "High load. Batched %d commands (%dB) with %.4fs latency.",
                        len_commands, commands_bytes,
                        now - deadline + latency_limit)

                # Ensure at the last possible moment that we don't send
                # responses for Subscriptions that have been canceled at some
                # time after the response was queued. The important thing is
                # that no EventAddResponse be sent after the corresponding
                # EventCancelResponse.
                all_subscription_ids = set(sub.subscriptionid
                                           for subs in self.subscriptions.values()
                                           for sub in subs)
                culled_commands = (command for command in commands
                                   if command.subscriptionid in all_subscription_ids)
                await self.send(*culled_commands)

                # When we are stuck in the "fast producer" regime,
                # stuggling to push updates out, send larger and larger
                # pakcets by increasing the allowed latency between each
                # send until we either catch up or reach MAX_LATENCY.
                latency_limit = min(MAX_LATENCY, latency_limit * 2)
            except DisconnectedCircuit:
                await self._on_disconnect()
                self.circuit.disconnect()
                await self.context.circuit_disconnected(self)
                break

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
            self.most_recent_updates.pop(sub.subscriptionid, None)
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
        elif isinstance(command, ca.SearchRequest):
            pv_name = command.name
            try:
                self.context[pv_name]
            except KeyError:
                if command.reply == ca.DO_REPLY:
                    return [
                        ca.NotFoundResponse(
                            version=ca.DEFAULT_PROTOCOL_VERSION,
                            cid=command.cid)
                    ]
            else:
                return [
                    ca.SearchResponse(self.context.port, None, command.cid,
                                      ca.DEFAULT_PROTOCOL_VERSION)
                ]
        elif isinstance(command, ca.CreateChanRequest):
            try:
                db_entry = self.context[command.name]
            except KeyError:
                self.log.debug('Client requested invalid channel name: %s',
                               command.name)
                return [ca.CreateChFailResponse(cid=command.cid)]

            access = db_entry.check_access(self.client_hostname,
                                           self.client_username)

            return [ca.AccessRightsResponse(cid=command.cid,
                                            access_rights=access),
                    ca.CreateChanResponse(data_type=db_entry.data_type,
                                          data_count=db_entry.max_length,
                                          cid=command.cid,
                                          sid=self.circuit.new_channel_id()),
                    ]
        elif isinstance(command, ca.HostNameRequest):
            self.client_hostname = command.name
        elif isinstance(command, ca.ClientNameRequest):
            self.client_username = command.name
        elif isinstance(command, (ca.ReadNotifyRequest, ca.ReadRequest)):
            chan, db_entry = get_db_entry()
            try:
                data_type = command.data_type
            except ValueError:
                raise ca.RemoteProtocolError('Invalid data type')

            # If we are in the middle of processing a Write[Notify]Request,
            # allow a bit of time for that to (maybe) finish. Some requests
            # may take a long time, so give up rather quickly to avoid
            # introducing too much latency.
            await self.write_event.wait(timeout=WRITE_LOCK_TIMEOUT)

            metadata, data = await db_entry.auth_read(
                self.client_hostname, self.client_username,
                data_type, user_address=self.circuit.address)

            old_version = self.circuit.protocol_version < 13
            if command.data_count > 0 or old_version:
                data = data[:command.data_count]

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
            data_count = db_entry.calculate_length(data)
            return [chan.read(data=data, data_type=command.data_type,
                              data_count=data_count, status=1,
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
                        status=ca.CAStatus.ECA_PUTFAIL,
                        error_message=('Python exception: {} {}'
                                       ''.format(type(ex).__name__, ex))
                    )
                    await self.send(response_command)
                else:
                    if client_waiting:
                        if write_status is None:
                            # errors can be passed back by exceptions, and
                            # returning none for write_status can just be
                            # considered laziness
                            write_status = True

                        response_command = chan.write(
                            ioid=command.ioid,
                            status=write_status,
                            data_count=db_entry.length
                        )
                        await self.send(response_command)
                finally:
                    maybe_awaitable = self.write_event.set()
                    # The curio backend makes this an awaitable thing.
                    if maybe_awaitable is not None:
                        await maybe_awaitable

            self.write_event.clear()
            await self._start_write_task(handle_write)
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

            # If we are in the middle of processing a Write[Notify]Request,
            # allow a bit of time for that to (maybe) finish. Some requests
            # may take a long time, so give up rather quickly to avoid
            # introducing too much latency.
            if not self.write_event.is_set():
                await self.write_event.wait(timeout=WRITE_LOCK_TIMEOUT)

            await db_entry.subscribe(self.context.subscription_queue, sub_spec,
                                     sub)
        elif isinstance(command, ca.EventCancelRequest):
            chan, db_entry = get_db_entry()
            removed = await self._cull_subscriptions(
                db_entry,
                lambda sub: sub.subscriptionid == command.subscriptionid)
            if removed:
                _, removed_sub = removed[0]
                data_count = removed_sub.data_count
            else:
                data_count = db_entry.length
            return [chan.unsubscribe(command.subscriptionid,
                                     data_type=command.data_type,
                                     data_count=data_count)]
        elif isinstance(command, ca.EventsOnRequest):
            # Immediately send most recent updates for all subscriptions.
            most_recent_updates = list(self.most_recent_updates.values())
            self.most_recent_updates.clear()
            if most_recent_updates:
                await self.send(*most_recent_updates)
            maybe_awaitable = self.events_on.set()
            # The curio backend makes this an awaitable thing.
            if maybe_awaitable is not None:
                await maybe_awaitable
            self.circuit.log.info("Client at %s:%d has turned events on.",
                                  *self.circuit.address)
        elif isinstance(command, ca.EventsOffRequest):
            # The client has signaled that it does not think it will be able to
            # catch up to the backlog. Clear all updates queued to be sent...
            self.unexpired_updates.clear()
            # ...and tell the Context that any future updates from ChannelData
            # should not be added to this circuit's queue until further notice.
            self.events_on.clear()
            self.circuit.log.info("Client at %s:%d has turned events off.",
                                  *self.circuit.address)
        elif isinstance(command, ca.ClearChannelRequest):
            chan, db_entry = get_db_entry()
            await self._cull_subscriptions(
                db_entry,
                lambda sub: sub.channel == command.sid)
            return [chan.clear()]
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

        # ca_server_port: the default tcp/udp port from the environment
        self.ca_server_port = self.environ['EPICS_CA_SERVER_PORT']
        # the specific tcp port in use by this server
        self.port = None

        self.log.debug('EPICS_CA_SERVER_PORT set to %d. This is the UDP port '
                       'to be used for searches, and the first TCP server port'
                       ' to be tried.', self.ca_server_port)

        ignore_addresses = self.environ['EPICS_CAS_IGNORE_ADDR_LIST']
        self.ignore_addresses = ignore_addresses.split(' ')

    @property
    def pvdb_with_fields(self):
        'Dynamically generated each time - use sparingly'
        # TODO is static generation sufficient?
        pvdb = {}
        for name, instance in self.pvdb.items():
            pvdb[name] = instance
            if hasattr(instance, 'fields'):
                # Note that we support PvpropertyData along with ChannelData
                # instances here (which may not have fields)
                for field_name, field in instance.fields.items():
                    pvdb[f'{name}.{field_name}'] = field
        return pvdb

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
        try:
            if bytes_received:
                commands = self.broadcaster.recv(bytes_received, address)
        except RemoteProtocolError:
            self.log.exception('Broadcaster received bad packet')
        else:
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
                raise CaprotoKeyError(f'Neither record nor field exists: '
                                      f'{rec_field}')

            try:
                inst = inst.get_field(field)
            except (AttributeError, KeyError):
                raise CaprotoKeyError(f'Neither record nor field exists: '
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
            elif isinstance(command, ca.SearchRequest):
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

        if search_replies:
            if version_requested:
                bytes_to_send = self.broadcaster.send(ca.VersionResponse(13),
                                                      *search_replies)
            else:
                bytes_to_send = self.broadcaster.send(*search_replies)

            for udp_sock in self.udp_socks.values():
                try:
                    await udp_sock.sendto(bytes_to_send, addr)
                except OSError as exc:
                    host, port = addr
                    raise CaprotoNetworkError(f"Failed to send to {host}:{port}") from exc

    async def subscription_queue_loop(self):
        while True:
            # This queue receives updates that match the db_entry, data_type
            # and mask ("subscription spec") of one or more subscriptions.
            sub_specs, metadata, values, flags, sub = await self.subscription_queue.get()

            subs = []
            if sub is None:
                # Broadcast to all Subscriptions for the relevant
                # SubscriptionSpec(s).
                for sub_spec in sub_specs:
                    subs.extend(self.subscriptions[sub_spec])
            else:
                # A specific Subscription has been specified, which means this
                # specific update was prompted by Subscription being new, not
                # prompted by a new value. The update should only be sent to
                # that specific Subscription.
                subs = [sub]
                sub_spec, = sub_specs
            # Pack the data and metadata into an EventAddResponse and send it.
            # We have to make a new response for each channel because each may
            # have a different requested data_count.
            for sub in subs:
                circuit = sub.circuit
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
                    if hasattr(new, 'endian'):
                        if new.endian != host_endian:
                            new = copy.copy(new)
                            new.byteswap()
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

                # This update will be put at the back of the line of updates to
                # be sent.
                #
                # If len(unexpired_updates[id]) == SUBSCRIPTION_BACKLOG_QUOTA,
                # then the command at the front of the line will be kicked out.
                # It is not literally removed from the queue but whenever it
                # reaches the front of the line it will dropped on the floor
                # instead of sent. This effectively prioritizes sending the
                # client "new news" instead of "old news".

                # If this circuit has been sent EventsOff by the client, do not
                # queue any updates until the client sends EventsOn to signal
                # that it has caught up. But stash the most recent update for
                # each subscription, which will immediately send when we turn
                # events back on.
                if not circuit.events_on.is_set():
                    circuit.most_recent_updates[sub.subscriptionid] = command
                    continue

                # This is an OrderedBoundedSet, a set with a maxlen, containing
                # only commands for this particular subscription.
                circuit.unexpired_updates[sub.subscriptionid].append(command)

                # This is a queue with the commands from _all_ subscriptions on
                # this circuit.
                try:
                    await circuit.subscription_queue.put(weakref.ref(command))
                except circuit.QueueFull:
                    # We have hit the overall max for subscription backlog.
                    circuit.log.warning(
                        "Critically high EventAddResponse load. Dropping all "
                        "queued responses on this circuit.")
                    circuit.subscription_queue.clear()
                    circuit.unexpired_updates.clear()

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
                for name, instance in self.pvdb_with_fields.items()
                if hasattr(instance, 'server_startup') and
                instance.server_startup is not None}

    @property
    def shutdown_methods(self):
        'Notify all ChannelData instances of the server shutdown'
        return {name: instance.server_shutdown
                for name, instance in self.pvdb.items()
                if hasattr(instance, 'server_shutdown') and
                instance.server_shutdown is not None}

    async def _bind_tcp_sockets_with_consistent_port_number(self, make_socket):
        # Find a random port number that is free on all self.interfaces,
        # and get a bound TCP socket with that port number on each
        # interface. The argument `make_socket` is expected to be a coroutine
        # with the signature `make_socket(interface, port)` that does whatever
        # library-specific incantation is necessary to return a bound socket or
        # raise an IOError.
        tcp_sockets = {}  # maps interface to bound socket
        stashed_ex = None
        for port in ca.random_ports(100, try_first=self.ca_server_port):
            try:
                for interface in self.interfaces:
                    s = await make_socket(interface, port)
                    tcp_sockets[interface] = s
            except IOError as ex:
                stashed_ex = ex
                for s in tcp_sockets.values():
                    s.close()
                tcp_sockets.clear()
            else:
                break
        else:
            raise CaprotoRuntimeError('No available ports and/or bind failed') from stashed_ex
        return port, tcp_sockets

    async def tcp_handler(self, client, addr):
        '''Handler for each new TCP client to the server'''
        cavc = ca.VirtualCircuit(ca.SERVER, addr, None)
        circuit = self.CircuitClass(cavc, client, self)
        self.circuits.add(circuit)
        self.log.info('Connected to new client at %s:%d (total: %d).', *addr,
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
        self.log.info('Disconnected from client at %s:%d (total: %d).', *addr,
                      len(self.circuits))

    def stop(self):
        ...
