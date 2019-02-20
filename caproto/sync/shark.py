import ctypes
from dpkt.pcap import Reader
from dpkt.ethernet import Ethernet
from dpkt.tcp import TCP
from dpkt.udp import UDP
from dpkt.ip6 import IP6
from socket import inet_ntoa
from types import SimpleNamespace


from .. import NEED_DATA
from .._headers import MessageHeader, ExtendedMessageHeader
from .._commands import (AccessRightsResponse, CreateChFailResponse,
                         ClearChannelRequest,
                         ClientNameRequest, CreateChanRequest,
                         CreateChanResponse, EventAddRequest, EventAddResponse,
                         EchoRequest, ErrorResponse, SearchRequest,
                         EventsOnRequest, EventsOffRequest,
                         NotFoundResponse, ReadSyncRequest, Beacon,
                         RepeaterConfirmResponse, RepeaterRegisterRequest,
                         EventCancelRequest, EventCancelResponse,
                         HostNameRequest, ReadNotifyRequest, ReadRequest,
                         ReadNotifyResponse, ReadResponse,
                         SearchResponse, ServerDisconnResponse,
                         VersionRequest, VersionResponse, WriteNotifyRequest,
                         WriteNotifyResponse, WriteRequest)
from .._utils import ValidationError


# These are similar to read_datagram and read_from_bytestream in _commands.py
# but in this situation we do not have access to the role (CLIENT|SERVER); we
# have to infer it on the message-by-message basis.

def read_datagram(data, address):
    "Parse bytes from one datagram into one or more commands."
    if len(data) < 16:
        raise ValidationError("Not enough bytes to be a CA header")
    barray = bytearray(data)
    commands = []
    while barray:
        header = MessageHeader.from_buffer(barray)
        barray = barray[_MessageHeaderSize:]
        _class = infer_command_class(header)
        payload_size = header.payload_size
        if _class.HAS_PAYLOAD:
            payload_bytes = barray[:header.payload_size]
            barray = barray[payload_size:]
        else:
            payload_bytes = None
        command = _class.from_wire(header, payload_bytes,
                                   sender_address=address,
                                   validate=True)
        commands.append(command)
    return commands


_MessageHeaderSize = ctypes.sizeof(MessageHeader)
_ExtendedMessageHeaderSize = ctypes.sizeof(ExtendedMessageHeader)


def bytes_needed_for_command(data):
    '''
    Parameters
    ----------
    data

    Returns
    -------
    (header, num_bytes_needed)
    '''

    header_size = _MessageHeaderSize
    data_len = len(data)

    # We need at least one header's worth of bytes to interpret anything.
    if data_len < header_size:
        return None, header_size - data_len

    header = MessageHeader.from_buffer(data)
    # Looks for sentinels that mark this as an "extended header".
    if header.payload_size == 0xFFFF and header.data_count == 0:
        header_size = _ExtendedMessageHeaderSize
        # Do we have enough bytes to interpret the extended header?
        if data_len < header_size:
            return None, header_size - data_len
        header = ExtendedMessageHeader.from_buffer(data)

    total_size = header_size + header.payload_size
    # Do we have all the bytes in the payload?
    if data_len < total_size:
        return header, total_size - data_len
    return header, 0


def read_from_bytestream(data):
    '''
    Parameters
    ----------
    data

    Returns
    -------
    (remaining_data, command, num_bytes_needed)
        if more data is required, NEED_DATA will be returned in place of
        `command`
    '''

    header, num_bytes_needed = bytes_needed_for_command(data)

    if num_bytes_needed > 0:
        return data, NEED_DATA, num_bytes_needed

    class_ = infer_command_class(header)

    header_size = ctypes.sizeof(header)
    total_size = header_size + header.payload_size

    # Receive the buffer (zero-copy).
    payload_bytes = memoryview(data)[header_size:total_size]
    command = class_.from_wire(header, payload_bytes, validate=True)
    # Advance the buffer.
    return data[total_size:], command, 0


class EventAddRequestOrResponse(EventAddRequest, register=False):
    "We cannot tell if it is a request or a response."
    pass


class EchoRequestOrResponse(EchoRequest, register=False):
    "We cannot tell if it is a request or a response."
    pass


class ClearChannelRequestOrResponse(ClearChannelRequest, register=False):
    "We cannot tell if it is a request or a response."
    pass


