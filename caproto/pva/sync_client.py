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
from caproto.pva import (CLIENT, SERVER, Broadcaster, MessageTypeFlag,
                         ErrorResponseReceived, CaprotoError, SearchResponse,
                         VirtualCircuit, ClientChannel,
                         NEED_DATA,
                         ConnectionValidationRequest)

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

    return

    if msg.found:
        id_to_pv = {id_: pv for pv, id_ in search_ids.items()}
        found_pv = id_to_pv[msg.search_instance_ids[0]]
        print('Found {} on {}:{}!'
              ''.format(found_pv, msg.server_address, msg.server_port))
        return (msg.server_address, msg.server_port)
    else:
        # TODO as a simple client, this only grabs the first response from
        # the quickest server, which is clearly not the right way to do it
        raise ValueError('PVs {} not found in brief search'
                         ''.format(pvs))


def make_channel(pv_name, logger, udp_sock, udp_port, timeout):
    address = search([pv_name], logger, udp_sock, udp_port, timeout)
    circuit = VirtualCircuit(our_role=CLIENT,
                                address=address,
                                )
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
            # if chan.states[CLIENT] is CONNECTED:
            #     break

        logger.debug('Channel created.')
    except BaseException:
        sockets[chan.circuit].close()
        raise
    return chan


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
            if (isinstance(command, ReadNotifyResponse) and
                    command.ioid == req.ioid):
                response = command
                break
            elif isinstance(command, ErrorResponse):
                raise ErrorResponseReceived(command)
            elif command is DISCONNECTED:
                raise CaprotoError('Disconnected while waiting for '
                                   'read response')
        else:
            continue
        break
    return response


def get_cli():
    parser = argparse.ArgumentParser(description='Read the value of a PV.')
    # parser.register('action', 'list_types', _ListTypesAction)
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
    # parser.add_argument('--list-types', action='list_types',
    #                     default=argparse.SUPPRESS,
    #                     help="List allowed values for -d and exit.")
    parser.add_argument('-n', action='store_true',
                        help=("Retrieve enums as integers (default is "
                              "strings)."))
    parser.add_argument('--no-repeater', action='store_true',
                        help=("Do not spawn a Channel Access repeater daemon "
                              "process."))
    # parser.add_argument('--priority', '-p', type=int, default=0,
    #                     help="Channel Access Virtual Circuit priority. "
                             # "Lowest is 0; highest is 99.")
    fmt_group.add_argument('--terse', '-t', action='store_true',
                           help=("Display data only. Unpack scalars: "
                                 "[3.] -> 3."))
    parser.add_argument('--timeout', '-w', type=float, default=1,
                        help=("Timeout ('wait') in seconds for server "
                              "responses."))
    parser.add_argument('--verbose', '-v', action='store_true',
                        help="Show DEBUG log messages.")
    args = parser.parse_args()
    # data_type = parse_data_type(args.d)
    data_type = None
    try:
        for pv_name in args.pv_names:
            response = get(pv_name=pv_name, data_type=data_type,
                           verbose=args.verbose, timeout=args.timeout,
                           force_int_enums=args.n)
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


