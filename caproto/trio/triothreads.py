import itertools
import time
import copy
import logging
import functools
import threading
import queue
import trio

from math import log10
from collections import Iterable

import caproto as ca
from . import client as trioclient
from caproto import AccessRights, field_types, ChannelType
from ..threading.client import (AUTOMONITOR_MAXLENGTH, STR_ENC, Subscription)
from ..threading.pyepics_compat import (_parse_dbr_metadata,
                                        _read_response_to_pyepics,
                                        _pyepics_get_value)


__all__ = ['PV', 'get_pv']


logger = logging.getLogger(__name__)


def ensure_connection(func):
    # TODO get timeout default from func signature
    @functools.wraps(func)
    def inner(self, *args, **kwargs):
        self.wait_for_connection(timeout=kwargs.get('timeout', 5.0))
        return func(self, *args, **kwargs)
    return inner


class TrioPV:
    def __init__(self, pvname, connection_state_callback, context, portal):
        self.pvname = pvname
        self.connection_state_callback = connection_state_callback
        self.context = context
        self.portal = portal
        self._channel_set_event = threading.Event()
        self._channel = None
        self._subscriptions = {}

    @property
    def channel(self):
        return self._channel

    @channel.setter
    def channel(self, channel):
        self._channel = channel
        if not self.connection_state_callback:
            return

        self._channel_set_event.clear()
        self.context._queue_cb(self.connection_state_callback,
                               self, 'connected' if channel is not None
                               else 'disconnected')

    @property
    def circuit(self):
        channel = self.channel
        return (channel.circuit if channel is not None
                else None)

    async def _ensure_connection(self, timeout):
        try:
            circuit = None
            with trio.fail_after(timeout):
                bc = self.context.broadcaster
                async with bc.broadcaster_command_condition:
                    while (self.channel is None and
                           self.pvname not in bc.search_results):
                        await bc.broadcaster_command_condition.wait()
                        # TODO search again after a period of time

                while self.channel is None:
                    await trio.sleep(0)
                    # TODO

                circuit = self.circuit
                async with circuit.new_command_condition:
                    while not circuit.connected:
                        await circuit.new_command_condition.wait()
        except trio.TooSlowError:
            if circuit is None or circuit.state is not ca.CONNECTED:
                raise TimeoutError(f'Failed to connect within {timeout} sec '
                                   f'timeout') from None

    def wait_for_connection(self, timeout):
        return self.portal.run(self._ensure_connection, timeout)

    def write(self, *args, **kwargs):
        async def _write():
            await self._ensure_connection(kwargs.get('timeout', 2.0))
            return await self.channel.write(*args, **kwargs)
        return self.portal.run(_write)

    def read(self, *args, timeout=2.0, **kwargs):
        async def _read():
            await self._ensure_connection(timeout)
            return await self.channel.read(*args, **kwargs)
        return self.portal.run(_read)

    def subscribe(self, *args, **kwargs):
        "Start a new subscription and spawn an async task to receive readings."
        subscription = None
        queue = trio.Queue(capacity=100)

        async def _queue_loop(task_status):
            nonlocal subscription
            sub_id = subscription.subscriptionid
            task_status.started()

            while True:
                command = await queue.get()
                if command is ca.DISCONNECTED:
                    self._subscriptions.pop(sub_id, None)
                    break
                self.context._queue_cb(subscription.process, command)

        async def _subscribe():
            nonlocal subscription
            await self._ensure_connection(kwargs.get('timeout', 2.0))

            command = self.channel.channel.subscribe(*args, **kwargs)
            # Stash the subscriptionid to match the response to the request.
            sub_id = command.subscriptionid
            self.circuit.subscriptionids[sub_id] = queue

            subscription = Subscription(self, command.subscriptionid, (), {})
            self._subscriptions[sub_id] = subscription

            await self.circuit.send(command)
            await self.context.nursery.start(_queue_loop)
            return subscription

        return self.portal.run(_subscribe)

    def unsubscribe(self, subscriptionid, *args, **kwargs):
        "Cancel a subscription and await confirmation from the server."
        # queue = self.circuit.subscriptionids[subscriptionid]
        async def _unsubscribe():
            unsub = self.channel.channel.unsubscribe(subscriptionid)
            await self.circuit.send(unsub)
            while subscriptionid in self.circuit.subscriptionids:
                await self.channel.wait_on_new_command()

        return self.portal.run(_unsubscribe)


