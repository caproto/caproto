import sys
import logging
import random

import curio
from curio import socket

import caproto as ca
from caproto import (ChannelDouble, ChannelInteger,
                     ChannelEnum)
from caproto import (EPICS_CA1_PORT, EPICS_CA2_PORT)


class DisconnectedCircuit(Exception):
    ...


logger = logging.getLogger(__name__)

SERVER_ENCODING = 'latin-1'


def find_next_tcp_port(host='0.0.0.0', starting_port=EPICS_CA2_PORT + 1):
    import socket

    port = starting_port
    attempts = 0

    while attempts < 100:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind((host, port))
        except IOError as ex:
            print(ex, port)
            port = random.randint(49152, 65535)
            attempts += 1
        else:
            break

    return port


class DisconnectedCircuit(Exception):
    ...


class VirtualCircuit:
    "Wraps a caproto.VirtualCircuit with a curio client."
    def __init__(self, circuit, client, context):
        self.circuit = circuit  # a caproto.VirtualCircuit
        self.client = client
        self.context = context
        self.client_hostname = None
        self.client_username = None
        self.new_command_condition = curio.Condition()

    async def send(self, *commands):
        """
        Process a command and tranport it over the TCP socket for this circuit.
        """
        buffers_to_send = self.circuit.send(*commands)
        await self.client.sendmsg(buffers_to_send)

    async def recv(self):
        """
        Receive bytes over TCP and cache them in this circuit's buffer.
        """
        bytes_received = await self.client.recv(4096)
        if not bytes_received:
            raise DisconnectedCircuit()
        self.circuit.recv(bytes_received)

    async def command_queue_loop(self):
        """
        Coroutine which feeds from the circuit command queue.

        1. Dispatch and validate through caproto.VirtualCircuit.process_command
            - Upon server failure, respond to the client with
              caproto.ErrorResponse
        2. Update Channel state if applicable.
        """
        while True:
            command = await self.circuit.command_queue.get()

            try:
                for response_command in self._process_command(command):
                    if isinstance(response_command, (list, tuple)):
                        await self.send(*response_command)
                    else:
                        await self.send(response_command)
            except Exception as ex:
                logger.error('Curio server failed to process command: %s',
                             command, exc_info=ex)

                if hasattr(command, 'sid'):
                    cid = self.circuit.channels_sid[command.sid].cid

                    response_command = ca.ErrorResponse(
                        command, cid,
                        status_code=ca.ECA_INTERNAL.code_with_severity,
                        error_message=('Python exception: {} {}'
                                       ''.format(type(ex).__name__, ex))
                    )
                    await self.send(response_command)

            async with self.new_command_condition:
                await self.new_command_condition.notify_all()

    def _process_command(self, command):
        self.circuit.process_command(self.circuit.their_role, command)

        def get_db_entry():
            chan = self.circuit.channels_sid[command.sid]
            db_entry = self.context.pvdb[chan.name.decode(SERVER_ENCODING)]
            return chan, db_entry

        if isinstance(command, ca.CreateChanRequest):
            db_entry = self.context.pvdb[command.name.decode(SERVER_ENCODING)]
            access = db_entry.check_access(self.client_hostname,
                                           self.client_username)

            yield [ca.VersionResponse(13),
                   ca.AccessRightsResponse(cid=command.cid,
                                           access_rights=access),
                   ca.CreateChanResponse(data_type=db_entry.data_type,
                                         data_count=len(db_entry),
                                         cid=command.cid,
                                         sid=self.circuit.new_channel_id()),
                   ]
        elif isinstance(command, ca.HostNameRequest):
            self.client_hostname = command.name.decode(SERVER_ENCODING)
        elif isinstance(command, ca.ClientNameRequest):
            self.client_username = command.name.decode(SERVER_ENCODING)
        elif isinstance(command, ca.ReadNotifyRequest):
            chan, db_entry = get_db_entry()
            metadata, data = db_entry.get_dbr_data(command.data_type)
            yield chan.read(data=data, data_type=command.data_type,
                            data_count=len(data), status=1,
                            ioid=command.ioid, metadata=metadata)
        elif isinstance(command, ca.WriteNotifyRequest):
            chan, db_entry = get_db_entry()
            yield chan.write(ioid=command.ioid)
        elif isinstance(command, ca.EventAddRequest):
            chan, db_entry = get_db_entry()
            yield chan.subscribe((3.14,), command.subscriptionid)
        elif isinstance(command, ca.EventCancelRequest):
            chan, db_entry = get_db_entry()
            yield chan.unsubscribe(command.subscriptionid)
        elif isinstance(command, ca.ClearChannelRequest):
            chan, db_entry = get_db_entry()
            yield chan.disconnect()


