import collections
import dataclasses
import getpass
import logging
import socket
import time
import typing
from typing import Dict, Tuple

# REBASE TODO this will go away - need to rebase
from caproto import (MAX_UDP_RECV, bcast_socket, get_address_list,
                     get_environment_variables, pva)
from caproto.pva import (CLIENT, CONNECTED, DISCONNECTED, NEED_DATA,
                         Broadcaster, CaprotoError, ChannelFieldInfoResponse,
                         ChannelGetResponse, ChannelMonitorResponse,
                         ChannelPutResponse, ClientChannel,
                         ClientVirtualCircuit, ConnectionValidatedResponse,
                         ConnectionValidationRequest, CreateChannelResponse,
                         ErrorResponseReceived, MonitorSubcommand, QOSFlags,
                         SearchResponse, Subcommand, VirtualCircuit)

from ..._utils import safe_getsockname
from .._dataclass import (dataclass_from_field_desc, fill_dataclass,
                          is_pva_dataclass_instance)

# Make a dict to hold our tcp sockets.
AddressTuple = Tuple[str, int]

sockets: Dict[VirtualCircuit, socket.socket] = {}
global_circuits: Dict[AddressTuple, VirtualCircuit] = {}

env = get_environment_variables()
broadcast_port = env['EPICS_PVA_BROADCAST_PORT']

logger = logging.getLogger('caproto.pva.ctx')
serialization_logger = logging.getLogger('caproto.pva.serialization_debug')


# Convenience functions that do both transport and caproto validation/ingest.
def send(circuit, command, pv_name=None):
    if pv_name is not None:
        tags = {'pv': pv_name}
    else:
        tags = None
    buffers_to_send = circuit.send(command, extra=tags)
    sockets[circuit].sendmsg(buffers_to_send)

    if serialization_logger.isEnabledFor(logging.DEBUG):
        to_send = b''.join(buffers_to_send)
        serialization_logger.debug('-> %d bytes: %r', len(to_send), to_send)


def recv(circuit):
    commands = collections.deque()
    bytes_received = sockets[circuit].recv(4096)
    for c, remaining in circuit.recv(bytes_received):
        if c is NEED_DATA:
            break
        circuit.process_command(c)
        commands.append(c)

    return commands


def make_broadcaster_socket() -> Tuple[socket.socket, int]:
    """
    Make and bind a broadcaster socket.

    Returns
    -------
    udp_sock : socket.socket
        The UDP socket.

    port : int
        The bound port.
    """
    udp_sock = bcast_socket()
    udp_sock.bind(('', 0))
    port = udp_sock.getsockname()[1]
    logger.debug('Bound to UDP port %d for search', port)
    return udp_sock, port


def search(pv, udp_sock, udp_port, timeout, max_retries=2):
    """
    Search for a PV over the network by broadcasting over UDP

    Returns: (host, port)
    """
    broadcaster = Broadcaster(our_role=CLIENT, broadcast_port=udp_port)
    broadcaster.client_address = safe_getsockname(udp_sock)

    def send_search(message):
        bytes_to_send = broadcaster.send(message)
        for host in get_address_list(protocol='PVA'):
            udp_sock.sendto(bytes_to_send, (host, broadcast_port))
            logger.debug('Search request sent to %r.', (host, broadcast_port))
            logger.debug('%s', bytes_to_send)

    def check_timeout():
        nonlocal retry_at

        if time.monotonic() >= retry_at:
            send_search(search_req)
            retry_at = time.monotonic() + retry_timeout

        if time.monotonic() - t > timeout:
            raise TimeoutError(
                f"Timed out while awaiting a response searching for {pv!r}"
            )

    # Initial search attempt
    pv_to_cid, search_req = broadcaster.search(pv)
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

            commands = broadcaster.recv(bytes_received, address)
            broadcaster.process_commands(commands)
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


