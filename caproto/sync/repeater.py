# Channel Access Repeater
#
# The CA Repeater is basically a UDP proxy server. Its only role is to forward
# server beacons (a.k.a RsrvIsUp commands) to all clients on a host. It exists
# to cope with older system that do not broadcast correctly, failing to fan out
# the message to all clients reliably.

# Operation:
# 1. Try to bind to 0.0.0.0 on the CA REPEATER PORT. This may be set by the
#    environment variable EPICS_CA_REPEATER_PORT. The default is 5065.
# 2. If binding fails, assume a CA Repeater is already running. Exit.
# 3. When a UDP datagram is received from an unknown port:
#    - Check that the source host is localhost. If it is not, ignore it.
#    - The datagram data may be a RegisterRepeaterRequest (recent versions of
#      Channel Access) or blank (old versions of Channel Access).
#    - Stash the source port number.
#    - Send a RepeaterConfirmResponse to that source port.
#    - Send an empty datagram to any other ports we have stashed.
#    - Forward all subsequent messages to all ports we know about.


import logging
import socket
import time

import caproto


logger = logging.getLogger('repeater')


class RepeaterAlreadyRunning(RuntimeError):
    ...


def check_clients(clients, skip=None):
    'Check clients by binding to their ports on specific interfaces'
    # no_op = bytes(caproto.VersionRequest(priority=0, version=0).header)
    sock = None
    for port, host in clients.items():
        addr = (host, port)
        if sock is None:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,
                                 socket.IPPROTO_UDP)
        try:
            sock.bind(addr)
        except Exception as ex:
            # in use, still taken by client
            ...
        else:
            # free - time to remove client
            sock = None
            yield addr


def _update_all(clients, servers, *, remove_clients=None,
                checkin_threshold=60):
    'Update client and server dicts (remove clients, check heartbeat)'
    nclients_init, nservers_init = len(clients), len(servers)
    if remove_clients:
        for host, port in remove_clients:
            logger.debug('Removing client %s:%d', host, port)
            del clients[port]

    for server_port, server_info in list(servers.items()):
        last_checkin = time.time() - server_info['up_at']
        if last_checkin > checkin_threshold:
            del servers[server_port]

    nclients, nservers = len(clients), len(servers)
    if (nclients, nservers) != (nclients_init, nservers_init):
        logger.debug('Active clients: %d servers: %d', nclients, nservers)


def _run_repeater(server_sock, bind_addr):
    'Run the repeater using server_socket and bind_address'
    bind_host, bind_port = bind_addr

    servers = {}
    clients = {}
    broadcaster = caproto.Broadcaster(our_role=caproto.SERVER)

    while True:
        # NOTE: this magic numer is MAX_UDP_RECV in epics-base
        msg, addr = server_sock.recvfrom(0xffff - 16)
        client_host, client_port = addr

        if client_port in clients and clients[client_port] != client_host:
            # broadcast only from one interface
            continue
        elif client_port not in clients:
            clients[client_port] = client_host
            logger.debug('New client %s', addr)
            # confirmation = caproto.RepeaterConfirmResponse(bind_host)
            # confirmation_bytes = broadcaster.send(confirmation)

        try:
            commands = broadcaster.recv(msg, addr)
            broadcaster.process_commands(commands)
        except Exception as ex:
            logger.exception('Failed to process incoming packet')
            continue

        bytes_to_broadcast = b''.join(bytes(cmd) for cmd in commands)

        for command in commands:
            # logger.debug('[%s] Received %r', addr, command)
            if isinstance(command, caproto.RsrvIsUpResponse):
                servers[command.server_port] = dict(up_at=time.time())
            elif isinstance(command, caproto.RepeaterRegisterRequest):
                confirmation_bytes = broadcaster.send(
                    caproto.RepeaterConfirmResponse(client_host))

                server_sock.sendto(confirmation_bytes, (client_host,
                                                        client_port))

                remove_clients = list(check_clients(clients, skip=client_port))
                _update_all(clients, servers,
                            remove_clients=remove_clients)

        to_remove = []
        for other_port, other_host in clients.items():
            if other_port != client_port:
                try:
                    server_sock.sendto(bytes_to_broadcast, (other_host,
                                                            other_port))
                except Exception as ex:
                    to_remove.append((other_host, other_port))

        if to_remove:
            _update_all(clients, servers,
                        remove_clients=to_remove)


def check_for_running_repeater(addr):
    '''If a repeater is already running, this raises RepeaterAlreadyRunning

    Parameters
    ----------
    addr : (ip, port)

    Returns
    -------
    socket : socket.socket
        Socket used to check
    '''
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.bind(addr)
    except OSError as ex:
        if 'Address already in use' in str(ex):
            raise RepeaterAlreadyRunning(str(ex))
        else:
            raise
    return sock


def run(host='0.0.0.0'):
    port = caproto.get_environment_variables()['EPICS_CA_REPEATER_PORT']
    addr = (host, port)
    logger.debug('Checking for another repeater')

    try:
        sock = check_for_running_repeater(addr)
    except RepeaterAlreadyRunning:
        logger.error('Another repeater is already running; exiting')
        return

    try:
        _run_repeater(sock, addr)
    except KeyboardInterrupt:
        logger.info('Keyboard interrupt; exiting')
