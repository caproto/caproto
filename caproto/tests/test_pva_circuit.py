import logging

import pytest

pytest.importorskip('dataclasses')
pytest.importorskip('caproto.pva')

import dataclasses  # isort: noqa

from caproto import pva
from caproto.pva import BitSet

logger = logging.getLogger(__name__)


@pytest.fixture
def verbose_logging(caplog):
    caplog.set_level('DEBUG', logger='caproto.pva')
    yield
    caplog.set_level('INFO', logger='caproto.pva')


@pytest.fixture
def server_address():
    return ('127.0.0.1', 456)


@pytest.fixture
def client_address():
    return ('127.0.0.1', 123)


@pytest.fixture
def client(client_address) -> pva.ClientVirtualCircuit:
    return pva._circuit.ClientVirtualCircuit(
        our_role=pva.Role.CLIENT, address=client_address,
        priority=pva.QOSFlags.encode(priority=0, flags=0)
    )


@pytest.fixture
def server(server_address) -> pva.ServerVirtualCircuit:
    return pva._circuit.ServerVirtualCircuit(
        our_role=pva.Role.SERVER, address=server_address,
        priority=pva.QOSFlags.encode(priority=0, flags=0)
    )


def send(from_: pva.VirtualCircuit,
         to: pva.VirtualCircuit,
         *commands
         ) -> None:
    bytes_received = b''.join(from_.send(*commands))
    received = []
    for message, remaining in to.recv(bytes_received):
        if message is pva.NEED_DATA:
            break
        to.process_command(message)
        received.append(message)

    return received


def connect(client: pva.ClientVirtualCircuit, server: pva.ServerVirtualCircuit):
    send(server, client,
         server.set_byte_order(pva.EndianSetting.use_server_byte_order)
         )

    send(server, client,
         server.validate_connection(
             buffer_size=50, registry_size=50,
             authorization_options=['ca', 'anonymous'])
         )

    send(client, server,
         client.validate_connection(
             buffer_size=50, registry_size=50,
             connection_qos=int(client.priority),
             auth_nz='ca',
             data=pva.ChannelAccessAuthentication(user='test', host='server'),)
         )

    send(server, client,
         server.validated_connection())


def test_connect(verbose_logging,
                 client: pva.ClientVirtualCircuit,
                 server: pva.ServerVirtualCircuit,
                 ):
    connect(client, server)


def test_channel_get(client: pva.ClientVirtualCircuit,
                     server: pva.ServerVirtualCircuit,
                     ):
    connect(client, server)

    client_chan = client.create_channel('pvname')
    send(client, server, client_chan.create())

    server_chan = server.create_channel('pvname')
    send(server, client, server_chan.create(sid=1))

    @pva.pva_dataclass
    class Data:
        a: int
        b: str

    server_value = Data(a=4, b='string')

    interface_req = client_chan.read_interface()
    send(client, server, interface_req)
    # TODO: uses cache, top-level interface .name gets set to None
    # and then hashes no longer match
    # send(server, client,
    #      server_chan.read_interface(ioid=interface_req.ioid,
    #                                 interface=server_value))

    request = client_chan.read()
    response = server_chan.read(ioid=request.ioid,
                                interface=server_value)
    send(client, server, request)
    send(server, client, response)

    data_bs = pva.DataWithBitSet(data=server_value, bitset=BitSet({0}))

    send(client, server, request.to_get())
    roundtrip = send(server, client, response.to_get(pv_data=data_bs))

    assert hash(roundtrip[0].pv_data.interface) == hash(Data._pva_struct_)
    assert roundtrip[0].pv_data.data == {'a': 4, 'b': 'string'}


