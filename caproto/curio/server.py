import logging
import random
from collections import namedtuple

import curio
from curio import socket

import caproto as ca
from caproto import (ChannelDouble, ChannelInteger, ChannelEnum,
                     get_address_list, get_beacon_address_list,
                     get_environment_variables)


class DisconnectedCircuit(Exception):
    ...


Subscription = namedtuple('Subscription', ('mask', 'circuit', 'data_type',
                                           'subscription_id'))


logger = logging.getLogger(__name__)

SERVER_ENCODING = 'latin-1'


def find_next_tcp_port(host='0.0.0.0', starting_port=ca.EPICS_CA2_PORT + 1):
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


class CurioVirtualCircuit:
    "Wraps a caproto.VirtualCircuit with a curio client."
    def __init__(self, circuit, client, context):
        self.connected = True
        self.circuit = circuit  # a caproto.VirtualCircuit
        self.client = client
        self.context = context
        self.client_hostname = None
        self.client_username = None
        self.command_queue = curio.Queue()
        self.new_command_condition = curio.Condition()
        self.pending_tasks = curio.TaskGroup()
        self.subscriptions = {}

    async def run(self):
        await self.pending_tasks.spawn(self.command_queue_loop())

    async def _on_disconnect(self):
        """Executed when disconnection detected"""
        if not self.connected:
            return

        self.connected = False
        for db_entry, subs in self.subscriptions.items():
            for sub in subs:
                self.context.subscriptions[db_entry].remove(sub)
            if not self.context.subscriptions[db_entry]:
                db_entry.subscribe(None)
                del self.context.subscriptions[db_entry]
        self.subscriptions.clear()

        # TODO this may cancel some caputs in progress, need to rethink it
        # await self.pending_tasks.cancel_remaining()

    async def send(self, *commands):
        """
        Process a command and tranport it over the TCP socket for this circuit.
        """
        if self.connected:
            buffers_to_send = self.circuit.send(*commands)
            await self.client.sendmsg(buffers_to_send)

    async def recv(self):
        """
        Receive bytes over TCP and cache them in this circuit's buffer.
        """
        bytes_received = await self.client.recv(4096)
        commands, _ = self.circuit.recv(bytes_received)
        for c in commands:
            await self.command_queue.put(c)
        if not bytes_received:
            await self._on_disconnect()
            raise DisconnectedCircuit()

    async def command_queue_loop(self):
        """
        Coroutine which feeds from the circuit command queue.

        1. Dispatch and validate through caproto.VirtualCircuit.process_command
            - Upon server failure, respond to the client with
              caproto.ErrorResponse
        2. Update Channel state if applicable.
        """
        while True:
            try:
                command = await self.command_queue.get()
                self.circuit.process_command(command)
            except curio.TaskCancelled:
                break
            except Exception as ex:
                logger.error('Circuit command queue evaluation failed',
                             exc_info=ex)
                continue

            try:
                response_command = await self._process_command(command)
                if response_command is not None:
                    await self.send(*response_command)
            except DisconnectedCircuit:
                await self._on_disconnect()
                self.circuit.disconnect()
                await self.context.circuit_disconnected(self)
                break
            except Exception as ex:
                if not self.connected:
                    if not isinstance(command, ca.ClearChannelRequest):
                        logger.error('Curio server error after client '
                                     'disconnection: %s', command)
                    break

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

    async def _process_command(self, command):
        '''Process a command from a client, and return the server response'''
        def get_db_entry():
            chan = self.circuit.channels_sid[command.sid]
            db_entry = self.context.pvdb[chan.name.decode(SERVER_ENCODING)]
            return chan, db_entry

        if command is ca.DISCONNECTED:
            raise DisconnectedCircuit()
        elif isinstance(command, ca.CreateChanRequest):
            db_entry = self.context.pvdb[command.name.decode(SERVER_ENCODING)]
            access = db_entry.check_access(self.client_hostname,
                                           self.client_username)

            return [ca.VersionResponse(13),
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
            return [chan.read(data=data, data_type=command.data_type,
                              data_count=len(data), status=1,
                              ioid=command.ioid, metadata=metadata)
                    ]
        elif isinstance(command, (ca.WriteRequest, ca.WriteNotifyRequest)):
            chan, db_entry = get_db_entry()
            client_waiting = isinstance(command, ca.WriteNotifyRequest)

            async def handle_write():
                '''Wait for an asynchronous caput to finish'''
                try:
                    write_status = await db_entry.set_dbr_data(
                        command.data, command.data_type, command.metadata)
                except Exception as ex:
                    cid = self.circuit.channels_sid[command.sid].cid
                    response_command = ca.ErrorResponse(
                        command, cid,
                        status_code=ca.ECA_INTERNAL.code_with_severity,
                        error_message=('Python exception: {} {}'
                                       ''.format(type(ex).__name__, ex))
                    )
                else:
                    if write_status is None:
                        # errors can be passed back by exceptions, and
                        # returning none for write_status can just be
                        # considered laziness
                        write_status = True
                    response_command = chan.write(ioid=command.ioid,
                                                  status=write_status)

                if client_waiting:
                    await self.send(response_command)

            await self.pending_tasks.spawn(handle_write, ignore_result=True)
            # TODO pretty sure using the taskgroup will bog things down,
            # but it suppresses an annoying warning message, so... there
        elif isinstance(command, ca.EventAddRequest):
            chan, db_entry = get_db_entry()
            # TODO no support for deprecated low/high/to
            sub = Subscription(mask=command.mask,
                               circuit=self,
                               data_type=command.data_type,
                               subscription_id=command.subscriptionid)
            if db_entry not in self.context.subscriptions:
                self.context.subscriptions[db_entry] = []
                db_entry.subscribe(self.context.subscription_queue, chan)
            self.context.subscriptions[db_entry].append(sub)
            if db_entry not in self.subscriptions:
                self.subscriptions[db_entry] = []
            self.subscriptions[db_entry].append(sub)

            # send back a first monitor always
            metadata, data = db_entry.get_dbr_data(command.data_type)
            return [chan.subscribe(data=data, data_type=command.data_type,
                                   data_count=len(data),
                                   subscriptionid=command.subscriptionid,
                                   metadata=metadata, status_code=1)
                    ]
        elif isinstance(command, ca.EventCancelRequest):
            chan, db_entry = get_db_entry()
            sub = [sub for sub in self.subscriptions[db_entry]
                   if sub.subscription_id == command.subscriptionid]
            if sub:
                sub = sub[0]
                unsub_response = chan.unsubscribe(command.subscriptionid)
                self.context.subscriptions[db_entry].remove(sub)
                if not self.context.subscriptions[db_entry]:
                    db_entry.subscribe(None)
                    del self.context.subscriptions[db_entry]
                self.subscriptions[db_entry].remove(sub)
                return [unsub_response]
        elif isinstance(command, ca.ClearChannelRequest):
            chan, db_entry = get_db_entry()
            return [chan.disconnect()]
        elif isinstance(command, ca.EchoRequest):
            return [ca.EchoResponse()]


class Context:
    def __init__(self, host, port, pvdb, *, log_level='ERROR'):
        self.host = host
        self.port = port
        self.pvdb = pvdb

        self.circuits = set()
        self.log_level = log_level
        self.broadcaster = ca.Broadcaster(our_role=ca.SERVER)
        self.broadcaster.log.setLevel(self.log_level)
        self.command_bundle_queue = curio.Queue()

        self.subscriptions = {}
        self.subscription_queue = curio.UniversalQueue()
        self.beacon_count = 0
        self.environ = get_environment_variables()

        ignore_addresses = self.environ['EPICS_CAS_IGNORE_ADDR_LIST']
        self.ignore_addresses = ignore_addresses.split(' ')

    async def broadcaster_udp_server_loop(self):
        self.udp_sock = ca.bcast_socket(socket)
        try:
            self.udp_sock.bind((self.host, ca.EPICS_CA1_PORT))
        except Exception:
            print('[server] udp bind failure!')
            raise

        while True:
            bytes_received, address = await self.udp_sock.recvfrom(4096)
            if bytes_received:
                commands = self.broadcaster.recv(bytes_received, address)
                await self.command_bundle_queue.put((address, commands))

    async def broadcaster_queue_loop(self):
        responses = []

        while True:
            try:
                addr, commands = await self.command_bundle_queue.get()
                self.broadcaster.process_commands(commands)
            except curio.TaskCancelled:
                break
            except Exception as ex:
                logger.error('Broadcaster command queue evaluation failed',
                             exc_info=ex)
                continue

            if addr in self.ignore_addresses:
                continue

            responses.clear()
            for command in commands:
                if isinstance(command, ca.VersionRequest):
                    responses.append(ca.VersionResponse(13))
                if isinstance(command, ca.SearchRequest):
                    pv_name = command.name.decode(SERVER_ENCODING)
                    known_pv = pv_name in self.pvdb
                    if (not known_pv) and command.reply == ca.NO_REPLY:
                        responses.clear()
                        break  # Do not send any repsonse to this datagram.

                    # responding with an IP of `None` tells client to get IP
                    # address from packet
                    responses.append(ca.SearchResponse(self.port, None,
                                                       command.cid, 13))
            if responses:
                bytes_to_send = self.broadcaster.send(*responses)
                await self.udp_sock.sendto(bytes_to_send, addr)

    async def tcp_handler(self, client, addr):
        '''Handler for each new TCP client to the server'''
        cavc = ca.VirtualCircuit(ca.SERVER, addr, None)
        circuit = CurioVirtualCircuit(cavc, client, self)
        self.circuits.add(circuit)

        circuit.circuit.log.setLevel(self.log_level)

        await circuit.run()

        while True:
            try:
                await circuit.recv()
            except DisconnectedCircuit:
                break

    async def circuit_disconnected(self, circuit):
        '''Notification from circuit that its connection has closed'''
        self.circuits.remove(circuit)

    async def subscription_queue_loop(self):
        while True:
            db_entry, mask, data, chan = await self.subscription_queue.get()
            try:
                subs = self.subscriptions[db_entry]
            except KeyError:
                continue

            matching_subs = [(sub.circuit, sub.data_type, sub.subscription_id)
                             for sub in subs
                             if sub.mask & mask]
            print('{} matching subs'.format(len(matching_subs)))
            if matching_subs:
                commands = {db_entry.data_type:
                            chan.subscribe(data=data, subscriptionid=0,
                                           status_code=1)}
                for circuit, data_type, sub_id in matching_subs:
                    try:
                        cmd = commands[data_type]
                    except KeyError:
                        metadata, data = db_entry.get_dbr_data(data_type)
                        cmd = chan.subscribe(data=data, data_type=data_type,
                                             data_count=len(data),
                                             subscriptionid=0,
                                             metadata=metadata,
                                             status_code=1)
                        commands[data_type] = cmd

                    cmd.header.parameter2 = sub_id  # TODO setter?
                    await circuit.send(cmd)

    async def broadcast_beacon_loop(self):
        beacon_period = self.environ['EPICS_CAS_BEACON_PERIOD']
        addresses = get_beacon_address_list()

        while True:
            beacon = ca.RsrvIsUpResponse(13, self.port, self.beacon_count,
                                         self.host)
            bytes_to_send = self.broadcaster.send(beacon)
            for addr_port in addresses:
                await self.udp_sock.sendto(bytes_to_send, addr_port)
            self.beacon_count += 1
            await curio.sleep(beacon_period)

    async def run(self):
        try:
            async with curio.TaskGroup() as g:
                await g.spawn(curio.tcp_server,
                              '', self.port, self.tcp_handler)
                await g.spawn(self.broadcaster_udp_server_loop)
                await g.spawn(self.broadcaster_queue_loop)
                await g.spawn(self.subscription_queue_loop)
                await g.spawn(self.broadcast_beacon_loop)
        except curio.TaskGroupError as ex:
            logger.error('Curio server failed: %s', ex.errors)
            for task in ex:
                logger.error('Task %s failed: %s', task, task.exception)
        except curio.TaskCancelled:
            logger.info('Server task cancelled')
            await g.cancel_remaining()
            for circuit in list(self.circuits):
                logger.debug('Cancelling tasks from circuit %s', circuit)
                await circuit.pending_tasks.cancel_remaining()


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
                                    enum_strings=['a', 'b', 'c', 'd'],
                                    ),
                'enum2': ChannelEnum(value='bb',
                                     enum_strings=['aa', 'bb', 'cc', 'dd'],
                                     ),
                'int': ChannelInteger(value=96,
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
                'chararray': ca.ChannelChar(value=b'1234567890' * 2),
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