class Context:
    def __init__(self, log_level='DEBUG'):
        self.running = True
        self.log_level = log_level
        self.portal = None
        self.nursery = None
        self.context = None
        self._initialized = False
        self._callback_queue = queue.Queue()
        self.sub_thread = threading.Thread(target=self._sub_loop, daemon=True)
        self.sub_thread.start()
        self.trio_thread = threading.Thread(target=self._loop, daemon=True)
        self.trio_thread.start()

        while not self._initialized:
            print('trio initializing...')
            # TODO
            time.sleep(0.1)

    def _queue_cb(self, func, *args, **kwargs):
        self._callback_queue.put((time.monotonic(), func, args, kwargs))

    def stop(self):
        self.running = False

    def _sub_loop(self):
        while self.running:
            timestamp, cb, args, kwargs = self._callback_queue.get()
            cb(*args, **kwargs)

    def _loop(self):
        async def _loop():
            async with trio.open_nursery() as self.nursery:
                self.portal = trio.BlockingTrioPortal()
                self.broadcaster = trioclient.SharedBroadcaster(
                    nursery=self.nursery, log_level=self.log_level)
                self.context = trioclient.Context(self.broadcaster,
                                                  nursery=self.nursery,
                                                  log_level=self.log_level)

                # TODO trio still waits for registration!
                self.nursery.start_soon(self.broadcaster._broadcaster_queue_loop)
                self._initialized = True
                while self.running:
                    await trio.sleep(1)

        trio.run(_loop)

    def get_pvs(self, *pvnames, connection_state_callback=None):
        pvs = {pvname: TrioPV(pvname, connection_state_callback, self,
                              self.portal)
               for pvname in pvnames}
        channels = {}

        async def _wait_connect(name):
            channel = channels[name]
            await channel.wait_for_connection()
            pvs[name].channel = channels[name]

        async def _connect(task_status):
            task_status.started()
            async for addr, names in self.broadcaster.search_many(*pvnames):
                for name in names:
                    channels[name] = await self.context.create_channel(name,
                                                                       priority=0)
                    self.nursery.start_soon(_wait_connect, name)

        self.portal.run(self.nursery.start, _connect)
        return list(pvs.values())


