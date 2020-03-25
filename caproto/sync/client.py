# This module contains a synchronous implementation of a Channel Access client
# as three top-level functions: read, write, subscribe. They are comparatively
# simple and naive, with no caching or concurrency, and therefore less
# performant but more robust.
import inspect
import getpass
import logging
import selectors
import socket
import threading  # just to make callback processing thread-safe
import time
import weakref

import caproto as ca
from .._dbr import (field_types, ChannelType, native_type, SubscriptionType)
from .._utils import (ErrorResponseReceived, CaprotoError, CaprotoTimeoutError,
                      get_environment_variables, safe_getsockname)
from .repeater import spawn_repeater


__all__ = ('read', 'write', 'subscribe', 'block', 'interrupt',
           'read_write_read')
logger = logging.getLogger('caproto.ctx')

CA_SERVER_PORT = 5064  # just a default

# Make a dict to hold our tcp sockets.
sockets = {}
global_circuits = {}

_permission_to_block = []  # mutable state shared by block and interrupt


# Convenience functions that do both transport and caproto validation/ingest.
def send(circuit, command):
    buffers_to_send = circuit.send(command)
    sockets[circuit].sendmsg(buffers_to_send)


def recv(circuit):
    bytes_received = sockets[circuit].recv(4096)
    commands, _ = circuit.recv(bytes_received)
    for c in commands:
        circuit.process_command(c)
    return commands


def search(pv_name, udp_sock, timeout, *, max_retries=2):
    # Set Broadcaster log level to match our logger.
    b = ca.Broadcaster(our_role=ca.CLIENT)
    b.our_address = safe_getsockname(udp_sock)[:2]

    # Send registration request to the repeater
    logger.debug('Registering with the Channel Access repeater.')
    bytes_to_send = b.send(ca.RepeaterRegisterRequest())

    repeater_port = get_environment_variables()['EPICS_CA_REPEATER_PORT']
    for host in ca.get_address_list():
        try:
            udp_sock.sendto(bytes_to_send, (host, repeater_port))
        except OSError as exc:
            raise ca.CaprotoNetworkError(f"Failed to send to {host}:{repeater_port}") from exc

    logger.debug("Searching for '%s'....", pv_name)
    bytes_to_send = b.send(
        ca.VersionRequest(0, ca.DEFAULT_PROTOCOL_VERSION),
        ca.SearchRequest(pv_name, 0, ca.DEFAULT_PROTOCOL_VERSION))

    def send_search():
        for host in ca.get_address_list():
            if ':' in host:
                host, _, specified_port = host.partition(':')
                dest = (host, int(specified_port))
            else:
                dest = (host, CA_SERVER_PORT)
            try:
                udp_sock.sendto(bytes_to_send, dest)
            except OSError as exc:
                host, port = dest
                raise ca.CaprotoNetworkError(f"Failed to send to {host}:{port}") from exc
            logger.debug('Search request sent to %r.', dest)

    def check_timeout():
        nonlocal retry_at

        if time.monotonic() >= retry_at:
            send_search()
            retry_at = time.monotonic() + retry_timeout

        if time.monotonic() - t > timeout:
            raise CaprotoTimeoutError(f"Timed out while awaiting a response "
                                      f"from the search for {pv_name!r}. Search "
                                      f"requests were sent to this address list: "
                                      f"{ca.get_address_list()}.")

    # Initial search attempt
    send_search()

    # Await a search response, and keep track of registration status
    retry_timeout = timeout / max((max_retries, 1))
    t = time.monotonic()
    retry_at = t + retry_timeout

    try:
        orig_timeout = udp_sock.gettimeout()
        udp_sock.settimeout(retry_timeout)
        while True:
            try:
                bytes_received, address = udp_sock.recvfrom(ca.MAX_UDP_RECV)
            except socket.timeout:
                check_timeout()
                continue

            check_timeout()

            commands = b.recv(bytes_received, address)
            b.process_commands(commands)
            for command in commands:
                if isinstance(command, ca.SearchResponse) and command.cid == 0:
                    address = ca.extract_address(command)
                    logger.debug('Found %s at %s', pv_name, address)
                    return address
            else:
                # None of the commands we have seen are a reply to our request.
                # Receive more data.
                continue
    finally:
        udp_sock.settimeout(orig_timeout)


