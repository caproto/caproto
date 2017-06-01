import logging
import random
from collections import namedtuple
from concurrent.futures import Future

import curio
from curio import socket

import caproto as ca
from caproto import (ChannelDouble, ChannelInteger, ChannelEnum)


class DisconnectedCircuit(Exception):
    ...


Subscription = namedtuple('Subscription', ('mask', 'circuit', 'data_type',
                                           'subscription_id'))


class FutureResult(Exception):
    def __init__(self, future, callable):
        self.future = future
        self.callable = callable


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


class VirtualCircuit:
    "Wraps a caproto.VirtualCircuit with a curio client."
    def __init__(self, circuit, client, context):
        self.connected = True
        self.circuit = circuit  # a caproto.VirtualCircuit
        self.client = client
        self.context = context
        self.client_hostname = None
        self.client_username = None
        self.new_command_condition = curio.Condition()
        # self.pending_writes = {}
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
        self.circuit.recv(bytes_received)
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
                command = await self.circuit.async_next_command()
            except curio.TaskCancelled:
                break
            except Exception as ex:
                logger.error('Circuit command queue evaluation failed',
                             exc_info=ex)
                continue

            try:
                for response_command in self._process_command(command):
                    if isinstance(response_command, (list, tuple)):
                        await self.send(*response_command)
                    else:
                        await self.send(response_command)
            except FutureResult as fut_res:
                # pretty sure this is a bad way of doing things
                # future = fut_res.future
                await self.pending_tasks.spawn(fut_res.callable,
                                               ignore_result=True)
                # TODO pretty sure using the taskgroup will bog things down,
                # but it suppresses an annoying warning message, so... there
            except DisconnectedCircuit:
                await self._on_disconnect()
                self.circuit.disconnect()
                await self.context.circuit_disconnected(self)
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

    def _process_command(self, command):
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
        elif isinstance(command, (ca.WriteRequest, ca.WriteNotifyRequest)):
            chan, db_entry = get_db_entry()
            client_waiting = isinstance(command, ca.WriteNotifyRequest)
            future = Future()

            async def handle_write():
                if curio.meta.iscoroutinefunction(db_entry.set_dbr_data):
                    await db_entry.set_dbr_data(command.data,
                                                command.data_type,
                                                command.metadata, future)
                else:
                    await curio.abide(db_entry.set_dbr_data, command.data,
                                      command.data_type, command.metadata,
                                      future)
                await self._wait_write_completion(chan, command, future,
                                                  client_waiting)

            raise FutureResult(future, handle_write)
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
        elif isinstance(command, ca.EventCancelRequest):
            chan, db_entry = get_db_entry()
            sub = [sub for sub in self.subscriptions[db_entry]
                   if sub.subscription_id == command.subscriptionid]
            if sub:
                sub = sub[0]
                yield chan.unsubscribe(command.subscriptionid)
                self.context.subscriptions[db_entry].remove(sub)
                if not self.context.subscriptions[db_entry]:
                    db_entry.subscribe(None)
                    del self.context.subscriptions[db_entry]
                self.subscriptions[db_entry].remove(sub)
        elif isinstance(command, ca.ClearChannelRequest):
            chan, db_entry = get_db_entry()
            yield chan.disconnect()

    async def _wait_write_completion(self, chan, command, future,
                                     client_waiting):
        # key = (chan, command.ioid)
        # self.pending_writes[key] = future
        try:
            await curio.traps._future_wait(future)
            try:
                write_status = future.result()
            except Exception as ex:
                cid = self.circuit.channels_sid[command.sid].cid
                response_command = ca.ErrorResponse(
                    command, cid,
                    status_code=ca.ECA_INTERNAL.code_with_severity,
                    error_message=('Python exception: {} {}'
                                   ''.format(type(ex).__name__, ex))
                )
            else:
                response_command = chan.write(ioid=command.ioid,
                                              status=write_status)

            if client_waiting:
                await self.send(response_command)
        finally:
            # del self.pending_writes[key]
            pass


class Context:
    def __init__(self, host, port, pvdb, *, log_level='ERROR'):
        self.host = host
        self.port = port
        self.pvdb = pvdb

        self.circuits = set()
        self.log_level = log_level
        self.broadcaster = ca.Broadcaster(our_role=ca.SERVER,
                                          queue_class=curio.UniversalQueue)
        self.broadcaster.log.setLevel(self.log_level)
        self.broadcaster_command_condition = curio.Condition()

        self.subscriptions = {}
        self.subscription_queue = curio.UniversalQueue()

    async def broadcaster_udp_server_loop(self):
        self.udp_sock = ca.bcast_socket(socket)
        try:
            self.udp_sock.bind((self.host, ca.EPICS_CA1_PORT))
        except Exception:
            print('[server] udp bind failure!')
            raise

        while True:
            bytes_received, address = await self.udp_sock.recvfrom(4096)
            self.broadcaster.recv(bytes_received, address)

    async def broadcaster_queue_loop(self):
        responses = []

        while True:
            try:
                addr, commands = await self.broadcaster.async_next_command()
            except curio.TaskCancelled:
                break
            except Exception as ex:
                logger.error('Broadcaster command queue evaluation failed',
                             exc_info=ex)
                continue

            responses.clear()
            for command in commands:
                if isinstance(command, ca.VersionRequest):
                    responses.append(ca.VersionResponse(13))
                if isinstance(command, ca.SearchRequest):
                    known_pv = command.name.decode(SERVER_ENCODING) in self.pvdb
                    if (not known_pv) and command.reply == ca.NO_REPLY:
                        responses.clear()
                        break  # Do not send any repsonse to this datagram.

                    # we can get the IP but it's more reliable (AFAIK) to
                    # let the client get the ip from the packet
                    # ip = _get_my_ip()
                    responses.append(ca.SearchResponse(self.port, None,
                                                       command.cid, 13))

                if responses:
                    bytes_to_send = self.broadcaster.send(*responses)
                    await self.udp_sock.sendto(bytes_to_send, addr)

                async with self.broadcaster_command_condition:
                    await self.broadcaster_command_condition.notify_all()

    async def tcp_handler(self, client, addr):
        cavc = ca.VirtualCircuit(ca.SERVER, addr, None,
                                 queue_class=curio.UniversalQueue)
        circuit = VirtualCircuit(cavc, client, self)
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

    async def run(self):
        try:
            async with curio.TaskGroup() as g:
                await g.spawn(curio.tcp_server('', self.port,
                                               self.tcp_handler))
                await g.spawn(self.broadcaster_udp_server_loop())
                await g.spawn(self.broadcaster_queue_loop())
                await g.spawn(self.subscription_queue_loop())
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
