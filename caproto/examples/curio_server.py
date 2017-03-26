import time
import getpass

import curio
from curio import socket

import caproto as ca
from caproto import _dbr as dbr
from caproto import ChType
from caproto import (EPICS_CA1_PORT, EPICS_CA2_PORT)


class DisconnectedCircuit(Exception):
    ...


def find_next_tcp_port(host='0.0.0.0', starting_port=EPICS_CA2_PORT + 1):
    import socket

    port = starting_port

    while port <= 65535:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind((host, port))
        except IOError as ex:
            print(ex, port)
            port += 1
        else:
            break

    return port


def convert_to(values, from_dtype, to_dtype):
    if from_dtype == to_dtype:
        return values

    # TODO metadata is expected to be of this type as well!
    native_to_dtype = dbr.native_type(to_dtype)

    if (from_dtype in dbr.native_float_types and native_to_dtype in
            dbr.native_int_types):
        # TODO performance
        values = [int(v) for v in values]
    elif native_to_dtype == ChType.STRING:
        values = [str(v) for v in values]

    return values


class DatabaseRecordBase:
    data_type = ca.DBR_LONG.DBR_ID

    def __init__(self, *, timestamp=None, status=0, severity=0, value=None):
        if timestamp is None:
            timestamp = time.time()
        self.timestamp = timestamp
        self.status = status
        self.severity = severity
        self.value = value

    def __len__(self):
        try:
            return len(self.value)
        except TypeError:
            return 1

    def check_access(self, sender_address):
        print('{} has full access to {}'.format(sender_address, self))
        return 3  # read-write


class DatabaseRecordEnum(DatabaseRecordBase):
    data_type = ca.DBR_ENUM.DBR_ID

    def __init__(self, *, strs=None, **kwargs):
        self.strs = strs

        super().__init__(**kwargs)

    @property
    def no_str(self):
        return len(self.strs) if self.strs else 0


class DatabaseRecordNumeric(DatabaseRecordBase):
    def __init__(self, *, units='', upper_disp_limit=0.0,
                 lower_disp_limit=0.0, upper_alarm_limit=0.0,
                 upper_warning_limit=0.0, lower_warning_limit=0.0,
                 lower_alarm_limit=0.0, upper_ctrl_limit=0.0,
                 lower_ctrl_limit=0.0, **kwargs):

        super().__init__(**kwargs)
        self.units = units
        self.upper_disp_limit = upper_disp_limit
        self.lower_disp_limit = lower_disp_limit
        self.upper_alarm_limit = upper_alarm_limit
        self.upper_warning_limit = upper_warning_limit
        self.lower_warning_limit = lower_warning_limit
        self.lower_alarm_limit = lower_alarm_limit
        self.upper_ctrl_limit = upper_ctrl_limit
        self.lower_ctrl_limit = lower_ctrl_limit


class DatabaseRecordInteger(DatabaseRecordNumeric):
    data_type = ca.DBR_LONG.DBR_ID


class DatabaseRecordDouble(DatabaseRecordNumeric):
    data_type = ca.DBR_DOUBLE.DBR_ID

    def __init__(self, *, precision=0, **kwargs):
        super().__init__(**kwargs)

        self.precision = precision


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
        bytes_to_send = self.circuit.send(*commands)
        await self.client.sendall(bytes_to_send)

    async def recv(self):
        """
        Receive bytes over TCP and cache them in this circuit's buffer.
        """
        bytes_received = await self.client.recv(4096)
        if not bytes_received:
            raise DisconnectedCircuit()
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

        for response_command in self._process_command(command):
            if isinstance(response_command, (list, tuple)):
                await self.send(*response_command)
            else:
                await self.send(response_command)

        return command

    def _process_command(self, command):
        def get_db_entry():
            chan = self.circuit.channels_sid[command.sid]
            db_entry = self.context.pvdb[chan.name.decode('latin-1')]
            return chan, db_entry

        if isinstance(command, ca.CreateChanRequest):
            db_entry = self.context.pvdb[command.name.decode('latin-1')]
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
            values = db_entry.value
            try:
                len(values)
            except TypeError:
                values = [values, ]

            yield chan.read(values=convert_to(values, db_entry.data_type,
                                              command.data_type),
                            data_type=command.data_type, ioid=command.ioid,
                            metadata=db_entry)
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
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            sock.bind((self.host, EPICS_CA1_PORT))
        except Exception:
            print('udp bind failure!')
            raise
        else:
            print('udp server bound', sock)
        responses = []
        while True:
            responses.clear()
            bytes_received, addr = await sock.recvfrom(1024)
            self.broadcaster.recv(bytes_received, addr)
            while True:
                command = self.broadcaster.next_command()
                if isinstance(command, ca.NEED_DATA):
                    # Respond, and then break to receive the next datagram.
                    bytes_to_send = self.broadcaster.send(*responses)
                    await sock.sendto(bytes_to_send, addr)
                    break
                if isinstance(command, ca.VersionRequest):
                    res = ca.VersionResponse(13)
                    responses.append(res)
                if isinstance(command, ca.SearchRequest):
                    known_pv = command.name.decode('latin-1') in self.pvdb
                    if (not known_pv) and command.reply == ca.NO_REPLY:
                        responses.clear()
                        break  # Do not send any repsonse to this datagram.

                    # we can get the IP but it's more reliable (AFAIK) to
                    # let the client get the ip from the packet
                    # ip = _get_my_ip()
                    res = ca.SearchResponse(self.port, None, command.cid, 13)
                    responses.append(res)

    async def tcp_handler(self, client, addr):
        circuit = VirtualCircuit(ca.VirtualCircuit(ca.SERVER, addr, None), client,
                                 self)
        circuit.circuit.log.setLevel('DEBUG')
        while True:
            try:
                await circuit.next_command()
            except DisconnectedCircuit:
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

    if not ipv4s:
        return '127.0.0.1'
    return ipv4s[0]


if __name__ == '__main__':
    pvdb = {'pi': DatabaseRecordDouble(value=3.14,
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
            'enum' : DatabaseRecordEnum(value='a',
                                        strs=['a', 'b', 'c', 'd'],
                                        ),
            'int' : DatabaseRecordInteger(value=0,
                                          units='doodles',
                                          ),
            }

    ctx = Context('0.0.0.0', find_next_tcp_port(), pvdb)
    curio.run(ctx.run())
