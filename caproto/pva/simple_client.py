import sys
import socket
import ctypes
import random

from caproto import pva
from caproto import (get_netifaces_addresses, bcast_socket)


def send_message(sock, client_byte_order, server_byte_order, msg, cache):
    print('->', msg)
    header_cls = (pva.MessageHeaderLE
                  if server_byte_order == pva.LITTLE_ENDIAN
                  else pva.MessageHeaderBE)

    payload = msg.serialize(cache=cache)
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


def recv_message(sock, fixed_byte_order, server_byte_order, cache, buf):
    if not len(buf):
        buf = bytearray(sock.recv(4096))
        print('<-', buf)

    header_cls = (pva.MessageHeaderLE
                  if server_byte_order == pva.LITTLE_ENDIAN
                  else pva.MessageHeaderBE)

    header = header_cls.from_buffer(buf)
    assert header.valid

    if header.segment == pva.SegmentFlag.UNSEGMENTED:
        header, buf, offset = header_cls.deserialize(buf, cache=cache)
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
                                   use_fixed_byte_order=fixed_byte_order)

    print()
    print('<-', header)

    assert len(buf) >= header.payload_size
    return msg_class.deserialize(buf, cache=cache)


def search(*pvs):
    '''Search for a PV over the network by broadcasting over UDP

    Returns: (host, port)
    '''

    udp_sock = bcast_socket()
    port = 49152
    while True:
        try:
            udp_sock.bind(('', port))
        except IOError as ex:
            port = random.randint(49152, 65535)
        else:
            break

    seq_id = random.randint(1, 2 ** 31)
    search_ids = {pv: random.randint(1, 2 ** 31)
                  for pv in pvs}

    search_req = pva.SearchRequestLE(
        sequence_id=seq_id,
        flags=(pva.SearchFlags.reply_required | pva.SearchFlags.broadcast),
        response_address='127.0.0.1',   # TODO host ip
        response_port=port,
        protocols=['tcp'],
        channels=[{'id': search_ids[pv], 'channel_name': pv}
                  for pv in pvs]
    )

    # NOTE: cache needed here to give interface for channels
    cache = pva.SerializeCache(ours={}, theirs={}, user_types=pva.basic_types,
                               ioid_interfaces={})
    payload = search_req.serialize(cache=cache)

    header = pva.MessageHeaderLE(
        message_type=pva.MessageTypeFlag.APP_MESSAGE,
        direction=pva.DirectionFlag.FROM_CLIENT,
        endian=pva.LITTLE_ENDIAN,
        command=search_req.ID,
        payload_size=len(payload)
    )

    for addr, bcast_addr in get_netifaces_addresses():
        search_req.response_address = addr
        bytes_to_send = bytes(header) + search_req.serialize(cache=cache)

        dest = (addr, pva.PVA_BROADCAST_PORT)
        print('Sending SearchRequest to', bcast_addr,
              'requesting response at {}:{}'.format(addr, port))
        udp_sock.sendto(bytes_to_send, dest)

    response_data, addr = udp_sock.recvfrom(1024)
    response_data = bytearray(response_data)
    print('Received from', addr, ':', response_data)

    response_header, buf, offset = pva.MessageHeaderLE.deserialize(
        response_data, cache=pva.NullCache)
    assert response_header.valid

    msg_class = response_header.get_message(
        pva.DirectionFlag.FROM_SERVER, use_fixed_byte_order=pva.LITTLE_ENDIAN)

    print('Response header:', response_header)
    print('Response msg class:', msg_class)

    msg, buf, off = msg_class.deserialize(buf, cache=pva.NullCache)
    offset += off

    print('Response message:', msg)
    assert offset == len(response_data)

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


def main(host, server_port, pv):
    'Directly connect to a host that has a PV'
    # cache of types from server
    our_cache = {}
    # local copy of types cached on server
    their_cache = {}
    # locally-defined types
    user_types = pva.basic_types.copy()

    cache = pva.SerializeCache(ours=our_cache,
                               theirs=their_cache,
                               user_types=user_types,
                               ioid_interfaces={})

    sock = socket.create_connection((host, server_port))
    buf = bytearray(sock.recv(4096))

    # (1)
    print()
    print('- 1. initialization: byte order setting')
    msg, buf, offset = pva.SetByteOrder.deserialize(buf, cache=cache)
    print('<-', msg, msg.byte_order_setting, msg.byte_order)

    server_byte_order = msg.byte_order
    client_byte_order = server_byte_order

    cli_messages = pva.messages_grouped[(client_byte_order,
                                         pva.DirectionFlag.FROM_CLIENT)]

    # srv_msgs = pva.messages_grouped[(server_byte_order,
    #                                  pva.DirectionFlag.FROM_SERVER)]

    if msg.byte_order_setting == pva.EndianSetting.use_server_byte_order:
        fixed_byte_order = server_byte_order
        print('\n* Using fixed byte order:', server_byte_order)
    else:
        fixed_byte_order = None
        print('\n* Using byte order from individual messages.')

    # convenience functions:
    def send(msg):
        return send_message(sock, client_byte_order, server_byte_order, msg,
                            cache)

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

    auth_cls = cli_messages[pva.ApplicationCommands.CONNECTION_VALIDATION]
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
    create_cls = cli_messages[pva.ApplicationCommands.CREATE_CHANNEL]
    create_req = create_cls(count=1, channels={'id': 0x01, 'channel_name': pv})
    send(create_req)

    create_reply, buf, off = recv(buf)
    print('\n<-', create_reply)

    assert create_reply.status_type == pva.StatusType.OK

    server_chid = create_reply.server_chid

    # (5)
    print()
    print('- 5. Get field interface request')
    if_cls = cli_messages[pva.ApplicationCommands.GET_FIELD]
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
    get_ioid = 2
    get_cls = cli_messages[pva.ApplicationCommands.GET]
    get_init_req = get_cls(server_chid=server_chid, ioid=get_ioid,
                           subcommand=pva.Subcommands.INIT,
                           pv_request_if='field(value)',
                           pv_request=dict(field=dict(value=None)),
                           # or if field() then pv_request ignored
                           )
    send(get_init_req)
    get_init_reply, buf, off = recv(buf)
    print('init reply', repr(get_init_reply)[:80], '...')

    interface = get_init_reply.pv_structure_if
    cache.ioid_interfaces[get_ioid] = get_init_reply.pv_structure_if
    print()
    print('Field info according to init:')
    pva.print_field_info(interface, user_types)

    # (7)
    print()
    print('- 7. Perform an actual get request')
    get_cls = cli_messages[pva.ApplicationCommands.GET]
    get_req = get_cls(server_chid=server_chid, ioid=get_ioid,  # <-- note same ioid
                      subcommand=pva.Subcommands.GET,
                      )
    send(get_req)
    get_reply, buf, off = recv(buf)
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

    host, server_port = search(pv)
    main(host, server_port, pv)