def make_channel(pv_name, udp_sock, udp_port, timeout):
    # log = logging.LoggerAdapter(logging.getLogger('caproto.pva.ch'),
    #                             {'pv': pv_name})
    address = search([pv_name], udp_sock, udp_port, timeout)
    try:
        circuit = global_circuits[address]
    except KeyError:
        circuit = ClientVirtualCircuit(
            our_role=CLIENT, address=address,
            priority=QOSFlags.encode(priority=0, flags=0)
        )
        global_circuits[address] = circuit

    chan = ClientChannel(pv_name, circuit)

    if chan.circuit not in sockets:
        sockets[chan.circuit] = socket.create_connection(chan.circuit.address,
                                                         timeout)
        circuit.our_address = sockets[chan.circuit].getsockname()

    try:
        for command in _receive_commands(circuit, timeout=timeout):
            if isinstance(command, ConnectionValidationRequest):
                if command.auth_nz and 'ca' in command.auth_nz:
                    auth_method = 'ca'
                    auth_data = pva.ChannelAccessAuthentication(
                        user=getpass.getuser(),
                        host=socket.gethostname(),
                    )
                elif command.auth_nz and 'anonymous' in command.auth_nz:
                    auth_method = 'anonymous'
                    auth_data = None
                else:
                    auth_method = ''
                    auth_data = None

                response = circuit.validate_connection(
                    buffer_size=command.server_buffer_size,
                    registry_size=command.server_registry_size,
                    connection_qos=0,
                    auth_nz=auth_method,
                    data=auth_data,
                )
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


def _receive_commands(circuit, timeout):
    t = time.monotonic()
    while True:
        try:
            commands = recv(circuit)
        except socket.timeout:
            commands = []

        for command in commands:
            yield command
            if command is DISCONNECTED:
                raise CaprotoError(
                    'Disconnected while waiting for a response'
                )

        if timeout is not None and time.monotonic() - t > timeout:
            raise TimeoutError("Timeout while awaiting reading.")


def _read(chan, timeout, pvrequest):
    interface_req = chan.read_interface()
    send(chan.circuit, interface_req)

    init_req = chan.read_init(pvrequest=pvrequest)
    ioid = init_req.ioid

    send(chan.circuit, init_req)

    for command in _receive_commands(chan.circuit, timeout):
        if isinstance(command, ChannelFieldInfoResponse):
            # interface = command.field_if
            ...
        elif isinstance(command, ChannelGetResponse):
            if not command.status.is_successful:
                raise ErrorResponseReceived(str(command.status))
            if command.status.message:
                logger.info('Message from server: %s', command.status)

            if command.subcommand == Subcommand.INIT:
                interface = command.pv_structure_if
                read_req = chan.read(ioid, interface=interface)
                send(chan.circuit, read_req)
            elif command.subcommand == Subcommand.GET:
                interface = command.pv_data.interface
                value = command.pv_data.data
                dataclass = dataclass_from_field_desc(interface)
                instance = dataclass()
                fill_dataclass(instance, value)
                command.dataclass_instance = instance
                return command


def read(pv_name, *, pvrequest='field()', verbose=False, timeout=1):
    """
    Read a Channel.

    Parameters
    ----------
    pv_name : str
        The PV name.

    pvrequest : str, optional
        The PVRequest, such as 'field(value)'.  Defaults to 'field()' for
        retrieving all data.

    verbose : boolean, optional
        Verbose logging. Default is False.

    timeout : float, optional
        Default is 1 second.

    Returns
    -------

    Examples
    --------
    Get the value of a Channel named 'cat'.
    >>> get('cat')
    """
    udp_sock, udp_port = make_broadcaster_socket()
    try:
        udp_sock.settimeout(timeout)
        chan = make_channel(pv_name, udp_sock, udp_port, timeout)
    finally:
        udp_sock.close()

    try:
        return _read(chan, timeout, pvrequest=pvrequest)
    finally:
        try:
            if chan.states[CLIENT] is CONNECTED:
                send(chan.circuit, chan.disconnect())
        finally:
            sockets[chan.circuit].close()
            del sockets[chan.circuit]
            del global_circuits[chan.circuit.address]


