import time
import weakref

# TODO: assuming USE_NUMPY for now
import numpy as np

from ._dbr import (DBR_TYPES, ChType, promote_type, native_type,
                   native_float_types, native_int_types, native_types,
                   timestamp_to_epics, time_types, MAX_ENUM_STRING_SIZE,
                   DBR_STSACK_STRING, AccessRights, _numpy_map,
                   SubscriptionType)
from ._utils import CaprotoError


class Forbidden(CaprotoError):
    ...


def _convert_enum_values(values, to_dtype, string_encoding, enum_strings):
    if isinstance(values, (str, bytes)):
        values = [values]

    if to_dtype == ChType.STRING:
        return [value.encode(string_encoding) for value in values]
    else:
        if enum_strings is not None:
            return [enum_strings.index(value) for value in values]
        else:
            return [0 for value in values]


def _convert_char_values(values, to_dtype, string_encoding, enum_strings):
    if isinstance(values, str):
        values = values.encode(string_encoding)

    if not isinstance(values, bytes):
        # for single value or metadata conversion, let numpy take care of
        # typing
        return np.asarray(values).astype(_numpy_map[to_dtype])
    elif to_dtype in native_int_types or to_dtype in native_float_types:
        arr = np.frombuffer(values, dtype=np.uint8)
        if to_dtype != ChType.CHAR:
            return arr.astype(_numpy_map[to_dtype])
        return arr

    return values


def _convert_string_values(values, to_dtype, string_encoding, enum_strings):
    if to_dtype == ChType.ENUM:
        if not isinstance(values, (str, bytes)):
            values = values[0]
        if enum_strings:
            if isinstance(values, bytes):
                byte_value = values
                str_value = values.decode(string_encoding)
            else:
                byte_value = values.encode(string_encoding)
                str_value = values

            if byte_value in enum_strings:
                return byte_value
            elif str_value in enum_strings:
                return str_value
            else:
                raise ValueError('Invalid enum string')
        else:
            return 0
    elif to_dtype in native_int_types or to_dtype in native_float_types:
        return np.asarray(values).astype(_numpy_map[to_dtype])

    if isinstance(values, str):
        # single string
        return [values.encode(string_encoding)]
    elif isinstance(values, bytes):
        # single bytestring
        return [values]
    else:
        # array of strings/bytestrings
        return [v.encode(string_encoding)
                if isinstance(v, str)
                else v
                for v in values]


_custom_conversions = {ChType.ENUM: _convert_enum_values,
                       ChType.CHAR: _convert_char_values,
                       ChType.STRING: _convert_string_values,
                       }


def convert_values(values, from_dtype, to_dtype, *, string_encoding='latin-1',
                   enum_strings=None):
    '''Convert values from one ChType to another

    Parameters
    ----------
    values :
    from_dtype : caproto.ChannelType
        The dtype of the values
    to_dtype : caproto.ChannelType
        The dtype to convert to
    string_encoding : str, optional
        The encoding to be used for strings
    enum_strings : list, optional
        List of enum strings, if available
    '''

    if to_dtype not in native_types:
        raise ValueError('Expecting a native type')

    if to_dtype in (ChType.STSACK_STRING, ChType.CLASS_NAME):
        if from_dtype != to_dtype:
            raise ValueError('Cannot convert values for stsack_string or '
                             'class_name to other types')

    try:
        len(values)
    except TypeError:
        values = (values, )

    if from_dtype in _custom_conversions:
        convert_func = _custom_conversions[from_dtype]
        return convert_func(values=values, to_dtype=to_dtype,
                            string_encoding=string_encoding,
                            enum_strings=enum_strings)

    if to_dtype == ChType.STRING:
        return [str(v).encode(string_encoding) for v in values]

    return np.asarray(values).astype(_numpy_map[to_dtype])