def make_channel(pv_name, udp_sock, priority, timeout):
    log = logging.LoggerAdapter(logging.getLogger('caproto.ch'), {'pv': pv_name})
    address = search(pv_name, udp_sock, timeout)
    try:
        circuit = global_circuits[(address, priority)]
    except KeyError:

        circuit = global_circuits[(address, priority)] = ca.VirtualCircuit(
            our_role=ca.CLIENT,
            address=address,
            priority=priority)

    chan = ca.ClientChannel(pv_name, circuit)
    new = False
    if chan.circuit not in sockets:
        new = True
        sockets[chan.circuit] = socket.create_connection(chan.circuit.address,
                                                         timeout)
        circuit.our_address = sockets[chan.circuit].getsockname()[:2]
    try:
        if new:
            # Initialize our new TCP-based CA connection with a VersionRequest.
            send(chan.circuit, ca.VersionRequest(
                priority=priority,
                version=ca.DEFAULT_PROTOCOL_VERSION))
            send(chan.circuit, chan.host_name(socket.gethostname()))
            send(chan.circuit, chan.client_name(getpass.getuser()))
        send(chan.circuit, chan.create())
        t = time.monotonic()
        while True:
            try:
                commands = recv(chan.circuit)
                if time.monotonic() - t > timeout:
                    raise socket.timeout
            except socket.timeout:
                raise CaprotoTimeoutError("Timeout while awaiting channel "
                                          "creation.")
            if chan.states[ca.CLIENT] is ca.CONNECTED:
                log.info('%s connected' % pv_name)
                break
            for command in commands:
                if command is ca.DISCONNECTED:
                    raise CaprotoError('Disconnected during initialization')

    except BaseException:
        sockets[chan.circuit].close()
        del sockets[chan.circuit]
        del global_circuits[(chan.circuit.address, chan.circuit.priority)]
        raise
    return chan


def _read(chan, timeout, data_type, notify, force_int_enums):
    logger = chan.log
    logger.debug("Detected native data_type %r.", chan.native_data_type)
    ntype = native_type(chan.native_data_type)  # abundance of caution
    if ((ntype is ChannelType.ENUM) and
            (data_type is None) and (not force_int_enums)):
        logger.debug("Changing requested data_type to STRING.")
        data_type = ChannelType.STRING
    req = chan.read(data_type=data_type, notify=notify)
    send(chan.circuit, req)
    t = time.monotonic()
    while True:
        try:
            commands = recv(chan.circuit)
        except socket.timeout:
            commands = []

        if time.monotonic() - t > timeout:
            raise CaprotoTimeoutError("Timeout while awaiting reading.")

        for command in commands:
            if (isinstance(command, (ca.ReadResponse, ca.ReadNotifyResponse)) and
                    command.ioid == req.ioid):
                return command
            elif isinstance(command, ca.ErrorResponse):
                raise ErrorResponseReceived(command)
            elif command is ca.DISCONNECTED:
                raise CaprotoError('Disconnected while waiting for '
                                   'read response')


