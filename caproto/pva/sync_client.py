import argparse
import logging
import time
import socket
import collections
import sys

# from .._dbr import (field_types, ChannelType, native_type, SubscriptionType)

# REBASE TODO this will go away - need to rebase
from caproto import (get_address_list_with_ports, get_environment_variables,
                     MAX_UDP_RECV)

import ctypes
import random

from caproto import pva
from caproto import bcast_socket
from caproto.pva import (CLIENT, SERVER, CONNECTED, NEED_DATA, CLEAR_SEGMENTS,
                         DISCONNECTED, Broadcaster, QOSFlags, MessageTypeFlag,
                         ErrorResponseReceived, CaprotoError, SearchResponse,
                         VirtualCircuit, ClientChannel,
                         ConnectionValidationRequest,
                         ConnectionValidatedResponse, CreateChannelResponse,
                         ChannelFieldInfoResponse, ChannelGetResponse,
                         ChannelMonitorResponse, MonitorSubcommands,
                         Subcommands, basic_types)
from .helpers import StructuredValueBase

# __all__ = ['get', 'put', 'monitor']

# Make a dict to hold our tcp sockets.
sockets = {}
env = get_environment_variables()
broadcast_port = env['EPICS_PVA_BROADCAST_PORT']

serialization_logger = logging.getLogger('caproto.pva.serialization_debug')

# Convenience functions that do both transport and caproto validation/ingest.
def send(circuit, command):
    buffers_to_send = circuit.send(command)
    sockets[circuit].sendmsg(buffers_to_send)

    if serialization_logger.isEnabledFor(logging.DEBUG):
        to_send = b''.join(buffers_to_send)
        serialization_logger.debug('-> %d bytes: %r', len(to_send), to_send)


def recv(circuit):
    commands = collections.deque()
    bytes_received = sockets[circuit].recv(4096)
    # serialization_logger.debug('<- %d bytes: %r', len(bytes_received),
    #                            bytes_received)

    for c, remaining in circuit.recv(bytes_received):
        if type(c) is NEED_DATA:
            break
        circuit.process_command(c)
        commands.append(c)

    return commands


def make_broadcaster_socket(logger):
    'Returns (udp_sock, port)'
    udp_sock = bcast_socket()
    port = 49152
    while True:
        try:
            udp_sock.bind(('', port))
        except IOError as ex:
            port = random.randint(49152, 65535)
        else:
            break

    logger.debug('Bound to UDP port %d for search', port)
    return udp_sock, port


def search(pv, logger, udp_sock, udp_port, timeout, max_retries=2):
    '''Search for a PV over the network by broadcasting over UDP

    Returns: (host, port)
    '''

    # b = Broadcaster(our_role=CLIENT, response_addr=('0.0.0.0', udp_port))
    b = Broadcaster(our_role=CLIENT, response_addr=('127.0.0.1', udp_port))
    # TODO: host address
    b.log.setLevel(logger.level)

    cache = pva.SerializeCache(ours={},
                               theirs={},
                               user_types=basic_types,
                               ioid_interfaces={})

    def send_search(message):
        payload = message.serialize(cache=cache)
        header = pva.MessageHeaderLE(
            message_type=MessageTypeFlag.APP_MESSAGE,
            direction=pva.DirectionFlag.FROM_CLIENT,
            endian=pva.LITTLE_ENDIAN,
            command=message.ID,
            payload_size=len(payload)
        )
        bytes_to_send = bytes(header) + payload
        for host, port in get_address_list_with_ports(
                protocol='PVA', default_port=broadcast_port):
            udp_sock.sendto(bytes_to_send, (host, port))
            logger.debug('Search request sent to %r.', (host, port))
            logger.debug('%s', bytes_to_send)

    def check_timeout():
        nonlocal retry_at

        if time.monotonic() >= retry_at:
            send_search(search_req)
            retry_at = time.monotonic() + retry_timeout

        if time.monotonic() - t > timeout:
            raise TimeoutError(f"Timed out while awaiting a response "
                               f"from the search for {pv!r}")

    # Initial search attempt
    pv_to_cid, search_req = b.search(pv)
    cid_to_pv = dict((v, k) for k, v in pv_to_cid.items())
    send_search(search_req)

    # Await a search response, and keep track of registration status
    retry_timeout = timeout / max((max_retries, 1))
    t = time.monotonic()
    retry_at = t + retry_timeout

    try:
        orig_timeout = udp_sock.gettimeout()
        udp_sock.settimeout(retry_timeout)
        while True:
            try:
                bytes_received, address = udp_sock.recvfrom(MAX_UDP_RECV)
            except socket.timeout:
                check_timeout()
                continue

            check_timeout()

            commands = b.recv(bytes_received, address)
            b.process_commands(commands)
            response_commands = [command for command in commands
                                 if isinstance(command, SearchResponse)]
            for command in response_commands:
                response_pvs = [cid_to_pv.get(cid, None)
                                for cid in command.search_instance_ids]
                if not any(response_pvs):
                    continue

                if command.found:
                    host_port = (command.server_address,
                                 command.server_port)
                    logger.debug('Found %r at %r.', response_pvs,
                                 host_port)
                    return host_port
                else:
                    logger.debug('Server responded: not found %r.',
                                 response_pvs)
    finally:
        udp_sock.settimeout(orig_timeout)


