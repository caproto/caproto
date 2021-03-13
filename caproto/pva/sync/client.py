import collections
import copy
import dataclasses
import getpass
import logging
import socket
import time
import typing
from typing import Dict, Tuple

# REBASE TODO this will go away - need to rebase
from caproto import (MAX_UDP_RECV, bcast_socket, get_client_address_list,
                     get_environment_variables, pva)
from caproto.pva import (CLIENT, CONNECTED, DISCONNECTED, NEED_DATA,
                         AddressTuple, Broadcaster, CaprotoError,
                         ChannelFieldInfoResponse, ChannelGetResponse,
                         ChannelMonitorResponse, ChannelPutResponse,
                         ClientChannel, ClientVirtualCircuit,
                         ConnectionValidatedResponse,
                         ConnectionValidationRequest, CreateChannelResponse,
                         ErrorResponseReceived, MonitorSubcommand, QOSFlags,
                         SearchResponse, Subcommand, VirtualCircuit)

from ..._utils import safe_getsockname
from .._dataclass import (dataclass_from_field_desc, fill_dataclass,
                          is_pva_dataclass_instance)

# Make a dict to hold our tcp sockets.
sockets: Dict[VirtualCircuit, socket.socket] = {}
global_circuits: Dict[AddressTuple, VirtualCircuit] = {}

env = get_environment_variables()
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
        for host, port in get_client_address_list(protocol='PVA'):
            udp_sock.sendto(bytes_to_send, (host, port))
            logger.debug('Search request sent to %r.', (host, port))
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
            except ConnectionResetError as ex:
                # Win32: "On a UDP-datagram socket this error indicates a
                # previous send operation resulted in an ICMP Port Unreachable
                # message."
                #
                # https://docs.microsoft.com/en-us/windows/win32/api/winsock/nf-winsock-recvfrom
                #
                # Despite the above, this does not *appear* to be fatal;
                # sometimes the second try will work.
                logger.debug('Connection reset, retrying: %s', ex)
                check_timeout()
                time.sleep(0.1)
                continue
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
                    if command.server_address == '0.0.0.0':
                        host_port = (address[0],
                                     command.server_port)
                    else:
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

    read_request = chan.read(pvrequest=pvrequest)
    send(chan.circuit, read_request)

    for response in _receive_commands(chan.circuit, timeout):
        if isinstance(response, ChannelFieldInfoResponse):
            # interface = response.field_if
            ...
        elif isinstance(response, ChannelGetResponse):
            if not response.status.is_successful:
                raise ErrorResponseReceived(str(response.status))
            if response.status.message:
                logger.info('Message from server: %s', response.status)

            if response.subcommand == Subcommand.INIT:
                read_request.to_get()
                send(chan.circuit, read_request)
            elif response.subcommand == Subcommand.GET:
                interface = response.pv_data.interface
                value = response.pv_data.data
                dataclass = dataclass_from_field_desc(interface)
                instance = dataclass()
                fill_dataclass(instance, value)
                return response, instance


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
    request: pva.ChannelMonitorRequest = chan.subscribe(pvrequest=pvrequest)
    send(chan.circuit, request)

    dataclass = None
    instance = None
    event_count = 0
    for response in _receive_commands(chan.circuit, timeout=None):
        if not isinstance(response, ChannelMonitorResponse):
            continue

        response: ChannelMonitorResponse

        if response.subcommand == MonitorSubcommand.INIT:
            if not response.status.is_successful:
                raise ErrorResponseReceived(str(response.status))

            if response.status.message:
                logger.info('Message from server: %s', response.status)

            send(chan.circuit, request.to_start())

            field_desc = response.pv_structure_if
            dataclass = dataclass_from_field_desc(field_desc)
            instance = dataclass()
        else:
            event_data = response.pv_data.data  # and 'field'
            fill_dataclass(instance, event_data)
            yield response, copy.deepcopy(instance)

            if maximum_events is not None:
                event_count += 1
                if event_count >= maximum_events:
                    break


def monitor(pv_name, *, pvrequest='field()', verbose=False, timeout=1,
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


def _read_and_write(chan, timeout, value, pvrequest='field()',
                    cancel_on_keyboardinterrupt=False):
    """
    Read then write structured data to the given channel.
    """
    # TODO: validate dictionary keys against the interface.
    request: pva.ChannelPutRequest = chan.write(pvrequest=pvrequest)

    send(chan.circuit, request)
    if is_pva_dataclass_instance(value):
        value = dataclasses.asdict(value)
    if not isinstance(value, dict):
        value = {'value': value}

    dataclass = None
    old_value = None
    ioid = None

    try:
        for command in _receive_commands(chan.circuit, timeout):
            if not isinstance(command, ChannelPutResponse):
                continue

            command = typing.cast(ChannelPutResponse, command)
            if not command.status.is_successful:
                raise ErrorResponseReceived(str(command.status))
            if command.status.message:
                logger.info('Message from server: %s', command.status)

            if command.subcommand == Subcommand.INIT:
                ioid = command.ioid

                # Get the latest value with this request
                send(chan.circuit, request.to_get())

                # Then perform the write request
                dataclass = dataclass_from_field_desc(command.put_structure_if)
                instance = dataclass()

                # TODO logic can move up to the circuit?
                bitset = fill_dataclass(instance, value)

                request.to_default(
                    put_data=pva.DataWithBitSet(data=instance,
                                                bitset=bitset)
                )
                send(chan.circuit, request)
            elif command.subcommand == Subcommand.GET:
                old_value = dataclass()
                bitset = fill_dataclass(old_value, command.put_data.data)
            elif command.subcommand == Subcommand.DEFAULT:
                return old_value, command
    except KeyboardInterrupt:
        if ioid is not None and cancel_on_keyboardinterrupt:
            send(chan.circuit, chan.cancel(ioid))
        raise


def read_write_read(pv_name: str, data: dict, *,
                    options: typing.Optional[dict] = None,
                    pvrequest: str = 'field()',
                    cancel_on_keyboardinterrupt: bool = False,
                    timeout=1):
    """
    Write to a Channel, but sandwich the write between two reads.

    Parameters
    ----------
    pv_name : str
        The PV name.

    data : dict or Mapping
        The structured data to write.

    pvrequest : str, optional
        The PVRequest, such as 'field(value)'.  Defaults to 'field()' for
        retrieving all data.

    options : dict, optional
        Options to use in the pvRequest. (TODO not yet implemented)

    timeout : float, optional
        Timeout for the operation.

    cancel_on_keyboardinterrupt : bool, optional
        Cancel the write in the event of a KeyboardInterrupt.
    """
    udp_sock, udp_port = make_broadcaster_socket()
    try:
        udp_sock.settimeout(timeout)
        chan = make_channel(pv_name, udp_sock, udp_port, timeout)
    finally:
        udp_sock.close()

    try:
        initial, res = _read_and_write(
            chan, timeout, data, pvrequest=pvrequest,
            cancel_on_keyboardinterrupt=cancel_on_keyboardinterrupt
        )
        _, final = _read(chan, timeout, pvrequest=pvrequest)
    finally:
        try:
            if chan.states[CLIENT] is CONNECTED:
                send(chan.circuit, chan.disconnect())
        finally:
            sockets[chan.circuit].close()
            del sockets[chan.circuit]
            del global_circuits[chan.circuit.address]

    return initial, res, final