class ChannelAlarm:
    def __init__(self, *, status=0, severity=0,
                 acknowledge_transient=True, acknowledge_severity=0,
                 alarm_string='', string_encoding='latin-1'):
        self._channels = weakref.WeakSet()
        self.string_encoding = string_encoding
        data = {}
        data['status'] = status
        data['severity'] = severity
        data['acknowledge_transient'] = acknowledge_transient
        data['acknowledge_severity'] = acknowledge_severity
        data['alarm_string'] = alarm_string
        self._data = data

    status = property(lambda self: self._data['status'])
    severity = property(lambda self: self._data['severity'])
    acknowledge_transient = property(lambda self: self._data['acknowledge_transient'])
    acknowledge_severity = property(lambda self: self._data['acknowledge_severity'])
    alarm_string = property(lambda self: self._data['alarm_string'])

    def connect(self, channel_data):
        self._channels.add(channel_data)

    def disconnect(self, channel_data):
        self._channels.remove(channel_data)

    def acknowledge(self):
        pass

    def _set_instance_from_dbr(self, dbr):
        data = self._data
        data['status'] = dbr.status
        data['severity'] = dbr.severity
        data['acknowledge_transient'] = (dbr.ackt != 0)
        data['acknowledge_severity'] = dbr.acks
        data['alarm_string'] = dbr.value.decode(self.string_encoding)

    @classmethod
    def _from_dbr(cls, dbr, **kwargs):
        instance = cls(**kwargs)
        instance._set_instance_from_dbr(dbr)
        return instance

    async def read(self, dbr=None):
        if dbr is None:
            dbr = DBR_STSACK_STRING()
        dbr.status = self.status
        dbr.severity = self.severity
        dbr.ackt = 1 if self.acknowledge_transient else 0
        dbr.acks = self.acknowledge_severity
        dbr.value = self.alarm_string.encode(self.string_encoding)
        return dbr

    async def write(self, *, status=None, severity=None,
                    acknowledge_transient=None,
                    acknowledge_severity=None,
                    alarm_string=None, caller=None):
        data = self._data
        if status is not None:
            data['status'] = status
        if severity is not None:
            data['severity'] = severity
        if acknowledge_transient is not None:
            data['acknowledge_transient'] = acknowledge_transient
        if acknowledge_severity is not None:
            data['acknowledge_severity'] = acknowledge_severity
        if alarm_string is not None:
            data['alarm_string'] = alarm_string
        for channel in self._channels:
            # TODO
            ...

