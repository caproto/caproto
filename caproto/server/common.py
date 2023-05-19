from __future__ import annotations

import logging
import os
import sys
import time
import typing
import weakref
from collections import ChainMap, defaultdict, deque, namedtuple
from typing import DefaultDict, Deque, Tuple

import caproto as ca
from caproto import (CaprotoKeyError, CaprotoNetworkError, CaprotoRuntimeError,
                     ChannelType, RemoteProtocolError, apply_arr_filter,
                     get_environment_variables)

from .._constants import MAX_UDP_RECV
from .._dbr import DbrTypeBase, _LongStringChannelType
from .._utils import apply_deadband_filter

if typing.TYPE_CHECKING:
    from .._circuit import ServerChannel, SubscriptionType
    from .._data import ChannelData
    from .._utils import ChannelFilter


# ** Tuning this parameters will affect the servers' performance **
# ** under high load. **
# If the queue of subscriptions to has a new update ready within this timeout,
# we consider ourselves under high load and trade accept some latency for some
# efficiency.
HIGH_LOAD_TIMEOUT = float(
    os.environ.get("CAPROTO_SERVER_HIGH_LOAD_TIMEOUT_SEC", 0.01)
)
HIGH_LOAD_EVENT_TIME_THRESHOLD = float(
    os.environ.get("CAPROTO_SERVER_HIGH_LOAD_EVENT_TIME_THRESHOLD_SEC", 0.1)
)
# Warn the user if packets are delayed by more than this amount: 30ms
# Set to 0 to disable the warning entirely.
HIGH_LOAD_WARN_LATENCY_SEC = float(
    os.environ.get("CAPROTO_SERVER_HIGH_LOAD_WARN_LATENCY_SEC", 0.03)
)
# When a batch of subscription updates has this many bytes or more, send it.
SUB_BATCH_THRESH = int(os.environ.get("CAPROTO_SERVER_SUB_BATCH_THRESH", 2 ** 16))
# Tune this to change the max time between packets. If it's too high, the
# client will experience long gaps when the server is under load. If it's too
# low, the *overall* latency will be higher because the server will have to
# waste time bundling many small packets.
MAX_LATENCY = float(os.environ.get("CAPROTO_SERVER_MAX_LATENCY_SEC", 1.0))
# If a Read[Notify]Request or EventAddRequest is received, wait for up to this
# long for the currently-processing Write[Notify]Request to finish.
WRITE_LOCK_TIMEOUT = float(
    os.environ.get("CAPROTO_SERVER_WRITE_LOCK_TIMEOUT_SEC", 0.001)
)


class DisconnectedCircuit(Exception):
    ...


class LoopExit(Exception):
    ...


class Subscription(namedtuple('Subscription',
                              ('mask', 'channel_filter', 'circuit', 'channel',
                               'data_type', 'data_count', 'subscriptionid',
                               'db_entry'))
                   ):
    '''
    An individual subscription from a client

    Attributes
    ----------
    mask : SubscriptionType
        The subscription mask indicating different properties
    channel_filter : ChannelFilter
        The channel filter specified, including timestamp, deadband,
        array and sync options.
    circuit : VirtualCircuit
        The associated virtual circuit
    channel : ServerChannel
        The associated channel
    data_type : ChannelType
        The requested data type
    data_count : int
        The number of requested elements
    subscriptionid : int
        The ID of the subscription
    db_entry : ChannelData
        The database entry
    '''
    mask: SubscriptionType
    channel_filter: ChannelFilter
    circuit: VirtualCircuit
    channel: ServerChannel
    data_type: ChannelType
    data_count: int
    subscriptionid: int
    db_entry: ChannelData


