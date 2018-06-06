# This module contains a synchronous implementation of a Channel Access client
# as three top-level functions: read, write, subscribe. They are comparatively
# simple and naive, with no caching or concurrency, and therefore less
# performant but more robust.

import ast
from collections import Iterable
import inspect
import getpass
import logging
import os
import selectors
import socket
import threading  # just to make callback processing thread-safe
import time
import weakref

import caproto as ca
from .._dbr import (field_types, ChannelType, native_type, SubscriptionType)
from .._utils import ErrorResponseReceived, CaprotoError
from .repeater import spawn_repeater


__all__ = ['read', 'write', 'subscribe', 'block']
logger = logging.getLogger('caproto')

CA_SERVER_PORT = 5064  # just a default

# Make a dict to hold our tcp sockets.
sockets = {}

poison_pill = False


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

    # Send registration request to the repeater
    logger.debug('Registering with the Channel Access repeater.')
    bytes_to_send = b.send(ca.RepeaterRegisterRequest())

    repeater_port = os.environ.get('EPICS_CA_REPEATER_PORT', 5065)
    for host in ca.get_address_list():
        udp_sock.sendto(bytes_to_send, (host, repeater_port))

    logger.debug("Searching for '%s'....", pv_name)
    bytes_to_send = b.send(ca.VersionRequest(0, 13),
                           ca.SearchRequest(pv_name, 0, 13))

    def send_search():
        for host in ca.get_address_list():
            if ':' in host:
                host, _, specified_port = host.partition(':')
                dest = (host, int(specified_port))
            else:
                dest = (host, CA_SERVER_PORT)
            udp_sock.sendto(bytes_to_send, dest)
            logger.debug('Search request sent to %r.', dest)

    def check_timeout():
        nonlocal retry_at

        if time.monotonic() >= retry_at:
            send_search()
            retry_at = time.monotonic() + retry_timeout

        if time.monotonic() - t > timeout:
            raise TimeoutError(f"Timed out while awaiting a response "
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
                    return ca.extract_address(command)
            else:
                # None of the commands we have seen are a reply to our request.
                # Receive more data.
                continue
    finally:
        udp_sock.settimeout(orig_timeout)


def make_channel(pv_name, udp_sock, priority, timeout):
    address = search(pv_name, udp_sock, timeout)
    circuit = ca.VirtualCircuit(our_role=ca.CLIENT,
                                address=address,
                                priority=priority)
    chan = ca.ClientChannel(pv_name, circuit)
    sockets[chan.circuit] = socket.create_connection(chan.circuit.address,
                                                     timeout)

    try:
        # Initialize our new TCP-based CA connection with a VersionRequest.
        send(chan.circuit, ca.VersionRequest(priority=priority, version=13))
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
                raise TimeoutError("Timeout while awaiting channel creation.")
            if chan.states[ca.CLIENT] is ca.CONNECTED:
                break
            for command in commands:
                if command is ca.DISCONNECTED:
                    raise CaprotoError('Disconnected during initialization')

    except BaseException:
        sockets[chan.circuit].close()
        raise
    return chan


def _read(chan, timeout, data_type):
    req = chan.read(data_type=data_type)
    send(chan.circuit, req)
    t = time.monotonic()
    while True:
        try:
            commands = recv(chan.circuit)
        except socket.timeout:
            commands = []

        if time.monotonic() - t > timeout:
            raise TimeoutError("Timeout while awaiting reading.")

        for command in commands:
            if (isinstance(command, ca.ReadNotifyResponse) and
                    command.ioid == req.ioid):
                return command
            elif isinstance(command, ca.ErrorResponse):
                raise ErrorResponseReceived(command)
            elif command is ca.DISCONNECTED:
                raise CaprotoError('Disconnected while waiting for '
                                   'read response')


def read(pv_name, *, data_type=None, timeout=1, priority=0,
         force_int_enums=False, repeater=True):
    """
    Read a Channel.

    Parameters
    ----------
    pv_name : str
    data_type : int, optional
        Request specific data type. Default is Channel's native data type.
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
    response : ReadNotifyResponse

    Examples
    --------
    Get the value of a Channel named 'cat'.
    >>> get('cat').data
    """
    logger = logging.getLogger(f'caproto.ch.{pv_name}')
    if repeater:
        # As per the EPICS spec, a well-behaved client should start a
        # caproto-repeater that will continue running after it exits.
        spawn_repeater(['--quiet'])
    udp_sock = ca.bcast_socket()
    try:
        udp_sock.settimeout(timeout)
        chan = make_channel(pv_name, udp_sock, priority, timeout)
    finally:
        udp_sock.close()
    try:
        logger.debug("Detected native data_type %r.", chan.native_data_type)
        ntype = native_type(chan.native_data_type)  # abundance of caution
        if ((ntype is ChannelType.ENUM) and
                (data_type is None) and (not force_int_enums)):
            logger.debug("Changing requested data_type to STRING.")
            data_type = ChannelType.STRING
        return _read(chan, timeout, data_type=data_type)
    finally:
        try:
            if chan.states[ca.CLIENT] is ca.CONNECTED:
                send(chan.circuit, chan.disconnect())
        finally:
            sockets[chan.circuit].close()


def subscribe(pv_name, priority=0, data_type=None, data_count=None,
              low=0.0, high=0.0, to=0.0, mask=None):
    return Subscription(pv_name, priority, data_type, data_count, low, high,
                        to, mask)


def interrupt():
    global poison_pill
    poison_pill = True


def block(*subscriptions, duration=None, timeout=1, force_int_enums=False,
          repeater=True):
    """
    Monitor one or more Channels indefinitely.

    Use Ctrl+C (SIGINT) to escape, or from another thread, call interrupt().

    Parameters
    ----------
    *subscriptions : Subscriptions
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
    if duration is not None:
        deadline = time.time() + duration
    else:
        deadline = None
    if repeater:
        # As per the EPICS spec, a well-behaved client should start a
        # caproto-repeater that will continue running after it exits.
        spawn_repeater(['--quiet'])
    loggers = {}
    for sub in subscriptions:
        loggers[sub.pv_name] = logging.getLogger(f'caproto.ch.{sub.pv_name}')
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
            sub_ids[req.subscriptionid] = sub
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
                global poison_pill
                if poison_pill:
                    poison_pill = False
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
                        sub = sub_ids.get(response.subscriptionid)
                        if sub:
                            sub.process(response)
        except KeyboardInterrupt:
            logger.debug('Received SIGINT. Closing.')
            pass
    finally:
        try:
            for chan in channels.values():
                if chan.states[ca.CLIENT] is ca.CONNECTED:
                    send(chan.circuit, chan.disconnect())
        finally:
            # Reinstate the timeout for channel cleanup.
            for chan in channels.values():
                sockets[chan.circuit].settimeout(timeout)
                sockets[chan.circuit].close()


def write(pv_name, data, *, data_type=None, metadata=None,
          timeout=1, priority=0,
          repeater=True):
    """
    Write to a Channel.

    Parameters
    ----------
    pv_name : str
    data : str, int, or float or a list of these
        Value to write.
    data_type : int, optional
        Request specific data type. Default is inferred from input.
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
    Write the value 5 to a Channel named 'cat'.
    >>> initial, final = put('cat', 5)
    """
    raw_data = data
    logger = logging.getLogger(f'caproto.ch.{pv_name}')
    if repeater:
        # As per the EPICS spec, a well-behaved client should start a
        # caproto-repeater that will continue running after it exits.
        spawn_repeater(['--quiet'])
    if isinstance(raw_data, str):
        try:
            data = ast.literal_eval(raw_data)
        except ValueError:
            # interpret as string
            data = raw_data
    if not isinstance(data, Iterable) or isinstance(data, (str, bytes)):
        data = [data]
    if data and isinstance(data[0], str):
        data = [val.encode('latin-1') for val in data]
    logger.debug('Data argument %s parsed as %r.', raw_data, data)

    udp_sock = ca.bcast_socket()
    try:
        udp_sock.settimeout(timeout)
        chan = make_channel(pv_name, udp_sock, priority, timeout)
    finally:
        udp_sock.close()
    try:
        logger.debug("Detected native data_type %r.", chan.native_data_type)
        # abundance of caution
        ntype = field_types['native'][chan.native_data_type]
        # Stash initial value
        logger.debug("Taking 'initial' reading before writing.")
        initial_response = _read(chan, timeout, None)

        if data_type is None:
            # Handle ENUM: If data is INT, carry on. If data is STRING,
            # write it specifically as STRING data_Type.
            if (ntype is ChannelType.ENUM) and isinstance(data[0], bytes):
                logger.debug("Will write to ENUM as data_type STRING.")
                data_type = ChannelType.STRING
        logger.debug("Writing.")
        req = chan.write(data=data, data_type=data_type, metadata=metadata)
        send(chan.circuit, req)
        t = time.monotonic()
        while True:
            try:
                commands = recv(chan.circuit)
            except socket.timeout:
                commands = []

            if time.monotonic() - t > timeout:
                raise TimeoutError("Timeout while awaiting write reply.")

            for command in commands:
                if (isinstance(command, ca.WriteNotifyResponse) and
                        command.ioid == req.ioid):
                    break
                elif isinstance(command, ca.ErrorResponse):
                    raise ErrorResponseReceived(command)
                elif command is ca.DISCONNECTED:
                    raise CaprotoError('Disconnected while waiting for '
                                       'write response')
            else:
                continue
            break
        logger.debug("Taking 'final' reading after writing.")
        final_response = _read(chan, timeout, None)
    finally:
        try:
            if chan.states[ca.CLIENT] is ca.CONNECTED:
                send(chan.circuit, chan.disconnect())
        finally:
            sockets[chan.circuit].close()
    return initial_response, final_response


class Subscription:
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

    def block(self, *subscriptions, duration=None, timeout=1,
              force_int_enums=False,
              repeater=True):
        block(self, *subscriptions, duration=None, timeout=1,
              force_int_enums=False,
              repeater=True)

    def interrupt(self):
        interrupt()

    def add_callback(self, func):
        with self._callback_lock:
            cb_id = self._callback_id
            self._callback_id += 1

            def removed(_):
                self.remove_callback(cb_id)

            if inspect.ismethod(func):
                ref = weakref.WeakMethod(func, removed)
            else:
                # TODO: strong reference to non-instance methods?
                ref = weakref.ref(func, removed)

            self.callbacks[cb_id] = ref
        return cb_id

    def remove_callback(self, cb_id):
        with self._callback_lock:
            self.callbacks.pop(cb_id, None)

    def process(self, response):
        """
        This is a fast operation that submits jobs to the Context's
        ThreadPoolExecutor and then returns.
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
