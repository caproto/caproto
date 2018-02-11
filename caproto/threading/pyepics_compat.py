import functools
import caproto as ca
from .client import Context, SharedBroadcaster




def ensure_connection(func):
    # TODO get timeout default from func signature
    @functools.wraps(func)
    def inner(self, *args, **kwargs):
        self.wait_for_connection(timeout=kwargs.get('timeout', None))
        return func(self, *args, **kwargs)
    return inner


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
      >>> p.type           # EPICS data type: 'string','double','enum','long',..
"""

    _fmtsca = "<PV '%(pvname)s', count=%(count)i, type=%(typefull)s, access=%(access)s>"
    _fmtarr = "<PV '%(pvname)s', count=%(count)i/%(nelm)i, type=%(typefull)s, access=%(access)s>"
    _fields = ('pvname',  'value',  'char_value',  'status',  'ftype',  'chid',
               'host', 'count', 'access', 'write_access', 'read_access',
               'severity', 'timestamp', 'posixseconds', 'nanoseconds',
               'precision', 'units', 'enum_strs',
               'upper_disp_limit', 'lower_disp_limit', 'upper_alarm_limit',
               'lower_alarm_limit', 'lower_warning_limit',
               'upper_warning_limit', 'upper_ctrl_limit', 'lower_ctrl_limit')
    _default_context = Context(SharedBroadcaster())

    def __init__(self, pvname, callback=None, form='time',
                 verbose=False, auto_monitor=False, count=None,
                 connection_callback=None,
                 connection_timeout=None, *, context=None):
        # TODO
        # - connection_callback
        # - connection_timeout
        self.chid = None

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
        self.connection_timeout = connection_timeout
        self.dflt_count = count
        self._subid = None

        if self.connection_timeout is None:
            self.connection_timeout = 1

        self._args = {}.fromkeys(self._fields)
        self._args['pvname'] = self.pvname
        self._args['count'] = count
        self._args['nelm'] = -1
        self._args['type'] = 'unknown'
        self._args['typefull'] = 'unknown'
        self._args['access'] = 'unknown'
        self.connection_callbacks = []

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

        self._caproto_pv, = _default_context.get_pvs(self.pvname)

    @property
    def connected(self):
        return self._caproto_pv.connected

    def force_connect(self, pvname=None, chid=None, conn=True, **kws):
        # not quite sure what this is for in pyepics, probably should
        # be an arias for reconnect?
        ...

    def wait_for_connection(self, timeout=None, *, form=None, count=None):
        """wait for a connection that started with connect() to finish
        Returns
        -------
        connected : bool
            If the PV is connected when this method returns
        """
        # TODO
        # - check if there is a form or count on the object we should respect
        # - do something with the timeout value
        if self.connected:
            return

        self.chid = self._context.create_channel(self.pvname)

        self._args['type'] = ca.ChannelType(self.chid.channel.native_data_type)
        self._args['typefull'] = ca.promote_type(self.type,
                                                 use_time=(form == 'time'),
                                                 use_ctrl=(form != 'time'))
        self._args['nelm'] = self.chid.channel.native_data_count
        self._args['count'] = self.chid.channel.native_data_count

        # yeah... enum.Flag would be nice here
        self._args['write_access'] = (self.chid.channel.access_rights & 2) == 2
        self._args['read_access'] = (self.chid.channel.access_rights & 1) == 1

        access_strs = ('no access', 'read-only', 'write-only', 'read/write')
        self._args['access'] = access_strs[self.chid.channel.access_rights]

        self.chid.register_user_callback(self.__on_changes)

        if self.auto_monitor is None:
            mcount = count if count is not None else self._args['count']
            self.auto_monitor = mcount < AUTOMONITOR_MAXLENGTH

        if self.auto_monitor:
            self._subid = self.chid.subscribe(data_type=self.typefull,
                                              data_count=count)

        self._cb_count = iter(itertools.count())

        # todo move to async connect logic
        for cb in self.connection_callbacks:
            cb(pvname=self.pvname, conn=True, pv=self)

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
        self.disconnect()
        return self.wait_for_connection()

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
        # TODO
        # - timeout
        # - with_ctrlvars

        if count is None:
            count = self.dflt_count
        dt = self.typefull
        if not as_string and self.typefull in ca.char_types:
            re_map = {ca.ChannelType.CHAR: ca.ChannelType.INT,
                      ca.ChannelType.CTRL_CHAR: ca.ChannelType.CTRL_INT,
                      ca.ChannelType.TIME_CHAR: ca.ChannelType.TIME_INT,
                      ca.ChannelType.STS_CHAR: ca.ChannelType.STS_INT}
            dt = re_map[self.typefull]
            # TODO if you want char arrays not as_string
            # force no-monitor rather than
            use_monitor = False

        # trigger going out to got data from network
        if ((not use_monitor) or
            (self._subid is None) or
            (self._args['value'] is None) or
            (count is not None and
             count > len(self._args['value']))):
            command = self._caproto_pv.read(data_type=dt,
                                            data_count=count)
            self.__ingest_read_response_command(command)

        info = self._args

        if (as_string and (self.typefull in ca.char_types) or
                self.typefull in ca.string_types):
            return info['char_value']
        elif as_string and self.typefull in ca.enum_types:
            enum_strs = self.enum_strs
            ret = []
            for r in info['value']:
                try:
                    ret.append(enum_strs[r])
                except IndexError:
                    ret.append('')
            if len(ret) == 1:
                ret, = ret
            return ret

        elif not as_numpy:
            return list(info['value'])
        return info['value']

    def __ingest_read_response_command(self, command):
        info = self._parse_dbr_metadata(command.metadata)
        info['value'] = command.data

        ret = info['value']
        if self.typefull in ca.char_types:
            ret = ret.tobytes().partition(b'\x00')[0].decode(STR_ENC)
            info['char_value'] = ret
        elif self.typefull in ca.string_types:
            ret = [v.decode(STR_ENC).strip() for v in ret]
            if len(ret) == 1:
                ret = ret[0]
            info['char_value'] = ret

        self._args.update(**info)

    @ensure_connection
    def put(self, value, *, wait=False, timeout=30.0,
            use_complete=False, callback=None, callback_data=None):
        """set value for PV, optionally waiting until the processing is
        complete, and optionally specifying a callback function to be run
        when the processing is complete.
        """
        # TODO
        # - wait
        # - timeout
        # - put complete (use_complete, callback, callback_data)
        # API
        # consider returning futures instead of storing state on the PV object
        if callback_data is None:
            callback_data = ()
        if self._args['typefull'] in ca.enum_types:
            if isinstance(value, str):
                try:
                    value = self.enum_strs.index(value)
                except ValueError:
                    raise ValueError('{} is not in Enum ({}'.format(
                        value, self.enum_strs))

        if isinstance(value, str) or not isinstance(value, Iterable):
            value = (value, )

        if isinstance(value[0], str):
            value = tuple(v.encode(STR_ENC) for v in value)

        def run_callback(cmd):
            callback(*callback_data)
        cb = run_callback if callback is not None else None
        ret = self.value
        self.chid.write(value, wait=wait, cb=cb, timeout=timeout)
        return ret if wait else None

    @ensure_connection
    def get_ctrlvars(self, timeout=5, warn=True):
        "get control values for variable"
        dtype = ca.promote_type(self.type, use_ctrl=True)
        command = self.chid.read(data_type=dtype, timeout=timeout)
        info = self._parse_dbr_metadata(command.metadata)
        info['value'] = command.data
        self._args.update(**info)
        return info

    @ensure_connection
    def get_timevars(self, timeout=5, warn=True):
        "get time values for variable"
        dtype = ca.promote_type(self.type, use_time=True)
        command = self.chid.read(data_type=dtype, timeout=timeout)
        info = self._parse_dbr_metadata(command.metadata)
        info['value'] = command.data
        self._args.update(**info)

    def _parse_dbr_metadata(self, dbr_data):
        ret = {}

        arg_map = {'status': 'status',
                   'severity': 'severity',
                   'precision': 'precision',
                   'units': 'units',
                   'upper_disp_limit': 'upper_disp_limit',
                   'lower_disp_limit': 'lower_disp_limit',
                   'upper_alarm_limit': 'upper_alarm_limit',
                   'upper_warning_limit': 'upper_warning_limit',
                   'lower_warning_limit': 'lower_warning_limit',
                   'lower_alarm_limit': 'lower_alarm_limit',
                   'upper_ctrl_limit': 'upper_ctrl_limit',
                   'lower_ctrl_limit': 'lower_ctrl_limit',
                   'strs': 'enum_strs',
                   # 'secondsSinceEpoch': 'posixseconds',
                   # 'nanoSeconds': 'nanoseconds',
                   }

        for attr, arg in arg_map.items():
            if hasattr(dbr_data, attr):
                ret[arg] = getattr(dbr_data, attr)

        if ret.get('enum_strs', None):
            ret['enum_strs'] = tuple(k.value.decode(STR_ENC) for
                                     k in ret['enum_strs'] if k.value)

        if hasattr(dbr_data, 'nanoSeconds'):
            ret['posixseconds'] = dbr_data.secondsSinceEpoch
            ret['nanoseconds'] = dbr_data.nanoSeconds
            timestamp = ca.epics_timestamp_to_unix(dbr_data.secondsSinceEpoch,
                                                   dbr_data.nanoSeconds)
            ret['timestamp'] = timestamp

        if 'units' in ret:
            ret['units'] = ret['units'].decode(STR_ENC)

        return ret

    def __on_changes(self, command):
        """internal callback function: do not overwrite!!
        To have user-defined code run when the PV value changes,
        use add_callback()
        """
        self.__ingest_read_response_command(command)
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
        if self._subid is None:
            self._subid = self.chid.subscribe(data_type=self.typefull,
                                              data_count=self.dflt_count)
        if index is not None:
            raise ValueError("why do this")
        index = next(self._cb_count)
        self.callbacks[index] = (callback, kw)

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
        return self.chid.channel.host_name().name.decode(STR_ENC)

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
        return self.chid.channel.native_data_count

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
        True

    def _getinfo(self):
        "get information paragraph"
        self.get_ctrlvars()
        out = []
        xtype = self._args['typefull']
        mod_map = {'enum': ca.enum_types,
                   'status': ca.status_types,
                   'time': ca.time_types,
                   'control': ca.control_types,
                   'native': ca.native_types}
        mod = next(k for k, v in mod_map.items() if xtype in v)
        nt_type = ca.native_type(xtype)
        fmt = '%i'

        if nt_type in (ca.ChannelType.FLOAT, ca.ChannelType.DOUBLE):
            fmt = '%g'
        elif nt_type in (ca.ChannelType.CHAR, ca.ChannelType.STRING):
            fmt = '%s'

        # self._set_charval(self._args['value'], call_ca=False)
        out.append("== %s  (%s) ==" % (self.pvname, ca.DBR_TYPES[xtype].__name__))
        if self.count == 1:
            val = self._args['value']
            out.append('   value      = %s' % fmt % val)
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
                            return "%s.%5.5i" % (time.strftime("%Y-%m-%d %H:%M:%S",
                                                               time.localtime(tstamp)),
                                                 round(1.e5*frac))

                        att = "%.3f (%s)" % (att, fmt_time(att))
                    elif nam == 'char_value':
                        att = "'%s'" % att
                    if len(nam) < 12:
                        out.append('   %.11s= %s' % (nam+' '*12, str(att)))
                    else:
                        out.append('   %.20s= %s' % (nam+' '*20, str(att)))
        if xtype == 'enum':  # list enum strings
            out.append('   enum strings: ')
            for index, nam in enumerate(self.enum_strs):
                out.append("       %i = %s " % (index, nam))

        if len(self.chid.channel.subscriptions) > 0:
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
                self.get_timevars(timeout=1, warn=False)
            else:
                self.get_ctrlvars(timeout=1, warn=False)
        return self._args.get(arg, None)

    def __repr__(self):
        "string representation"

        if self.connected:
            if self.count == 1:
                return self._fmtsca % self._args
            else:
                return self._fmtarr % self._args
        else:
            return "<PV '%s': not connected>" % self.pvname

    def __eq__(self, other):
        "test for equality"
        return False

    def disconnect(self):
        "disconnect PV"
        if self.connected:
            self.chid.disconnect()

    def __del__(self):
        if self.connected:
            self.chid.disconnect(wait=False)


_dflt_context = None


def get_pv(pvname, *args, **kwargs):
    global _dflt_context
    if _dflt_context is None:
        _dflt_context = PVContext()

    return _dflt_context.get_pv(pvname)


def caput(pvname, value, wait=False, timeout=60):
    """caput(pvname, value, wait=False, timeout=60)
    simple put to a pv's value.
       >>> caput('xx.VAL',3.0)

    to wait for pv to complete processing, use 'wait=True':
       >>> caput('xx.VAL',3.0,wait=True)
    """
    thispv = get_pv(pvname, connect=True)
    if thispv.connected:
        return thispv.put(value, wait=wait, timeout=timeout)


def caget(pvname, as_string=False, count=None, as_numpy=True,
          use_monitor=False, timeout=5.0):
    """caget(pvname, as_string=False)
    simple get of a pv's value..
       >>> x = caget('xx.VAL')

    to get the character string representation (formatted double,
    enum string, etc):
       >>> x = caget('xx.VAL', as_string=True)

    to get a truncated amount of data from an array, you can specify
    the count with
       >>> x = caget('MyArray.VAL', count=1000)
    """
    start_time = time.time()
    thispv = get_pv(pvname, timeout=timeout, connect=True)
    if thispv.connected:
        if as_string:
            thispv.get_ctrlvars()
        timeout -= (time.time() - start_time)
        val = thispv.get(count=count, timeout=timeout,
                         use_monitor=use_monitor,
                         as_string=as_string,
                         as_numpy=as_numpy)

        return val


def cainfo(pvname, print_out=True):
    """cainfo(pvname,print_out=True)

    return printable information about pv
       >>>cainfo('xx.VAL')

    will return a status report for the pv.

    If print_out=False, the status report will be printed,
    and not returned.
    """
    thispv = get_pv(pvname, connect=True)
    if thispv.connected:
        thispv.get()
        thispv.get_ctrlvars()
        if print_out:
            print(thispv.info)
        else:
            return thispv.info