class PV:
    """Epics Process Variable

    A PV encapsulates an Epics Process Variable.

    The primary interface methods for a pv are to get() and put() is value::

      >>> p = PV(pv_name)  # create a pv object given a pv name
      >>> p.get()          # get pv value
      >>> p.put(val)       # set pv to specified value.

    Additional important attributes include::

      >>> p.pvname         # name of pv
      >>> p.value          # pv value (can be set or get)
      >>> p.char_value     # string representation of pv value
      >>> p.count          # number of elements in array pvs
      >>> p.type           # EPICS data type:'string','double','enum','long',..
"""

    _fmtsca = ("<PV '{pvname}', count={count}, type={typefull!r}, "
               "access={access}>")
    _fmtarr = ("<PV '{pvname}', count={count}/{nelm}, type={typefull!r}, "
               "access={access}>")
    _fields = ('pvname', 'value', 'char_value', 'status', 'ftype', 'chid',
               'host', 'count', 'access', 'write_access', 'read_access',
               'severity', 'timestamp', 'posixseconds', 'nanoseconds',
               'precision', 'units', 'enum_strs',
               'upper_disp_limit', 'lower_disp_limit', 'upper_alarm_limit',
               'lower_alarm_limit', 'lower_warning_limit',
               'upper_warning_limit', 'upper_ctrl_limit', 'lower_ctrl_limit',
               'put_complete')
    _default_context = Context()

    def __init__(self, pvname, callback=None, form='time',
                 verbose=False, auto_monitor=False, count=None,
                 connection_callback=None,
                 connection_timeout=None, *, context=None):

        if context is None:
            context = self._default_context
        if context is None:
            raise RuntimeError("must have a valid context")
        self._context = context
        self.pvname = pvname.strip()
        self.form = form.lower()
        self.verbose = verbose
        self.auto_monitor = auto_monitor
        self.ftype = None
        self._connect_event = threading.Event()
        self._state_lock = threading.RLock()
        self.connection_timeout = connection_timeout
        self.default_count = count
        self._auto_monitor_sub = None
        self._connected = False

        if self.connection_timeout is None:
            self.connection_timeout = 1

        self._args = {}.fromkeys(self._fields)
        self._args['pvname'] = self.pvname
        self._args['count'] = count
        self._args['nelm'] = -1
        self._args['type'] = None
        self._args['typefull'] = None
        self._args['access'] = None
        self.connection_callbacks = []
        self._cb_count = iter(itertools.count())

        if connection_callback is not None:
            self.connection_callbacks = [connection_callback]

        self.callbacks = {}
        self._conn_started = False

        if isinstance(callback, (tuple, list)):
            for i, thiscb in enumerate(callback):
                if hasattr(thiscb, '__call__'):
                    self.callbacks[i] = (thiscb, {})

        elif hasattr(callback, '__call__'):
            self.callbacks[0] = (callback, {})

        self._caproto_pv, = self._context.get_pvs(
            self.pvname,
            connection_state_callback=self._connection_state_changed)

    @property
    def connected(self):
        'Connection state'
        return self._connected

    def force_connect(self, pvname=None, chid=None, conn=True, **kws):
        # not quite sure what this is for in pyepics
        raise NotImplementedError

    def wait_for_connection(self, timeout=None):
        """wait for a connection that started with connect() to finish
        Returns
        -------
        connected : bool
            If the PV is connected when this method returns
        """
        logger.debug(f'{self} wait for connection...')
        self._caproto_pv.wait_for_connection(timeout)
        return True

    def _connection_closed(self):
        'Callback when connection is closed'
        logger.debug('%r disconnected', self)
        self._connected = False

    def _connection_established(self):
        'Callback when connection is initially established'
        logger.debug('%r connected', self)
        ch = self._caproto_pv.channel.channel
        form = self.form
        count = self.default_count

        if ch is None:
            logger.error('Connection dropped in connection callback')
            logger.error('Connected = %r', self._connected)
            return

        self._host = ch.circuit.address
        self._args['type'] = ch.native_data_type

        type_key = 'control' if form == 'ctrl' else form
        self._args['typefull'] = field_types[type_key][ch.native_data_type]
        self._args['nelm'] = ch.native_data_count
        self._args['count'] = ch.native_data_count

        self._args['write_access'] = AccessRights.WRITE in ch.access_rights
        self._args['read_access'] = AccessRights.READ in ch.access_rights

        access_strs = ('no access', 'read-only', 'write-only', 'read/write')
        self._args['access'] = access_strs[ch.access_rights]

        if self.auto_monitor is None:
            mcount = count if count is not None else self._args['count']
            self.auto_monitor = mcount < AUTOMONITOR_MAXLENGTH

        self._check_auto_monitor_sub()
        self._connected = True

    def _check_auto_monitor_sub(self, count=None):
        'Ensure auto-monitor subscription is running'
        if ((self.auto_monitor or self.callbacks) and
                not self._auto_monitor_sub):
            if count is None:
                count = self.default_count

            self._auto_monitor_sub = self._caproto_pv.subscribe(
                data_type=self.typefull, data_count=count)
            self._auto_monitor_sub.add_callback(self.__on_changes)

    def _connection_state_changed(self, caproto_pv, state):
        'Connection callback hook from threading.PV.connection_state_changed'
        connected = (state == 'connected')
        with self._state_lock:
            try:
                if connected:
                    self._connection_established()
                else:
                    ...
                    # TODO type can change if reconnected
                    # if not self.connected or self._args['type'] is not None:
                    #     return
                    self._connection_closed()
            except Exception as ex:
                logger.exception('Connection state callback failed!')
                raise
            finally:
                self._connect_event.set()

        # todo move to async connect logic
        for cb in self.connection_callbacks:
            cb(pvname=self.pvname, conn=connected, pv=self)

    def connect(self, timeout=None):
        """check that a PV is connected, forcing a connection if needed

        Returns
        -------
        connected : bool
            If the PV is connected when this method returns
        """
        self.wait_for_connection(timeout=timeout)

    def reconnect(self):
        "try to reconnect PV"

        return True

    @ensure_connection
    def get(self, *, count=None, as_string=False, as_numpy=True,
            timeout=None, with_ctrlvars=False, use_monitor=True):
        """returns current value of PV.

        Parameters
        ----------
        count : int, optional
             explicitly limit count for array data
        as_string : bool, optional
            flag(True/False) to get a string representation
            of the value.
        as_numpy : bool, optional
            use numpy array as the return type for array data.
        timeout : float, optional
            maximum time to wait for value to be received.
            (default = 0.5 + log10(count) seconds)
        use_monitor : bool, optional
            use value from latest monitor callback (True, default)
            or to make an explicit CA call for the value.

        Returns
        -------
        val : Object
            The value, the type is dependent on the underlying PV
        """
        if count is None:
            count = self.default_count

        if timeout is None:
            if count is None:
                timeout = 1.0
            else:
                timeout = 1.0 + log10(max(1, count))

        if with_ctrlvars:
            dt = field_types['control'][self.type]

        dt = self.typefull
        if not as_string and self.typefull in ca.char_types:
            re_map = {ChannelType.CHAR: ChannelType.INT,
                      ChannelType.CTRL_CHAR: ChannelType.CTRL_INT,
                      ChannelType.TIME_CHAR: ChannelType.TIME_INT,
                      ChannelType.STS_CHAR: ChannelType.STS_INT}
            dt = re_map[self.typefull]
            # TODO if you want char arrays not as_string
            # force no-monitor rather than
            use_monitor = False

        # trigger going out to got data from network
        if ((not use_monitor) or
            (self._auto_monitor_sub is None) or
            (self._args['value'] is None) or
            (count is not None and
             count > len(self._args['value']))):
            command = self._caproto_pv.read(data_type=dt, data_count=count)
            info = _read_response_to_pyepics(self.typefull, command)
            self._args.update(**info)

        info = self._args

        if as_string and self.typefull in ca.enum_types:
            enum_strs = self.enum_strs
        else:
            enum_strs = None

        return _pyepics_get_value(
            value=info['value'], string_value=info['char_value'],
            full_type=self.typefull, native_count=info['count'],
            requested_count=count, enum_strings=enum_strs,
            as_string=as_string, as_numpy=as_numpy)

    @ensure_connection
    def put(self, value, *, wait=False, timeout=30.0,
            use_complete=False, callback=None, callback_data=None):
        """set value for PV, optionally waiting until the processing is
        complete, and optionally specifying a callback function to be run
        when the processing is complete.
        """
        if callback_data is None:
            callback_data = ()
        if self._args['typefull'] in ca.enum_types:
            if isinstance(value, str):
                try:
                    value = self.enum_strs.index(value)
                except ValueError:
                    raise ValueError('{} is not in Enum ({}'.format(
                        value, self.enum_strs))

        if isinstance(value, str):
            if self.typefull in ca.char_types:
                # have to add a null-terminator char
                value = value.encode(STR_ENC) + b'\0'
            else:
                value = (value, )
        elif not isinstance(value, Iterable):
            value = (value, )

        if isinstance(value[0], str):
            value = tuple(v.encode(STR_ENC) for v in value)

        def run_callback(cmd):
            self._args['put_complete'] = True
            if callback is not None:
                callback(*callback_data)

        self._args['put_complete'] = False
        self._caproto_pv.write(value, wait=wait, cb=run_callback,
                               timeout=timeout)

    @ensure_connection
    def get_ctrlvars(self, timeout=5, warn=True):
        "get control values for variable"
        dtype = field_types['control'][self.type]
        command = self._caproto_pv.read(data_type=dtype, timeout=timeout)
        info = _parse_dbr_metadata(command.metadata)
        info['value'] = command.data
        self._args.update(**info)
        return info

    @ensure_connection
    def get_timevars(self, timeout=5, warn=True):
        "get time values for variable"
        dtype = field_types['time'][self.type]
        command = self._caproto_pv.read(data_type=dtype, timeout=timeout)
        info = _parse_dbr_metadata(command.metadata)
        info['value'] = command.data
        self._args.update(**info)

    def __on_changes(self, command):
        """internal callback function: do not overwrite!!
        To have user-defined code run when the PV value changes,
        use add_callback()
        """
        info = _read_response_to_pyepics(self.typefull, command)
        self._args.update(**info)
        self.run_callbacks()

    def run_callbacks(self):
        """run all user-defined callbacks with the current data

        Normally, this is to be run automatically on event, but
        it is provided here as a separate function for testing
        purposes.
        """
        for index in sorted(list(self.callbacks.keys())):
            self.run_callback(index)

    def run_callback(self, index):
        """run a specific user-defined callback, specified by index,
        with the current data
        Note that callback functions are called with keyword/val
        arguments including:
             self._args  (all PV data available, keys = __fields)
             keyword args included in add_callback()
             keyword 'cb_info' = (index, self)
        where the 'cb_info' is provided as a hook so that a callback
        function  that fails may de-register itself (for example, if
        a GUI resource is no longer available).
        """
        try:
            fcn, kwargs = self.callbacks[index]
        except KeyError:
            return
        kwd = copy.copy(self._args)
        kwd.update(kwargs)
        kwd['cb_info'] = (index, self)
        if hasattr(fcn, '__call__'):
            fcn(**kwd)

    def add_callback(self, callback, *, index=None, run_now=False,
                     with_ctrlvars=True, **kw):
        """add a callback to a PV.  Optional keyword arguments
        set here will be preserved and passed on to the callback
        at runtime.

        Note that a PV may have multiple callbacks, so that each
        has a unique index (small integer) that is returned by
        add_callback.  This index is needed to remove a callback."""
        if not callable(callback):
            raise ValueError()
        if index is not None:
            raise ValueError("why do this")
        index = next(self._cb_count)
        self.callbacks[index] = (callback, kw)

        if self.connected:
            self._check_auto_monitor_sub()

        if with_ctrlvars and self.connected:
            self.get_ctrlvars()
        if run_now:
            self.get(as_string=True)
            if self.connected:
                self.run_callback(index)
        return index

    def remove_callback(self, index):
        """remove a callback by index"""
        self.callbacks.pop(index, None)

    def clear_callbacks(self):
        "clear all callbacks"
        self.callbacks = {}

    def __getval(self):
        "get value"
        return self.get()

    def __setval(self, val):
        "put-value"
        return self.put(val)

    value = property(__getval, __setval, None, "value property")

    @property
    def char_value(self):
        "character string representation of value"
        return self._getarg('char_value')

    @property
    def status(self):
        "pv status"
        return self._getarg('status')

    @property
    def type(self):
        "pv type"
        return self._args['type']

    @property
    def typefull(self):
        "pv type"
        return self._args['typefull']

    @property
    def host(self):
        "pv host"
        return self._host

    @property
    def count(self):
        """count (number of elements). For array data and later EPICS versions,
        this is equivalent to the .NORD field.  See also 'nelm' property"""
        if self._args['count'] is not None:
            return self._args['count']
        else:
            return self._getarg('count')

    @property
    def nelm(self):
        """native count (number of elements).
        For array data this will return the full array size (ie, the
        .NELM field).  See also 'count' property"""
        if self._getarg('count') == 1:
            return 1
        return self._caproto_pv.channel.native_data_count

    @property
    def read_access(self):
        "read access"
        return self._getarg('read_access')

    @property
    def write_access(self):
        "write access"
        return self._getarg('write_access')

    @property
    def access(self):
        "read/write access as string"
        return self._getarg('access')

    @property
    def severity(self):
        "pv severity"
        return self._getarg('severity')

    @property
    def timestamp(self):
        "timestamp of last pv action"
        return self._getarg('timestamp')

    @property
    def posixseconds(self):
        """integer seconds for timestamp of last pv action
        using POSIX time convention"""
        return self._getarg('posixseconds')

    @property
    def nanoseconds(self):
        "integer nanoseconds for timestamp of last pv action"
        return self._getarg('nanoseconds')

    @property
    def precision(self):
        "number of digits after decimal point"
        return self._getarg('precision')

    @property
    def units(self):
        "engineering units for pv"
        return self._getarg('units')

    @property
    def enum_strs(self):
        "list of enumeration strings"
        return self._getarg('enum_strs')

    @property
    def upper_disp_limit(self):
        "limit"
        return self._getarg('upper_disp_limit')

    @property
    def lower_disp_limit(self):
        "limit"
        return self._getarg('lower_disp_limit')

    @property
    def upper_alarm_limit(self):
        "limit"
        return self._getarg('upper_alarm_limit')

    @property
    def lower_alarm_limit(self):
        "limit"
        return self._getarg('lower_alarm_limit')

    @property
    def lower_warning_limit(self):
        "limit"
        return self._getarg('lower_warning_limit')

    @property
    def upper_warning_limit(self):
        "limit"
        return self._getarg('upper_warning_limit')

    @property
    def upper_ctrl_limit(self):
        "limit"
        return self._getarg('upper_ctrl_limit')

    @property
    def lower_ctrl_limit(self):
        "limit"
        return self._getarg('lower_ctrl_limit')

    @property
    def info(self):
        "info string"
        return self._getinfo()

    @property
    def put_complete(self):
        "returns True if a put-with-wait has completed"
        return self._args['put_complete']

    def _getinfo(self):
        "get information paragraph"
        self.get_ctrlvars()
        out = []
        xtype = self._args['typefull']
        nt_type = ca.native_type(xtype)
        fmt = '%i'

        if nt_type in (ChannelType.FLOAT, ChannelType.DOUBLE):
            fmt = '%g'
        elif nt_type in (ChannelType.CHAR, ChannelType.STRING):
            fmt = '%s'

        # self._set_charval(self._args['value'], call_ca=False)
        out.append(f"== {self.pvname}  ({ca.DBR_TYPES[xtype].__name__}) ==")
        if self.count == 1:
            val = self._args['value']
            out.append(f'   value      = {fmt}' % val)
        else:
            ext = {True: '...', False: ''}[self.count > 10]
            elems = range(min(5, self.count))
            try:
                aval = [fmt % self._args['value'][i] for i in elems]
            except TypeError:
                aval = ('unknown',)
            out.append("   value      = array  [%s%s]" % (",".join(aval), ext))
        for nam in ('char_value', 'count', 'nelm', 'type', 'units',
                    'precision', 'host', 'access',
                    'status', 'severity', 'timestamp',
                    'posixseconds', 'nanoseconds',
                    'upper_ctrl_limit', 'lower_ctrl_limit',
                    'upper_disp_limit', 'lower_disp_limit',
                    'upper_alarm_limit', 'lower_alarm_limit',
                    'upper_warning_limit', 'lower_warning_limit'):
            if hasattr(self, nam):
                att = getattr(self, nam)
                if att is not None:
                    if nam == 'timestamp':
                        def fmt_time(tstamp=None):
                            "simple formatter for time values"
                            if tstamp is None:
                                tstamp = time.time()
                            tstamp, frac = divmod(tstamp, 1)
                            return "%s.%5.5i" % (
                                time.strftime("%Y-%m-%d %H:%M:%S",
                                              time.localtime(tstamp)),
                                round(1.e5 * frac))

                        att = "%.3f (%s)" % (att, fmt_time(att))
                    elif nam == 'char_value':
                        att = "'%s'" % att
                    if len(nam) < 12:
                        out.append('   %.11s= %s' % (nam + ' ' * 12, str(att)))
                    else:
                        out.append('   %.20s= %s' % (nam + ' ' * 20, str(att)))
        if xtype == 'enum':  # list enum strings
            out.append('   enum strings: ')
            for index, nam in enumerate(self.enum_strs):
                out.append("       %i = %s " % (index, nam))

        if self._auto_monitor_sub is not None:
            msg = 'PV is internally monitored'
            out.append('   %s, with %i user-defined callbacks:' %
                       (msg, len(self.callbacks)))
            if len(self.callbacks) > 0:
                for nam in sorted(self.callbacks.keys()):
                    cback = self.callbacks[nam][0]
                    out.append('      {!r}'.format(cback))
        else:
            out.append('   PV is NOT internally monitored')
        out.append('=============================')
        return '\n'.join(out)

    def _getarg(self, arg):
        "wrapper for property retrieval"
        if self._args['value'] is None:
            self.get()
        if self._args[arg] is None and self.connected:
            if arg in ('status', 'severity', 'timestamp',
                       'posixseconds', 'nanoseconds'):
                self.get_timevars(warn=False)
            else:
                self.get_ctrlvars(warn=False)
        return self._args.get(arg, None)

    def __repr__(self):
        "string representation"

        if self.connected:
            if self._args['count'] == 1:  # self.count == 1:
                return self._fmtsca.format(**self._args)
            else:
                return self._fmtarr.format(**self._args)
        else:
            return "<PV '%s': not connected>" % self.pvname

    def __eq__(self, other):
        "test for equality"
        return False

    def disconnect(self):
        "disconnect PV"
        if self.connected:
            # self._caproto_pv.go_idle()
            ...


def get_pv(pvname, *args, context=None, connect=False, timeout=5, **kwargs):
    if context is None:
        context = PV._default_context
    pv = PV(pvname, *args, context=context, **kwargs)
    if connect:
        pv.wait_for_connection(timeout=timeout)
    return pv