def make_channel(pv_name, logger, udp_sock, udp_port, timeout):
    address = search([pv_name], logger, udp_sock, udp_port, timeout)
    circuit = VirtualCircuit(our_role=CLIENT, address=address,
                             priority=QOSFlags.encode(priority=0, flags=0))

    # Set circuit log level to match our logger.
    circuit.log.setLevel(logger.level)

    chan = ClientChannel(pv_name, circuit)
    sockets[circuit] = socket.create_connection(circuit.address, timeout)

    try:
        t = time.monotonic()
        while True:
            try:
                commands = recv(circuit)
                if time.monotonic() - t > timeout:
                    raise TimeoutError("Timeout while awaiting channel creation.")
            except socket.timeout:
                raise

            for command in commands:
                if isinstance(command, ConnectionValidationRequest):
                    response = circuit.validate_connection(
                        client_buffer_size=command.server_buffer_size,
                        client_registry_size=command.server_registry_size,
                        connection_qos=0,
                        auth_nz='')
                    send(circuit, response)
                elif isinstance(command, ConnectionValidatedResponse):
                    logger.debug('Connection validated! Creating channel.')
                    create_chan = chan.create()
                    send(circuit, create_chan)
                elif isinstance(command, CreateChannelResponse):
                    logger.debug('Channel created.')
                    return chan

            # if chan.states[CLIENT] is CONNECTED:
            #     break

        logger.debug('Channel created.')
    except Exception:
        sockets[chan.circuit].close()
        raise


def read(chan, timeout, pvrequest):
    interface_req = chan.read_interface()
    send(chan.circuit, interface_req)

    init_req = chan.read_init(pvrequest=pvrequest)
    ioid = init_req.ioid

    send(chan.circuit, init_req)

    t = time.monotonic()
    while True:
        try:
            commands = recv(chan.circuit)
        except socket.timeout:
            commands = []

        if time.monotonic() - t > timeout:
            raise TimeoutError("Timeout while awaiting reading.")

        for command in commands:
            if isinstance(command, ChannelFieldInfoResponse):
                # interface = command.field_if
                ...
            elif isinstance(command, ChannelGetResponse):
                if command.subcommand == Subcommands.INIT:
                    interface = command.pv_structure_if
                    read_req = chan.read(ioid, interface=interface)
                    send(chan.circuit, read_req)
                elif command.subcommand == Subcommands.GET:
                    return interface, command

                # raise ErrorResponseReceived(command)
            elif command is DISCONNECTED:
                raise CaprotoError('Disconnected while waiting for '
                                   'read response')


