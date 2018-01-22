import argparse
import ast
from collections import Iterable
import logging
import os
import time
import socket
import sys

import caproto as ca
from caproto._utils import conf_logger, spawn_daemon
from caproto.asyncio.repeater import run as run_repeater


CA_SERVER_PORT = 5064  # just a default

# Make a dict to hold our tcp sockets.
sockets = {}

ca_logger = logging.getLogger()
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter('[%(name)s] %(message)s'))
ca_logger.addHandler(handler)

# Convenience functions that do both transport caproto validation/ingest.
def send(circuit, command):
    buffers_to_send = circuit.send(command)
    sockets[circuit].sendmsg(buffers_to_send)


def recv(circuit):
    bytes_received = sockets[circuit].recv(4096)
    commands, _ = circuit.recv(bytes_received)
    for c in commands:
        circuit.process_command(c)
    return commands


def make_channel(pv_name, logger, timeout=2):
    # A broadcast socket
    udp_sock = ca.bcast_socket()
    udp_sock.settimeout(timeout)

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
                                priority=0)
    # Set circuit log level to match our logger.
    circuit.log.setLevel(logger.level)
    chan = ca.ClientChannel(pv_name, circuit)
    sockets[chan.circuit] = socket.create_connection(chan.circuit.address,
                                                     timeout)

    # Initialize our new TCP-based CA connection with a VersionRequest.
    send(chan.circuit, ca.VersionRequest(priority=0, version=13))
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
    udp_sock.close()
    return chan


def read(chan, timeout):
    req = chan.read()
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
        else:
            continue
        break
    # Some niceties from printing...
    if len(response.data) == 1:
        data, = response.data
    else:
        data = response.data
    return data


def get():
    parser = argparse.ArgumentParser(description='Read the value of a PV.')
    parser.add_argument('pv_name', type=str,
                        help="PV (channel) name")
    parser.add_argument('--verbose', '-v', action='store_true',
                        help="Show DEBUG log messages.")
    parser.add_argument('--timeout', type=float, default=2,
                        help="Timeout in seconds for server responses.")
    parser.add_argument('--no-repeater', action='store_true',
                        help="Do not spawn a Channel Access repeater daemon process.")
    args = parser.parse_args()
    pv_name = args.pv_name
    if args.verbose:
        level = 'DEBUG'
    else:
        level = 'INFO'

    logger = logging.getLogger('get')
    logger.setLevel(level)
    handler.setLevel(level)
    ca_logger.setLevel(level)

    try:
        if not args.no_repeater:
            # As per the EPICS spec, a well-behaved client should start a
            # caproto-repeater that will continue running after it exits.
            spawn_daemon(run_repeater,
                        conf_logger(logging.getLogger('repeater'), 'WARNING'))
            logger.debug('Spawned caproto-repeater daemon process.')

        chan = make_channel(pv_name, logger, args.timeout)
        data = read(chan, args.timeout)
        print('{0: <40}  {1}'.format(pv_name, data))
    except BaseException as exc:
        if args.verbose:
            raise
        else:
            print(exc)
    finally:
        try:
            chan
        except NameError:
            pass
        else:
            if chan.states[ca.CLIENT] is ca.CONNECTED:
                send(chan.circuit, chan.disconnect())


def monitor():
    parser = argparse.ArgumentParser(description='Read the value of a PV.')
    parser.add_argument('pv_name', type=str,
                        help="PV (channel) name")
    parser.add_argument('--verbose', '-v', action='store_true',
                        help="Show DEBUG log messages.")
    parser.add_argument('--timeout', type=float, default=2,
                        help="Timeout in seconds for server responses.")
    parser.add_argument('--no-repeater', action='store_true',
                        help="Do not spawn a Channel Access repeater daemon process.")
    args = parser.parse_args()
    pv_name = args.pv_name
    if args.verbose:
        level = 'DEBUG'
    else:
        level = 'INFO'

    logger = logging.getLogger('get')
    logger.setLevel(level)
    handler.setLevel(level)
    ca_logger.setLevel(level)

    try:
        if not args.no_repeater:
            # As per the EPICS spec, a well-behaved client should start a
            # caproto-repeater that will continue running after it exits.
            spawn_daemon(run_repeater,
                        conf_logger(logging.getLogger('repeater'), 'WARNING'))
            logger.debug('Spawned caproto-repeater daemon process.')

        chan = make_channel(pv_name, logger, args.timeout)
        # Remove the timeout during monitoring.
        sockets[chan.circuit].settimeout(None)
        req = chan.subscribe()
        send(chan.circuit, req)

        try:
            logger.debug('Monitoring until SIGINT is received....')
            while True:
                commands = recv(chan.circuit)
                for response in commands:
                    if response.subscriptionid == req.subscriptionid:
                        # Some niceties from printing...
                        if len(response.data) == 1:
                            data, = response.data
                        else:
                            data = response.data
                        print('{0: <40}  {1}'.format(pv_name, data))
        except KeyboardInterrupt:
            pass
    except BaseException as exc:
        if args.verbose:
            raise
        else:
            print(exc)
    finally:
        try:
            chan
        except NameError:
            pass
        else:
            if chan.states[ca.CLIENT] is ca.CONNECTED:
                # Reinstate the timeout for channel cleanup.
                sockets[chan.circuit].settimeout(args.timeout)
                send(chan.circuit, chan.disconnect())