class ChannelData:
    data_type = ChType.LONG

    def __init__(self, *, alarm=None,
                 value=None, timestamp=None,
                 string_encoding='latin-1',
                 reported_record_type='caproto'):
        '''Metadata and Data for a single caproto Channel

        Parameters
        ----------
        value :
            Data which has to match with this class's data_type
        timestamp : float, optional
            Posix timestamp associated with the value
            Defaults to `time.time()`
        string_encoding : str, optional
            Encoding to use for strings, used both in and out
        reported_record_type : str, optional
            Though this is not a record, the channel access protocol supports
            querying the record type.  This can be set to mimic an actual
            record or be set to something arbitrary.
            Defaults to 'caproto'
        '''
        if timestamp is None:
            timestamp = time.time()
        if alarm is None:
            alarm = ChannelAlarm()
        self.alarm = alarm
        self.alarm.connect(self)
        self.string_encoding = string_encoding
        self.reported_record_type = reported_record_type
        self._data = {}
        self._data['value'] = value
        self._data['timestamp'] = timestamp
        self._subscription_queue = None
        self._dbr_metadata = {
            chtype: DBR_TYPES[chtype]()
            for chtype in (promote_type(self.data_type, use_ctrl=True),
                           promote_type(self.data_type, use_time=True),
                           promote_type(self.data_type, use_status=True),
                           promote_type(self.data_type, use_gr=True),
                           )
        }

    value = property(lambda self: self._data['value'])
    timestamp = property(lambda self: self._data['timestamp'])

    def subscribe(self, queue, *sub_queue_args):
        '''Set subscription queue'''
        self._subscription_queue = queue
        self._subscription_queue_args = sub_queue_args

    async def auth_read(self, hostname, username, data_type):
        '''Get DBR data and native data, converted to a specific type'''
        access = self.check_access(hostname, username)
        if access not in (AccessRights.READ, AccessRights.READ_WRITE):
            raise Forbidden("Client with hostname {} and username {} cannot "
                            "read.".format(hostname, username))
        return (await self.read(data_type))

    async def read(self, data_type):
        # special cases for alarm strings and class name
        if data_type == ChType.STSACK_STRING:
            ret = await self.alarm.read()
            return (ret, b'')
        elif data_type == ChType.CLASS_NAME:
            class_name = DBR_TYPES[data_type]()
            rtyp = self.reported_record_type.encode(self.string_encoding)
            class_name.value = rtyp
            return class_name, b''

        # for native types, there is no dbr metadata - just data
        native_to = native_type(data_type)
        values = convert_values(values=self.value, from_dtype=self.data_type,
                              to_dtype=native_to,
                              string_encoding=self.string_encoding,
                              enum_strings=getattr(self, 'enum_strings', None))


        if data_type in native_types:
            return b'', values

        if data_type in self._dbr_metadata:
            dbr_metadata = self._dbr_metadata[data_type]
        else:
            # TODO: non-standard type request. frequent ones probably should be
            # cached?
            dbr_metadata = DBR_TYPES[data_type]()

        self._copy_metadata_to_dbr(dbr_metadata)
        return dbr_metadata, values

    async def auth_write(self, hostname, username,
                         data, data_type,metadata):
        access = self.check_access(hostname, username)
        if access not in (AccessRights.WRITE, AccessRights.READ_WRITE):
            raise Forbidden("Client with hostname {} and username {} cannot "
                            "write.".format(hostname, username))
        return (await self.write(data, data_type, metadata))

    async def write(self, data, data_type, metadata):
        '''Set data from DBR metadata/values'''
        timestamp = time.time()  # will only be used if metadata is None
        native_from = native_type(data_type)
        self._data['value'] = convert_values(
            values=data,
            from_dtype=native_from,
            to_dtype=self.data_type,
            string_encoding=self.string_encoding,
            enum_strings=getattr(self, 'enum_strings', None))

        if metadata is None:
            self._data['timestamp'] = timestamp
        else:
            md_payload = parse_metadata(metadata, data_type)
            # TODO Do something with this.

        if self._subscription_queue is not None:
            await self._subscription_queue.put((self,
                                                SubscriptionType.DBE_VALUE,
                                                self.value) +
                                               self._subscription_queue_args)

    def _copy_metadata_to_dbr(self, dbr_metadata):
        'Set all metadata fields of a given DBR type instance'
        to_type = ChType(dbr_metadata.DBR_ID)

        if hasattr(dbr_metadata, 'units'):
            units = getattr(self, 'units', '')
            if isinstance(units, str):
                units = units.encode(self.string_encoding)
            dbr_metadata.units = units

        if hasattr(dbr_metadata, 'precision'):
            dbr_metadata.precision = getattr(self, 'precision', 0)

        if to_type in time_types:
            epics_ts = self.epics_timestamp
            dbr_metadata.secondsSinceEpoch, dbr_metadata.nanoSeconds = epics_ts

        if hasattr(dbr_metadata, 'status'):
            # many have status/severity
            dbr_metadata.status = self.status
            dbr_metadata.severity = self.severity

        convert_attrs = ('upper_disp_limit', 'lower_disp_limit',
                         'upper_alarm_limit', 'upper_warning_limit',
                         'lower_warning_limit', 'lower_alarm_limit',
                         'upper_ctrl_limit', 'lower_ctrl_limit')

        if not any(hasattr(dbr_metadata, attr) for attr in convert_attrs):
            return

        # convert all metadata types to the target type
        values = convert_values(values=[getattr(self, key, 0)
                                        for key in convert_attrs],
                                from_dtype=self.data_type,
                                to_dtype=native_type(to_type),
                                string_encoding=self.string_encoding)
        if isinstance(values, np.ndarray):
            values = values.tolist()
        for attr, value in zip(convert_attrs, values):
            if hasattr(dbr_metadata, attr):
                setattr(dbr_metadata, attr, value)

    @property
    def epics_timestamp(self):
        'EPICS timestamp as (seconds, nanoseconds) since EPICS epoch'
        return timestamp_to_epics(self.timestamp)

    @property
    def status(self):
        '''Alarm status'''
        return self.alarm.status

    @property
    def severity(self):
        '''Alarm severity'''
        return self.alarm.severity

    def __len__(self):
        try:
            return len(self.value)
        except TypeError:
            return 1

    def check_access(self, hostname, username):
        """
        This always returns ``AccessRights.READ_WRITE``.

        Subclasses can override to implement access logic
        using hostname, username and returning one of
        ``{AccessRights.READ_WRITE, AccessRights.READ, AccessRights.WRITE}``.

        Parameters
        ----------
        hostname : string
        username : string
        
        Returns
        -------
        access : :data:`AccessRights.READ_WRITE`
        """
        return AccessRights.READ_WRITE