def read(pv_name, *, data_type=None, timeout=1, priority=0, notify=True,
         force_int_enums=False, repeater=True):
    """
    Read a Channel.

    Parameters
    ----------
    pv_name : str
        The PV name to read from
    data_type : {'native', 'status', 'time', 'graphic', 'control'} or ChannelType or int ID, optional
        Request specific data type or a class of data types, matched to the
        channel's native data type. Default is Channel's native data type.
    timeout : float, optional
        Default is 1 second.
    priority : 0, optional
        Virtual Circuit priority. Default is 0, lowest. Highest is 99.
    notify : boolean, optional
        Send a ReadNotifyRequest instead of a ReadRequest. True by default.
    force_int_enums : boolean, optional
        Retrieve enums as integers. (Default is strings.)
    repeater : boolean, optional
        Spawn a Channel Access Repeater process if the port is available.
        True default, as the Channel Access spec stipulates that well-behaved
        clients should do this.

    Returns
    -------
    response : ReadResponse or ReadNotifyResponse

    Examples
    --------

    Get the value of a Channel named 'simple:A'.

    >>> read('simple:A').data
    array([1], dtype=int32)

    Request a richer Channel Access data type that includes the timestamp, and
    access the timestamp.

    >>> read('cat', data_type='time').metadata.timestmap
    1570622339.042392

    A convenience method is provided for access the timestamp as a Python
    datetime object.

    >>> read('cat' data_type='time').metadata.stamp.as_datetime()
    datetime.datetime(2019, 10, 9, 11, 58, 59, 42392)

    The requested data type may also been given as a specific Channel Access
    type

    >>> from caproto import ChannelType
    >>> read('cat', data_type=ChannelType.CTRL_FLOAT).metadata
    DBR_CTRL_FLOAT(
        status=<AlarmStatus.NO_ALARM: 0>,
        severity=<AlarmSeverity.NO_ALARM: 0>,
        upper_disp_limit=0.0,
        lower_disp_limit=0.0,
        upper_alarm_limit=0.0,
        upper_warning_limit=0.0,
        lower_warning_limit=0.0,
        lower_alarm_limit=0.0,
        upper_ctrl_limit=0.0,
        lower_ctrl_limit=0.0,
        precision=0,
        units=b'')

    or the corresponding integer identifer

    >>> read('cat', data_type=30).metadata
    DBR_CTRL_FLOAT(
    status=<AlarmStatus.NO_ALARM: 0>,
    severity=<AlarmSeverity.NO_ALARM: 0>,
    upper_disp_limit=0.0,
    lower_disp_limit=0.0,
    upper_alarm_limit=0.0,
    upper_warning_limit=0.0,
    lower_warning_limit=0.0,
    lower_alarm_limit=0.0,
    upper_ctrl_limit=0.0,
    lower_ctrl_limit=0.0,
    precision=0,
    units=b'')
    """
    if repeater:
        # As per the EPICS spec, a well-behaved client should start a
        # caproto-repeater that will continue running after it exits.
        spawn_repeater()
    udp_sock = ca.bcast_socket()
    try:
        udp_sock.settimeout(timeout)
        chan = make_channel(pv_name, udp_sock, priority, timeout)
    finally:
        udp_sock.close()
    try:
        return _read(chan, timeout, data_type=data_type, notify=notify,
                     force_int_enums=force_int_enums)
    finally:
        try:
            if chan.states[ca.CLIENT] is ca.CONNECTED:
                send(chan.circuit, chan.clear())
        finally:
            sockets[chan.circuit].close()
            del sockets[chan.circuit]
            del global_circuits[(chan.circuit.address, chan.circuit.priority)]


def subscribe(pv_name, priority=0, data_type=None, data_count=None,
              low=0.0, high=0.0, to=0.0, mask=None):
    """
    Define a subscription.

    Parameters
    ----------
    pv_name : string
        The PV name to subscribe to
    priority : integer, optional
        Used by the server to triage subscription responses when under high
        load. 0 is lowest; 99 is highest.
    data_type : {'native', 'status', 'time', 'graphic', 'control'} or ChannelType or int ID, optional
        Request specific data type or a class of data types, matched to the
        channel's native data type. Default is Channel's native data type.
    data_count : integer, optional
        Requested number of values. Default is the channel's native data
        count, which can be checked in the Channel's attribute
        :attr:`native_data_count`.
    low, high, to : float, optional
        deprecated by Channel Access, not yet implemented by caproto
    mask :  SubscriptionType, optional
        Subscribe to selective updates.

    Examples
    --------

    Define a subscription on the ``random_walk:x`` PV.

    >>> sub = subscribe('random_walk:x')

    Add one or more user-defined callbacks to process responses.

    >>> def f(response):
    ...     print(repsonse.data)
    ...
    >>> sub.add_callback(f)

    Activate the subscription and process incoming responses.

    >>> sub.block()

    This is a blocking operation in the sync client. (To do this on a
    background thread, use the threading client.) Interrupt using Ctrl+C or
    by calling :meth:`sub.interrupt()` from another thread.

    The subscription may be reactivated by calling ``sub.block()`` again.

    To process multiple subscriptions at once, use the *function*
    :func:`block`, which takes one or more Subscriptions as arguments.

    >>> block(sub1, sub2)

    There is also an :func:`interrupt` function, which is merely an alias to
    the method.
    """
    return Subscription(pv_name, priority, data_type, data_count, low, high,
                        to, mask)