def put():
    parser = argparse.ArgumentParser(description='Write a value to a PV.')
    parser.add_argument('pv_name', type=str,
                        help="PV (channel) name")
    parser.add_argument('data', type=str,
                        help="Value or values to write.")
    parser.add_argument('--verbose', '-v', action='store_true',
                        help="Show DEBUG log messages.")
    parser.add_argument('--timeout', type=float, default=2,
                        help="Timeout in seconds for server responses.")
    parser.add_argument('--no-repeater', action='store_true',
                        help="Do not spawn a Channel Access repeater daemon process.")
    args = parser.parse_args()
    pv_name = args.pv_name
    if args.verbose:
        level = 'DEBUG'
    else:
        level = 'INFO'

    logger = logging.getLogger('put')
    logger.setLevel(level)
    handler.setLevel(level)
    ca_logger.setLevel(level)

    try:
        if not args.no_repeater:
            # As per the EPICS spec, a well-behaved client should start a
            # caproto-repeater that will continue running after it exits.
            spawn_daemon(run_repeater,
                        conf_logger(logging.getLogger('repeater'), 'WARNING'))
            logger.debug('Spawned caproto-repeater daemon process.')

        try:
            data = ast.literal_eval(args.data)
        except ValueError:
            # interpret as string
            data = args.data
        logger.debug('Data argument %s parsed as %r.', args.data, data)
        if not isinstance(data, Iterable) or isinstance(data, (str, bytes)):
            data = [data]
        if isinstance(data[0], str):
            data = [val.encode('latin-1') for val in data]

        chan = make_channel(pv_name, logger, args.timeout)

        # Stash initial value
        initial_data = read(chan, args.timeout)
        req = chan.write(data=data)
        send(chan.circuit, req)
        t = time.monotonic()
        while True:
            try:
                commands = recv(chan.circuit)
                if time.monotonic() - t > args.timeout:
                    raise socket.timeout
            except socket.timeout:
                raise TimeoutError("Timeout while awaiting write reply.")
            for command in commands:
                if (isinstance(command, ca.WriteNotifyResponse) and
                            command.ioid == req.ioid):
                    response = command
                    break
            else:
                continue
            break
        final_data = read(chan, args.timeout)
        print('{0: <40}  {1}'.format(pv_name, initial_data))
        print('{0: <40}  {1}'.format(pv_name, final_data))
    except BaseException as exc:
        if args.verbose:
            raise
        else:
            print(exc)
    finally:
        try:
            chan
        except NameError:
            pass
        else:
            if chan.states[ca.CLIENT] is ca.CONNECTED:
                send(chan.circuit, chan.disconnect())


def repeater():
    parser = argparse.ArgumentParser(
        description="""
Run a Channel Access Repeater.

If the Repeater port is already in use, assume a Repeater is already running
and exit. That port number is set by the environment variable
EPICS_CA_REPEATER_PORT. It defaults to the standard 5065. The current value is
{}.""".format(os.environ.get('EPICS_CA_REPEATER_PORT', 5065)))

    group = parser.add_mutually_exclusive_group()
    group.add_argument('-v', '--verbose', action='store_true',
                       help="Show DEBUG log messages.")
    group.add_argument('-q', '--quiet', action='store_true',
                       help="Suppress INFO log messages. (Still show WARNING or higher.)")
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
        run_repeater(logger=logger)
    except BaseException as exc:
        if args.verbose:
            raise
        else:
            print(exc)
