# This module contains a synchronous implementation of a Channel Access client
# as three top-level functions: get, put, and monitor. They are comparatively
# simple and naive, with no caching or concurrency, and therefore less
# performant but more robust.

# The module also includes variants intended for use at the command line
# (get_cli, put_cli, monitor_cli) which layers argparse on top of the get, put
# and monitor. These can be called directly from the shell using the scripts
# caproto-get, caproto-put, and caproto-monitor, which are added to the PATH
# when caproto is installed.

# Additionally, there is repeater_cli and caproto-repeater, which spawns a
# repeater in a detached subprocess.

import argparse
import ast
from collections import Iterable
from datetime import datetime
import getpass
import logging
import os
import time
import selectors
import socket
import subprocess
import sys

import caproto as ca
from .._dbr import (field_types, ChannelType, native_type, SubscriptionType)
from .._utils import ErrorResponseReceived, CaprotoError
from .repeater import run as run_repeater


__all__ = ['get', 'put', 'monitor']


CA_SERVER_PORT = 5064  # just a default

# Make a dict to hold our tcp sockets.
sockets = {}

ca_logger = logging.getLogger()
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter('[%(name)s] %(message)s'))
ca_logger.addHandler(handler)


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


def search(pv_name, logger, udp_sock, timeout, *, max_retries=2):
    # Set Broadcaster log level to match our logger.
    b = ca.Broadcaster(our_role=ca.CLIENT)
    b.log.setLevel(logger.level)

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
                               f"from the search for {pv_name!r}")

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


def make_channel(pv_name, logger, udp_sock, priority, timeout):
    address = search(pv_name, logger, udp_sock, timeout)
    circuit = ca.VirtualCircuit(our_role=ca.CLIENT,
                                address=address,
                                priority=priority)
    # Set circuit log level to match our logger.
    circuit.log.setLevel(logger.level)
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
                recv(chan.circuit)
                if time.monotonic() - t > timeout:
                    raise socket.timeout
            except socket.timeout:
                raise TimeoutError("Timeout while awaiting channel creation.")
            if chan.states[ca.CLIENT] is ca.CONNECTED:
                break

        logger.debug('Channel created.')
    except BaseException:
        sockets[chan.circuit].close()
        raise
    return chan