def get_cli():
    parser = argparse.ArgumentParser(description='Read the value of a PV.')
    fmt_group = parser.add_mutually_exclusive_group()
    parser.add_argument('pv_names', type=str, nargs='+',
                        help="PV (channel) name(s) separated by spaces")
    parser.add_argument('-r', '--pvrequest', type=str, default='field()',
                        help=("PVRequest"))
    fmt_group.add_argument('--terse', '-t', action='store_true',
                           help=("Display data only. Unpack scalars: "
                                 "[3.] -> 3."))
    parser.add_argument('--timeout', '-w', type=float, default=1,
                        help=("Timeout ('wait') in seconds for server "
                              "responses."))
    parser.add_argument('--verbose', '-v', action='store_true',
                        help="Show DEBUG log messages.")
    parser.add_argument('-vv', action='store_true',
                        help=argparse.SUPPRESS)
    parser.add_argument('-vvv', action='store_true',
                        help=argparse.SUPPRESS)

    args = parser.parse_args()
    if args.verbose:
        logging.getLogger('caproto.pva.get').setLevel('DEBUG')
    elif args.vv:
        logging.getLogger('caproto.pva').setLevel('DEBUG')
        logging.getLogger('caproto.pva.serialization').setLevel('INFO')
    elif args.vvv:
        logging.getLogger('caproto.pva').setLevel('DEBUG')
        logging.getLogger('caproto.pva.serialization').setLevel('DEBUG')

    try:
        for pv_name in args.pv_names:
            interface, response = get(pv_name=pv_name,
                                      pvrequest=args.pvrequest,
                                      verbose=args.verbose,
                                      timeout=args.timeout)
            if args.terse:
                ...

            pva.print_field_info(interface, user_types={},
                                 values={'': response.pv_data})

    except BaseException as exc:
        if args.verbose or args.vv or args.vvv:
            # Show the full traceback.
            raise
        else:
            # Print a one-line error message.
            print(exc)


def get(pv_name, *, pvrequest, verbose=False, timeout=1):
    """
    Read a Channel.

    Parameters
    ----------
    pv_name : str
    verbose : boolean, optional
        Verbose logging. Default is False.
    timeout : float, optional
        Default is 1 second.
    priority : 0, optional
        Virtual Circuit qos. Default is 0, lowest. Highest is 99.

    Returns
    -------

    Examples
    --------
    Get the value of a Channel named 'cat'.
    >>> get('cat')
    """
    logger = logging.getLogger('caproto.pva.get')

    udp_sock, udp_port = make_broadcaster_socket(logger)
    try:
        udp_sock.settimeout(timeout)
        chan = make_channel(pv_name, logger, udp_sock, udp_port, timeout)
    finally:
        udp_sock.close()

    try:
        return read(chan, timeout, pvrequest=pvrequest)
    finally:
        try:
            ...
            # if chan.states[CLIENT] is CONNECTED:
            #     send(chan.circuit, chan.disconnect())
        finally:
            sockets[chan.circuit].close()


def _monitor(chan, timeout, pvrequest, maximum_events):
    interface_req = chan.read_interface()
    send(chan.circuit, interface_req)

    init_req = chan.subscribe_init(pvrequest=pvrequest)
    ioid = init_req.ioid
    send(chan.circuit, init_req)

    event_count = 0
    while True:
        try:
            commands = recv(chan.circuit)
        except socket.timeout:
            continue

        for command in commands:
            if isinstance(command, ChannelMonitorResponse):
                if command.subcommand == Subcommands.INIT:
                    monitor_start_req = chan.subscribe_control(
                        ioid=ioid, subcommand=MonitorSubcommands.START)
                    send(chan.circuit, monitor_start_req)
                    yield command
                else:
                    event_count += 1
                    yield command
                    if maximum_events is not None:
                        if event_count >= maximum_events:
                            break

            elif command is DISCONNECTED:
                raise CaprotoError('Disconnected while waiting for '
                                   'read response')