def interrupt():
    """
    Signal to :func:`block` to stop blocking. Idempotent.

    This obviously cannot be called interactively while blocked;
    it is intended to be called from another thread.
    """
    _permission_to_block.clear()


def block(*subscriptions, duration=None, timeout=1, force_int_enums=False,
          repeater=True):
    """
    Activate one or more subscriptions and process incoming responses.

    Use Ctrl+C (SIGINT) to escape, or from another thread, call
    :func:`interrupt()`.

    Parameters
    ----------
    *subscriptions : Subscriptions
        The list of subscriptions.
    duration : float, optional
        How many seconds to run for. Run forever (None) by default.
    timeout : float, optional
        Default is 1 second. This is not the same as `for`; this is the timeout
        for failure in the event of no connection.
    force_int_enums : boolean, optional
        Retrieve enums as integers. (Default is strings.)
    repeater : boolean, optional
        Spawn a Channel Access Repeater process if the port is available.
        True default, as the Channel Access spec stipulates that well-behaved
        clients should do this.

    Examples
    --------

    Activate subscription(s) and block while they process updates.

    >>> sub1 = subscribe('cat')
    >>> sub1 = subscribe('dog')
    >>> block(sub1, sub2)
    """
    _permission_to_block.append(object())
    if duration is not None:
        deadline = time.time() + duration
    else:
        deadline = None
    if repeater:
        # As per the EPICS spec, a well-behaved client should start a
        # caproto-repeater that will continue running after it exits.
        spawn_repeater()
    loggers = {}
    for sub in subscriptions:
        loggers[sub.pv_name] = logging.LoggerAdapter(logging.getLogger('caproto.ch'),
                                                     {'pv': sub.pv_name})
    udp_sock = ca.bcast_socket()
    try:
        udp_sock.settimeout(timeout)
        channels = {}
        for sub in subscriptions:
            pv_name = sub.pv_name
            chan = make_channel(pv_name, udp_sock, sub.priority, timeout)
            channels[sub] = chan
    finally:
        udp_sock.close()
    try:
        # Subscribe to all the channels.
        sub_ids = {}
        for sub, chan in channels.items():
            loggers[chan.name].debug("Detected native data_type %r.",
                                     chan.native_data_type)

            # abundance of caution
            ntype = field_types['native'][chan.native_data_type]
            if ((ntype is ChannelType.ENUM) and (not force_int_enums)):
                ntype = ChannelType.STRING
            time_type = field_types['time'][ntype]
            # Adjust the timeout during monitoring.
            sockets[chan.circuit].settimeout(None)
            loggers[chan.name].debug("Subscribing with data_type %r.",
                                     time_type)
            req = chan.subscribe(data_type=time_type, mask=sub.mask)
            send(chan.circuit, req)
            sub_ids[(chan.circuit, req.subscriptionid)] = sub
        logger.debug('Subscribed. Building socket selector.')
        try:
            circuits = set(chan.circuit for chan in channels.values())
            selector = selectors.DefaultSelector()
            sock_to_circuit = {}
            for circuit in circuits:
                sock = sockets[circuit]
                sock_to_circuit[sock] = circuit
                selector.register(sock, selectors.EVENT_READ)
            if duration is None:
                logger.debug('Continuing until SIGINT is received....')
            while True:
                events = selector.select(timeout=0.1)
                if deadline is not None and time.time() > deadline:
                    logger.debug('Deadline reached.')
                    return
                if not _permission_to_block:
                    logger.debug("Interrupted via "
                                 "caproto.sync.client.interrupt().")
                    break
                for selector_key, mask in events:
                    circuit = sock_to_circuit[selector_key.fileobj]
                    commands = recv(circuit)
                    for response in commands:
                        if isinstance(response, ca.ErrorResponse):
                            raise ErrorResponseReceived(response)
                        if response is ca.DISCONNECTED:
                            # TODO Re-connect.
                            raise CaprotoError("Disconnected")
                        sub = sub_ids.get((circuit, response.subscriptionid))
                        if sub:
                            sub.process(response)
        except KeyboardInterrupt:
            logger.debug('Received SIGINT. Closing.')
            pass
    finally:
        _permission_to_block.clear()
        try:
            for chan in channels.values():
                if chan.states[ca.CLIENT] is ca.CONNECTED:
                    send(chan.circuit, chan.clear())
        finally:
            # Reinstate the timeout for channel cleanup.
            for chan in channels.values():
                sockets[chan.circuit].settimeout(timeout)
                sockets[chan.circuit].close()
                del sockets[chan.circuit]
                del global_circuits[(chan.circuit.address, chan.circuit.priority)]


