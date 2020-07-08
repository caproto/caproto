import collections
import functools
import logging
import random
import threading
import time
import weakref

import caproto as ca

from .. import _utils as utils
from .. import _constants as constants
from . import common


class UnknownSearchResponse(ca.CaprotoError):
    ...


class DuplicateSearchResponse(ca.CaprotoError):
    def __init__(self, name, cid, addresses):
        super().__init__()
        self.name = name
        self.cid = cid
        self.addresses = addresses


def _locked(func):
    @functools.wraps(func)
    def wrapped(self, *args, **kwargs):
        with self._lock:
            return func(self, *args, **kwargs)
    return wrapped


class _UnansweredSearch:
    name: str
    results_queue: object
    last_sent: float
    retirement_deadline: float

    def __init__(self, name, results_queue, last_sent,
                 retirement_deadline):
        self.name = name
        self.results_queue = results_queue
        self.last_sent = last_sent
        self.retirement_deadline = retirement_deadline

    def __repr__(self):
        retire = self.retirement_deadline - time.monotonic()

        if self.last_sent > 0:
            resend = self.last_sent - time.monotonic()
        else:
            resend = 'never'

        return (
            f'<_UnansweredSearch name={self.name} '
            f'relative_resend_deadline={resend}) '
            f'relative_retirement_deadline={retire})'
        )