def test_channel_put(client: pva.ClientVirtualCircuit,
                     server: pva.ServerVirtualCircuit,
                     ):
    connect(client, server)

    client_chan: pva.ClientChannel = client.create_channel('pvname')
    send(client, server, client_chan.create())

    server_chan: pva.ServerChannel = server.create_channel('pvname')
    send(server, client, server_chan.create(sid=1))

    @pva.pva_dataclass
    class Data:
        a: int
        b: str

    server_value = Data(a=4, b='string')
    client_value = Data(a=5, b='string')
    server_data_bs = pva.DataWithBitSet(data=server_value, bitset=BitSet({0}))
    client_data_bs = pva.DataWithBitSet(data=client_value, bitset=BitSet({0}))

    request = client_chan.write(pvrequest='field()')
    response = server_chan.write(ioid=request.ioid,
                                 put_structure_if=server_value)
    send(client, server, request)
    send(server, client, response)

    send(client, server, request.to_get())
    roundtrip = send(server, client, response.to_get(data=server_data_bs))

    assert hash(roundtrip[0].put_data.interface) == hash(Data._pva_struct_)
    assert roundtrip[0].put_data.data == {'a': 4, 'b': 'string'}

    roundtrip = send(client, server, request.to_default(put_data=client_data_bs))
    send(server, client, response.to_default())

    assert hash(roundtrip[0].put_data.interface) == hash(Data._pva_struct_)
    assert roundtrip[0].put_data.data == {'a': 5, 'b': 'string'}


def test_channel_monitor(client: pva.ClientVirtualCircuit,
                         server: pva.ServerVirtualCircuit,
                         ):
    connect(client, server)

    client_chan: pva.ClientChannel = client.create_channel('pvname')
    send(client, server, client_chan.create())

    server_chan: pva.ServerChannel = server.create_channel('pvname')
    send(server, client, server_chan.create(sid=1))

    @pva.pva_dataclass
    class Data:
        a: int
        b: str

    server_value = Data(a=4, b='string')
    server_data_bs = pva.DataWithBitSet(data=server_value, bitset=BitSet({0}))

    request = client_chan.subscribe(pvrequest='field(a,b)')
    response = server_chan.subscribe(ioid=request.ioid,
                                     interface=server_value)
    send(client, server, request)
    send(server, client, response)

    send(client, server, request.to_start())
    roundtrip = send(server, client, response.to_default(pv_data=server_data_bs,
                                                         overrun_bitset=BitSet({})))

    assert hash(roundtrip[0].pv_data.interface) == hash(Data._pva_struct_)
    assert roundtrip[0].pv_data.data == {'a': 4, 'b': 'string'}

    server_value.a = 5
    server_value.b = 'string test'

    roundtrip = send(server, client, response.to_default(pv_data=server_data_bs,
                                                         overrun_bitset=BitSet({})))

    assert hash(roundtrip[0].pv_data.interface) == hash(Data._pva_struct_)
    assert roundtrip[0].pv_data.data == {'a': 5, 'b': 'string test'}

    send(client, server, request.to_stop())


def test_channel_rpc(client: pva.ClientVirtualCircuit,
                     server: pva.ServerVirtualCircuit,
                     ):
    connect(client, server)

    client_chan: pva.ClientChannel = client.create_channel('pvname')
    send(client, server, client_chan.create())

    server_chan: pva.ServerChannel = server.create_channel('pvname')
    send(server, client, server_chan.create(sid=1))

    @pva.pva_dataclass
    class Data:
        a: int
        b: str

    client_value = Data(a=3, b='two')
    server_value = Data(a=4, b='string')
    client_data = pva.FieldDescAndData(data=client_value)
    server_data = pva.FieldDescAndData(data=server_value)

    request = client_chan.rpc(pvrequest='field(a,b)')
    response = server_chan.rpc(ioid=request.ioid)
    send(client, server, request)
    send(server, client, response)

    send(client, server, request.to_default(pv_data=client_data))
    roundtrip = send(server, client,
                     response.to_default(pv_response=server_data,
                                         status=pva.Status.create_success(),
                                         )
                     )

    assert hash(roundtrip[0].pv_response.interface) == hash(Data._pva_struct_)
    assert dataclasses.asdict(roundtrip[0].pv_response.data) == {'a': 4, 'b': 'string'}
