import time
import getpass

import curio
from curio import socket

import caproto as ca
from caproto import _dbr as dbr
from caproto import ChType


SERVER_PORT = 5064


class DisconnectedCircuit(Exception):
    ...


def convert_to(values, from_dtype, to_dtype):
    if from_dtype == to_dtype:
        return values

    if (from_dtype in dbr.native_float_types and to_dtype in
            dbr.native_int_types):
        # TODO performance
        values = [int(v) for v in values]
    elif to_dtype in (ChType.STRING, ChType.STS_STRING, ChType.TIME_STRING,
                      ChType.CTRL_STRING):
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
    data_type = ca.DBR_LONG.DBR_ID

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
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind((self.host, self.port))
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
                    ip = _get_my_ip()
                    res = ca.SearchResponse(self.port, ip, command.cid, 13)
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
    # Reliably getting the IP is a surprisingly tricky problem solved by this
    # crazy one-liner from http://stackoverflow.com/a/1267524/1221924
    # This uses the synchronous socket API, not the curio one, which we should
    # eventually fix.
    import socket
    try:
        return [l for l in ([ip for ip in socket.gethostbyname_ex(socket.gethostname())[2] if not ip.startswith("127.")][:1], [[(s.connect(('8.8.8.8', 53)), s.getsockname()[0], s.close()) for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]]) if l][0][0]
    except Exception:
        return '127.0.0.1'


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
            }
    ctx = Context('0.0.0.0', SERVER_PORT, pvdb)
    curio.run(ctx.run())