def _write(chan, data, metadata, timeout, data_type, notify):
    logger.debug("Detected native data_type %r.", chan.native_data_type)
    # abundance of caution
    ntype = field_types['native'][chan.native_data_type]
    if (data_type is None) and (ntype is ChannelType.ENUM):
        # Change data_type to STRING if data contains string-like data, or
        # iterable of string-like data
        stringy_data = False
        if isinstance(data, (str, bytes)):
            stringy_data = True
        if hasattr(data, '__getitem__') \
                and len(data) > 0 \
                and isinstance(data[0], (str, bytes)):
            stringy_data = True

        if stringy_data:
            logger.debug("Will write to ENUM as data_type STRING.")
            data_type = ChannelType.STRING
    logger.debug("Writing.")
    req = chan.write(data=data, notify=notify,
                     data_type=data_type, metadata=metadata)
    send(chan.circuit, req)
    t = time.monotonic()
    if notify:
        while True:
            try:
                commands = recv(chan.circuit)
            except socket.timeout:
                commands = []

            if time.monotonic() - t > timeout:
                raise CaprotoTimeoutError("Timeout while awaiting write reply.")

            for command in commands:
                if (isinstance(command, ca.WriteNotifyResponse) and
                        command.ioid == req.ioid):
                    response = command
                    break
                elif isinstance(command, ca.ErrorResponse):
                    raise ErrorResponseReceived(command)
                elif command is ca.DISCONNECTED:
                    raise CaprotoError('Disconnected while waiting for '
                                       'write response')
            else:
                continue
            break
        return response
    else:
        return None


