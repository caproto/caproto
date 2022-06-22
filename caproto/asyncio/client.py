# This is a channel access client implemented using asyncio.

# It builds on the abstractions used in caproto, adding transport and some
# caches for matching requests with responses.
#
# VirtualCircuit: has a caproto.VirtualCircuit, a socket, and some caches.
# Channel: has a VirtualCircuit and a caproto.ClientChannel.
# Context: has a caproto.Broadcaster, a UDP socket, a cache of
#          search results and a cache of VirtualCircuits.
#
import asyncio
import collections
import functools
import getpass
import inspect
import logging
import socket
import threading
import time
import weakref

import caproto as ca

from .. import _constants as constants
from .._utils import (ThreadsafeCounter, batch_requests,
                      get_environment_variables, safe_getsockname)
from ..client import common
from ..client.search_results import (DuplicateSearchResponse, SearchResults,
                                     UnknownSearchResponse)
from .utils import (AsyncioQueue, _CallbackExecutor, _DatagramProtocol,
                    _TaskHandler, _TransportWrapper, _UdpTransportWrapper,
                    get_running_loop)

ch_logger = logging.getLogger('caproto.ch')
search_logger = logging.getLogger('caproto.bcast.search')


class SharedBroadcaster:
    '''
    A broadcaster client which can be shared among multiple Contexts

    Parameters
    ----------
    registration_retry_time : float, optional
        The time, in seconds, between attempts made to register with the
        repeater. Default is 10.
    '''

    def __init__(self, *, registration_retry_time=10.0):
        self.environ = get_environment_variables()
        self.ca_server_port = self.environ['EPICS_CA_SERVER_PORT']

        self._registration_retry_time = registration_retry_time
        self._registration_last_sent = 0

        self.broadcaster = ca.Broadcaster(our_role=ca.CLIENT)
        self.log = self.broadcaster.log
        self.wrapped_transport = None

        self.command_queue = AsyncioQueue()
        self.receive_queue = AsyncioQueue()
        self._cleanup_event = asyncio.Event()
        self._search_now = asyncio.Event()
        self._searching_enabled = asyncio.Event()
        self._tasks = _TaskHandler()

        self.results = SearchResults()
        self.server_protocol_versions = {}  # map address to protocol version
        self.listeners = weakref.WeakSet()

        # UDP socket broadcasting to CA servers
        self.udp_sock = None
        self._essential_tasks_started = False

    def _ensure_essential_tasks_running(self):
        ""
        if self._essential_tasks_started:
            return

        self._essential_tasks_started = True
        self._tasks.create(self._broadcaster_retry_loop())
        self._tasks.create(self._broadcaster_receive_loop())
        self._tasks.create(self._check_for_unresponsive_servers_loop())

    def add_listener(self, listener):
        self.listeners.add(listener)

    async def remove_listener(self, listener):
        try:
            self.listeners.remove(listener)
        except KeyError:
            pass

        if not self.listeners:
            await self.disconnect()

    def _get_servers_from_listeners(self):
        'Map of address to VirtualCircuitManagers'
        servers = collections.defaultdict(weakref.WeakSet)

        # Map each server address to VirtualCircuitManagers connected to that
        # address, across all Contexts ("listeners").
        for listener in self.listeners:
            for (address, _), circuit_manager in listener.circuit_managers.items():
                servers[address].add(circuit_manager)

        return servers

    async def send(self, *commands):
        """
        Process a command and tranport it over the UDP socket.
        """
        bytes_to_send = self.broadcaster.send(*commands)
        tags = {'role': 'CLIENT',
                'our_address': self.broadcaster.client_address,
                'direction': '--->>>'}

        for host_tuple in ca.get_client_address_list():
            tags['their_address'] = host_tuple
            self.log.debug(
                '%d commands %dB',
                len(commands), len(bytes_to_send), extra=tags)
            try:
                await self.wrapped_transport.sendto(bytes_to_send, host_tuple)
            except OSError as ex:
                host, specified_port = host_tuple
                raise ca.CaprotoNetworkError(
                    f'{ex} while sending {len(bytes_to_send)} bytes to '
                    f'{host}:{specified_port}') from ex

    async def disconnect(self):
        'Disconnect the broadcaster and stop listening'
        self._registration_last_sent = 0
        await self._tasks.cancel_all(wait=True)
        self.log.debug('Broadcaster: Closing the UDP socket')
        self.udp_sock = None
        try:
            if self.protocol is not None:
                if self.protocol.transport is not None:
                    self.protocol.transport.close()
        except OSError:
            self.log.exception('Broadcaster transport close error')

        self.log.debug('Broadcaster disconnect complete')

    def _should_attempt_registration(self):
        'Whether or not a registration attempt should be tried'
        if self.udp_sock is None:
            return True

        if (self.broadcaster.registered or
                self._registration_retry_time is None):
            return False

        since_last_attempt = time.monotonic() - self._registration_last_sent
        if since_last_attempt < self._registration_retry_time:
            return False

        return True

    async def _create_socket(self):
        self.udp_sock = ca.bcast_socket(socket_module=socket)

        # Must bind or getsocketname() will raise on Windows.
        # See https://github.com/caproto/caproto/issues/514.
        self.udp_sock.bind(('', 0))
        await self._create_transport()

    async def _create_transport(self):
        """Create the _UdpTransportWrapper for the UDP socket"""
        loop = get_running_loop()
        transport, self.protocol = await loop.create_datagram_endpoint(
            functools.partial(_DatagramProtocol, parent=self,
                              identifier='client-search',
                              queue=self.receive_queue),
            sock=self.udp_sock)

        self.wrapped_transport = _UdpTransportWrapper(transport)
        self.broadcaster.client_address = safe_getsockname(self.udp_sock)

    async def register(self):
        "Register this client with the CA Repeater."
        self._ensure_essential_tasks_running()

        self._registration_last_sent = time.monotonic()
        if self.udp_sock is None:
            await self._create_socket()

        await self._register()
        self._searching_enabled.set()

    async def _register(self):
        commands = [self.broadcaster.register('127.0.0.1')]
        bytes_to_send = self.broadcaster.send(*commands)
        addr = (ca.get_local_address(), self.environ['EPICS_CA_REPEATER_PORT'])
        tags = {
            'role': 'CLIENT',
            'our_address': self.broadcaster.client_address,
            'direction': '--->>>',
            'their_address': addr,
        }
        tags['their_address'] = addr
        self.broadcaster.log.debug(
            '%d commands %dB', len(commands), len(bytes_to_send), extra=tags)

        try:
            await self.wrapped_transport.sendto(bytes_to_send, addr)
        except OSError as ex:
            host, specified_port = addr
            self.log.exception('%s while sending %d bytes to %s:%d',
                               ex, len(bytes_to_send), host, specified_port)

    async def _broadcaster_receive_loop(self):
        'Loop which consumes receive_queue datagrams from _DatagramProtocol.'
        queues = collections.defaultdict(list)
        while True:
            _, bytes_received, address = await self.receive_queue.async_get()
            if isinstance(bytes_received, ConnectionResetError):
                # Win32: "On a UDP-datagram socket this error indicates a
                # previous send operation resulted in an ICMP Port Unreachable
                # message."
                #
                # https://docs.microsoft.com/en-us/windows/win32/api/winsock/nf-winsock-recvfrom
                self.log.debug(
                    "Broadcaster received ConnectionResetError",
                    exc_info=bytes_received
                )
                await self._create_transport()
                continue
            if isinstance(bytes_received, Exception):
                self.log.exception('Broadcaster receive exception',
                                   exc_info=bytes_received)
                continue

            try:
                commands = self.broadcaster.recv(bytes_received, address)
            except ca.RemoteProtocolError:
                self.log.exception('Broadcaster received bad packet')
                continue

            if commands is ca.DISCONNECTED:
                break

            queues.clear()

            try:
                self.broadcaster.process_commands(commands)
                for command in commands:
                    self._process_command(address, command, queues)

                # Receive commands in 'bundles' (corresponding to the contents
                # of one UDP datagram). Match SearchResponses to their
                # SearchRequests, and put (address, (name1, name2, name3, ...))
                # into a queue. The receiving end of that queue is held by
                # Context._process_search_results.  Send the search results to
                # the Contexts that asked for them.
                for (queue, address), names in queues.items():
                    queue.put((address, names))
            except Exception:
                self.log.exception('Broadcaster receive loop evaluation')

    def _process_command(self, addr, command, queues):
        # if isinstance(command, ca.RepeaterConfirmResponse):
        #     self.registered = True
        if isinstance(command, ca.Beacon):
            address = (command.address, command.server_port)
            self.results.mark_server_alive(address, command.beacon_id)
        elif isinstance(command, ca.SearchResponse):
            address = ca.extract_address(command)
            self.server_protocol_versions[address] = command.version
            cid = command.cid
            try:
                name, queue = self.results.received_search_response(
                    cid, address)
            except UnknownSearchResponse:
                self.log.debug('Unknown search response cid=%d', cid)
            except DuplicateSearchResponse as ex:
                if len(ex.addresses) <= 1:
                    return

                name = ex.name
                accepted_address = ex.addresses[0]
                other_addresses = ', '.join(
                    '%s:%d' % addr for addr in ex.addresses[1:]
                )

                search_logger.warning(
                    "PV %s with cid %d found on multiple servers. "
                    "Accepted address is %s:%d.  Also found on %s",
                    name, cid, *accepted_address, other_addresses,
                    extra={
                        'pv': name,
                        'their_address': accepted_address,
                        'our_address': self.broadcaster.client_address,
                    },
                )
            else:
                queues[(queue, address)].append(name)

    async def search(self, results_queue, *names):
        "Generate, process, and transport search request(s)"
        # TODO: where else? is this sufficient?
        # can't do it on add_listener...
        self._ensure_essential_tasks_running()

        if self._should_attempt_registration():
            await self.register()

        # We have have already searched for these names recently.
        # Filter `pv_names` down to a subset, `needs_search`.
        use_cached_search, needs_search = self.results.split_cached_results(names)

        for address, names in use_cached_search.items():
            results_queue.put((address, names))

        self.results.search(
            *needs_search, results_queue=results_queue,
            retirement_deadline=time.monotonic() + common.SEARCH_RETIREMENT_AGE)
        self._search_now.set()

    def time_since_last_heard(self):
        """
        Map each known server address to seconds since its last message.

        The time is reset to 0 whenever we receive a TCP message related to
        user activity *or* a Beacon. Servers are expected to send Beacons at
        regular intervals. If we do not receive either a Beacon or TCP message,
        we initiate an Echo over TCP, to which the server is expected to
        promptly respond.

        Therefore, the time reported here should not much exceed
        ``EPICS_CA_CONN_TMO`` (default 30 seconds unless overriden by that
        environment variable) if the server is healthy.

        If the server fails to send a Beacon on schedule *and* fails to reply
        to an Echo, the server is assumed dead. A warning is issued, and all
        PVs are disconnected to initiate a reconnection attempt.
        """
        return {
            address: time.monotonic() - t
            for address, t in self._get_last_heard().items()
        }

    def _get_last_heard(self):
        """
        When is the last time we heard from each server, either via a Beacon or
        from TCP packets related to user activity or any circuit?

        Returns
        -------
        dict
            {addr: last_heard_time}
        """
        beacons = self.results.get_last_beacon_times()
        last_heard = {}
        for addr, circuit_managers in self._get_servers_from_listeners().items():
            # Aggregate TCP results
            last_tcp_receipt = (cm.last_tcp_receipt for cm in circuit_managers)
            last_heard[addr] = max(beacons.get(addr, 0), *last_tcp_receipt)

        return last_heard

    async def _check_for_unresponsive_servers_loop(self):
        self.log.debug('Broadcaster check for unresponsive servers loop is running.')
        checking = {}

        while True:
            now = time.monotonic()
            cutoff = now - (self.environ['EPICS_CA_CONN_TMO'] + common.BEACON_MARGIN)

            last_heard = self._get_last_heard()
            servers = self._get_servers_from_listeners()

            newly_unresponsive = {
                addr: circuit_managers
                for addr, circuit_managers in servers.items()
                if last_heard.get(addr, 0) < cutoff and addr not in checking
            }

            # self.log.debug(
            #     'Unresponsive checks: \n'
            #     '  servers: %s\n'
            #     '  last heard: %s\n'
            #     '  newly unresponsive: %s\n'
            #     '  checking: %s',
            #     servers, last_heard, newly_unresponsive, checking
            # )

            for address, circuit_managers in newly_unresponsive.items():
                # Record that we are checking on this address and set a
                # deadline for a response.
                checking[address] = now + constants.RESPONSIVENESS_TIMEOUT
                tags = {
                    'role': 'CLIENT',
                    'their_address': address,
                    'our_address': self.broadcaster.client_address,
                    'direction': '--->>>'
                }

                self.broadcaster.log.debug(
                    "Missed Beacons from %s:%d. Sending EchoRequest to "
                    "check that server is responsive.", *address, extra=tags)

                # Send on all circuits. One might be less backlogged with
                # queued commands than the others and thus able to respond
                # faster. In the majority of cases there will only be one
                # circuit per server anyway, so this is a minor distinction.
                for circuit_manager in circuit_managers:
                    try:
                        await circuit_manager.send(ca.EchoRequest())
                    except Exception:
                        # Send failed. Server is likely dead, but we'll
                        # catch that shortly; no need to handle it
                        # specially here.
                        pass

            # Check to see if any of our ongoing checks have resolved or
            # failed to resolve within the allowed response window.
            for address, deadline in list(checking.items()):
                if last_heard[address] > cutoff:
                    # It's alive!
                    checking.pop(address)
                elif deadline < now:
                    # No circuit connected to the server at this address has
                    # sent Beacons or responded to the EchoRequest. We assume
                    # it is unresponsive. The EPICS specification says the
                    # behavior is undefined at this point. We choose to
                    # disconnect all circuits from that server so that PVs can
                    # attempt to connect to a new server, such as a failover
                    # backup.
                    for circuit_manager in servers[address]:
                        if circuit_manager.connected:
                            circuit_manager.log.warning(
                                "Server at %s:%d is unresponsive. "
                                "Disconnecting circuit manager %r. PVs will "
                                "automatically begin attempting to reconnect "
                                "to a responsive server.",
                                *address, circuit_manager)
                            circuit_manager.disconnect()
                    checking.pop(address)

            await asyncio.sleep(0.5)

        self.log.debug('Broadcaster check for unresponsive servers loop has exited.')

    async def _broadcaster_retry_loop(self):
        self.log.debug('Broadcaster search-retry thread has started.')

        interval = common.MIN_RETRY_SEARCHES_INTERVAL
        time_to_check_on_retirees = (
            time.monotonic() + common.RETRY_RETIRED_SEARCHES_INTERVAL)

        while True:
            await self._searching_enabled.wait()

            last_send_time = time.monotonic()

            if last_send_time >= time_to_check_on_retirees:
                # Send everything
                threshold = None
            else:
                threshold = last_send_time

            await self._retry_unanswered_searches(
                threshold, resend_deadline=last_send_time - interval)

            wait_time = max(0, interval - (time.monotonic() - last_send_time))
            # Double the interval for the next loop.
            interval = min(2 * interval, common.MAX_RETRY_SEARCHES_INTERVAL)

            try:
                await asyncio.wait_for(self._search_now.wait(),
                                       timeout=wait_time)
            except asyncio.TimeoutError:
                ...
            else:
                # New searches have been requested. Reset the interval between
                # subseqent searches and force a check on the "retirees".
                time_to_check_on_retirees = last_send_time
                interval = common.MIN_RETRY_SEARCHES_INTERVAL

            self._search_now.clear()

        # self.log.debug('Broadcaster search-retry thread has exited.')

    async def _retry_unanswered_searches(self, threshold, resend_deadline):
        """
        Periodically (re-)send a SearchRequest for all unanswered searches.

        Notes
        -----
        Each time new searches are added, the self._search_now Event is set,
        and we reissue *all* unanswered searches.

        We then frequently retry the unanswered searches that are younger than
        SEARCH_RETIREMENT_AGE, backing off from an interval of
        MIN_RETRY_SEARCHES_INTERVAL to MAX_RETRY_SEARCHES_INTERVAL. The
        interval is reset to MIN_RETRY_SEARCHES_INTERVAL each time new searches
        are added.

        For the searches older than SEARCH_RETIREMENT_AGE, we adopt a slower
        period to minimize network traffic. We only resend every
        RETRY_RETIRED_SEARCHES_INTERVAL or, again, whenever new searches are
        added.
        """
        t = time.monotonic()

        def _construct_search_requests(items):
            for search_id, it in items:
                yield ca.SearchRequest(it.name, search_id,
                                       ca.DEFAULT_PROTOCOL_VERSION)
                it.last_sent = t

        items = self.results.items_to_retry(
            threshold, resend_deadline=resend_deadline)
        requests = _construct_search_requests(items)

        if items:
            self.log.debug('Sending %d SearchRequests', len(items))

        ver = ca.VersionRequest(0, ca.DEFAULT_PROTOCOL_VERSION)
        for batch in batch_requests(
                requests, constants.SEARCH_MAX_DATAGRAM_BYTES - len(ver)):
            await self.send(ver, *batch)