class Context:
    def __init__(self, host, port, pvdb, *, log_level='ERROR'):
        self.host = host
        self.port = port
        self.pvdb = pvdb
        self.log_level = log_level
        self.broadcaster = ca.Broadcaster(our_role=ca.SERVER,
                                          queue_class=curio.UniversalQueue)
        self.broadcaster.log.setLevel(self.log_level)
        self.broadcaster_command_condition = curio.Condition()

    async def broadcaster_udp_server_loop(self):
        self.udp_sock = ca.bcast_socket(socket)
        try:
            self.udp_sock.bind((self.host, EPICS_CA1_PORT))
        except Exception:
            print('[server] udp bind failure!')
            raise

        while True:
            bytes_received, address = await self.udp_sock.recvfrom(4096)
            self.broadcaster.recv(bytes_received, address)

    async def broadcaster_queue_loop(self):
        queue = self.broadcaster.command_queue
        role = self.broadcaster.their_role
        responses = []

        while True:
            addr, commands = await queue.get()
            print('got', addr, commands)
            responses.clear()
            for command in commands:
                try:
                    self.broadcaster.process_command(role, command)
                except Exception as ex:
                    logger.error('Broadcaster command queue evaluation '
                                 'failed: {!r}'.format(command), exc_info=ex)
                    continue

                if isinstance(command, ca.VersionRequest):
                    res = ca.VersionResponse(13)
                    responses.append(res)
                if isinstance(command, ca.SearchRequest):
                    known_pv = command.name.decode(SERVER_ENCODING) in self.pvdb
                    if (not known_pv) and command.reply == ca.NO_REPLY:
                        responses.clear()
                        break  # Do not send any repsonse to this datagram.

                    # we can get the IP but it's more reliable (AFAIK) to
                    # let the client get the ip from the packet
                    # ip = _get_my_ip()
                    res = ca.SearchResponse(self.port, None, command.cid, 13)
                    responses.append(res)

                if responses:
                    bytes_to_send = self.broadcaster.send(*responses)
                    await self.udp_sock.sendto(bytes_to_send, addr)

                async with self.broadcaster_command_condition:
                    await self.broadcaster_command_condition.notify_all()

    async def tcp_handler(self, client, addr):
        cavc = ca.VirtualCircuit(ca.SERVER, addr, None,
                                 queue_class=curio.UniversalQueue)
        circuit = VirtualCircuit(cavc, client, self)
        circuit.circuit.log.setLevel(self.log_level)

        tcp_queue_loop = await curio.spawn(circuit.command_queue_loop())
        while True:
            try:
                await circuit.recv()
            except DisconnectedCircuit:
                await tcp_queue_loop.cancel()
                circuit.circuit.disconnect()
                return

    async def run(self):
        try:
            async with curio.TaskGroup() as g:
                await g.spawn(curio.tcp_server('', self.port, self.tcp_handler))
                await g.spawn(self.broadcaster_udp_server_loop())
                await g.spawn(self.broadcaster_queue_loop())
        except curio.TaskGroupError as ex:
            logger.error('Curio server failed: %s', ex.errors)
            for task in ex:
                logger.error('Task %s failed: %s', task, task.exception)


async def _test(pvdb=None):
    logger.setLevel('DEBUG')
    if pvdb is None:
        pvdb = {'pi': ChannelDouble(value=3.14,
                                    lower_disp_limit=3.13,
                                    upper_disp_limit=3.15,
                                    lower_alarm_limit=3.12,
                                    upper_alarm_limit=3.16,
                                    lower_warning_limit=3.11,
                                    upper_warning_limit=3.17,
                                    lower_ctrl_limit=3.10,
                                    upper_ctrl_limit=3.18,
                                    precision=5,
                                    units='doodles',
                                    ),
                'enum': ChannelEnum(value='b',
                                    strs=['a', 'b', 'c', 'd'],
                                    ),
                'int': ChannelInteger(value=0,
                                      units='doodles',
                                      ),
                'char': ca.ChannelChar(value=b'3',
                                       units='poodles',
                                       lower_disp_limit=33,
                                       upper_disp_limit=35,
                                       lower_alarm_limit=32,
                                       upper_alarm_limit=36,
                                       lower_warning_limit=31,
                                       upper_warning_limit=37,
                                       lower_ctrl_limit=30,
                                       upper_ctrl_limit=38,
                                       ),
                'str': ca.ChannelString(value='hello',
                                        string_encoding='latin-1'),
                'stra': ca.ChannelString(value=['hello', 'how is it', 'going'],
                                         string_encoding='latin-1'),
                }
        pvdb['pi'].alarm.alarm_string = 'delicious'

    ctx = Context('0.0.0.0', find_next_tcp_port(), pvdb)
    logger.info('Server starting up on %s:%d', ctx.host, ctx.port)
    return await ctx.run()


if __name__ == '__main__':
    logging.basicConfig()
    curio.run(_test())