class SearchResults:
    '''
    Thread-safe handling of all past and in-process search results

    Acts partially as a container type which is keyed on PV name, such that the
    following are possible::

        1. `SearchResults()[name] -> [time, address]`
        2. `name in SearchResults()`

    Attributes
    ----------
    name_to_addrs : dict
        Holds search results.
        Maps name -> [(address, name, time), ...]

    addr_to_name : dict
        Holds search results.
        Maps address -> {name1, name2, ...}

    _unanswered_searches : dict
        Holds pending searches
        Maps search_id -> [name, results_queue, retirement_deadline]

    _lock : threading.RLock
        Lock for internal updates to SearchResults status

    _search_id_counter : ThreadsafeCounter
        Counter for new searches. This will be kept in sync with
        _unanswered_searches such that there is no overlap in keys.
    '''

    def __init__(self):
        self._lock = threading.RLock()
        self.environ = ca.get_environment_variables()
        # map name to (time, address)
        self.beacon_log = logging.getLogger('caproto.bcast.beacon')
        self.search_log = logging.getLogger('caproto.bcast.search')
        self.name_to_addrs = collections.defaultdict(dict)
        self.addr_to_names = collections.defaultdict(set)
        self._searches = {}
        self._searches_by_name = {}
        self._unanswered_searches = {}
        self.last_beacon = {}
        self._search_id_counter = ca.ThreadsafeCounter(
            initial_value=random.randint(0, constants.MAX_ID),
            dont_clash_with=self._unanswered_searches,
        )
        self._search_id_counter.lock = self._lock  # use our lock
        self._unresponsive_servers_to_check = []
        self._last_unresponsive_update = 0

    def _update_unresponsive_server_list(self):
        MARGIN = 1  # extra time (seconds) allowed between Beacons
        checking = dict()  # map address to deadline for check to resolve
        servers = collections.defaultdict(weakref.WeakSet)  # map address to VirtualCircuitManagers
        last_heard = dict()  # map address to time of last response
        servers.clear()
        last_heard.clear()
        now = time.monotonic()

        # We are interested in identifying servers that we have not heard
        # from since some time cutoff in the past.
        cutoff = now - (self.environ['EPICS_CA_CONN_TMO'] + MARGIN)

        # Map each server address to VirtualCircuitManagers connected to
        # that address, across all Contexts ("listeners").
        for listener in self.listeners:
            for (address, _), circuit_manager in listener.circuit_managers.items():
                servers[address].add(circuit_manager)

        # When is the last time we heard from each server, either via a
        # Beacon or from TCP packets related to user activity or any
        # circuit?
        for address, circuit_managers in servers.items():
            last_tcp_receipt = (cm.last_tcp_receipt for cm in circuit_managers)
            last_heard[address] = max((self.last_beacon.get(address, 0),  # TODO time
                                       *last_tcp_receipt))

            # If is has been too long --- and if we aren't already checking
            # on this server --- try to prompt a response over TCP by
            # sending an EchoRequest.
            if last_heard[address] < cutoff and address not in checking:
                # Record that we are checking on this address and set a
                # deadline for a response.
                checking[address] = now + constants.RESPONSIVENESS_TIMEOUT
                tags = {'role': 'CLIENT',
                        'their_address': address,
                        'our_address': self.broadcaster.client_address,
                        'direction': '--->>>'}

                self.beacon_log.debug(
                    "Missed Beacons from %s:%d. Sending EchoRequest to "
                    "check that server is responsive.", *address, extra=tags)
                # Send on all circuits. One might be less backlogged
                # with queued commands than the others and thus able to
                # respond faster. In the majority of cases there will only
                # be one circuit per server anyway, so this is a minor
                # distinction.
                for circuit_manager in circuit_managers:
                    try:
                        circuit_manager.send(ca.EchoRequest())
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
            # else:
            #     # We are still waiting to give the server time to respond
            #     # to the EchoRequest.

    def get_next_unresponsive_server(self):
        if time.monotonic() - self._last_unresponsive_update > 0.5:
            self._update_unresponsive_server_list()

        return self._unresponsive_servers_to_check.pop(-1)

    @_locked
    def mark_server_alive(self, address, identifier):
        'Beacon from a server received'
        for name in self.addr_to_names[address]:
            self.name_to_addrs[name][address] = time.monotonic()

        now = time.monotonic()
        if address not in self.last_beacon:
            # We made a new friend!
            self.beacon_log.info("Watching Beacons from %s:%d", *address,
                                 # extra=tags TODO
                                 )
            self.new_server_found(address)
            interval = 0
        else:
            last_beacon = self.last_beacon[address]
            last_identifier = last_beacon['identifier']
            interval = now - last_beacon['time']
            if last_identifier == identifier and interval < 0.1:
                # Network misconfiguration, or multiple users of SearchResults?
                return

            if interval < last_beacon['interval'] / 4:
                # Beacons are arriving *faster*? The server at this
                # address may have restarted.
                self.beacon_log.info(
                    "Beacon anomaly: %s:%d may have restarted.", *address,
                    # extra=TODO
                )
                self.new_server_found(address)
            self.last_beacon_interval[address] = interval

        self.last_beacon[address] = {
            'time': now,
            'identifier': identifier,
            'interval': interval
        }

    @_locked
    def new_server_found(self, address):
        '''
        Call when a new server beacon is found:
        Bring all the unanswered searches out of retirement to see if we have a
        new match.
        '''
        retirement_deadline = (
            time.monotonic() + common.SEARCH_RETIREMENT_AGE
        )

        for item in self._unanswered_searches.values():
            item.retirement_deadline = retirement_deadline

    @property
    @_locked
    def unanswered_searches(self):
        'All unanswered searches'
        return dict(self._unanswered_searches)

    @_locked
    def cancel(self, *names):
        """
        Cancel searches for these names.

        Parameters
        ----------
        *names : strings
            any number of PV names

        Any PV instances that were awaiting these results will be stuck until
        :meth:`get_pvs` is called again.
        """
        for name in names:
            cid = self._searches_by_name.pop(name, None)
            if cid is not None:
                self._unanswered_searches.pop(cid, None)

    def __contains__(self, name):
        return bool(self.name_to_addrs.get(name, {}))

    def __getitem__(self, name):
        return self.name_to_addrs[name]

    @_locked
    def clear(self):
        'Clear all status'
        self.name_to_addrs.clear()
        self.addr_to_names.clear()
        self._unanswered_searches.clear()
        self._searches_by_name.clear()
        self._searches.clear()

    @_locked
    def mark_server_disconnected(self, addr):
        'Server disconnected; update all status'
        for name in self.addr_to_names.pop(addr, []):
            self.name_to_addrs[name].pop(addr, None)

    @_locked
    def mark_name_found(self, name, addr):
        '{name} was found at {addr}; update state'
        self.name_to_addrs[name][addr] = time.monotonic()
        self.addr_to_names[addr].add(name)

    @_locked
    def mark_channel_created(self, name, addr):
        'Channel was created with {name} at {addr}'
        self.name_to_addrs[name][addr] = common.VALID_CHANNEL_MARKER
        self.addr_to_names[addr].add(name)

    @_locked
    def mark_channel_disconnected(self, name, addr):
        'Channel by name {name} was disconnected from {addr}'
        if name in self.addr_to_names[addr]:
            self.addr_to_names[addr].remove(name)

        self.name_to_addrs[name].pop(addr, None)

    @_locked
    def get_cached_search_result(self, name, *,
                                 threshold=constants.STALE_SEARCH_EXPIRATION):
        'Returns address if found, raises KeyError if missing or stale.'
        entry = self.name_to_addrs[name]
        result_addr = None
        result_timestamp = None
        for addr, timestamp in list(entry.items()):
            dt = time.monotonic() - timestamp
            if timestamp is common.VALID_CHANNEL_MARKER or dt < threshold:
                if result_timestamp is not common.VALID_CHANNEL_MARKER:
                    result_addr = addr
                    result_timestamp = timestamp
            else:
                # Clean up expired result.
                entry.pop(addr)

        if result_addr is not None:
            return result_addr

        raise utils.CaprotoKeyError(f'{name!r}: stale search result')

    @_locked
    def received_search_response(self, cid, addr):
        'Get an unanswered search by (cid, addr) -> name, queue'
        first_response = True
        try:
            info = self._unanswered_searches.pop(cid)
        except KeyError:
            first_response = False
            try:
                info = self._searches[cid]
            except KeyError:
                # Completely unknown cid... ignore
                raise UnknownSearchResponse('No matching cid') from None

        self.mark_name_found(info.name, addr)

        name = info.name
        queue = info.results_queue

        if first_response:
            return name, queue

        raise DuplicateSearchResponse(
            name=name,
            cid=cid,
            addresses=list(self.name_to_addrs[name])
        )

    def items_to_retry(self, threshold, resend_deadline):
        'All search results in need of retrying (if beyond threshold)'
        with self._lock:
            items = list(self._unanswered_searches.items())

        if not threshold:
            return items

        # Skip over searches that haven't gotten any results in
        # SEARCH_RETIREMENT_AGE.
        return list(
            (search_id, it)
            for search_id, it in items
            if (it.retirement_deadline > threshold and
                it.last_sent < resend_deadline)
        )

    @_locked
    def search(self, *names, results_queue, retirement_deadline):
        'Search for names, adding items to results_queue'
        # Search requests that are past their retirement deadline with no
        # results will be searched for less frequently.
        for name in names:
            id_ = self._search_id_counter()
            item = _UnansweredSearch(name=name,
                                     results_queue=results_queue,
                                     last_sent=0,
                                     retirement_deadline=retirement_deadline)

            self._unanswered_searches[id_] = item
            self._searches[id_] = item
            self._searches_by_name[name] = item

    @_locked
    def split_cached_results(self, names):
        """
        Tell which PVs have valid cached addresses, and which do not.

        Returns
        -------
        use_cached_search : dict
            Address to list of names
        needs_search : list
            Remaining PVs that need a search attempt
        """
        needs_search = []
        use_cached_search = collections.defaultdict(list)

        for name in names:
            try:
                address = self.get_cached_search_result(name)
            except KeyError:
                needs_search.append(name)
            else:
                use_cached_search[address].append(name)

        return use_cached_search, needs_search