class Context:
    """
    Encapsulates the state and connections of a client.

    Parameters
    ----------
    broadcaster : SharedBroadcaster, optional
        If None is specified, a fresh one is instantiated.

    timeout : number or None, optional
        Number of seconds before a CaprotoTimeoutError is raised. This default
        can be overridden at the PV level or for any given operation. If unset,
        the default is 2 seconds. If None, never timeout. A global timeout can
        be specified via an environment variable ``CAPROTO_DEFAULT_TIMEOUT``.

    host_name : string, optional
        uses value of ``socket.gethostname()`` by default

    client_name : string, optional
        uses value of ``getpass.getuser()`` by default

    max_workers : integer, optional
        Number of worker threaders *per VirtualCircuit* for executing user
        callbacks. Default is 1. For any number of workers, workers will
        receive updates in the order which they are received from the server.
        That is, work on each update will *begin* in sequential order.
        Work-scheduling internal to the user callback is outside caproto's
        control. If the number of workers is set to greater than 1, the work on
        each update may not *finish* in a deterministic order. For example, if
        workers are writing lines into a file, the only way to guarantee that
        the lines are ordered properly is to use only one worker. If ordering
        matters for your application, think carefully before increasing this
        value from 1.
    """
    def __init__(self, broadcaster=None, *,
                 timeout=common.GLOBAL_DEFAULT_TIMEOUT,
                 host_name=None, client_name=None, max_workers=1):
        self._user_disconnected = False
        self.broadcaster = broadcaster or SharedBroadcaster()
        self.client_name = client_name or getpass.getuser()
        self.host_name = host_name or socket.gethostname()
        self.max_workers = max_workers
        self.timeout = timeout
        self.log = logging.LoggerAdapter(
            logging.getLogger('caproto.ctx'), {'role': 'CLIENT'})
        self.pv_cache_lock = threading.RLock()  # TODO: remove?
        self.circuit_managers = {}  # keyed on ((host, port), priority)
        self._lock_during_get_circuit_manager = threading.RLock()
        self.pvs = {}  # (name, priority) -> pv
        # name -> set of pvs  --- with varied priority
        self.pvs_needing_circuits = collections.defaultdict(set)
        self.broadcaster.add_listener(self)
        # an event to close and clean up the whole context
        self.subscriptions_lock = threading.RLock()
        self.subscriptions_to_activate = collections.defaultdict(set)
        self.activate_subscriptions_now = asyncio.Event()

        self._search_results_queue = AsyncioQueue()
        self._tasks = _TaskHandler()

        self._essential_tasks_started = False

    def __repr__(self):
        return (f"<Context "
                f"circuits={len(self.circuit_managers)} "
                f"pvs={len(self.pvs)} "
                f"idle={len([1 for pv in self.pvs.values() if pv._idle])}>")

    async def disconnect(self):
        self._user_disconnected = True
        try:
            # disconnect any circuits we have
            circuits = list(self.circuit_managers.values())
            total_circuits = len(circuits)
            disconnected = False
            for idx, circuit in enumerate(circuits, 1):
                if circuit.connected:
                    self.log.debug('Disconnecting circuit %d/%d: %s',
                                   idx, total_circuits, circuit)
                    await circuit.disconnect()
                    disconnected = True
            if disconnected:
                self.log.debug('All circuits disconnected')
        finally:
            # Remove from Broadcaster.
            await self.broadcaster.remove_listener(self)

        # clear any state about circuits and search results
        self.log.debug('Clearing circuit managers')
        self.circuit_managers.clear()

        await self._tasks.cancel_all()

        self.log.debug('Context disconnection complete')

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.disconnect()

    def get_circuit_manager(self, address, priority):
        """
        Return a VirtualCircuitManager for this address, priority. (It manages
        a caproto.VirtualCircuit and a TCP socket.)

        Make a new one if necessary.
        """
        with self._lock_during_get_circuit_manager:
            cm = self.circuit_managers.get((address, priority), None)
            if cm is None or cm.dead.is_set():
                version = self.broadcaster.server_protocol_versions[address]
                circuit = ca.VirtualCircuit(our_role=ca.CLIENT,
                                            address=address,
                                            priority=priority,
                                            protocol_version=version)
                cm = VirtualCircuitManager(self, circuit)
                self.circuit_managers[(address, priority)] = cm
            return cm

    async def search(self, *names):
        "Generate, process, transport a search request with the broadcaster"
        await self.broadcaster.search(self._search_results_queue, *names)

    def _ensure_essential_tasks_running(self):
        ""
        if self._essential_tasks_started:
            return

        self._essential_tasks_started = True
        self._tasks.create(self._process_search_results_loop())
        self._tasks.create(self._activate_subscriptions_loop())

    async def get_pvs(
            self, *names, priority=0, connection_state_callback=None,
            access_rights_callback=None,
            timeout=common.CONTEXT_DEFAULT_TIMEOUT):
        """
        Return a list of PV objects.

        These objects may not be connected at first. Channel creation occurs on
        a background thread.

        PVs are uniquely defined by their name and priority. If a PV with the
        same name and priority is requested twice, the same (cached) object is
        returned. Any callbacks included here are added to added alongside any
        existing ones.

        Parameters
        ----------
        *names : strings
            any number of PV names

        priority : integer
            Used by the server to triage subscription responses when under high
            load. 0 is lowest; 99 is highest.

        connection_state_callback : callable
            Expected signature: ``f(pv, state)`` where ``pv`` is the instance
            of ``PV`` whose state has changed and ``state`` is a string

        access_rights_callback : callable
            Expected signature: ``f(pv, access_rights)`` where ``pv`` is the
            instance of ``PV`` whose state has changed and ``access_rights`` is
            a member of the caproto ``AccessRights`` enum

        timeout : number or None, optional
            Number of seconds before a CaprotoTimeoutError is raised. This
            default can be overridden for any specific operation. By default,
            fall back to the default timeout set by the Context. If None, never
            timeout.
        """
        if self._user_disconnected:
            raise common.ContextDisconnectedError(
                "This Context is no longer usable.")

        self._ensure_essential_tasks_running()

        pvs = []  # list of all PV objects to return
        names_to_search = []  # subset of names that we need to search for
        for name in names:
            with self.pv_cache_lock:
                try:
                    pv = self.pvs[(name, priority)]
                except KeyError:
                    pv = PV(name, priority, self, None, None, timeout)
                    names_to_search.append(name)
                    self.pvs[(name, priority)] = pv
                    self.pvs_needing_circuits[name].add(pv)

            if connection_state_callback is not None:
                pv.connection_state_callback.add_callback(
                    connection_state_callback, run=True)
            if access_rights_callback is not None:
                pv.access_rights_callback.add_callback(
                    access_rights_callback, run=True)

            pvs.append(pv)

        # Ask the Broadcaster to search for every PV for which we do not
        # already have an instance. It might already have a cached search
        # result, but that is the concern of broadcaster.search.
        if names_to_search:
            await self.broadcaster.search(self._search_results_queue,
                                          *names_to_search)
        return pvs

    async def reconnect(self, keys):
        # We will reuse the same PV object but use a new cid.
        names = []
        pvs = []

        for key in keys:
            with self.pv_cache_lock:
                pv = self.pvs[key]
            pvs.append(pv)
            name, _ = key
            names.append(name)

            # If there is a cached search result for this name, expire it.
            self.broadcaster.results.invalidate_by_name(name)

            with self.pv_cache_lock:
                self.pvs_needing_circuits[name].add(pv)

        if names:
            await self.broadcaster.search(self._search_results_queue, *names)

    async def _activate_subscriptions(self):
        with self.subscriptions_lock:
            items = list(self.subscriptions_to_activate.items())
            self.subscriptions_to_activate.clear()

        for cm, subs in items:
            async def requests(subs):
                "Yield EventAddRequest commands."
                requests = []
                for sub in subs:
                    command = await sub.compose_command()
                    # compose_command() returns None if this Subscription
                    # is inactive (meaning there are no user callbacks
                    # attached). It will send an EventAddRequest on its own
                    # if/when the user does add any callbacks, so we can
                    # skip it here.
                    if command is not None:
                        requests.append(command)
                return requests

            for batch in batch_requests(await requests(subs),
                                        common.EVENT_ADD_BATCH_MAX_BYTES):
                try:
                    await cm.send(*batch)
                except Exception:
                    if cm.dead.is_set():
                        self.log.debug(
                            "Circuit died while we were trying to activate"
                            " subscriptions. We will keep attempting this"
                            " until it works.")
                    # When the Context creates a new circuit, we will
                    # end up here again. No big deal.
                    break

    async def _activate_subscriptions_loop(self):
        while True:
            t = time.monotonic()
            await self._activate_subscriptions()
            elapsed = time.monotonic() - t

            wait_time = max(0, (common.RESTART_SUBS_PERIOD - elapsed))

            try:
                await asyncio.wait_for(self.activate_subscriptions_now.wait(),
                                       timeout=wait_time)
            except asyncio.TimeoutError:
                ...

            self.activate_subscriptions_now.clear()

        self.log.debug('Context restart-subscriptions thread exiting')

    async def _process_search_results_loop(self):
        # Receive (address, (name1, name2, ...)). The sending side of this
        # queue is held by the SharedBroadcaster.
        self.log.debug('Context search-results processing loop has started.')
        while True:
            address, names = await self._search_results_queue.async_get()

            channels_grouped_by_circuit = collections.defaultdict(list)
            # Assign each PV a VirtualCircuitManager for managing a socket
            # and tracking circuit state, as well as a ClientChannel for
            # tracking channel state.
            for name in names:
                extra = {
                    'pv': name,
                    'their_address': address,
                    'our_address': self.broadcaster.broadcaster.client_address,
                    'direction': '--->>>',
                    'role': 'CLIENT'
                }
                search_logger.debug(
                    'Connecting %s on circuit with %s:%d', name, *address,
                    extra=extra)

                # There could be multiple PVs with the same name and different
                # priority. That is what we are looping over here. There could
                # also be NO PVs with this name that need a circuit, because we
                # could be receiving a duplicate search response (which we are
                # supposed to ignore).
                with self.pv_cache_lock:
                    pvs = self.pvs_needing_circuits.pop(name, set())

                for pv in pvs:
                    # Get (make if necessary) a VirtualCircuitManager. This
                    # is where TCP socket creation happens.
                    cm = self.get_circuit_manager(address, pv.priority)
                    circuit = cm.circuit

                    pv.circuit_manager = cm
                    # TODO: NOTE: we are not following the suggestion to use
                    # the same cid as in the search. This simplifies things
                    # between the broadcaster and Context.
                    cid = cm.circuit.new_channel_id()
                    chan = ca.ClientChannel(name, circuit, cid=cid)
                    cm.channels[cid] = chan
                    cm.pvs[cid] = pv
                    channels_grouped_by_circuit[cm].append(chan)
                    pv.circuit_ready.set()

            # Initiate channel creation with the server.
            for cm, channels in channels_grouped_by_circuit.items():
                commands = [chan.create() for chan in channels]
                try:
                    await cm.send(*commands)
                except Exception:
                    if cm.dead.is_set():
                        self.log.debug(
                            "Circuit died while we were trying to create the "
                            "channel. We will keep attempting this until it "
                            "works."
                        )
                        # When the Context creates a new circuit, we will end
                        # up here again. No big deal.
                        continue
                    raise

        self.log.debug('Context search-results processing thread has exited.')

    async def monitor(self, *pv_names, context=None, data_type='time'):
        """
        Monitor pv_names asynchronously, yielding events as they happen.

        Parameters
        ----------
        *pv_names : str
            PV names to monitor.

        data_type : {'time', 'control', 'native'}
            The subscription type.

        Yields
        -------
        event : {'subscription', 'connection'}
            The event type.

        context : str or Subscription
            For a 'connection' event, this is the PV name.  For a 'subscription'
            event, this is the `Subscription` instance.

        data : str or EventAddResponse
            For a 'subscription' event, the `EventAddResponse` holds the data and
            timestamp.  For a 'connection' event, this is one of ``{'connected',
            'disconnected'}``.
        """
        queue = AsyncioQueue()

        def value_update(sub, event_add_response):
            queue.put(('subscription', sub, event_add_response))

        def connection_state_callback(pv, state):
            queue.put(('connection', pv, state))

        channels = await self.get_pvs(
            *pv_names, connection_state_callback=connection_state_callback
        )
        subscriptions = []

        for channel in channels:
            sub = channel.subscribe(data_type=data_type)
            token = sub.add_callback(value_update)
            subscriptions.append(
                dict(
                    channel=channel,
                    sub=sub,
                    token=token,
                )
            )

        try:
            while True:
                event, context, data = await queue.async_get()
                yield event, context, data
        finally:
            for info in subscriptions.values():
                await info['sub'].remove_callback(info['token'])


