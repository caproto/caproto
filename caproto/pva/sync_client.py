import argparse
import ast
from collections import Iterable
from datetime import datetime
import getpass
import logging
import os
import time
import selectors
import logging
import socket
import subprocess
import collections
import sys

# from .._dbr import (field_types, ChannelType, native_type, SubscriptionType)
from caproto import (get_address_list_with_ports, get_environment_variables,
                     MAX_UDP_RECV)

import ctypes
import random

from caproto import pva
from caproto import (get_netifaces_addresses, bcast_socket)
from caproto.pva import (CLIENT, SERVER, CONNECTED, NEED_DATA, DISCONNECTED,
                         Broadcaster, MessageTypeFlag, ErrorResponseReceived,
                         CaprotoError, SearchResponse, VirtualCircuit,
                         ClientChannel, ConnectionValidationRequest,
                         ConnectionValidatedResponse, CreateChannelResponse,
                         ChannelFieldInfoResponse, ChannelGetResponse,
                         GetSubcommands)

# __all__ = ['get', 'put', 'monitor']

# Make a dict to hold our tcp sockets.
sockets = {}
env = get_environment_variables()
broadcast_port = env['EPICS_PVA_BROADCAST_PORT']

ca_logger = logging.getLogger()
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter('[%(name)s] %(message)s'))
ca_logger.addHandler(handler)


# Convenience functions that do both transport and caproto validation/ingest.
def send(circuit, command):
    buffers_to_send = circuit.send(command)
    sockets[circuit].sendmsg(buffers_to_send)


def recv(circuit):
    commands = collections.deque()
    bytes_received = sockets[circuit].recv(4096)
    for c, remaining in circuit.recv(bytes_received):
        if type(c) is NEED_DATA:
            # TODO isn't this wrong?
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

    def send_search(message):
        payload = message.serialize()
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
    circuit = VirtualCircuit(our_role=CLIENT, address=address)

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
                    raise socket.timeout
            except socket.timeout:
                raise TimeoutError("Timeout while awaiting channel creation.")

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

    init_req = chan.read_init(pvrequest_if=pvrequest)
    ioid = init_req.ioid

    send(chan.circuit, init_req)

    t = time.monotonic()
    while True:
        try:
            commands = recv(chan.circuit)
            if time.monotonic() - t > timeout:
                raise socket.timeout
        except socket.timeout:
            raise TimeoutError("Timeout while awaiting reading.")

        for command in commands:
            if isinstance(command, ChannelFieldInfoResponse):
                # interface = command.field_if
                ...
            elif isinstance(command, ChannelGetResponse):
                if command.subcommand == GetSubcommands.INIT:
                    interface = command.pv_structure_if
                    read_req = chan.read(ioid, interface=interface)
                    send(chan.circuit, read_req)
                elif command.subcommand == GetSubcommands.GET:
                    return interface, command

                # raise ErrorResponseReceived(command)
            elif command is DISCONNECTED:
                raise CaprotoError('Disconnected while waiting for '
                                   'read response')


def get_cli():
    parser = argparse.ArgumentParser(description='Read the value of a PV.')
    # parser.register('action', 'list_types', _ListTypesAction)
    fmt_group = parser.add_mutually_exclusive_group()
    parser.add_argument('pv_names', type=str, nargs='+',
                        help="PV (channel) name(s) separated by spaces")
    parser.add_argument('--pvrequest', type=str, default='field(value)',
                        help=("PVRequest"))
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
        if args.verbose:
            # Show the full traceback.
            raise
        else:
            # Print a one-line error message.
            print(exc)


def get(pv_name, *, pvrequest, verbose=False, timeout=1,
        force_int_enums=False):
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
            if chan.states[CLIENT] is CONNECTED:
                send(chan.circuit, chan.disconnect())
        finally:
            sockets[chan.circuit].close()


# TODO TODO TODO segmentation in sync client

def recv_message(sock, fixed_byte_order, server_byte_order, cache, buf,
                 **deserialize_kw):
    if not len(buf):
        buf = bytearray(sock.recv(4096))
        print('<-', buf)

    header_cls = (pva.MessageHeaderLE
                  if server_byte_order == pva.LITTLE_ENDIAN
                  else pva.MessageHeaderBE)

    header = header_cls.from_buffer(buf)
    assert header.valid

    if header.segment == pva.SegmentFlag.UNSEGMENTED:
        header, buf, offset = header_cls.deserialize(buf, our_cache=cache.ours)
    else:
        header_size = ctypes.sizeof(header_cls)

        first_header = header

        segmented_payload = []
        while header.segment != pva.SegmentFlag.LAST:
            while len(buf) < header_size:
                buf += sock.recv(4096)

            header = header_cls.from_buffer(buf)
            assert header.valid
            # TODO note, control messages can be interspersed here
            assert first_header.message_command == header.message_command

            buf = buf[header_size:]

            segment_size = header.payload_size
            while len(buf) < segment_size:
                buf += sock.recv(max((4096, segment_size - len(buf))))

            segmented_payload.append(buf[:segment_size])
            buf = buf[segment_size:]

        buf = bytearray(b''.join(segmented_payload))
        print('Segmented message. Final payload length: {}'
              ''.format(len(buf)))
        header.payload_size = len(buf)

    msg_class = header.get_message(pva.DirectionFlag.FROM_SERVER,
                                   fixed_byte_order)

    print()
    print('<-', header)

    assert len(buf) >= header.payload_size
    return msg_class.deserialize(buf, our_cache=cache.ours, **deserialize_kw)


if __name__ == '__main__':
    import logging
    logging.getLogger('caproto.pva.serialization').setLevel(logging.DEBUG)
    logging.basicConfig()

    try:
        pv = sys.argv[1]
    except IndexError:
        pv = 'TST:image1:Array'

    # get(pv)
    get_cli()