def write(pv_name, data, *, notify=False, data_type=None, metadata=None,
          timeout=1, priority=0,
          repeater=True):
    """
    Write to a Channel.

    Parameters
    ----------
    pv_name : str
        The PV name to write to
    data : str, bytes, int, or float or any Iterable of these
        Value(s) to write.
    notify : boolean, optional
        Request notification of completion and wait for it. False by default.
    data_type : {'native', 'status', 'time', 'graphic', 'control'} or ChannelType or int ID, optional
        Write as specific data type. Default is inferred from input.
    metadata : ``ctypes.BigEndianStructure`` or tuple
        Status and control metadata for the values
    timeout : float, optional
        Default is 1 second.
    priority : 0, optional
        Virtual Circuit priority. Default is 0, lowest. Highest is 99.
    repeater : boolean, optional
        Spawn a Channel Access Repeater process if the port is available.
        True default, as the Channel Access spec stipulates that well-behaved
        clients should do this.

    Returns
    -------
    initial, final : tuple of ReadNotifyResponse objects

    Examples
    --------
    Write the value 5 to a Channel named 'simple:A'.

    >>> write('simple:A', 5)  # returns None

    Request notification of completion ("put completion") and wait for it.
    >>> write('cat', 5, notify=True)  # blocks until complete, then returns:
    WriteNotifyResponse(
    data_type=<ChannelType.LONG: 5>,
    data_count=1,
    status=CAStatusCode(
    name='ECA_NORMAL', code=0, code_with_severity=1,
    severity=<CASeverity.SUCCESS: 1>,
    success=1, defunct=False,
    description='Normal successful completion'),
    ioid=0)
    """
    if repeater:
        # As per the EPICS spec, a well-behaved client should start a
        # caproto-repeater that will continue running after it exits.
        spawn_repeater()

    udp_sock = ca.bcast_socket()
    try:
        udp_sock.settimeout(timeout)
        chan = make_channel(pv_name, udp_sock, priority, timeout)
    finally:
        udp_sock.close()
    try:
        return _write(chan, data, metadata, timeout, data_type, notify)
    finally:
        try:
            if chan.states[ca.CLIENT] is ca.CONNECTED:
                send(chan.circuit, chan.clear())
        finally:
            sockets[chan.circuit].close()
            del sockets[chan.circuit]
            del global_circuits[(chan.circuit.address, chan.circuit.priority)]


def read_write_read(pv_name, data, *, notify=False,
                    read_data_type=None, write_data_type=None,
                    metadata=None, timeout=1, priority=0,
                    force_int_enums=False, repeater=True):
    """
    Write to a Channel, but sandwich the write between to reads.

    This is what the command-line utilities ``caproto-put`` and ``caput`` do.
    Notice that if you want the second reading to reflect the written value,
    you should pass the parameter ``notify=True``. (This is also true of
    ``caproto-put``/``caput``, which needs the ``-c`` argument to behave the
    way you might expect it to behave.)

    This is provided as a separate function in order to support ``caproto-put``
    efficiently. Making separate calls to :func:`read` and :func:`write` would
    re-create a connection redundantly.

    Parameters
    ----------
    pv_name : str
        The PV name to write/read/write
    data : str, bytes, int, or float or any Iterable of these
        Value to write.
    notify : boolean, optional
        Request notification of completion and wait for it. False by default.
    read_data_type : {'native', 'status', 'time', 'graphic', 'control'} or ChannelType or int ID, optional
        Request specific data type.
    write_data_type : {'native', 'status', 'time', 'graphic', 'control'} or ChannelType or int ID, optional
        Write as specific data type. Default is inferred from input.
    metadata : ``ctypes.BigEndianStructure`` or tuple
        Status and control metadata for the values
    timeout : float, optional
        Default is 1 second.
    priority : 0, optional
        Virtual Circuit priority. Default is 0, lowest. Highest is 99.
    force_int_enums : boolean, optional
        Retrieve enums as integers. (Default is strings.)
    repeater : boolean, optional
        Spawn a Channel Access Repeater process if the port is available.
        True default, as the Channel Access spec stipulates that well-behaved
        clients should do this.

    Returns
    -------
    initial, write_response, final : tuple of response

    The middle response comes from the write, and it will be ``None`` unless
    ``notify=True``.

    Examples
    --------

    Write the value 5 to a Channel named 'simple:A'.

    >>> read_write_read('cat', 5)  # returns initial, None, final

    Request notification of completion ("put completion") and wait for it.

    >>> read_write_read('cat', 5, notify=True)  # initial, WriteNotifyResponse, final
    """
    if repeater:
        # As per the EPICS spec, a well-behaved client should start a
        # caproto-repeater that will continue running after it exits.
        spawn_repeater()

    udp_sock = ca.bcast_socket()
    try:
        udp_sock.settimeout(timeout)
        chan = make_channel(pv_name, udp_sock, priority, timeout)
    finally:
        udp_sock.close()
    try:
        initial = _read(chan, timeout, read_data_type, notify=True,
                        force_int_enums=force_int_enums)
        res = _write(chan, data, metadata, timeout, write_data_type, notify)
        final = _read(chan, timeout, read_data_type, notify=True,
                      force_int_enums=force_int_enums)
    finally:
        try:
            if chan.states[ca.CLIENT] is ca.CONNECTED:
                send(chan.circuit, chan.clear())
        finally:
            sockets[chan.circuit].close()
            del sockets[chan.circuit]
            del global_circuits[(chan.circuit.address, chan.circuit.priority)]
    return initial, res, final