def _monitor(chan, timeout, pvrequest, maximum_events):
    """Monitor a channel, using pvrequest, up to maximum_events."""
    interface_req = chan.read_interface()
    send(chan.circuit, interface_req)

    init_req = chan.subscribe_init(pvrequest=pvrequest)
    ioid = init_req.ioid
    send(chan.circuit, init_req)

    dataclass = None
    instance = None
    event_count = 0
    for command in _receive_commands(chan.circuit, timeout=None):
        if isinstance(command, ChannelMonitorResponse):
            if command.subcommand == Subcommand.INIT:
                if not command.status.is_successful:
                    raise ErrorResponseReceived(str(command.status))
                if command.status.message:
                    logger.info('Message from server: %s', command.status)

                monitor_start_req = chan.subscribe_control(
                    ioid=ioid, subcommand=MonitorSubcommand.START)
                send(chan.circuit, monitor_start_req)

                field_desc = command.pv_structure_if
                dataclass = dataclass_from_field_desc(field_desc)
                instance = dataclass()
                command.dataclass_instance = instance
                yield command
            else:
                event_count += 1
                # fill_dataclass(instance, command.pv_data.data)
                command.dataclass_instance = instance
                yield command
                if maximum_events is not None:
                    if event_count >= maximum_events:
                        break


def monitor(pv_name, *, pvrequest, verbose=False, timeout=1,
            maximum_events=None):
    """
    Monitor a Channel.

    Parameters
    ----------
    pv_name : str
        The PV name.

    pvrequest : str
        The PVRequest, such as 'field(value)'.

    verbose : boolean, optional
        Verbose logging. Default is False.

    timeout : float, optional
        Default is 1 second.

    Returns
    -------

    Examples
    --------
    """
    udp_sock, udp_port = make_broadcaster_socket()
    try:
        udp_sock.settimeout(timeout)
        chan = make_channel(pv_name, udp_sock, udp_port, timeout)
    finally:
        udp_sock.close()

    try:
        yield from _monitor(chan, timeout, pvrequest=pvrequest,
                            maximum_events=maximum_events)
    finally:
        try:
            if chan.states[CLIENT] is CONNECTED:
                send(chan.circuit, chan.disconnect())
        finally:
            sockets[chan.circuit].close()
            del sockets[chan.circuit]
            del global_circuits[chan.circuit.address]


def _write(chan, timeout, value):
    """
    Write structured data to channel.
    """
    # TODO: validate dictionary keys against the interface.
    init_req = chan.write_init(pvrequest='field()')
    ioid = init_req.ioid
    send(chan.circuit, init_req)
    if is_pva_dataclass_instance(value):
        value = dataclasses.asdict(value)
    if not isinstance(value, dict):
        value = {'value': value}

    for command in _receive_commands(chan.circuit, timeout):
        if isinstance(command, ChannelFieldInfoResponse):
            # interface = command.field_if
            ...
        elif isinstance(command, ChannelPutResponse):
            if not command.status.is_successful:
                raise ErrorResponseReceived(str(command.status))
            if command.status.message:
                logger.info('Message from server: %s', command.status)
            if command.subcommand == Subcommand.INIT:
                interface = command.put_structure_if
                instance = dataclass_from_field_desc(interface)()
                # TODO logic can move up to the circuit
                bitset = fill_dataclass(instance, value)
                write_req = chan.write(ioid, instance, bitset)
                send(chan.circuit, write_req)
            elif command.subcommand == Subcommand.DEFAULT:
                return command


def read_write_read(pv_name: str, data: dict, *,
                    options: typing.Optional[dict] = None,
                    pvrequest: str = 'field()',
                    timeout=1):
    """
    Write to a Channel, but sandwich the write between two reads.

    Parameters
    ----------
    pv_name : str
        The PV name.

    data : dict or Mapping
        The structured data to write.

    options : dict, optional
        Options to use in the pvRequest.
    """
    udp_sock, udp_port = make_broadcaster_socket()
    try:
        udp_sock.settimeout(timeout)
        chan = make_channel(pv_name, udp_sock, udp_port, timeout)
    finally:
        udp_sock.close()

    try:
        initial = _read(chan, timeout, pvrequest=pvrequest)
        res = _write(chan, timeout, data)
        final = _read(chan, timeout, pvrequest=pvrequest)
    finally:
        try:
            if chan.states[CLIENT] is CONNECTED:
                send(chan.circuit, chan.disconnect())
        finally:
            sockets[chan.circuit].close()
            del sockets[chan.circuit]
            del global_circuits[chan.circuit.address]

    return initial, res, final