def get(pv_name, *, data_type=None, verbose=False, timeout=1,
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
    # try:
    #     logger.debug("Detected native data_type %r.", chan.native_data_type)
    #     ntype = native_type(chan.native_data_type)  # abundance of caution
    #     if ((ntype is ChannelType.ENUM) and
    #             (data_type is None) and (not force_int_enums)):
    #         logger.debug("Changing requested data_type to STRING.")
    #         data_type = ChannelType.STRING
    #     return read(chan, timeout, data_type=data_type)
    # finally:
    #     try:
    #         if chan.states[CLIENT] is CONNECTED:
    #             send(chan.circuit, chan.disconnect())
    #     finally:
    #         sockets[chan.circuit].close()














def send_message(sock, client_byte_order, server_byte_order, msg):
    print('->', msg)
    header_cls = (pva.MessageHeaderLE
                  if server_byte_order == pva.LITTLE_ENDIAN
                  else pva.MessageHeaderBE)

    payload = msg.serialize()
    header = header_cls(message_type=pva.MessageTypeFlag.APP_MESSAGE,
                        direction=pva.DirectionFlag.FROM_CLIENT,
                        endian=client_byte_order,
                        command=msg.ID,
                        payload_size=len(payload)
                        )

    to_send = b''.join((header.serialize(), payload))
    print('-b>', to_send)
    sock.sendall(to_send)
    return header, payload


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


def main(host, server_port, pv):
    'Directly connect to a host that has a PV'
    # cache of types from server
    our_cache = {}
    # local copy of types cached on server
    their_cache = {}
    # locally-defined types
    user_types = {}
    cache = pva.SerializeCache(ours=our_cache,
                               theirs=their_cache,
                               user_types=user_types)

    sock = socket.create_connection((host, server_port))
    buf = bytearray(sock.recv(4096))

    # (1)
    print()
    print('- 1. initialization: byte order setting')
    msg, buf, offset = pva.SetByteOrder.deserialize(buf, our_cache=cache.ours)
    print('<-', msg, msg.byte_order_setting, msg.byte_order)

    server_byte_order = msg.byte_order
    client_byte_order = server_byte_order
    cli_msgs = pva.messages[client_byte_order][pva.DirectionFlag.FROM_CLIENT]
    srv_msgs = pva.messages[server_byte_order][pva.DirectionFlag.FROM_SERVER]

    if msg.byte_order_setting == pva.EndianSetting.use_server_byte_order:
        fixed_byte_order = server_byte_order
        print('\n* Using fixed byte order:', server_byte_order)
    else:
        fixed_byte_order = None
        print('\n* Using byte order from individual messages.')

    # convenience functions:
    def send(msg):
        return send_message(sock, client_byte_order, server_byte_order, msg)

    def recv(buf, **kw):
        return recv_message(sock, fixed_byte_order, server_byte_order, cache,
                            buf, **kw)

    # (2)
    print()
    print('- 2. Connection validation request from server')

    auth_request, buf, off = recv(buf)

    # (3)
    print()
    print('- 3. Connection validation response')

    auth_cls = cli_msgs[pva.ApplicationCommands.CONNECTION_VALIDATION]
    auth_resp = auth_cls(
        client_buffer_size=auth_request.server_buffer_size,
        client_registry_size=auth_request.server_registry_size,
        connection_qos=auth_request.server_registry_size,
        auth_nz='',
    )

    send(auth_resp)
    auth_ack, buf, off = recv(buf)

    # (4)
    print()
    print('- 4. Create channel request')
    create_cls = cli_msgs[pva.ApplicationCommands.CREATE_CHANNEL]
    create_req = create_cls(count=1, channels={'id': 0x01, 'channel_name': pv})
    send(create_req)

    create_reply, buf, off = recv(buf)
    print('\n<-', create_reply)

    assert create_reply.status_type == pva.StatusType.OK

    server_chid = create_reply.server_chid

    # (5)
    print()
    print('- 5. Get field interface request')
    if_cls = cli_msgs[pva.ApplicationCommands.GET_FIELD]
    if_req = if_cls(server_chid=server_chid, ioid=1, sub_field_name='')
    send(if_req)

    if_reply, buf, off = recv(buf)
    pva.print_field_info(if_reply.field_if, user_types)

    pv_interface = if_reply.field_if

    struct_name = pv_interface['struct_name']
    print('Structure name is', struct_name)

    print()
    print('PV interface cache now contains:')
    # for i, (key, intf) in enumerate(cache.ours.items()):
    #     print('{}).'.format(i), key, intf)

    print(', '.join('{} ({})'.format(intf.get('struct_name', ''), key)
                    for key, intf in cache.ours.items()))

    reverse_cache = dict((v['struct_name'], k) for k, v in cache.ours.items()
                         if v.get('struct_name'))
    print('id for structure {} is {}'.format(struct_name,
                                             reverse_cache[struct_name]))

    # (6)
    print()
    print('- 6. Initialize the channel get request')
    get_cls = cli_msgs[pva.ApplicationCommands.GET]
    get_init_req = get_cls(server_chid=server_chid, ioid=2,
                           subcommand=pva.GetSubcommands.INIT,
                           pv_request_if='field(value)',
                           pv_request=dict(field=dict(value=None)),
                           # or if field() then pv_request ignored
                           )
    send(get_init_req)
    get_init_reply, buf, off = recv(buf)
    print('init reply', repr(get_init_reply)[:80], '...')
    interface = get_init_reply.pv_structure_if
    print()
    print('Field info according to init:')
    pva.print_field_info(interface, user_types)

    # (7)
    print()
    print('- 7. Perform an actual get request')
    get_cls = cli_msgs[pva.ApplicationCommands.GET]
    get_req = get_cls(server_chid=server_chid, ioid=2,  # <-- note same ioid
                      subcommand=pva.GetSubcommands.GET,
                      )
    send(get_req)
    get_reply, buf, off = recv(buf, interfaces=dict(pv_data=interface))
    get_data = get_reply.pv_data
    pva.print_field_info(interface, user_types,
                         values={'': get_data})

    assert len(buf) == 0
    return get_data


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
