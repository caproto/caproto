import argparse
import ast
from collections import Iterable
from datetime import datetime, timedelta
import logging
import os
import time
import selectors
import socket
import subprocess
import sys

import caproto as ca
from caproto._dbr import promote_type, ChannelType
from caproto._utils import spawn_daemon, ErrorResponseReceived
from caproto.asyncio.repeater import run as run_repeater


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


def make_channel(pv_name, logger, udp_sock, priority, timeout):
    # Set Broadcaster log level to match our logger.
    b = ca.Broadcaster(our_role=ca.CLIENT)
    b.log.setLevel(logger.level)

    # Register with the repeater.
    logger.debug('Registering with the Channel Access repeater.')
    bytes_to_send = b.send(ca.RepeaterRegisterRequest('0.0.0.0'))

    # Do multiple attempts in case the repeater is still starting up....
    for attempt in range(1, 4):
        repeater_port = os.environ.get('EPICS_CA_REPEATER_PORT', 5065)
        for host in ca.get_address_list():
            udp_sock.sendto(bytes_to_send, (host, repeater_port))

        # Await registration confirmation.
        try:
            t = time.monotonic()
            while True:
                try:
                    data, address = udp_sock.recvfrom(1024)
                    if time.monotonic() - t > timeout:
                        raise socket.timeout
                except socket.timeout:
                    raise TimeoutError("Timed out while awaiting confirmation "
                                       "from the Channel Access repeater.")
                commands = b.recv(data, address)
                b.process_commands(commands)
                if b.registered:
                    break
        except TimeoutError:
            if attempt == 3:
                raise
        if b.registered:
            break
    logger.debug('Repeater registration confirmed.')

    logger.debug("Searching for '%s'...." % pv_name)
    bytes_to_send = b.send(ca.VersionRequest(0, 13),
                           ca.SearchRequest(pv_name, 0, 13))
    for host in ca.get_address_list():
        if ':' in host:
            host, _, specified_port = host.partition(':')
            dest = (host, int(specified_port))
        else:
            dest = (host, CA_SERVER_PORT)
        udp_sock.sendto(bytes_to_send, dest)
        logger.debug('Search request sent to %r.', dest)

    # Await a search response.
    t = time.monotonic()
    while True:
        try:
            bytes_received, address = udp_sock.recvfrom(1024)
            if time.monotonic() - t > timeout:
                raise socket.timeout
        except socket.timeout:
            raise TimeoutError("Timed out while awaiting a response "
                               "from the search for '%s'" % pv_name)
        commands = b.recv(bytes_received, address)
        b.process_commands(commands)
        for command in commands:
            if isinstance(command, ca.SearchResponse) and command.cid == 0:
                address = ca.extract_address(command)
                break
        else:
            # None of the commands we have seen are a reply to our request.
            # Receive more data.
            continue
        break

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
        send(chan.circuit, chan.host_name())
        send(chan.circuit, chan.client_name())
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

        logger.debug('Channel created.')
    except BaseException:
        sockets[chan.circuit].close()
        raise
    return chan


def spawn_repeater(logger):
    subprocess.Popen(['caproto-repeater', '--quiet'],
                      cwd="/",
                      stdout=subprocess.PIPE,
                      stderr=subprocess.STDOUT)
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
        else:
            continue
        break
    return response


def get_cli():
    parser = argparse.ArgumentParser(description='Read the value of a PV.')
    fmt_group = parser.add_mutually_exclusive_group()
    parser.add_argument('pv_names', type=str, nargs='+',
                        help="PV (channel) name(s) separated by spaces")
    parser.add_argument('-d', type=str, default=None,
                        help=("Request a certain data type. Accepts numeric "
                              "code ('3') or case-insensitive string ('enum')"
                              "."))
    fmt_group.add_argument('--format', type=str,
                           help=("Python format string. Available tokens are "
                                 "{pv_name} and {response}. Additionally, if "
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
    data_type = parse_data_type(args.d)
    try:
        for pv_name in args.pv_names:
            response = get(pv_name=pv_name,
                        data_type=data_type,
                        verbose=args.verbose, timeout=args.timeout,
                        priority=args.priority,
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
        repeater=True):
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
        print(format_str.format(**tokens))
    try:
        monitor(*args.pv_names,
                callback=callback,
                verbose=args.verbose, timeout=args.timeout,
                priority=args.priority,
                repeater=not args.no_repeater)
    except BaseException as exc:
        if args.verbose:
            # Show the full traceback.
            raise
        else:
            # Print a one-line error message.
            print(exc)


def monitor(*pv_names, callback, verbose=False, timeout=1, priority=0,
            repeater=True):
    """
    Monitor one or more Channels indefinitely.

    Use Ctrl+C (SIGINT) to escape.

    Parameters
    ----------
    pv_names : str
    callback : callable, required keyword-only argument
        Expected signature is ``f(pv_name, ReadNotifyResponse)``.
    data_type : int, optional
        Request specific data type. Default is Channel's native data type.
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

    Examples
    --------
    Get the value of a Channel named 'cat'.
    >>> get('cat').data
    """
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
            time_type = promote_type(chan.native_data_type, use_time=True)
            # Adjust the timeout during monitoring.
            sockets[chan.circuit].settimeout(None)
            logger.debug("Subscribing with data_type %r.", time_type)
            req = chan.subscribe(data_type=time_type)
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
                            raise ErrorResponseReceived(command)
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


def put(pv_name, data, *, verbose=False, timeout=1, priority=0, repeater=True):
    """
    Write to a Channel.

    Parameters
    ----------
    pv_name : str
    data : str, int, or float or a list of these
        Value to write.
    data_type : int, optional
        Request specific data type. Default is Channel's native data type.
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
    logger.debug('Data argument %s parsed as %r.', raw_data, data)
    if not isinstance(data, Iterable) or isinstance(data, (str, bytes)):
        data = [data]
    if isinstance(data[0], str):
        data = [val.encode('latin-1') for val in data]

    udp_sock = ca.bcast_socket()
    try:
        udp_sock.settimeout(timeout)
        chan = make_channel(pv_name, logger, udp_sock, priority, timeout)
    finally:
        udp_sock.close()
    try:
        # Stash initial value
        logger.debug("Taking 'initial' reading before writing.")
        initial_response = read(chan, timeout, None)
        logger.debug("Writing.")
        req = chan.write(data=data)
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
                    response = command
                    break
                elif isinstance(command, ca.ErrorResponse):
                    raise ErrorResponseReceived(command)
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
                       help="Suppress INFO log messages. (Still show WARNING or higher.)")
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