one_way_commands = {
    AccessRightsResponse.ID: AccessRightsResponse,
    ClearChannelRequestOrResponse.ID: ClearChannelRequestOrResponse,
    ClientNameRequest.ID: ClientNameRequest,
    CreateChFailResponse.ID: CreateChFailResponse,
    EchoRequestOrResponse.ID: EchoRequestOrResponse,
    ErrorResponse.ID: ErrorResponse,
    EventsOffRequest.ID: EventsOffRequest,
    EventsOnRequest.ID: EventsOnRequest,
    HostNameRequest.ID: HostNameRequest,
    NotFoundResponse.ID: NotFoundResponse,
    ReadSyncRequest.ID: ReadSyncRequest,
    Beacon.ID: Beacon,
    WriteRequest.ID: WriteRequest,
    ServerDisconnResponse.ID: ServerDisconnResponse,
    RepeaterConfirmResponse.ID: RepeaterConfirmResponse,
    RepeaterRegisterRequest.ID: RepeaterRegisterRequest,
}


def sniff_version_header(header):
    if header.parameter1 == 0:
        return VersionRequest
    if header.parameter1 == 1:
        return VersionResponse
    else:
        raise ValueError("Unidentifiable command.")


def sniff_search_header(header):
    if header.payload_size == 0 or (header.payload_size == 8 and header.data_count == 0):
        return SearchResponse
    else:
        return SearchRequest


def sniff_event_add_or_cancel_header(header):
    if header.command == 2:
        return EventCancelRequest
    # Special case for EventCancelResponse which is coded inconsistently.
    if header.command == 1 and header.payload_size == 0 and header.data_count == 0:
        return EventCancelResponse
    if header.payload_size == 16:
        if header.parameter1 > 60:
            return EventAddRequest
        else:
            return EventAddRequestOrResponse  # probably Request but cannot be sure
    else:
        return EventAddResponse


def sniff_create_chan_header(header):
    if header.payload_size == 0:
        return CreateChanResponse
    else:
        return CreateChanRequest


def sniff_read_header(header):
    if header.payload_size == 0:
        return ReadRequest
    else:
        return ReadResponse


def sniff_read_notify_header(header):
    if header.payload_size == 0:
        return ReadNotifyRequest
    else:
        return ReadNotifyResponse


def sniff_write_notify_header(header):
    if header.payload_size == 0:
        return WriteNotifyResponse
    else:
        return WriteNotifyRequest


sniffers = {
    VersionRequest.ID: sniff_version_header,
    SearchRequest.ID: sniff_search_header,
    EventAddRequest.ID: sniff_event_add_or_cancel_header,
    EventCancelRequest.ID: sniff_event_add_or_cancel_header,
    ReadRequest.ID: sniff_read_header,
    ReadNotifyRequest.ID: sniff_read_notify_header,
    WriteNotifyRequest.ID: sniff_write_notify_header,
    CreateChanRequest.ID: sniff_create_chan_header,
}


def infer_command_class(header):
    id_ = header.command
    try:
        return one_way_commands[id_]
    except KeyError:
        try:
            return sniffers[id_](header)
        except KeyError:
            raise ValidationError("Unknown command ID")


def shark(file):
    """
    Parse pcap (tcpdump) to extract networking info and CA commands.

    This function is also accessible via a CLI installed with caproto. Example::

        sudo tcpdump -w - | caproto-shark

    Parameters
    ----------
    file : buffer

    Yields
    ------
    command_context : SimpleNamespace
        Contains timestamp, ethernet, src, dst, ip, transport, and command.
    """
    banned = set()
    for timestamp, buffer in Reader(file):
        ethernet = Ethernet(buffer)
        ip = ethernet.data
        transport = ip.data
        if not isinstance(transport, (TCP, UDP)):
            continue
        try:
            try:
                src = inet_ntoa(ip.src)
                dst = inet_ntoa(ip.dst)
            except OSError:
                if isinstance(ip, IP6):
                    raise ValidationError("CA does not support IP6")
                raise  # some other reason for the OSError....
            if isinstance(transport, TCP):
                if (ip.src, transport.sport) in banned:
                    continue
                data = bytearray(transport.data)
                while True:
                    data, command, _ = read_from_bytestream(data)
                    if command is NEED_DATA:
                        break
                    yield SimpleNamespace(timestamp=timestamp,
                                          ethernet=ethernet,
                                          src=src,
                                          dst=dst,
                                          ip=ip,
                                          transport=transport,
                                          command=command)
            elif isinstance(transport, UDP):
                if (ip.src, transport.sport) in banned:
                    continue
                address = inet_ntoa(ip.src)
                for command in read_datagram(transport.data, address):
                    yield SimpleNamespace(timestamp=timestamp,
                                          ethernet=ethernet,
                                          src=src,
                                          dst=dst,
                                          ip=ip,
                                          transport=transport,
                                          command=command)
        except ValidationError:
            banned.add((ip.src, transport.sport))
