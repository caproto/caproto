import collections
import functools
import logging
import random
import sys
import threading
import time

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

    unanswered_searches : dict
        Holds pending searches
        Maps search_id -> _UnansweredSearch
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
        self._last_beacon = {}
        self._search_id_counter = ca.ThreadsafeCounter(
            initial_value=random.randint(0, constants.MAX_ID),
            dont_clash_with=self._unanswered_searches,
        )
        self._search_id_counter.lock = self._lock  # use our lock

    @_locked
    def get_last_beacon_times(self):
        """
        Last beacon times, according to `time.monotonic`.

        Returns
        -------
        dict
            {address_tuple: monotonic_beacon_time}
        """
        return {
            addr: info['time']
            for addr, info in self._last_beacon.items()
        }

    @_locked
    def mark_server_alive(self, address, identifier):
        'Beacon from a server received'
        for name in self.addr_to_names[address]:
            self.name_to_addrs[name][address] = time.monotonic()

        now = time.monotonic()
        if address not in self._last_beacon:
            # We made a new friend!
            self.beacon_log.info("Watching Beacons from %s:%d", *address,
                                 # extra=tags TODO
                                 )
            self.new_server_found(address)
            interval = 0
        else:
            last_beacon = self._last_beacon[address]
            last_identifier = last_beacon['identifier']
            interval = now - last_beacon['time']
            if last_identifier == identifier and interval < 0.1:
                # Network misconfiguration, or multiple users of SearchResults?
                return

            if interval < last_beacon['interval'] / 4:
                # Beacons are arriving *faster*? The server at this address may
                # have restarted.
                self.beacon_log.info(
                    "Beacon anomaly: %s:%d may have restarted.", *address,
                    # extra=TODO
                )
                self.new_server_found(address)

        self._last_beacon[address] = {
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
        'Server disconnected; update all associated channels'
        for name in self.addr_to_names.pop(addr, []):
            self.name_to_addrs[name].pop(addr, None)

    @_locked
    def invalidate_by_name(self, name):
        'Invalidate all cached results associated with the given name'
        for addr in self.name_to_addrs.get(name, []):
            self.addr_to_names[addr].remove(name)

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

    @_locked
    def _debug_beacon_information(self):
        'Yields individual lines of server information.'
        # yield 'Host', 'Interval', 'Beacon ID'
        for addr, info in self._last_beacon.items():
            yield ('%s:%s' % addr, info['interval'], info['identifier'])

    @_locked
    def _debug_channel_information(self, specific_addresses=None):
        'Yields individual lines of channel name information.'
        specific_addresses = specific_addresses or list(self.addr_to_names)

        # yield 'Host', 'Name'
        for addr in specific_addresses:
            try:
                names = self.addr_to_names[addr]
            except KeyError:
                yield '(None)'
            else:
                for name in sorted(names):
                    yield ('%s:%s' % addr, name)

    def print_debug_information(self, file=sys.stdout):
        'Print debug information about servers and channels to `file`.'
        print('\t'.join(('Host', 'Interval', 'Beacon ID')), file=file)
        for line in self._debug_beacon_information():
            print('\t'.join(str(item) for item in line), file=file)

        print(file=file)
        print('\t'.join(('Host', 'Name')), file=file)
        for line in self._debug_channel_information():
            print('\t'.join(str(item) for item in line), file=file)