class SubscriptionSpec(namedtuple('SubscriptionSpec',
                                  ('db_entry', 'data_type_name', 'mask',
                                   'channel_filter'))
                       ):
    '''
    Subscription specification used to key all subscription updates

    Attributes
    ----------
    db_entry : ChannelData
        The database entry
    data_type_name : str
        The type name associated with the user's request. For example,
        all of the following are valid: {'STRING', 'INT', 'TIME_STRING',
        'TIME_INT', 'LONG_STRING'} and so on.  See also :class:`ChannelType`
        and :class:`_LongStringChannelType`.
    mask : SubscriptionType
        The subscription mask indicating different properties
    channel_filter : ChannelFilter
        The channel filter specified, including timestamp, deadband,
        array and sync options.
    '''
    db_entry: ChannelData
    data_type_name: str
    mask: SubscriptionType
    channel_filter: ChannelFilter


host_endian = ('>' if sys.byteorder == 'big' else '<')


class VirtualCircuit:
    circuit: ca.VirtualCircuit

    def __init__(self, circuit, client, context):
        self.connected = True
        self.circuit = circuit  # a caproto.VirtualCircuit
        self.circuit.our_address = client.getsockname()
        self.log = circuit.log
        self.client = client
        self.context = context
        self.client_hostname = None
        self.client_username = None
        # The structure of self.subscriptions is:
        # {SubscriptionSpec: deque([Subscription, Subscription, ...]), ...}
        self.subscriptions = defaultdict(deque)
        self.unexpired_updates = {}
        self.subscriptions_to_resend = {}
        self.time_events_toggled = time.monotonic()
        # This dict is passed to the loggers.
        self._tags = {'their_address': self.circuit.address,
                      'our_address': self.circuit.our_address,
                      'direction': '<<<---',
                      'role': repr(self.circuit.our_role)}
        # Subclasses are expected to define:
        # self.QueueFull = ...
        # self.command_queue = ...
        # self.new_command_condition = ...
        # self.subscription_queue = ...
        # self.get_from_sub_queue = ...
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

    async def _send_buffers(self, *commands):
        """To be implemented in a subclass"""
        raise NotImplementedError()

    async def send(self, *commands):
        """
        Process a command and tranport it over the TCP socket for this circuit.
        """
        if self.connected:
            buffers_to_send = self.circuit.send(*commands)
            try:
                await self._send_buffers(*buffers_to_send)
            except (OSError, CaprotoNetworkError) as ex:
                raise DisconnectedCircuit(
                    f"Circuit disconnected: {ex}"
                ) from ex

    async def recv(self):
        """
        Receive bytes over TCP and cache them in this circuit's buffer.
        """
        try:
            bytes_received = await self.client.recv(4096)
        except OSError:
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

    def _get_ids_from_command(self, command):
        """Returns (cid, sid) given a command"""
        cid, sid = None, None
        if hasattr(command, 'sid'):
            sid = command.sid
            cid = self.circuit.channels_sid[sid].cid
        elif hasattr(command, 'cid'):
            cid = command.cid
            sid = self.circuit.channels[cid].sid

        return cid, sid

    async def _command_queue_iteration(self, command):
        """
        Coroutine which evaluates one item from the circuit command queue.

        1. Dispatch and validate through caproto.VirtualCircuit.process_command
            - Upon server failure, respond to the client with
              caproto.ErrorResponse
        2. Update Channel state if applicable.
        """
        try:
            self.circuit.process_command(command)
        except ca.RemoteProtocolError:
            cid, sid = self._get_ids_from_command(command)

            if cid is not None:
                try:
                    await self.send(ca.ServerDisconnResponse(cid=cid))
                except Exception:
                    self.log.exception(
                        "Client broke the protocol in a recoverable way, but "
                        "channel disconnection of cid=%d sid=%d failed.", cid,
                        sid)
                    raise LoopExit('Recoverable protocol error failure')
                else:
                    self.log.exception(
                        "Client broke the protocol in a recoverable way. "
                        "Disconnected channel cid=%d sid=%d but keeping the "
                        "circuit alive.", cid, sid)

                await self._wake_new_command()
                return
            else:
                self.log.exception(
                    "Client broke the protocol in an unrecoverable way.")
                # TODO: Kill the circuit.
                raise LoopExit('Unrecoverable protocol error')
        except Exception:
            self.log.exception('Circuit command queue evaluation failed')
            # Internal error - ignore for now
            return

        if command is ca.DISCONNECTED:
            raise DisconnectedCircuit

        try:
            response = await self._process_command(command)
            return response
        except Exception as ex:
            if not self.connected:
                if not isinstance(command, ca.ClearChannelRequest):
                    self.log.error('Server error after client '
                                   'disconnection: %s', command)
                raise LoopExit('Server error after client disconnection')

            cid, sid = self._get_ids_from_command(command)
            chan, _ = self._get_db_entry_from_command(command)
            self.log.exception(
                'Server failed to process command (%r): %s',
                chan.name, command)

            if cid is not None:
                error_message = f'Python exception: {type(ex).__name__} {ex}'
                return [ca.ErrorResponse(command, cid,
                                         status=ca.CAStatus.ECA_INTERNAL,
                                         error_message=error_message)
                        ]

    async def command_queue_loop(self):
        """Reference implementation of the command queue loop

        Note
        ----
        Assumes self.command_bundle_queue functions as an async queue with
        awaitable .get()

        Async library implementations can (and should) reimplement this.
        Coroutine which evaluates one item from the circuit command queue.
        """

        # The write_event will be cleared when a write is scheduled and set
        # when one completes.
        maybe_awaitable = self.write_event.set()
        # The curio backend makes this an awaitable thing.
        if maybe_awaitable is not None:
            await maybe_awaitable

        try:
            while True:
                command = await self.command_queue.get()
                response = await self._command_queue_iteration(command)
                if response is not None:
                    await self.send(*response)
                await self._wake_new_command()
        except DisconnectedCircuit:
            await self._on_disconnect()
            self.circuit.disconnect()
            await self.context.circuit_disconnected(self)
        except self.TaskCancelled:
            ...
        except LoopExit:
            ...

    async def subscription_queue_loop(self):
        maybe_awaitable = self.events_on.set()
        # The curio backend makes this an awaitable thing.
        if maybe_awaitable is not None:
            await maybe_awaitable
        commands = deque()
        latency_limit = HIGH_LOAD_TIMEOUT
        deadline = 0.0
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
                    ref = await self.get_from_sub_queue(timeout=HIGH_LOAD_TIMEOUT)
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
                        ref = await self.get_from_sub_queue(timeout=None)

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

                # If events are toggled by the client, subscriptions values get
                # garbage- collected.  It's not a high load situation.  Let's
                # warn only if we're relatively sure that it wasn't due to
                # recent event toggling.
                time_since_events_toggled = time.monotonic() - self.time_events_toggled
                if num_expired and time_since_events_toggled > HIGH_LOAD_EVENT_TIME_THRESHOLD:
                    self.log.warning("High load. Dropped %d responses.", num_expired)

                if len_commands > 1 and HIGH_LOAD_WARN_LATENCY_SEC > 0:
                    latency = now - deadline + latency_limit
                    if latency >= HIGH_LOAD_WARN_LATENCY_SEC:
                        self.log.warning(
                            "High load. Batched %d commands (%dB) with %.4fs latency.",
                            len_commands, commands_bytes, latency
                        )

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
            resends = self.subscriptions_to_resend.get(sub_spec, [])
            if sub in resends:
                resends.remove(sub)
            self.context.subscriptions[sub_spec].remove(sub)
            self.context.last_dead_band.pop(sub, None)
            self.context.last_sync_edge_update.pop(sub, None)
            # Does anything else on the Context still care about sub_spec?
            # If not unsubscribe the Context's queue from the db_entry.
            if not self.context.subscriptions[sub_spec]:
                queue = self.context.subscription_queue
                await sub_spec.db_entry.unsubscribe(queue, sub_spec)
        return tuple(to_remove)

    def _get_db_entry_from_command(self, command):
        """Return a database entry from command, determined by the server id"""
        cid, sid = self._get_ids_from_command(command)
        chan = self.circuit.channels_sid[sid]
        db_entry = self.context[chan.name]
        return chan, db_entry

    async def _process_command(self, command):
        '''Process a command from a client, and return the server response'''
        tags = self._tags
        if command is ca.DISCONNECTED:
            raise DisconnectedCircuit()
        elif isinstance(command, ca.VersionRequest):
            to_send = [ca.VersionResponse(ca.DEFAULT_PROTOCOL_VERSION)]
        elif isinstance(command, ca.SearchRequest):
            pv_name = command.name
            try:
                self.context[pv_name]
            except KeyError:
                if command.reply == ca.DO_REPLY:
                    to_send = [
                        ca.NotFoundResponse(
                            version=ca.DEFAULT_PROTOCOL_VERSION,
                            cid=command.cid)
                    ]
                else:
                    to_send = []
            else:
                to_send = [
                    ca.SearchResponse(self.context.port, None, command.cid,
                                      ca.DEFAULT_PROTOCOL_VERSION)
                ]
        elif isinstance(command, ca.CreateChanRequest):
            pvname = command.name
            try:
                db_entry = self.context[pvname]
            except KeyError:
                self.log.debug('Client requested invalid channel name: %s',
                               pvname)
                to_send = [ca.CreateChFailResponse(cid=command.cid)]
            else:

                access = db_entry.check_access(self.client_hostname,
                                               self.client_username)

                modifiers = ca.parse_record_field(pvname).modifiers
                data_type = db_entry.data_type
                data_count = db_entry.max_length
                if ca.RecordModifiers.long_string in (modifiers or {}):
                    if data_type in (ChannelType.STRING, ):
                        data_type = ChannelType.CHAR
                        data_count = db_entry.long_string_max_length

                to_send = [ca.AccessRightsResponse(cid=command.cid,
                                                   access_rights=access),
                           ca.CreateChanResponse(data_type=data_type,
                                                 data_count=data_count,
                                                 cid=command.cid,
                                                 sid=self.circuit.new_channel_id()),
                           ]
        elif isinstance(command, ca.HostNameRequest):
            self.client_hostname = command.name
            to_send = []
        elif isinstance(command, ca.ClientNameRequest):
            self.client_username = command.name
            to_send = []
        elif isinstance(command, (ca.ReadNotifyRequest, ca.ReadRequest)):
            chan, db_entry = self._get_db_entry_from_command(command)
            try:
                data_type = command.data_type
            except ValueError:
                raise ca.RemoteProtocolError('Invalid data type')

            # If we are in the middle of processing a Write[Notify]Request,
            # allow a bit of time for that to (maybe) finish. Some requests
            # may take a long time, so give up rather quickly to avoid
            # introducing too much latency.
            await self.write_event.wait(timeout=WRITE_LOCK_TIMEOUT)

            read_data_type = data_type
            if chan.name.endswith('$'):
                try:
                    read_data_type = _LongStringChannelType(read_data_type)
                except ValueError:
                    # Not requesting a LONG_STRING type
                    ...

            metadata, data = await db_entry.auth_read(
                self.client_hostname, self.client_username,
                read_data_type, user_address=self.circuit.address,
            )

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
            to_send = [chan.read(data=data, data_type=command.data_type,
                                 data_count=data_count, status=1,
                                 ioid=command.ioid, metadata=metadata,
                                 notify=notify)
                       ]
        elif isinstance(command, (ca.WriteRequest, ca.WriteNotifyRequest)):
            chan, db_entry = self._get_db_entry_from_command(command)
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
            to_send = []
        elif isinstance(command, ca.EventAddRequest):
            chan, db_entry = self._get_db_entry_from_command(command)
            # TODO no support for deprecated low/high/to

            read_data_type = command.data_type
            if chan.name.endswith('$'):
                try:
                    read_data_type = _LongStringChannelType(read_data_type)
                except ValueError:
                    # Not requesting a LONG_STRING type
                    ...

            sub = Subscription(mask=command.mask,
                               channel_filter=chan.channel_filter,
                               channel=chan,
                               circuit=self,
                               data_type=read_data_type,
                               data_count=command.data_count,
                               subscriptionid=command.subscriptionid,
                               db_entry=db_entry)
            sub_spec = SubscriptionSpec(
                db_entry=db_entry,
                data_type_name=read_data_type.name,
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
            to_send = []
        elif isinstance(command, ca.EventCancelRequest):
            chan, db_entry = self._get_db_entry_from_command(command)
            removed = await self._cull_subscriptions(
                db_entry,
                lambda sub: sub.subscriptionid == command.subscriptionid)
            if removed:
                _, removed_sub = removed[0]
                data_count = removed_sub.data_count
            else:
                data_count = db_entry.length
            to_send = [chan.unsubscribe(command.subscriptionid,
                                        data_type=command.data_type,
                                        data_count=data_count)]
        elif isinstance(command, ca.EventsOnRequest):
            self.circuit.log.info("Client at %s:%d has turned events on.",
                                  *self.circuit.address)

            self.time_events_toggled = time.monotonic()
            maybe_awaitable = self.events_on.set()
            # The curio backend makes this an awaitable thing.
            if maybe_awaitable is not None:
                await maybe_awaitable

            # Send all subscriptions that were marked as "to be sent" during
            # the period that events were off.
            resend = list(self.subscriptions_to_resend.items())
            self.subscriptions_to_resend.clear()
            for sub_spec, subs in resend:
                for sub in subs:
                    await sub.db_entry.subscribe(
                        self.context.subscription_queue,
                        sub_spec=sub_spec,
                        sub=sub,
                    )

            to_send = []
        elif isinstance(command, ca.EventsOffRequest):
            self.circuit.log.info("Client at %s:%d has turned events off.",
                                  *self.circuit.address)
            self.time_events_toggled = time.monotonic()
            # ...and tell the Context that any future updates from ChannelData
            # should not be added to this circuit's queue until further notice.
            self.events_on.clear()
            # The client has signaled that it does not think it will be able to
            # catch up to the backlog. Clear all updates queued to be sent...
            self.unexpired_updates.clear()
            to_send = []
        elif isinstance(command, ca.ClearChannelRequest):
            chan, db_entry = self._get_db_entry_from_command(command)
            await self._cull_subscriptions(
                db_entry,
                lambda sub: sub.channel == command.sid)
            to_send = [chan.clear()]
        elif isinstance(command, ca.EchoRequest):
            to_send = [ca.EchoResponse()]
        if isinstance(command, ca.Message):
            tags['bytesize'] = len(command)
            self.log.debug("%r", command, extra=tags)
        return to_send


class Context:
    subscriptions: DefaultDict[SubscriptionSpec, Deque[Subscription]]

    def __init__(self, pvdb, interfaces=None):
        if interfaces is None:
            interfaces = ca.get_server_address_list()
        self.interfaces = interfaces
        self.udp_socks = {}  # map each interface to a UDP socket for searches
        self.beacon_socks = {}  # map each interface to a UDP socket for beacons
        self.pvdb = pvdb
        self.log = logging.getLogger('caproto.ctx')

        self.addresses = []
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
                bytes_received, address = await udp_sock.recvfrom(
                    MAX_UDP_RECV
                )
            except ConnectionResetError:
                # Win32: "On a UDP-datagram socket this error indicates
                # a previous send operation resulted in an ICMP Port
                # Unreachable message."
                #
                # https://docs.microsoft.com/en-us/windows/win32/api/winsock/nf-winsock-recvfrom
                self.log.debug('UDP server recvfrom error')
            except OSError:
                self.log.exception('UDP server recvfrom error')
            else:
                if bytes_received:
                    await self._broadcaster_recv_datagram(bytes_received, address)

    async def _broadcaster_recv_datagram(self, bytes_received, address):
        try:
            commands = self.broadcaster.recv(bytes_received, address)
        except RemoteProtocolError as ex:
            self.log.debug('_broadcaster_recv_datagram: %s', ex, exc_info=ex)
        else:
            await self.command_bundle_queue.put((address, commands))

    async def broadcaster_queue_loop(self):
        '''Reference broadcaster queue loop implementation

        Note
        ----
        Assumes self.command_bundle_queue functions as an async queue with
        awaitable .get()

        Async library implementations can (and should) reimplement this.
        '''
        while True:
            try:
                addr, commands = await self.command_bundle_queue.get()
                await self._broadcaster_queue_iteration(addr, commands)
            except self.TaskCancelled:
                break
            except Exception as ex:
                self.log.exception('Broadcaster command queue evaluation failed',
                                   exc_info=ex)

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
                raise ex from None

            if not field and not mods:
                # No field or modifiers, but a trailing '.' is valid
                return self.pvdb[rec]

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

        # Verify the modifiers are usable BEFORE caching rec_field in the pvdb:
        if ca.RecordModifiers.long_string in (mods or {}):
            if inst.data_type not in (ChannelType.STRING,
                                      ChannelType.CHAR):
                raise CaprotoKeyError(
                    f'Long-string modifier not supported with types '
                    f'other than string or char ({inst.data_type})'
                )

        # Cache record.FIELD for later usage
        self.pvdb[rec_field] = inst
        return inst

    async def _broadcaster_queue_iteration(self, addr, commands):
        self.broadcaster.process_commands(commands)
        if addr in self.ignore_addresses:
            return

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
        """Reference implementation of the subscription queue loop

        Note
        ----
        Assumes self.subscription-queue functions as an async queue with
        awaitable .get()

        Async library implementations can (and should) reimplement this.
        Coroutine which evaluates one item from the circuit command queue.
        """
        while True:
            # This queue receives updates that match the db_entry, data_type
            # and mask ("subscription spec") of one or more subscriptions.
            sub_specs, metadata, values, flags, sub = await self.subscription_queue.get()
            await self._subscription_queue_iteration(
                sub_specs,
                metadata,
                values,
                flags,
                sub,
            )

    async def _subscription_queue_iteration(
        self,
        sub_specs: Tuple[SubscriptionSpec, ...],
        metadata: DbrTypeBase,
        values,
        flags: int,
        sub: Subscription,
    ):
        """This handles a single queue item from ``subscription_queue``."""
        if sub is None:
            # Broadcast to all Subscriptions for the relevant
            # SubscriptionSpec(s).
            for sub_spec in sub_specs:
                for sub in self.subscriptions[sub_spec]:
                    await self._subscription_queue_send(
                        sub_spec,
                        sub,
                        metadata=metadata,
                        values=values,
                        flags=flags,
                    )
        else:
            # A specific Subscription has been specified, which means this
            # specific update was prompted by Subscription being new, not
            # prompted by a new value. The update should only be sent to that
            # specific Subscription.
            if len(sub_specs) != 1:
                raise RuntimeError("Unexpected sub_specs length")

            sub_spec, = sub_specs
            await self._subscription_queue_send(
                sub_spec,
                sub,
                metadata=metadata,
                values=values,
                flags=flags,
            )

    async def _subscription_queue_send(
        self,
        sub_spec: SubscriptionSpec,
        sub: Subscription,
        metadata: DbrTypeBase,
        values,
        flags: int,
    ):
        '''Called on every item from the Context subscription queue

        This queue receives updates that match the db_entry, data_type and mask
        ("subscription spec") of one or more subscriptions.
        '''
        circuit = sub.circuit

        # If this circuit has been sent EventsOff by the client, do not queue
        # any updates until the client sends EventsOn to signal that it has
        # caught up. Instead, mark this subscription as something that needs to
        # be redone when events come back on.
        if not circuit.events_on.is_set():
            to_resend = circuit.subscriptions_to_resend.setdefault(sub_spec, [])
            if sub not in to_resend:
                to_resend.append(sub)
            return

        # Pack the data and metadata into an EventAddResponse and send it.  We
        # have to make a new response for each channel because each may have a
        # different requested data_count.
        chan = sub.channel

        # This is a pass-through if arr is None.
        values = apply_arr_filter(sub_spec.channel_filter.arr, values)

        # If the subscription has a non-zero value respect it, else default
        # to the full length of the data.
        data_count = sub.data_count or len(values)
        if data_count != len(values):
            values = values[:data_count]

        command = chan.subscribe(
            data=values,
            metadata=metadata,
            data_type=sub.data_type,
            data_count=data_count,
            subscriptionid=sub.subscriptionid,
            status=1,
        )

        dbnd = sub.channel_filter.dbnd
        if dbnd is not None:
            deadband_tracking_value = apply_deadband_filter(
                previous_value=self.last_dead_band.get(sub),
                new_value=values,
                sub=sub,
                flags=flags,
                host_endian=host_endian
            )
            if deadband_tracking_value is None:
                return

            self.last_dead_band[sub] = deadband_tracking_value

        # Special-case for edge-triggered modes of the sync Channel
        # Filter (before, after, first, last). Only send the first
        # update to each channel.
        sync = sub.channel_filter.sync
        if sync is not None:
            last_update = self.last_sync_edge_update[sub][sync.s].get(sync.m)
            if last_update and last_update == command:
                # This is a redundant update. Do not send.
                return

            # Stash this and then send it.
            self.last_sync_edge_update[sub][sync.s][sync.m] = command

        # This update will be put at the back of the line of updates to be
        # sent.
        #
        # If len(unexpired_updates[id]) == SUBSCRIPTION_BACKLOG_QUOTA, then the
        # command at the front of the line will be kicked out.  It is not
        # literally removed from the queue but whenever it reaches the front of
        # the line it will dropped on the floor instead of sent. This
        # effectively prioritizes sending the client "new news" instead of "old
        # news".

        # This is an OrderedBoundedSet, a set with a maxlen, containing only
        # commands for this particular subscription.

        if sub.subscriptionid not in circuit.unexpired_updates:
            circuit.unexpired_updates[sub.subscriptionid] = deque(
                maxlen=sub.db_entry.max_subscription_backlog,
            )

        circuit.unexpired_updates[sub.subscriptionid].append(command)

        def destroyed(_):
            # If events are on, we hit a high load scenario and should drop
            # this subscription entirely.
            if circuit.events_on.is_set():
                return

            # However, if events are off, the data likely just got garbage
            # collected because the client requested as much.
            # Track this as a subscription to resend when events come back
            # online, but don't store the data.
            to_resend = circuit.subscriptions_to_resend.setdefault(sub_spec, [])
            if sub not in to_resend:
                to_resend.append(sub)

        # This is a queue with the commands from _all_ subscriptions on this
        # circuit.
        try:
            await circuit.subscription_queue.put(weakref.ref(command, destroyed))
        except circuit.QueueFull:
            # We have hit the overall max for subscription backlog.
            circuit.log.warning(
                "Critically high EventAddResponse load. Dropping all "
                "queued responses on this circuit."
            )
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

    def _find_hook_methods(self, *attrs):
        """Return a dictionary of (not-None) methods given attribute names."""
        return {
            f"{name}.{attr}": getattr(instance, attr)
            for attr in attrs
            for name, instance in self.pvdb_with_fields.items()
            if getattr(instance, attr, None) is not None
        }

    @property
    def startup_methods(self):
        'Notify all ChannelData instances of the server startup'
        return self._find_hook_methods("server_startup", "server_scan")

    @property
    def shutdown_methods(self):
        'Notify all ChannelData instances of the server shutdown'
        return self._find_hook_methods("server_shutdown")

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
                except Exception:
                    self.log.exception(
                        "Client disconnected in unexpected way"
                    )
                    await circuit._on_disconnect()
                    await self.circuit_disconnected(circuit)
                    break
        except KeyboardInterrupt as ex:
            self.log.debug('TCP handler received KeyboardInterrupt')
            raise self.ServerExit() from ex
        self.log.info('Disconnected from client at %s:%d (total: %d).', *addr,
                      len(self.circuits))

    def stop(self):
        ...
