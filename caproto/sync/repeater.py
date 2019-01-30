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
import subprocess
import sys
import time
import warnings

import caproto
from caproto._constants import MAX_UDP_RECV
from caproto._utils import get_environment_variables


logger = logging.getLogger('caproto.repeater')


class RepeaterAlreadyRunning(RuntimeError):
    ...


def check_clients(clients, skip=None):
    'Check clients by binding to their ports on specific interfaces'
    sock = None
    for port, host in clients.items():
        addr = (host, port)
        if sock is None:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,
                                 socket.IPPROTO_UDP)
        try:
            sock.bind(addr)
        except Exception:
            # in use, still taken by client
            ...
        else:
            # free - time to remove client
            sock = None
            yield addr


checkin_threshold = get_environment_variables()['EPICS_CA_CONN_TMO']


def _update_all(clients, servers, *, remove_clients=None,
                checkin_threshold=checkin_threshold):
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

    logger.info("Repeater is listening on %s:%d", bind_host, bind_port)
    while True:
        msg, addr = server_sock.recvfrom(MAX_UDP_RECV)
        host, port = addr

        if port in clients and clients[port] != host:
            # broadcast only from one interface
            continue
        elif (port in servers and servers[port]['host'] != host):
            continue

        try:
            commands = broadcaster.recv(msg, addr)
            broadcaster.process_commands(commands)
        except Exception:
            logger.exception('Failed to process incoming datagram')
            continue

        if not commands:
            # NOTE: additional valid way of registration is an empty
            # message, according to broadcaster source
            if port not in clients:
                clients[port] = host
                logger.debug('New client %s (zero-length registration)', addr)
            continue

        to_forward = []
        for command in commands:
            if isinstance(command, caproto.Beacon):
                # Update our records of the last time each server checked in
                # (i.e. issued a heartbeat).
                servers[command.server_port] = dict(up_at=time.time(),
                                                    host=host)
                # The sender of this command may leave the IP field empty (0),
                # leaving it up to the repeater to fill in the address so that
                # the ultimate recipient knows the correct origin. By leaving
                # that up to the repeater, the sender avoids providing the
                # wrong return address (i.e. picking the wrong interface). It
                # is safer to let the repeater determine the return address
                # by inspection.
                if command.header.parameter2 == 0:
                    updated_ip = caproto.ipv4_to_int32(host)
                    command.header.parameter2 = updated_ip
                to_forward.append(command)
            elif isinstance(command, caproto.RepeaterRegisterRequest):
                if port not in clients:
                    clients[port] = host
                    logger.debug('New client %s', addr)

                confirmation_bytes = broadcaster.send(
                    caproto.RepeaterConfirmResponse(host))

                try:
                    server_sock.sendto(confirmation_bytes, (host, port))
                except OSError as exc:
                    raise caproto.CaprotoNetworkError(
                        f"Failed to send to {host}:{port}") from exc

                remove_clients = list(check_clients(clients, skip=port))
                _update_all(clients, servers, remove_clients=remove_clients)
                # Do not broadcast registration requests to other clients.
                # Omit it from `to_forward`.
            else:
                to_forward.append(command)
        bytes_to_broadcast = b''.join(bytes(cmd) for cmd in to_forward)
        to_remove = []
        for other_port, other_host in clients.items():
            if other_port != port:
                try:
                    server_sock.sendto(bytes_to_broadcast, (other_host,
                                                            other_port))
                except Exception:
                    to_remove.append((other_host, other_port))

        if to_remove:
            _update_all(clients, servers, remove_clients=to_remove)


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
        elif 'WinError 10048' in str(ex):
            # [WinError 10048] Only one usage of each socket address
            # (protocol/network address/port) is normally permitted
            raise RepeaterAlreadyRunning(str(ex))
        else:
            raise
    return sock


def run(host='0.0.0.0'):
    port = caproto.get_environment_variables()['EPICS_CA_REPEATER_PORT']
    addr = (host, port)
    logger.debug('Checking for another repeater....')

    try:
        sock = check_for_running_repeater(addr)
    except RepeaterAlreadyRunning:
        logger.info('Another repeater is already running; exiting.')
        return

    try:
        _run_repeater(sock, addr)
    except KeyboardInterrupt:
        logger.info('Keyboard interrupt; exiting.')


def spawn_repeater():
    """
    Spawn a repeater process unless one is not already running.
    """
    host = '0.0.0.0'  # not configurable for a spawned repeater
    port = caproto.get_environment_variables()['EPICS_CA_REPEATER_PORT']
    try:
        sock = check_for_running_repeater((host, port))
    except RepeaterAlreadyRunning:
        logger.debug('Another repeater is already running; will not spawn '
                     'one.')
        return
    # We will now spawn a repeater in a subprocess at the same address as sock.
    # Make the address reusable so that, if the OS does not clean up sock
    # before the subprocess tries to bind to it, there is no conflict.
    try:
        reuse = socket.SO_REUSEADDR
    except AttributeError:
        warnings.warn("SO_REUSEADDR is not supported on this platform.")
    else:
        sock.setsockopt(socket.SOL_SOCKET, reuse, 1)
    logger.debug('Spawning caproto-repeater process....')
    try:
        subprocess.Popen(
            [sys.executable, '-m', 'caproto.commandline.repeater', '--quiet'],
            cwd="/")
    except Exception:
        logger.exception('Failed to spawn repeater.')
