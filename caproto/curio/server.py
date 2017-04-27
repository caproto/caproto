import sys
import traceback
import random

import curio
from curio import socket

import caproto as ca
from caproto import (ChannelDouble, ChannelInteger,
                     ChannelEnum)
from caproto import (EPICS_CA1_PORT, EPICS_CA2_PORT)


class DisconnectedCircuit(Exception):
    ...


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


class VirtualCircuit:
    "Wraps a caproto.VirtualCircuit with a curio client."
    def __init__(self, circuit, client, context):
        self.circuit = circuit  # a caproto.VirtualCircuit
        self.client = client
        self.context = context

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
            raise ca.DisconnectedCircuit()
        self.circuit.recv(bytes_received)

    async def next_command(self):
        """
        Process one incoming command.

        1. Receive data from the socket if a full comannd's worth of bytes are
           not already cached.
        2. Dispatch to caproto.VirtualCircuit.next_command which validates.
        3. Update Channel state if applicable.
        """
        while True:
            command = self.circuit.next_command()
            if isinstance(command, ca.NEED_DATA):
                await self.recv()
                continue
            break

        try:
            for response_command in self._process_command(command):
                if isinstance(response_command, (list, tuple)):
                    await self.send(*response_command)
                else:
                    await self.send(response_command)
        except Exception as ex:
            print('Curio server failed to process command: {}'.format(command))
            traceback.print_exc(file=sys.stdout)

            if hasattr(command, 'sid'):
                cid = self.circuit.channels_sid[command.sid].cid

                response_command = ca.ErrorResponse(
                    command, cid,
                    status_code=ca.ECA_INTERNAL.code_with_severity,
                    error_message=('Python exception: {} {}'
                                   ''.format(type(ex).__name__, ex))
                )
                await self.send(response_command)

        return command

    def _process_command(self, command):
        def get_db_entry():
            chan = self.circuit.channels_sid[command.sid]
            db_entry = self.context.pvdb[chan.name.decode(SERVER_ENCODING)]
            return chan, db_entry

        if isinstance(command, ca.CreateChanRequest):
            db_entry = self.context.pvdb[command.name.decode(SERVER_ENCODING)]
            access = db_entry.check_access(command.sender_address)

            yield [ca.VersionResponse(13),
                   ca.AccessRightsResponse(cid=command.cid,
                                           access_rights=access),
                   ca.CreateChanResponse(data_type=db_entry.data_type,
                                         data_count=len(db_entry),
                                         cid=command.cid,
                                         sid=self.circuit.new_channel_id()),
                   ]
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
            yield chan.clear()


class Context:
    def __init__(self, host, port, pvdb):
        self.host = host
        self.port = port
        self.pvdb = pvdb
        self.broadcaster = ca.Broadcaster(our_role=ca.SERVER)
        self.broadcaster.log.setLevel('DEBUG')

    async def udp_server(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # for BSD/Darwin
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError:
            pass
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            sock.bind((self.host, EPICS_CA1_PORT))
        except Exception:
            print('[server] udp bind failure!')
            raise
        else:
            print('[server] udp bound', sock)
        responses = []
        while True:
            responses.clear()
            print('[server] await recv')
            try:
                bytes_received, addr = await sock.recvfrom(1024)
            except Exception as ex:
                print('[server] await recv fail', ex)
                raise
            else:
                print('[server] await recv ok, addr', addr)
            self.broadcaster.recv(bytes_received, addr)
            while True:
                command = self.broadcaster.next_command()
                print('(server)', command)
                if isinstance(command, ca.NEED_DATA):
                    # Respond, and then break to receive the next datagram.
                    bytes_to_send = self.broadcaster.send(*responses)
                    await sock.sendto(bytes_to_send, addr)
                    break
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

    async def tcp_handler(self, client, addr):
        circuit = VirtualCircuit(ca.VirtualCircuit(ca.SERVER, addr, None),
                                 client,
                                 self)
        circuit.circuit.log.setLevel('DEBUG')
        while True:
            try:
                await circuit.next_command()
            except ca.DisconnectedCircuit:
                print('disconnected')
                return

    async def run(self):
        try:
            tcp_server = curio.tcp_server('', self.port, self.tcp_handler)
            tcp_task = await curio.spawn(tcp_server)
            udp_task = await curio.spawn(self.udp_server())
            await udp_task.join()
            await tcp_task.join()
        except curio.TaskCancelled:
            await tcp_task.cancel()
            await udp_task.cancel()


def _get_my_ip():
    try:
        import netifaces
    except ImportError:
        return '127.0.0.1'

    interfaces = [netifaces.ifaddresses(interface)
                  for interface in netifaces.interfaces()
                  ]
    ipv4s = [af_inet_info['addr']
             for interface in interfaces
             if netifaces.AF_INET in interface
             for af_inet_info in interface[netifaces.AF_INET]
             ]

    print([af_inet_info
           for interface in interfaces
           if netifaces.AF_INET in interface
           for af_inet_info in interface[netifaces.AF_INET]
           ])
    if not ipv4s:
        return '127.0.0.1'
    return ipv4s[0]


if __name__ == '__main__':
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
            }

    pvdb['pi'].alarm.alarm_string = 'delicious'
    ctx = Context('0.0.0.0', find_next_tcp_port(), pvdb)
    curio.run(ctx.run())