class Subscription:
    """
    This object encapsulates state related to a Subscription.

    See the :func:`subscribe` function.
    """
    def __init__(self, pv_name, priority=0, data_type=None, data_count=None,
                 low=0.0, high=0.0, to=0.0, mask=None):
        if mask is None:
            mask = SubscriptionType.DBE_VALUE | SubscriptionType.DBE_ALARM
        self.pv_name = pv_name
        self.priority = priority
        self.data_type = data_type
        self.data_count = data_count
        self.low = low
        self.high = high
        self.to = to
        self.mask = mask

        self.callbacks = {}
        self._callback_id = 0
        self._callback_lock = threading.RLock()

    def block(self, duration=None, timeout=1,
              force_int_enums=False,
              repeater=True):
        """
        Activate one or more subscriptions and process incoming responses.

        Use Ctrl+C (SIGINT) to escape, or from another thread, call
        :meth:`interrupt()`.

        Convenience alias for the top-level function :func:`block`, which may
        be used to process multiple Subscriptions concurrently.

        Parameters
        ----------

        duration : float, optional
            How many seconds to run for. Run forever (None) by default.
        timeout : float, optional
            Default is 1 second. This is not the same as `for`; this is the
            timeout for failure in the event of no connection.
        force_int_enums : boolean, optional
            Retrieve enums as integers. (Default is strings.)
        repeater : boolean, optional
            Spawn a Channel Access Repeater process if the port is available.
            True default, as the Channel Access spec stipulates that
            well-behaved clients should do this.
        """
        block(self, duration=duration, timeout=timeout,
              force_int_enums=force_int_enums,
              repeater=repeater)

    def interrupt(self):
        """
        Signal to block() to stop blocking. Idempotent.

        This obviously cannot be called interactively while blocked;
        it is intended to be called from another thread.
        This method is a convenience alias for the top-level function
        :func:`interrupt`.
        """
        interrupt()

    def add_callback(self, func):
        """
        Add a callback to receive responses.

        Parameters
        ----------
        func : callable
            Expected signature: ``func(response)``

        Returns
        -------
        token : int
            Integer token that can be passed to :meth:`remove_callback`.
        """
        def removed(_):
            self.remove_callback(cb_id)

        if inspect.ismethod(func):
            ref = weakref.WeakMethod(func, removed)
        else:
            # TODO: strong reference to non-instance methods?
            ref = weakref.ref(func, removed)

        with self._callback_lock:
            cb_id = self._callback_id
            self._callback_id += 1
            self.callbacks[cb_id] = ref
        return cb_id

    def remove_callback(self, cb_id):
        """
        Remove callback using token that was returned by :meth:`add_callback`.
        """
        with self._callback_lock:
            self.callbacks.pop(cb_id, None)

    def process(self, response):
        """
        Run the callbacks on a response.

        This is used internally by :func:`block()`, generally not called by the
        user.
        """
        to_remove = []
        with self._callback_lock:
            callbacks = list(self.callbacks.items())

        for cb_id, ref in callbacks:
            callback = ref()
            if callback is None:
                to_remove.append(cb_id)
                continue

            callback(response)

        with self._callback_lock:
            for remove_id in to_remove:
                self.callbacks.pop(remove_id, None)

    def clear(self):
        """
        Remove all callbacks. If currently blocking, interrupt.
        """
        interrupt()
        with self._callback_lock:
            for cb_id in list(self.callbacks):
                self.remove_callback(cb_id)