def spawn_repeater(logger):
    try:
        subprocess.Popen(['caproto-repeater', '--quiet'], cwd="/",
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except Exception:
        logger.exception('Failed to spawn repeater.')
    logger.debug('Spawned caproto-repeater process.')


def read(chan, timeout, data_type):
    req = chan.read(data_type=data_type)
    send(chan.circuit, req)
    t = time.monotonic()
    while True:
        try:
            commands = recv(chan.circuit)
            if time.monotonic() - t > timeout:
                raise socket.timeout
        except socket.timeout:
            raise TimeoutError("Timeout while awaiting reading.")
        for command in commands:
            if (isinstance(command, ca.ReadNotifyResponse) and
                    command.ioid == req.ioid):
                response = command
                break
            elif isinstance(command, ca.ErrorResponse):
                raise ErrorResponseReceived(command)
            elif command is ca.DISCONNECTED:
                raise CaprotoError('Disconnected while waiting for '
                                   'read response')
        else:
            continue
        break
    return response


def get_cli():
    parser = argparse.ArgumentParser(description='Read the value of a PV.')
    parser.register('action', 'list_types', _ListTypesAction)
    fmt_group = parser.add_mutually_exclusive_group()
    parser.add_argument('pv_names', type=str, nargs='+',
                        help="PV (channel) name(s) separated by spaces")
    parser.add_argument('-d', type=str, default=None, metavar="DATA_TYPE",
                        help=("Request a certain data type. Accepts numeric "
                              "code ('3') or case-insensitive string ('enum')"
                              ". See --list-types"))
    fmt_group.add_argument('--format', type=str,
                           help=("Python format string. Available tokens are "
                                 "{pv_name} and {response}. Additionally, if "
                                 "this data type includes time, {timestamp} "
                                 "and usages like "
                                 "{timestamp:%%Y-%%m-%%d %%H:%%M:%%S} are "
                                 "supported."))
    parser.add_argument('--list-types', action='list_types',
                        default=argparse.SUPPRESS,
                        help="List allowed values for -d and exit.")
    parser.add_argument('-n', action='store_true',
                        help=("Retrieve enums as integers (default is "
                              "strings)."))
    parser.add_argument('--no-repeater', action='store_true',
                        help=("Do not spawn a Channel Access repeater daemon "
                              "process."))
    parser.add_argument('--priority', '-p', type=int, default=0,
                        help="Channel Access Virtual Circuit priority. "
                             "Lowest is 0; highest is 99.")
    fmt_group.add_argument('--terse', '-t', action='store_true',
                           help=("Display data only. Unpack scalars: "
                                 "[3.] -> 3."))
    parser.add_argument('--timeout', '-w', type=float, default=1,
                        help=("Timeout ('wait') in seconds for server "
                              "responses."))
    parser.add_argument('--verbose', '-v', action='store_true',
                        help="Show DEBUG log messages.")
    args = parser.parse_args()
    data_type = parse_data_type(args.d)
    try:
        for pv_name in args.pv_names:
            response = get(pv_name=pv_name,
                           data_type=data_type,
                           verbose=args.verbose, timeout=args.timeout,
                           priority=args.priority,
                           force_int_enums=args.n,
                           repeater=not args.no_repeater)
            if args.format is None:
                format_str = '{pv_name: <40}  {response.data}'
            else:
                format_str = args.format
            if args.terse:
                if len(response.data) == 1:
                    format_str = '{response.data[0]}'
                else:
                    format_str = '{response.data}'
            tokens = dict(pv_name=pv_name, response=response)
            if hasattr(response.metadata, 'timestamp'):
                dt = datetime.fromtimestamp(response.metadata.timestamp)
                tokens['timestamp'] = dt
            print(format_str.format(**tokens))

    except BaseException as exc:
        if args.verbose:
            # Show the full traceback.
            raise
        else:
            # Print a one-line error message.
            print(exc)


def get(pv_name, *, data_type=None, verbose=False, timeout=1, priority=0,
        force_int_enums=False, repeater=True):
    """
    Read a Channel.

    Parameters
    ----------
    pv_name : str
    data_type : int, optional
        Request specific data type. Default is Channel's native data type.
    verbose : boolean, optional
        Verbose logging. Default is False.
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
    logger = logging.getLogger('get')
    if verbose:
        level = 'DEBUG'
    else:
        level = 'INFO'
    logger.setLevel(level)
    handler.setLevel(level)
    ca_logger.setLevel(level)

    if repeater:
        # As per the EPICS spec, a well-behaved client should start a
        # caproto-repeater that will continue running after it exits.
        spawn_repeater(logger)
    udp_sock = ca.bcast_socket()
    try:
        udp_sock.settimeout(timeout)
        chan = make_channel(pv_name, logger, udp_sock, priority, timeout)
    finally:
        udp_sock.close()
    try:
        logger.debug("Detected native data_type %r.", chan.native_data_type)
        ntype = native_type(chan.native_data_type)  # abundance of caution
        if ((ntype is ChannelType.ENUM) and
                (data_type is None) and (not force_int_enums)):
            logger.debug("Changing requested data_type to STRING.")
            data_type = ChannelType.STRING
        return read(chan, timeout, data_type=data_type)
    finally:
        try:
            if chan.states[ca.CLIENT] is ca.CONNECTED:
                send(chan.circuit, chan.disconnect())
        finally:
            sockets[chan.circuit].close()


def monitor_cli():
    parser = argparse.ArgumentParser(description='Read the value of a PV.')
    fmt_group = parser.add_mutually_exclusive_group()
    parser.add_argument('pv_names', type=str, nargs='+',
                        help="PV (channel) name")
    fmt_group.add_argument('--format', type=str,
                           help=("Python format string. Available tokens are "
                                 "{pv_name} and {response}. Additionally, if "
                                 "this data type includes time, {timestamp}, "
                                 "{timedelta} and usages like "
                                 "{timestamp:%%Y-%%m-%%d %%H:%%M:%%S} are "
                                 "supported."))
    parser.add_argument('-m', type=str, metavar='MASK', default='va',
                        help=("Channel Access mask. Any combination of "
                              "'v' (value), 'a' (alarm), 'l' (log/archive), "
                              "'p' (property). Default is 'va'."))
    parser.add_argument('-n', action='store_true',
                        help=("Retrieve enums as integers (default is "
                              "strings)."))
    parser.add_argument('--no-repeater', action='store_true',
                        help=("Do not spawn a Channel Access repeater daemon "
                              "process."))
    parser.add_argument('--priority', '-p', type=int, default=0,
                        help="Channel Access Virtual Circuit priority. "
                             "Lowest is 0; highest is 99.")
    parser.add_argument('--timeout', '-w', type=float, default=1,
                        help=("Timeout ('wait') in seconds for server "
                              "responses."))
    parser.add_argument('--verbose', '-v', action='store_true',
                        help="Show DEBUG log messages.")
    args = parser.parse_args()

    mask = 0
    if 'v' in args.m:
        mask |= SubscriptionType.DBE_VALUE
    if 'a' in args.m:
        mask |= SubscriptionType.DBE_ALARM
    if 'l' in args.m:
        mask |= SubscriptionType.DBE_LOG
    if 'p' in args.m:
        mask |= SubscriptionType.DBE_PROPERTY

    history = []

    def callback(pv_name, response):
        if args.format is None:
            format_str = ("{pv_name: <40}  {timestamp:%Y-%m-%d %H:%M:%S} "
                          "{response.data}")
        else:
            format_str = args.format
        tokens = dict(pv_name=pv_name, response=response)
        dt = datetime.fromtimestamp(response.metadata.timestamp)
        tokens['timestamp'] = dt
        if history:
            # Add a {timedelta} token using the previous timestamp.
            td = dt - history.pop()
        else:
            # Special case for the first reading: show difference between
            # timestamp and current time -- showing how old the most recent
            # update is.
            td = datetime.fromtimestamp(time.time()) - dt
        history.append(dt)
        tokens['timedelta'] = td
        print(format_str.format(**tokens), flush=True)
    try:
        monitor(*args.pv_names,
                callback=callback, mask=mask,
                verbose=args.verbose, timeout=args.timeout,
                priority=args.priority,
                force_int_enums=args.n,
                repeater=not args.no_repeater)
    except BaseException as exc:
        if args.verbose:
            # Show the full traceback.
            raise
        else:
            # Print a one-line error message.
            print(exc)


def monitor(*pv_names, callback, mask=None, verbose=False, timeout=1,
            priority=0, force_int_enums=False, repeater=True):
    """
    Monitor one or more Channels indefinitely.

    Use Ctrl+C (SIGINT) to escape.

    Parameters
    ----------
    pv_names : str
    callback : callable, required keyword-only argument
        Expected signature is ``f(pv_name, ReadNotifyResponse)``.
    mask : int, optional
        Default, None, resolves to
        ``(SubscriptionType.DBE_VALUE | SubscriptionType.DBE_ALARM)``.
    data_type : int, optional
        Request specific data type. Default is Channel's native data type.
    verbose : boolean, optional
        Verbose logging. Default is False.
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

    Examples
    --------
    Get the value of a Channel named 'cat'.
    >>> get('cat').data
    """
    if mask is None:
        mask = SubscriptionType.DBE_VALUE | SubscriptionType.DBE_ALARM
    logger = logging.getLogger('monitor')
    if verbose:
        level = 'DEBUG'
    else:
        level = 'INFO'
    logger.setLevel(level)
    handler.setLevel(level)
    ca_logger.setLevel(level)

    if repeater:
        # As per the EPICS spec, a well-behaved client should start a
        # caproto-repeater that will continue running after it exits.
        spawn_repeater(logger)
    udp_sock = ca.bcast_socket()
    try:
        udp_sock.settimeout(timeout)
        channels = []
        for pv_name in pv_names:
            chan = make_channel(pv_name, logger, udp_sock, priority, timeout)
            channels.append(chan)
    finally:
        udp_sock.close()
    try:
        # Subscribe to all the channels.
        sub_ids = {}
        for chan in channels:
            logger.debug("Detected native data_type %r.",
                         chan.native_data_type)

            # abundance of caution
            ntype = field_types['native'][chan.native_data_type]
            if ((ntype is ChannelType.ENUM) and (not force_int_enums)):
                ntype = ChannelType.STRING
            time_type = field_types['time'][ntype]
            # Adjust the timeout during monitoring.
            sockets[chan.circuit].settimeout(None)
            logger.debug("Subscribing with data_type %r.", time_type)
            req = chan.subscribe(data_type=time_type, mask=mask)
            send(chan.circuit, req)
            sub_ids[req.subscriptionid] = chan
        logger.debug('Subscribed. Building socket selector.')
        try:
            circuits = set(chan.circuit for chan in channels)
            selector = selectors.DefaultSelector()
            sock_to_circuit = {}
            for circuit in circuits:
                sock = sockets[circuit]
                sock_to_circuit[sock] = circuit
                selector.register(sock, selectors.EVENT_READ)
            logger.debug('Continuing until SIGINT is received....')
            while True:
                events = selector.select(timeout=0.1)
                for selector_key, mask in events:
                    circuit = sock_to_circuit[selector_key.fileobj]
                    commands = recv(circuit)
                    for response in commands:
                        if isinstance(response, ca.ErrorResponse):
                            raise ErrorResponseReceived(response)
                        if isinstance(response, ca.DISCONNECTED):
                            # TODO Re-connect.
                            raise CaprotoError("Disconnected")
                        chan = sub_ids.get(response.subscriptionid)
                        if chan:
                            callback(chan.name, response)
        except KeyboardInterrupt:
            logger.debug('Received SIGINT. Closing.')
            pass
    finally:
        try:
            for chan in channels:
                if chan.states[ca.CLIENT] is ca.CONNECTED:
                    send(chan.circuit, chan.disconnect())
        finally:
            # Reinstate the timeout for channel cleanup.
            for chan in channels:
                sockets[chan.circuit].settimeout(timeout)
                sockets[chan.circuit].close()


def put_cli():
    parser = argparse.ArgumentParser(description='Write a value to a PV.')
    fmt_group = parser.add_mutually_exclusive_group()
    parser.add_argument('pv_name', type=str,
                        help="PV (channel) name")
    parser.add_argument('data', type=str,
                        help="Value or values to write.")
    fmt_group.add_argument('--format', type=str,
                           help=("Python format string. Available tokens are "
                                 "{pv_name} and {response}. Additionally, "
                                 "this data type includes time, {timestamp} "
                                 "and usages like "
                                 "{timestamp:%%Y-%%m-%%d %%H:%%M:%%S} are "
                                 "supported."))
    parser.add_argument('--no-repeater', action='store_true',
                        help=("Do not spawn a Channel Access repeater daemon "
                              "process."))
    parser.add_argument('--priority', '-p', type=int, default=0,
                        help="Channel Access Virtual Circuit priority. "
                             "Lowest is 0; highest is 99.")
    fmt_group.add_argument('--terse', '-t', action='store_true',
                           help=("Display data only. Unpack scalars: "
                                 "[3.] -> 3."))
    parser.add_argument('--timeout', '-w', type=float, default=1,
                        help=("Timeout ('wait') in seconds for server "
                              "responses."))
    parser.add_argument('--verbose', '-v', action='store_true',
                        help="Show DEBUG log messages.")
    args = parser.parse_args()
    try:
        initial, final = put(pv_name=args.pv_name, data=args.data,
                             verbose=args.verbose, timeout=args.timeout,
                             priority=args.priority,
                             repeater=not args.no_repeater)
        if args.format is None:
            format_str = '{pv_name: <40}  {response.data}'
        else:
            format_str = args.format
        if args.terse:
            if len(initial.data) == 1:
                format_str = '{response.data[0]}'
            else:
                format_str = '{response.data}'
        tokens = dict(pv_name=args.pv_name, response=initial)
        if hasattr(initial.metadata, 'timestamp'):
            dt = datetime.fromtimestamp(initial.metadata.timestamp)
            tokens['timestamp'] = dt
        print(format_str.format(**tokens))
        tokens = dict(pv_name=args.pv_name, response=final)
        if hasattr(final.metadata, 'timestamp'):
            dt = datetime.fromtimestamp(final.metadata.timestamp)
            tokens['timestamp'] = dt
        tokens = dict(pv_name=args.pv_name, response=final)
        print(format_str.format(**tokens))
    except BaseException as exc:
        if args.verbose:
            # Show the full traceback.
            raise
        else:
            # Print a one-line error message.
            print(exc)


def put(pv_name, data, *, data_type=None, metadata=None,
        verbose=False, timeout=1, priority=0,
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
    verbose : boolean, optional
        Verbose logging. Default is False.
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
    logger = logging.getLogger('put')
    if verbose:
        level = 'DEBUG'
    else:
        level = 'INFO'
    logger.setLevel(level)
    handler.setLevel(level)
    ca_logger.setLevel(level)

    if repeater:
        # As per the EPICS spec, a well-behaved client should start a
        # caproto-repeater that will continue running after it exits.
        spawn_repeater(logger)
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
        chan = make_channel(pv_name, logger, udp_sock, priority, timeout)
    finally:
        udp_sock.close()
    try:
        logger.debug("Detected native data_type %r.", chan.native_data_type)
        # abundance of caution
        ntype = field_types['native'][chan.native_data_type]
        # Stash initial value
        logger.debug("Taking 'initial' reading before writing.")
        initial_response = read(chan, timeout, None)

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
                if time.monotonic() - t > timeout:
                    raise socket.timeout
            except socket.timeout:
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
        final_response = read(chan, timeout, None)
    finally:
        try:
            if chan.states[ca.CLIENT] is ca.CONNECTED:
                send(chan.circuit, chan.disconnect())
        finally:
            sockets[chan.circuit].close()
    return initial_response, final_response


def repeater_cli():
    parser = argparse.ArgumentParser(
        description="""
Run a Channel Access Repeater.

If the Repeater port is already in use, assume a Repeater is already running
and exit. That port number is set by the environment variable
EPICS_CA_REPEATER_PORT. It defaults to the standard 5065. The current value is
{}.""".format(os.environ.get('EPICS_CA_REPEATER_PORT', 5065)))

    group = parser.add_mutually_exclusive_group()
    group.add_argument('-q', '--quiet', action='store_true',
                       help=("Suppress INFO log messages. "
                             "(Still show WARNING or higher.)"))
    group.add_argument('-v', '--verbose', action='store_true',
                       help="Show DEBUG log messages.")
    args = parser.parse_args()
    if args.verbose:
        level = 'DEBUG'
    elif args.quiet:
        level = 'WARNING'
    else:
        level = 'INFO'
    logger = logging.getLogger('repeater')
    logger.setLevel(level)
    handler.setLevel(level)
    ca_logger.setLevel(level)
    try:
        run_repeater()
    except BaseException as exc:
        if args.verbose:
            # Show the full traceback.
            raise
        else:
            # Print a one-line error message.
            print(exc)


def parse_data_type(raw_data_type):
    """
    Parse raw_data_type string as ChannelType. None passes through.

    '3', 'ENUM', and 'enum' all parse as <ChannelType.ENUM 3>.
    """
    if raw_data_type is None:
        data_type = None
    else:
        assert isinstance(raw_data_type, str)
        # ChannelType is an IntEnum.
        # If d is int, use ChannelType(d). If string, getattr(ChannelType, d).
        try:
            data_type_int = int(raw_data_type)
        except ValueError:
            data_type = getattr(ChannelType, raw_data_type.upper())
        else:
            data_type = ChannelType(data_type_int)
    return data_type


class _ListTypesAction(argparse.Action):
    # a special action that allows the usage --list-types to override
    # any 'required args' requirements, the same way that --help does

    def __init__(self,
                 option_strings,
                 dest=argparse.SUPPRESS,
                 default=argparse.SUPPRESS,
                 help=None):
        super(_ListTypesAction, self).__init__(
            option_strings=option_strings,
            dest=dest,
            default=default,
            nargs=0,
            help=help)

    def __call__(self, parser, namespace, values, option_string=None):
        for elem in ChannelType:
            print(f'{elem.value: <2} {elem.name}')
        parser.exit()