def monitor(pv_name, *, pvrequest, verbose=False, timeout=1,
            maximum_events=None):
    """
    Monitor a Channel.

    Parameters
    ----------
    pv_name : str
    verbose : boolean, optional
        Verbose logging. Default is False.
    timeout : float, optional
        Default is 1 second.
    qos : 0, optional
        Virtual Circuit qos. Default is 0, lowest. Highest is 99.

    Returns
    -------

    Examples
    --------
    """
    logger = logging.getLogger('caproto.pva.monitor')

    udp_sock, udp_port = make_broadcaster_socket(logger)
    try:
        udp_sock.settimeout(timeout)
        chan = make_channel(pv_name, logger, udp_sock, udp_port, timeout)
    finally:
        udp_sock.close()

    try:
        yield from _monitor(chan, timeout, pvrequest=pvrequest,
                            maximum_events=maximum_events)
    finally:
        try:
            if chan.states[CLIENT] is CONNECTED:
                # send(chan.circuit, chan.disconnect())
                ...
        finally:
            sockets[chan.circuit].close()


def monitor_cli():
    parser = argparse.ArgumentParser(description='Read the value of a PV.')
    parser.add_argument('pv_names', type=str, nargs='+',
                        help="PV (channel) name(s) separated by spaces")
    parser.add_argument('--pvrequest', type=str, default='field()',
                        help=("PVRequest"))
    fmt_group = parser.add_mutually_exclusive_group()
    fmt_group.add_argument('--terse', '-t', action='store_true',
                           help=("Display data only. Unpack scalars: "
                                 "[3.] -> 3."))
    fmt_group.add_argument('--full', action='store_true',
                           help=("Print full structure each time"))
    fmt_group.add_argument('--format', type=str, default='{timestamp} {pv_name} {value}',
                           help=("Python format string. Available tokens are "
                                 "{pv_name} and {data}. Additionally, if "
                                 "this data type includes time, {timestamp} "
                                 "and usages like "
                                 "{timestamp:%%Y-%%m-%%d %%H:%%M:%%S} are "
                                 "supported. "))
    parser.add_argument('--timeout', '-w', type=float, default=1,
                        help=("Timeout ('wait') in seconds for server "
                              "responses."))
    parser.add_argument('--verbose', '-v', action='store_true',
                        help="Show DEBUG log messages.")
    parser.add_argument('-vvv', action='store_true',
                        help=argparse.SUPPRESS)
    parser.add_argument('--maximum', type=int, default=None,
                        help="Maximum number of monitor events to display.")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger('caproto.pva.put').setLevel('DEBUG')
    if args.vvv:
        logging.getLogger('caproto.pva').setLevel('DEBUG')
        serialization_logger.setLevel('DEBUG')

    try:
        pv_name = args.pv_names[0]
        data = {}
        if args.terse:
            format_str = '{timestamp} {pv_name} {value}'
        else:
            format_str = args.format

        timestamp = '(No timestamp)'

        for idx, event in enumerate(monitor(pv_name=pv_name,
                                            pvrequest=args.pvrequest,
                                            verbose=args.verbose,
                                            timeout=args.timeout,
                                            maximum_events=args.maximum)):
            if idx == 0:
                interface = event.pv_structure_if
                val = StructuredValueBase(interface)
                has_timestamp = 'timeStamp' in val
            else:
                event_data = event.pv_data
                data.update(**event_data)

                val.update(**event_data)

                if has_timestamp:
                    timestamp = val.timestamp

                if args.full:
                    print(val)
                    continue

                try:
                    print(format_str.format(pv_name=pv_name,
                                            timestamp=timestamp,
                                            **val._values))
                except Exception as ex:
                    print('(print format failed)', ex, data)

    except BaseException as exc:
        if args.verbose:
            # Show the full traceback.
            raise
        else:
            # Print a one-line error message.
            print(exc)


if __name__ == '__main__':
    logging.getLogger('caproto').setLevel(logging.DEBUG)
    logging.basicConfig()

    try:
        pv = sys.argv[1]
    except IndexError:
        pv = 'TST:image1:Array'

    # get(pv)
    # get_cli()
    monitor_cli()