class VirtualCircuitManager:
    """
    Encapsulates a VirtualCircuit, a TCP socket, and additional state

    # This object should never be instantiated directly by user code. It is used
    # internally by the Context. Its methods may be touched by user code, but
    # this is rarely necessary.
    # """

    def __init__(self, context, circuit,
                 timeout=common.GLOBAL_DEFAULT_TIMEOUT):
        self.context = context
        self.circuit = circuit  # a caproto.VirtualCircuit
        self.log = circuit.log
        self.channels = {}  # map cid to Channel
        self.pvs = {}  # map cid to PV
        self.ioids = {}  # map ioid to Channel and info dict
        self.subscriptions = {}  # map subscriptionid to Subscription
        self.transport = None
        self._ioid_counter = ThreadsafeCounter()
        self._ready = asyncio.Event()
        self._send_on_connection = []
        self._send_lock = asyncio.Lock()
        self._subscriptionid_counter = ThreadsafeCounter()
        self.command_queue = AsyncioQueue()
        self.dead = asyncio.Event()
        self.last_tcp_receipt = 0.0
        self.user_callback_executor = _CallbackExecutor(self.log)

        self._tags = {
            'their_address': self.circuit.address,
            'our_address': 'unset:0',
            'direction': '<<<---',
            'role': repr(self.circuit.our_role)
        }

        if self.circuit.states[ca.SERVER] is not ca.IDLE:
            raise ca.CaprotoRuntimeError("Cannot connect. States are {} "
                                         "".format(self.circuit.states))

        self._tasks = _TaskHandler()
        self._tasks.create(self._connection_ready_hook())
        self._tasks.create(self._connect(timeout=timeout))

    async def _transport_receive_loop(self, transport):
        while True:
            try:
                bytes_received = await transport.recv()
            except ca.CaprotoNetworkError:
                bytes_received = b''

            self.last_tcp_receipt = time.monotonic()
            commands, _ = self.circuit.recv(bytes_received)
            for c in commands:
                self.command_queue.put(c)

            if not bytes_received:
                break

    async def _connect(self, timeout):
        """Start the connection and spawn tasks."""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(*self.circuit.address),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            host, port = self.circuit.address
            raise ca.CaprotoTimeoutError(
                f"Circuit with server at {host}:{port} did not connect within "
                f"{float(timeout):.3}-second timeout."
            )

        self.transport = _TransportWrapper(reader, writer)
        self._tasks.create(self._transport_receive_loop(self.transport))

        self.circuit.our_address = self.transport.getsockname()

        # This dict is passed to the loggers.
        self._tags = {'their_address': self.circuit.address,
                      'our_address': self.circuit.our_address,
                      'direction': '<<<---',
                      'role': repr(self.circuit.our_role)}

        self.log.debug(
            'Connected to circuit with address %s:%d',
            *self.circuit.address,
            extra=self._tags)

        await self.send(
            ca.VersionRequest(self.circuit.priority, ca.DEFAULT_PROTOCOL_VERSION),
            ca.HostNameRequest(self.context.host_name),
            ca.ClientNameRequest(self.context.client_name),
            extra=self._tags)

        # Ensure we don't get any commands back before sending the above, lest
        # we confuse the state machine:
        self._tasks.create(self._command_queue_loop())

        # Old versions of the protocol do not send a VersionResponse at TCP
        # connection time, so set this Event manually rather than waiting for
        # it to be set by receipt of a VersionResponse.
        if self.server_protocol_version < 12:
            self._ready.set()

        try:
            await asyncio.wait_for(self._ready.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            host, port = self.circuit.address
            raise ca.CaprotoTimeoutError(
                f"Circuit with server at {host}:{port} did not connect within "
                f"{float(timeout):.3}-second timeout.") from None

    @property
    def server_protocol_version(self):
        return self.context.broadcaster.server_protocol_versions[
            self.circuit.address]

    def __repr__(self):
        return (f"<VirtualCircuitManager circuit={self.circuit} "
                f"pvs={len(self.pvs)} ioids={len(self.ioids)} "
                f"subscriptions={len(self.subscriptions)} "
                f"server_protocol_version={self.server_protocol_version}>")

    @property
    def connected(self):
        return self.circuit.states[ca.CLIENT] is ca.CONNECTED

    async def _connection_ready_hook(self):
        await self._ready.wait()

        to_send = list(self._send_on_connection)
        self._send_on_connection.clear()

        for commands, extra in to_send:
            await self.send(*commands, extra=extra)

    async def send(self, *commands, extra=None):
        if self.dead.is_set():
            raise common.DeadCircuitError()

        if self.transport is None:
            self._send_on_connection.append((commands, extra))
            return

        # Turn the crank: inform the VirtualCircuit that these commands will be
        # send, and convert them to buffers.
        buffers_to_send = self.circuit.send(*commands, extra=extra)
        async with self._send_lock:
            for buff in buffers_to_send:
                self.transport.writer.write(bytes(buff))

            await self.transport.writer.drain()

    async def events_off(self):
        """
        Suspend updates to all subscriptions on this circuit.

        This may be useful if the server produces updates faster than the
        client can processs them.
        """
        await self.send(ca.EventsOffRequest())

    async def events_on(self):
        """
        Reactive updates to all subscriptions on this circuit.
        """
        await self.send(ca.EventsOnRequest())

    async def _process_command(self, command):
        try:
            self.circuit.process_command(command)
        except ca.CaprotoError as ex:
            if hasattr(ex, 'channel'):
                channel = ex.channel
                self.log.warning('Invalid command %s for Channel %s in state %s',
                                 command, channel, channel.states, exc_info=ex)
                # channel exceptions are not fatal
                return

            self.log.exception(
                'Invalid command %s for VirtualCircuit %s in state %s',
                command, self, self.circuit.states)
            # circuit exceptions are fatal; exit the loop
            await self.disconnect()
            return

        tags = self._tags
        if command is ca.DISCONNECTED:
            await self._disconnected()
        elif isinstance(command, (ca.VersionResponse,)):
            assert self.connected  # double-check that the state machine agrees
            self._ready.set()
        elif isinstance(command, (ca.ReadNotifyResponse,
                                  ca.ReadResponse,
                                  ca.WriteNotifyResponse)):
            ioid_info = self.ioids.pop(command.ioid)
            deadline = ioid_info['deadline']
            pv = ioid_info['pv']
            tags = tags.copy()
            tags['pv'] = pv.name
            if deadline is not None and time.monotonic() > deadline:
                self.log.warning("Ignoring late response with ioid=%d regarding "
                                 "PV named %s because "
                                 "it arrived %.3f seconds after the deadline "
                                 "specified by the timeout.", command.ioid,
                                 pv.name, time.monotonic() - deadline)
                return

            event = ioid_info.get('event')
            if event is not None:
                # If PV.read() or PV.write() are waiting on this response,
                # they hold a reference to ioid_info. We will use that to
                # provide the response to them and then set the Event that they
                # are waiting on.
                ioid_info['response'] = command
                event.set()
            callback = ioid_info.get('callback')
            if callback is not None:
                self.user_callback_executor.submit(callback, command)

        elif isinstance(command, ca.EventAddResponse):
            try:
                sub = self.subscriptions[command.subscriptionid]
            except KeyError:
                # This subscription has been removed. We assume that this
                # response was in flight before the server processed our
                # unsubscription.
                pass
            else:
                # This method submits jobs to the Contexts's
                # ThreadPoolExecutor for user callbacks.
                sub.process(command)
                tags = tags.copy()
                tags['pv'] = sub.pv.name
        elif isinstance(command, ca.AccessRightsResponse):
            pv = self.pvs[command.cid]
            pv.access_rights_changed(command.access_rights)
            tags = tags.copy()
            tags['pv'] = pv.name
        elif isinstance(command, ca.EventCancelResponse):
            # TODO Any way to add the pv name to tags here?
            ...
        elif isinstance(command, ca.CreateChanResponse):
            pv = self.pvs[command.cid]
            chan = self.channels[command.cid]
            self._search_results.mark_channel_created(
                pv.name, self.circuit.address)

            with pv.component_lock:
                pv.channel = chan
                pv.channel_ready.set()
            pv.connection_state_changed('connected', chan)
            tags = tags.copy()
            tags['pv'] = pv.name
        elif isinstance(command, (ca.ServerDisconnResponse,
                                  ca.ClearChannelResponse)):
            pv = self.pvs[command.cid]
            pv.connection_state_changed('disconnected', None)
            tags = tags.copy()
            tags['pv'] = pv.name
            # NOTE: pv remains valid until server goes down
            # TODO: or do we not assume the server will remove it?
            # self._search_results.mark_channel_disconnected(
            #     pv.name, self.circuit.address)
        elif isinstance(command, ca.EchoResponse):
            # The important effect here is that it will have updated
            # self.last_tcp_receipt when the bytes flowed through
            # self.received.
            ...

        if not isinstance(command, ca.Message):
            return

        # Log each message with the above-gathered tags
        tags['bytesize'] = len(command)
        self.log.debug("%r", command, extra=tags)

    async def _command_queue_loop(self):
        command = None
        while True:
            try:
                command = await self.command_queue.async_get()
                await self._process_command(command)
                if command is ca.DISCONNECTED:
                    self.log.debug('Command queue loop exiting')
                    break
            except asyncio.CancelledError:
                break
            except Exception:
                self.log.exception('Circuit command evaluation failed: %r',
                                   command)
                continue

            # async with self.new_command_condition:
            #     self.new_command_condition.notify_all()

    @property
    def _search_results(self):
        return self.context.broadcaster.results

    async def _disconnected(self, *, reconnect=True):
        # Ensure that this method is idempotent.
        if self.dead.is_set():
            return
        tags = {'their_address': self.circuit.address}
        self.log.debug('Virtual circuit with address %s:%d has disconnected.',
                       *self.circuit.address, extra=tags)
        # Update circuit state. This will be reflected on all PVs, which
        # continue to hold a reference to this disconnected circuit.
        self.circuit.disconnect()
        for pv in self.pvs.values():
            pv.channel_ready.clear()
            pv.circuit_ready.clear()
        self.dead.set()
        for ioid_info in self.ioids.values():
            # Un-block any calls to PV.read() or PV.write() that are waiting on
            # responses that we now know will never arrive. They will check on
            # circuit health and raise appropriately.
            event = ioid_info.get('event')
            if event is not None:
                event.set()

        # Remove server + channels marked as created from the search results:
        self._search_results.mark_server_disconnected(self.circuit.address)

        for pv in self.pvs.values():
            pv.connection_state_changed('disconnected', None)
        # Remove VirtualCircuitManager from Context.
        # This will cause all future calls to Context.get_circuit_manager()
        # to create a fresh VirtualCiruit and VirtualCircuitManager.
        self.context.circuit_managers.pop(self.circuit.address, None)

        if self.transport is not None:
            try:
                self.transport.close()
            except OSError:
                self.log.exception(
                    'VirtualCircuitManager transport close error'
                )
            finally:
                self.transport = None

        tags = {'their_address': self.circuit.address}
        if reconnect:
            # Kick off attempt to reconnect all PVs via fresh circuit(s).
            self.log.debug(
                'Kicking off reconnection attempts for %d PVs disconnected '
                'from %s:%d....',
                len(self.channels), *self.circuit.address, extra=tags)
            await self.context.reconnect(
                ((chan.name, chan.circuit.priority)
                 for chan in self.channels.values())
            )
        else:
            self.log.debug('Not attempting reconnection', extra=tags)

    async def disconnect(self):
        await self._disconnected(reconnect=False)

        self.log.debug("Shutting down ThreadPoolExecutor for user callbacks",
                       extra={'their_address': self.circuit.address})
        await self.user_callback_executor.shutdown()

        if self.transport is None:
            return

        self.log.debug('Circuit manager disconnected by user')


def ensure_connected(func):
    '''
    Ensure connected decorator.

    Parameters
    ----------
    func : coroutine
    '''

    assert inspect.iscoroutinefunction(func)

    @functools.wraps(func)
    async def inner(self, *args, **kwargs):
        if isinstance(self, PV):
            pv = self
        elif isinstance(self, Subscription):
            pv = self.pv
        else:
            raise ca.CaprotoTypeError(
                "ensure_connected is intended to decorate "
                "methods of PV and Subscription.")

        # timeout may be decremented during disconnection-retry loops below.
        # Keep a copy of the original 'raw_timeout' for use in error messages.
        raw_timeout = timeout = kwargs.get('timeout', pv.timeout)
        if timeout is not None:
            deadline = time.monotonic() + timeout

        async with pv._in_use:
            # If needed, reconnect. Do this inside the lock so that we don't
            # try to do this twice. (No other threads that need this lock
            # can proceed until the connection is ready anyway!)
            if pv._idle:
                # The Context should have been maintaining a working circuit
                # for us while this was idle. We just need to re-create the
                # Channel.
                try:
                    await asyncio.wait_for(pv.circuit_ready.wait(),
                                           timeout=timeout)
                except asyncio.TimeoutError:
                    raise ca.CaprotoTimeoutError(
                        f"{pv} could not connect within "
                        f"{float(raw_timeout):.3}-second timeout.") from None

                with pv.component_lock:
                    cm = pv.circuit_manager
                    cid = cm.circuit.new_channel_id()
                    chan = ca.ClientChannel(pv.name, cm.circuit, cid=cid)
                    cm.channels[cid] = chan
                    cm.pvs[cid] = pv
                    await pv.circuit_manager.send(chan.create(),
                                                  extra={'pv': pv.name})
                    self._idle = False
            # increment the usage at the very end in case anything
            # goes wrong in the block of code above this.
            pv._usages += 1

        try:
            for _ in range(common.CIRCUIT_DEATH_ATTEMPTS):
                # On each iteration, subtract the time we already spent on any
                # previous attempts.
                if timeout is not None:
                    timeout = deadline - time.monotonic()

                try:
                    await asyncio.wait_for(pv.channel_ready.wait(),
                                           timeout=timeout)
                except asyncio.TimeoutError:
                    raise ca.CaprotoTimeoutError(
                        f"{pv} could not connect within "
                        f"{float(raw_timeout):.3}-second timeout.") from None

                if timeout is not None:
                    timeout = deadline - time.monotonic()
                    kwargs['timeout'] = timeout

                cm = pv.circuit_manager
                try:
                    return await func(self, *args, **kwargs)
                except common.DeadCircuitError:
                    # Something in func tried operate on the circuit after
                    # it died. The context will automatically build us a
                    # new circuit. Try again.
                    self.log.debug('Caught DeadCircuitError. '
                                   'Retrying %s.', func.__name__)
                    continue
                except (TimeoutError, asyncio.TimeoutError):
                    # The circuit may have died after func was done calling
                    # methods on it but before we received some response we
                    # were expecting. The context will automatically build
                    # us a new circuit. Try again.
                    if cm.dead.is_set():
                        self.log.debug('Caught TimeoutError due to dead '
                                       'circuit. '
                                       'Retrying %s.', func.__name__)
                        continue
                    # The circuit is fine -- this is a real error.
                    raise

        finally:
            async with pv._in_use:
                pv._usages -= 1
                pv._in_use.notify_all()

    return inner


class PV:
    """
    Represents one PV, specified by a name and priority.

    This object may exist prior to connection and persists across any
    subsequent re-connections.

    This object should never be instantiated directly by user code; rather it
    should be created by calling the ``get_pvs`` method on a ``Context``
    object.
    """

    def __init__(self, name, priority, context, connection_state_callback,
                 access_rights_callback, timeout):
        """
        These must be instantiated by a Context, never directly.
        """
        self.name = name
        self.priority = priority
        self.context = context
        self.access_rights = None  # will be overwritten with AccessRights
        self.log = logging.LoggerAdapter(ch_logger, {'pv': self.name, 'role': 'CLIENT'})
        # Use this lock whenever we touch circuit_manager or channel.
        self.component_lock = threading.RLock()
        self.circuit_ready = asyncio.Event()
        self.channel_ready = asyncio.Event()
        self.connection_state_callback = CallbackHandler(self)
        self.access_rights_callback = CallbackHandler(self)
        self._timeout = timeout

        if connection_state_callback is not None:
            self.connection_state_callback.add_callback(
                connection_state_callback, run=True)

        if access_rights_callback is not None:
            self.access_rights_callback.add_callback(
                access_rights_callback, run=True)

        self._circuit_manager = None
        self._channel = None
        self.subscriptions = {}
        self._idle = False
        self._in_use = asyncio.Condition()
        self._usages = 0

    @property
    def timeout(self):
        """
        Effective default timeout.

        Valid values are:
        * CONTEXT_DEFAULT_TIMEOUT (fall back to Context.timeout)
        * a floating-point number
        * None (never timeout)
        """
        if self._timeout is common.CONTEXT_DEFAULT_TIMEOUT:
            return self.context.timeout
        return self._timeout

    @timeout.setter
    def timeout(self, val):
        self._timeout = val

    @property
    def circuit_manager(self):
        return self._circuit_manager

    @circuit_manager.setter
    def circuit_manager(self, val):
        with self.component_lock:
            self._circuit_manager = val

    @property
    def channel(self):
        return self._channel

    @channel.setter
    def channel(self, val):
        with self.component_lock:
            self._channel = val

    def access_rights_changed(self, rights):
        self.access_rights = rights
        self.access_rights_callback.process(self, rights)

    def connection_state_changed(self, state, channel):
        self.log.info('connection state changed to %s.', state)
        self.connection_state_callback.process(self, state)
        if state == 'disconnected':
            for sub in self.subscriptions.values():
                with sub.callback_lock:
                    if sub.callbacks:
                        sub.needs_reactivation = True
        if state == 'connected':
            cm = self.circuit_manager
            ctx = cm.context
            with ctx.subscriptions_lock:
                for sub in self.subscriptions.values():
                    with sub.callback_lock:
                        if sub.needs_reactivation:
                            ctx.subscriptions_to_activate[cm].add(sub)
                            sub.needs_reactivation = False

    def __repr__(self):
        if self._idle:
            state = "(idle)"
        elif self.circuit_manager is None or self.circuit_manager.dead.is_set():
            state = "(searching....)"
        else:
            state = (f"address={self.circuit_manager.circuit.address}, "
                     f"circuit_state="
                     f"{self.circuit_manager.circuit.states[ca.CLIENT]}")
            if self.connected:
                state += f", channel_state={self.channel.states[ca.CLIENT]}"
            else:
                state += " (creating...)"
        return f"<PV name={self.name!r} priority={self.priority} {state}>"

    @property
    def connected(self):
        channel = self.channel
        if channel is None:
            return False
        return channel.states[ca.CLIENT] is ca.CONNECTED

    async def wait_for_search(self, *, timeout=common.PV_DEFAULT_TIMEOUT):
        """
        Wait for this PV to be found.

        This does not wait for the PV's Channel to be created; it merely waits
        for an address (and a VirtualCircuit) to be assigned.

        Parameters
        ----------
        timeout : number or None, optional
            Seconds to wait before a CaprotoTimeoutError is raised. Default is
            ``PV.timeout``, which falls back to Context.timeout if not set. If
            None, never timeout.
        """
        if timeout is common.PV_DEFAULT_TIMEOUT:
            timeout = self.timeout

        try:
            await asyncio.wait_for(self.circuit_ready.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            raise ca.CaprotoTimeoutError(
                "No servers responded to a search for a channel named {!r} "
                "within {:.3}-second timeout.".format(self.name,
                                                      float(timeout)))

    @ensure_connected
    async def wait_for_connection(self, *, timeout=common.PV_DEFAULT_TIMEOUT):
        """
        Wait for this PV to be connected.

        Parameters
        ----------
        timeout : number or None, optional
            Seconds to wait before a CaprotoTimeoutError is raised. Default is
            ``PV.timeout``, which falls back to ``PV.context.timeout`` if not
            set. If None, never timeout.
        """
        # NOTE: the logic happens in the wrapper.

    async def go_idle(self):
        """Request to clear this Channel to reduce load on client and server.

        A new Channel will be automatically, silently created the next time any
        method requiring a connection is called. Thus, this saves some memory
        in exchange for making the next request a bit slower, as it has to
        redo the handshake with the server first.

        If there are any subscriptions with callbacks, this request will be
        ignored. If the PV is in the process of connecting, this request will
        be ignored.  If there are any actions in progress (read, write) this
        request will be processed when they are complete.
        """
        for sub in self.subscriptions.values():
            if sub.callbacks:
                return
        async with self._in_use:
            if not self.channel_ready.is_set():
                return
            # Wait until no other methods that employ @self.ensure_connected
            # are in process.
            await self._in_use.wait_for(lambda: self._usages == 0)
            # No other threads are using the connection, and we are holding the
            # self._in_use Condition's lock, so we can safely close the
            # connection. The next thread to acquire the lock will re-connect
            # after it acquires the lock.
            try:
                self.channel_ready.clear()
                await self.circuit_manager.send(self.channel.clear(),
                                                extra={'pv': self.name})
            except OSError:
                # the socket is dead-dead, do nothing
                ...
            self._idle = True

    @ensure_connected
    async def read(self, *, wait=True, callback=None,
                   timeout=common.PV_DEFAULT_TIMEOUT, data_type=None,
                   data_count=None, notify=True):
        """Request a fresh reading.

        Can do one or both of:
        - Block while waiting for the response, and return it.
        - Pass the response to callback, with or without blocking.

        Parameters
        ----------
        wait : boolean
            If True (default) block until a matching response is
            received from the server. Raises CaprotoTimeoutError if that
            response is not received within the time specified by the `timeout`
            parameter.
        callback : callable or None
            Called with the response as its argument when received.
        timeout : number or None, optional
            Seconds to wait before a CaprotoTimeoutError is raised. Default is
            ``PV.timeout``, which falls back to ``PV.context.timeout`` if not
            set. If None, never timeout.
        data_type : {'native', 'status', 'time', 'graphic', 'control'} or ChannelType or int ID, optional
            Request specific data type or a class of data types, matched to the
            channel's native data type. Default is Channel's native data type.
        data_count : integer, optional
            Requested number of values. Default is the channel's native data
            count.
        notify: boolean, optional
            Send a ``ReadNotifyRequest`` instead of a ``ReadRequest``. True by
            default.
        """
        if timeout is common.PV_DEFAULT_TIMEOUT:
            timeout = self.timeout
        cm, chan = self._circuit_manager, self._channel
        ioid = cm._ioid_counter()
        command = chan.read(ioid=ioid, data_type=data_type,
                            data_count=data_count, notify=notify)
        # Stash the ioid to match the response to the request.

        event = asyncio.Event()
        ioid_info = dict(event=event, pv=self, request=command)
        if callback is not None:
            ioid_info['callback'] = callback

        cm.ioids[ioid] = ioid_info

        deadline = time.monotonic() + timeout if timeout is not None else None
        ioid_info['deadline'] = deadline
        await cm.send(command, extra={'pv': self.name})
        if not wait:
            return

        # The circuit_manager will put a reference to the response into
        # ioid_info and then set event.
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            host, port = cm.circuit.address
            raise ca.CaprotoTimeoutError(
                f"Server at {host}:{port} did "
                f"not respond to attempt to read channel named "
                f"{self.name!r} within {float(timeout):.3}-second timeout. "
                f"The ioid of the expected response is {ioid}."
            )

        if cm.dead.is_set():
            # This circuit has died sometime during this function call.
            # The exception raised here will be caught by
            # @ensure_connected, which will retry the function call a
            # in hopes of getting a working circuit until our `timeout` has
            # been used up.
            raise common.DeadCircuitError()
        return ioid_info['response']

    @ensure_connected
    async def write(self, data, *, wait=True, callback=None,
                    timeout=common.PV_DEFAULT_TIMEOUT, notify=None,
                    data_type=None, data_count=None):
        """
        Write a new value. Optionally, request confirmation from the server.

        Can do one or both of:
        - Block while waiting for the response, and return it.
        - Pass the response to callback, with or without blocking.

        Parameters
        ----------
        data : str, int, or float or any Iterable of these
            Value(s) to write.
        wait : boolean
            If True (default) block until a matching WriteNotifyResponse is
            received from the server. Raises CaprotoTimeoutError if that
            response is not received within the time specified by the `timeout`
            parameter.
        callback : callable or None
            Called with the WriteNotifyResponse as its argument when received.
        timeout : number or None, optional
            Seconds to wait before a CaprotoTimeoutError is raised. Default is
            ``PV.timeout``, which falls back to ``PV.context.timeout`` if not
            set. If None, never timeout.
        notify : boolean or None
            If None (default), set to True if wait=True or callback is set.
            Can be manually set to True or False. Will raise ValueError if set
            to False while wait=True or callback is set.
        data_type : {'native', 'status', 'time', 'graphic', 'control'} or ChannelType or int ID, optional
            Write specific data type or a class of data types, matched to the
            channel's native data type. Default is Channel's native data type.
        data_count : integer, optional
            Requested number of values. Default is the channel's native data
            count.
        """
        if timeout is common.PV_DEFAULT_TIMEOUT:
            timeout = self.timeout
        cm, chan = self._circuit_manager, self._channel
        if notify is None:
            notify = (wait or callback is not None)
        ioid = cm._ioid_counter()
        command = chan.write(data, ioid=ioid, notify=notify,
                             data_type=data_type, data_count=data_count)
        if notify:
            event = asyncio.Event()
            ioid_info = dict(event=event, pv=self, request=command)
            if callback is not None:
                ioid_info['callback'] = callback

            cm.ioids[ioid] = ioid_info

            deadline = time.monotonic() + timeout if timeout is not None else None
            ioid_info['deadline'] = deadline
            # do not need to lock this, locking happens in circuit command
        else:
            if wait or callback is not None:
                raise ca.CaprotoValueError(
                    "Must set notify=True in order to use `wait` or `callback`"
                    " because, without a notification of 'put-completion' from"
                    " the server, there is nothing to wait on or to trigger a"
                    " callback.")
        await cm.send(command, extra={'pv': self.name})

        if not wait:
            return

        # The circuit_manager will put a reference to the response into
        # ioid_info and then set event.
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            if cm.dead.is_set():
                # This circuit has died sometime during this function call.
                # The exception raised here will be caught by
                # @ensure_connected, which will retry the function call a
                # in hopes of getting a working circuit until our `timeout` has
                # been used up.
                raise common.DeadCircuitError()
            host, port = cm.circuit.address
            raise ca.CaprotoTimeoutError(
                f"Server at {host}:{port} did "
                f"not respond to attempt to write to channel named "
                f"{self.name!r} within {float(timeout):.3}-second timeout. "
                f"The ioid of the expected response is {ioid}."
            )
        return ioid_info['response']

    def subscribe(self, data_type=None, data_count=None, low=0.0, high=0.0,
                  to=0.0, mask=None):
        """
        Start a new subscription to which user callback may be added.

        Parameters
        ----------
        data_type : {'native', 'status', 'time', 'graphic', 'control'} or ChannelType or int ID, optional
            Request specific data type or a class of data types, matched to the
            channel's native data type. Default is Channel's native data type.
        data_count : integer, optional
            Requested number of values. Default is the channel's native data
            count.
        low, high, to : float, optional
            deprecated by Channel Access, not yet implemented by caproto
        mask :  SubscriptionType, optional
            Subscribe to selective updates.

        Returns
        -------
        subscription : Subscription

        Examples
        --------

        Define a subscription.

        >>> sub = pv.subscribe()

        Add a user callback. The subscription will be transparently activated
        (i.e. an ``EventAddRequest`` will be sent) when the first user callback
        is added.

        >>> sub.add_callback(my_func)

        Multiple callbacks may be added to the same subscription.

        >>> sub.add_callback(another_func)

        See the docstring for :class:`Subscription` for more.
        """
        # A Subscription is uniquely identified by the Signature created by its
        # args and kwargs.
        bound = common.SUBSCRIBE_SIG.bind(data_type, data_count, low, high, to, mask)
        key = tuple(bound.arguments.items())
        try:
            sub = self.subscriptions[key]
        except KeyError:
            sub = Subscription(self,
                               data_type, data_count,
                               low, high, to, mask)
            self.subscriptions[key] = sub
        # The actual EPICS messages will not be sent until the user adds
        # callbacks via sub.add_callback(user_func).
        return sub

    async def unsubscribe_all(self):
        "Clear all subscriptions. (Remove all user callbacks from them.)"
        for sub in self.subscriptions.values():
            await sub.clear()

    # @ensure_connected
    def time_since_last_heard(self, timeout=common.PV_DEFAULT_TIMEOUT):
        """
        Seconds since last message from the server that provides this channel.

        The time is reset to 0 whenever we receive a TCP message related to
        user activity *or* a Beacon. Servers are expected to send Beacons at
        regular intervals. If we do not receive either a Beacon or TCP message,
        we initiate an Echo over TCP, to which the server is expected to
        promptly respond.

        Therefore, the time reported here should not much exceed
        ``EPICS_CA_CONN_TMO`` (default 30 seconds unless overriden by that
        environment variable) if the server is healthy.

        If the server fails to send a Beacon on schedule *and* fails to reply to
        an Echo, the server is assumed dead. A warning is issued, and all PVs
        are disconnected to initiate a reconnection attempt.

        Parameters
        ----------
        timeout : number or None, optional
            Seconds to wait before a CaprotoTimeoutError is raised. Default is
            ``PV.timeout``, which falls back to ``PV.context.timeout`` if not
            set. If None, never timeout.
        """
        address = self.circuit_manager.circuit.address
        return self.context.broadcaster.time_since_last_heard()[address]


class CallbackHandler:
    def __init__(self, pv):
        # NOTE: not a WeakValueDictionary or WeakSet as PV is unhashable...
        self.callbacks = {}
        self.pv = pv
        self._callback_id = 0
        self.callback_lock = threading.RLock()
        self._last_call_values = None

    def add_callback(self, func, run=False):
        def removed(_):
            self.remove_callback(cb_id)  # defined below inside the lock

        if inspect.ismethod(func):
            ref = weakref.WeakMethod(func, removed)
        else:
            # TODO: strong reference to non-instance methods?
            ref = weakref.ref(func, removed)

        with self.callback_lock:
            cb_id = self._callback_id
            self._callback_id += 1
            self.callbacks[cb_id] = ref

        if run and self._last_call_values is not None:
            with self.callback_lock:
                args, kwargs = self._last_call_values
            self.process(*args, **kwargs)
        return cb_id

    def remove_callback(self, token):
        # TODO: async confusion:
        #       sync CallbackHandler.remove_callback
        #       async Subscription.remove_callback
        with self.callback_lock:
            self.callbacks.pop(token, None)

    def process(self, *args, **kwargs):
        """
        This is a fast operation that submits jobs to the Context's
        ThreadPoolExecutor and then returns.
        """
        to_remove = []
        with self.callback_lock:
            callbacks = list(self.callbacks.items())
            self._last_call_values = (args, kwargs)

        for cb_id, ref in callbacks:
            callback = ref()
            if callback is None:
                to_remove.append(cb_id)
                continue

            self.pv.circuit_manager.user_callback_executor.submit(
                callback, *args, **kwargs)

        with self.callback_lock:
            for remove_id in to_remove:
                self.callbacks.pop(remove_id, None)


class Subscription(CallbackHandler):
    """
    Represents one subscription, specified by a PV and configurational parameters

    It may fan out to zero, one, or multiple user-registered callback
    functions.

    This object should never be instantiated directly by user code; rather
    it should be made by calling the ``subscribe()`` method on a ``PV`` object.
    """
    def __init__(self, pv, data_type, data_count, low, high, to, mask):
        super().__init__(pv)
        # Stash everything, but do not send any EPICS messages until the first
        # user callback is attached.
        self.data_type = data_type
        self.data_count = data_count
        self.low = low
        self.high = high
        self.to = to
        self.mask = mask
        self.subscriptionid = None
        self.most_recent_response = None
        self.needs_reactivation = False
        # This is related to back-compat for user callbacks that have the old
        # signature, f(response).
        self.__wrapper_weakrefs = set()

    @property
    def log(self):
        return self.pv.log

    def __repr__(self):
        return f"<Subscription to {self.pv.name!r}, id={self.subscriptionid}>"

    async def __aiter__(self):
        queue = AsyncioQueue()

        async def iter_callback(sub, value):
            await queue.async_put(value)

        sid = self.add_callback(iter_callback)
        try:
            while True:
                item = await queue.async_get()
                yield item
        finally:
            await self.remove_callback(sid)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.clear()

    def _subscribe(self, timeout=common.PV_DEFAULT_TIMEOUT):
        """This is called automatically after the first callback is added.
        """
        cm = self.pv.circuit_manager
        if cm is None:
            # We are currently disconnected (perhaps have not yet connected).
            # When the PV connects, this subscription will be added.
            with self.callback_lock:
                self.needs_reactivation = True
        else:
            # We are (or very recently were) connected. In the rare event
            # where cm goes dead in the interim, subscription will be retried
            # by the activation loop.
            ctx = cm.context
            with ctx.subscriptions_lock:
                ctx.subscriptions_to_activate[cm].add(self)
            ctx.activate_subscriptions_now.set()

    @ensure_connected
    async def compose_command(self, timeout=common.PV_DEFAULT_TIMEOUT):
        "This is used by the Context to re-subscribe in bulk after dropping."
        # TODO: compose_command async due to ensure_connected?
        with self.callback_lock:
            if not self.callbacks:
                return None
            cm, chan = self.pv._circuit_manager, self.pv._channel
            subscriptionid = cm._subscriptionid_counter()
            command = chan.subscribe(data_type=self.data_type,
                                     data_count=self.data_count, low=self.low,
                                     high=self.high, to=self.to,
                                     mask=self.mask,
                                     subscriptionid=subscriptionid)
            subscriptionid = command.subscriptionid
            self.subscriptionid = subscriptionid
        # The circuit_manager needs to know the subscriptionid so that it can
        # route responses to this request.
        cm.subscriptions[subscriptionid] = self
        return command

    async def clear(self):
        """
        Remove all callbacks.
        """
        with self.callback_lock:
            for cb_id in list(self.callbacks):
                await self.remove_callback(cb_id)
        # Once self.callbacks is empty, self.remove_callback calls
        # self._unsubscribe for us.

    async def _unsubscribe(self):
        """
        This is automatically called if the number of callbacks goes to 0.
        """
        with self.callback_lock:
            if self.subscriptionid is None:
                # Already unsubscribed.
                return
            subscriptionid = self.subscriptionid
            self.subscriptionid = None
            self.most_recent_response = None

        self.pv.circuit_manager.subscriptions.pop(subscriptionid, None)
        chan = self.pv.channel
        if chan and chan.states[ca.CLIENT] is ca.CONNECTED:
            try:
                command = self.pv.channel.unsubscribe(subscriptionid)
            except ca.CaprotoKeyError:
                pass
            except ca.CaprotoValueError:
                self.log.exception('TODO')
            else:
                await self.pv.circuit_manager.send(command,
                                                   extra={'pv': self.pv.name})

    def process(self, command):
        # TODO here i think we can decouple PV update rates and callback
        # handling rates, if desirable, to not bog down performance.
        # As implemented below, updates are blocking further messages from
        # the CA servers from processing. (-> ThreadPool, etc.)
        pv = self.pv
        super().process(self, command)
        self.log.debug("%r: %r", pv.name, command)
        self.most_recent_response = command

    def add_callback(self, func):
        """
        Add a callback to receive responses.

        Parameters
        ----------
        func : callable
            Expected signature: ``func(sub, response)``.

            The signature ``func(response)`` is also supported for
            backward-compatibility but will issue warnings. Support will be
            removed in a future release of caproto.

        Returns
        -------
        token : int
            Integer token that can be passed to :meth:`remove_callback`.

        .. versionchanged:: 0.5.0

           Changed the expected signature of ``func`` from ``func(response)``
           to ``func(sub, response)``.
        """
        # Handle func with signature func(response) for back-compat.
        with self.callback_lock:
            was_empty = not self.callbacks
            cb_id = super().add_callback(func)
            most_recent_response = self.most_recent_response
        if was_empty:
            # This is the first callback. Set up a subscription, which
            # should elicit a response from the server soon giving the
            # current value to this func (and any other funcs added in the
            # mean time).
            self._subscribe()
        else:
            # This callback is piggy-backing onto an existing subscription.
            # Send it the most recent response, unless we are still waiting
            # for that first response from the server.
            if most_recent_response is not None:
                circuit_manager = self.pv.circuit_manager
                if circuit_manager is not None:
                    circuit_manager.user_callback_executor.submit(
                        func, self, most_recent_response)

        return cb_id

    async def remove_callback(self, token):
        """
        Remove callback using token that was returned by :meth:`add_callback`.

        Parameters
        ----------

        token : integer
            Token returned by :meth:`add_callback`.
        """
        with self.callback_lock:
            super().remove_callback(token)
            if not self.callbacks:
                # Go dormant.
                await self._unsubscribe()
                self.most_recent_response = None
                self.needs_reactivation = False