class ChannelEnum(ChannelData):
    data_type = ChType.ENUM

    def __init__(self, *, enum_strings=None, **kwargs):
        super().__init__(**kwargs)

        if enum_strings is None:
            enum_strings = []
        self._data['enum_strings'] = enum_strings

    enum_strings = property(lambda self: self._data['enum_strings'])

    def _copy_metadata_to_dbr(self, dbr_metadata):
        if hasattr(dbr_metadata, 'strs') and self.enum_strings:
            for i, string in enumerate(self.enum_strings):
                bytes_ = bytes(string, self.string_encoding)
                dbr_metadata.strs[i][:] = bytes_.ljust(MAX_ENUM_STRING_SIZE,
                                                       b'\x00')
            dbr_metadata.no_str = len(self.enum_strings)

        return super()._copy_metadata_to_dbr(dbr_metadata)


class ChannelNumeric(ChannelData):
    def __init__(self, *, units='',
                 upper_disp_limit=0, lower_disp_limit=0,
                 upper_alarm_limit=0, upper_warning_limit=0,
                 lower_warning_limit=0, lower_alarm_limit=0,
                 upper_ctrl_limit=0, lower_ctrl_limit=0,
                 **kwargs):

        super().__init__(**kwargs)
        self._data['units'] = units
        self._data['upper_disp_limit'] = upper_disp_limit
        self._data['lower_disp_limit'] = lower_disp_limit
        self._data['upper_alarm_limit'] = upper_alarm_limit
        self._data['upper_warning_limit'] = upper_warning_limit
        self._data['lower_warning_limit'] = lower_warning_limit
        self._data['lower_alarm_limit'] = lower_alarm_limit
        self._data['upper_ctrl_limit'] = upper_ctrl_limit
        self._data['lower_ctrl_limit'] = lower_ctrl_limit

    units = property(lambda self: self._data['units'])
    upper_disp_limit = property(lambda self: self._data['upper_disp_limit'])
    lower_disp_limit = property(lambda self: self._data['lower_disp_limit'])
    upper_alarm_limit = property(lambda self: self._data['upper_alarm_limit'])
    upper_warning_limit = property(lambda self: self._data['upper_warning_limit'])
    lower_warning_limit = property(lambda self: self._data['lower_warning_limit'])
    lower_alarm_limit = property(lambda self: self._data['lower_alarm_limit'])
    upper_ctrl_limit = property(lambda self: self._data['upper_ctrl_limit'])
    lower_ctrl_limit = property(lambda self: self._data['lower_ctrl_limit'])


class ChannelInteger(ChannelNumeric):
    data_type = ChType.LONG


class ChannelDouble(ChannelNumeric):
    data_type = ChType.DOUBLE

    def __init__(self, *, precision=0, **kwargs):
        super().__init__(**kwargs)

        self._data['precision'] = precision

    precision = property(lambda self: self._data['precision'])


class ChannelChar(ChannelNumeric):
    # 'Limits' on chars do not make much sense and are rarely used.
    data_type = ChType.CHAR

    def __init__(self, *, max_length=100, **kwargs):
        super().__init__(**kwargs)
        self.max_length = max_length


class ChannelString(ChannelData):
    data_type = ChType.STRING
    # There is no CTRL or GR variant of STRING.
