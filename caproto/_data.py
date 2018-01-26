from collections import defaultdict
import time
import weakref

# TODO: assuming USE_NUMPY for now
import numpy as np

from ._dbr import (DBR_TYPES, ChannelType, native_type, native_float_types,
                   native_int_types, native_types, timestamp_to_epics,
                   time_types, MAX_ENUM_STRING_SIZE, DBR_STSACK_STRING,
                   AccessRights, _numpy_map, epics_timestamp_to_unix,
                   GraphicControlBase, AlarmStatus, AlarmSeverity,
                   SubscriptionType)
from ._utils import CaprotoError
from ._commands import parse_metadata


class Forbidden(CaprotoError):
    ...


def _convert_enum_values(values, to_dtype, string_encoding, enum_strings):
    if isinstance(values, (str, bytes)):
        values = [values]

    if to_dtype == ChannelType.STRING:
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
        if to_dtype != ChannelType.CHAR:
            return arr.astype(_numpy_map[to_dtype])
        return arr

    return values


def _convert_string_values(values, to_dtype, string_encoding, enum_strings):
    if to_dtype == ChannelType.ENUM:
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


_custom_conversions = {ChannelType.ENUM: _convert_enum_values,
                       ChannelType.CHAR: _convert_char_values,
                       ChannelType.STRING: _convert_string_values,
                       }


def convert_values(values, from_dtype, to_dtype, *, string_encoding='latin-1',
                   enum_strings=None):
    '''Convert values from one ChannelType to another

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

    if to_dtype in (ChannelType.STSACK_STRING, ChannelType.CLASS_NAME):
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

    if to_dtype == ChannelType.STRING:
        return [str(v).encode(string_encoding) for v in values]

    return np.asarray(values).astype(_numpy_map[to_dtype])


def dbr_metadata_to_dict(dbr_metadata, string_encoding):
    '''Return a dictionary of metadata keys to values'''
    # TODO: Note that if dbr.py is restructured to be more like pypvasync
    # (again, but correctly this time) this could be handled nicely as a method
    # on the dbr types

    info = dbr_metadata.to_dict()
    if 'units' in info:
        info['units'] = info['units'].decode(string_encoding)

    return info


def _read_only_property(key, doc=None):
    '''Create property that gives read-only access to instance._data[key]'''
    if doc is None:
        doc = 'data from key {!r}'.format(key)
    return property(lambda self: self._data[key],
                    doc=doc)


class ChannelAlarm:
    def __init__(self, *, status=0, severity=0,
                 must_acknowledge_transient=True, severity_to_acknowledge=0,
                 alarm_string='', string_encoding='latin-1'):
        self._channels = weakref.WeakSet()
        self.string_encoding = string_encoding
        self._data = dict(
            status=status, severity=severity,
            must_acknowledge_transient=must_acknowledge_transient,
            severity_to_acknowledge=severity_to_acknowledge,
            alarm_string=alarm_string)

    status = _read_only_property('status',
                                 doc='Current alarm status')
    severity = _read_only_property('severity',
                                   doc='Current alarm severity')
    must_acknowledge_transient = _read_only_property(
        'must_acknowledge_transient',
        doc='Toggle whether or not transient alarms must be acknowledged')

    severity_to_acknowledge = _read_only_property(
        'severity_to_acknowledge',
        doc='The alarm severity that has been acknowledged')

    alarm_string = _read_only_property('alarm_string',
                                       doc='String associated with alarm')

    def connect(self, channel_data):
        self._channels.add(channel_data)

    def disconnect(self, channel_data):
        self._channels.remove(channel_data)

    async def read(self, dbr=None):
        if dbr is None:
            dbr = DBR_STSACK_STRING()
        dbr.status = self.status
        dbr.severity = self.severity
        dbr.ackt = 1 if self.must_acknowledge_transient else 0
        dbr.acks = self.severity_to_acknowledge
        dbr.value = self.alarm_string.encode(self.string_encoding)
        return dbr

    async def write(self, *, status=None, severity=None,
                    must_acknowledge_transient=None,
                    severity_to_acknowledge=None,
                    alarm_string=None, caller=None):
        data = self._data
        flags = 0

        if status is not None:
            data['status'] = AlarmStatus(status)
            flags |= SubscriptionType.DBE_VALUE

        if severity is not None:
            data['severity'] = AlarmSeverity(severity)

            if (not self.must_acknowledge_transient or
                    self.severity_to_acknowledge < self.severity):
                data['severity_to_acknowledge'] = self.severity

            flags |= SubscriptionType.DBE_ALARM

        if must_acknowledge_transient is not None:
            data['must_acknowledge_transient'] = must_acknowledge_transient
            if (not must_acknowledge_transient and
                    self.severity_to_acknowledge > self.severity):
                # Reset the severity to acknowledge if disabling transient
                # requirement
                data['severity_to_acknowledge'] = self.severity
            flags |= SubscriptionType.DBE_ALARM

        if severity_to_acknowledge is not None:
            # To clear, set greater than or equal to the
            # severity_to_acknowledge
            if severity_to_acknowledge >= self.severity:
                data['severity_to_acknowledge'] = 0
                flags |= SubscriptionType.DBE_ALARM

        if alarm_string is not None:
            data['alarm_string'] = alarm_string
            flags |= SubscriptionType.DBE_ALARM

        for channel in self._channels:
            await channel.publish(flags)


class ChannelData:
    data_type = ChannelType.LONG

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
        self._data = dict(value=value,
                          timestamp=timestamp)
        # This maps queues to SubscriptionSpecs. (Each queue belongs to a
        # Context.)
        self._queues = defaultdict(set)

        # Cache results of data_type conversions. This maps data_type to
        # (metdata, value). This is cleared each time publish() is called.
        self._content = {}

    value = _read_only_property('value')
    timestamp = _read_only_property('timestamp')

    async def subscribe(self, queue, sub_spec):
        self._queues[queue].add(sub_spec)
        # Always send current reading immediately upon subscription.
        data_type = sub_spec.data_type
        try:
            metadata, values = self._content[data_type]
        except KeyError:
            # Do the expensive data type conversion and cache it in case
            # a future subscription wants the same data type.
            metadata, values = await self._read(data_type)
            self._content[data_type] = metadata, values
        flags = (SubscriptionType.DBE_VALUE |
                 SubscriptionType.DBE_ALARM |
                 SubscriptionType.DBE_LOG |
                 SubscriptionType.DBE_PROPERTY)
        await queue.put(((sub_spec,), metadata, values))

    async def unsubscribe(self, queue, sub_spec):
        self._queues[queue].remove(sub_spec)

    async def auth_read(self, hostname, username, data_type):
        '''Get DBR data and native data, converted to a specific type'''
        access = self.check_access(hostname, username)
        if access not in (AccessRights.READ, AccessRights.READ_WRITE):
            raise Forbidden("Client with hostname {} and username {} cannot "
                            "read.".format(hostname, username))
        return (await self.read(data_type))

    async def read(self, data_type):
        # Subclass might trigger a write here to update self._data
        # before reading it out.
        return (await self._read(data_type))

    async def _read(self, data_type):
        # special cases for alarm strings and class name
        if data_type == ChannelType.STSACK_STRING:
            ret = await self.alarm.read()
            return (ret, b'')
        elif data_type == ChannelType.CLASS_NAME:
            class_name = DBR_TYPES[data_type]()
            rtyp = self.reported_record_type.encode(self.string_encoding)
            class_name.value = rtyp
            return class_name, b''

        native_to = native_type(data_type)
        values = convert_values(values=self._data['value'],
                                from_dtype=self.data_type,
                                to_dtype=native_to,
                                string_encoding=self.string_encoding,
                                enum_strings=self._data.get('enum_strings'))

        # for native types, there is no dbr metadata - just data
        if data_type in native_types:
            return b'', values

        dbr_metadata = DBR_TYPES[data_type]()
        self._read_metadata(dbr_metadata)

        # Copy alarm fields also.
        alarm_dbr = await self.alarm.read()
        for field, _ in alarm_dbr._fields_:
            if hasattr(dbr_metadata, field):
                setattr(dbr_metadata, field, getattr(alarm_dbr, field))

        return dbr_metadata, values

    async def auth_write(self, hostname, username, data, data_type, metadata):
        access = self.check_access(hostname, username)
        if access not in (AccessRights.WRITE, AccessRights.READ_WRITE):
            raise Forbidden("Client with hostname {} and username {} cannot "
                            "write.".format(hostname, username))
        return (await self.write_from_dbr(data, data_type, metadata))

    async def verify_value(self, data):
        '''Verify a value prior to it being written by CA or Python

        To reject a value, raise an exception. Otherwise, return the
        original value or a modified version of it.
        '''
        return data

    async def write_from_dbr(self, data, data_type, metadata):
        '''Set data from DBR metadata/values'''
        if data_type == ChannelType.PUT_ACKS:
            await self.alarm.write(severity_to_acknowledge=metadata.value)
            return
        elif data_type == ChannelType.PUT_ACKT:
            await self.alarm.write(must_acknowledge_transient=metadata.value)
            return
        elif data_type in (ChannelType.STSACK_STRING, ChannelType.CLASS_NAME):
            raise ValueError('Bad request')

        timestamp = time.time()
        native_from = native_type(data_type)
        value = convert_values(values=data, from_dtype=native_from,
                               to_dtype=self.data_type,
                               string_encoding=self.string_encoding,
                               enum_strings=getattr(self, 'enum_strings',
                                                    None))

        modified_value = await self.verify_value(value)
        # TODO: on exception raised, set alarm

        self._data['value'] = (modified_value
                               if modified_value is not None
                               else value)

        if metadata is None:
            self._data['timestamp'] = timestamp
        else:
            # Convert `metadata` to bytes-like (or pass it through).
            md_payload = parse_metadata(metadata, data_type)

            # Depending on the type of `metadata` above,
            # `md_payload` could be a DBR struct or plain bytes.
            # Load it into a struct (zero-copy) to be sure.
            dbr_metadata = DBR_TYPES[data_type].from_buffer(md_payload)
            metadata_dict = dbr_metadata_to_dict(dbr_metadata,
                                                 self.string_encoding)
            await self.write_metadata(publish=False, **metadata_dict)

        # Send a new event to subscribers.
        # TODO: mask should be at least DBE_VALUE
        await self.publish(SubscriptionType.DBE_VALUE)

    async def write(self, value, **metadata):
        '''Set data from native Python types'''
        metadata['timestamp'] = metadata.get('timestamp', time.time())
        modified_value = await self.verify_value(value)
        self._data['value'] = (modified_value
                               if modified_value is not None
                               else value)
        await self.write_metadata(publish=False, **metadata)
        # Send a new event to subscribers.
        # TO DO This should be DBE_VALUE or DBE_LOG or 0 depending on
        # deadband and archiver deadband, which we have not defined yet.
        await self.publish(SubscriptionType.DBE_VALUE)

    async def publish(self, flags):
        # Each SubscriptionSpec specifies a certain data type it is interested
        # in and a mask. Send one update per queue per data_type if and only if
        # any subscriptions specs on a queue have a compatible mask.

        # Copying the data into structs with various data types is expensive,
        # so we only want to do it if it's going to be used, and we only want
        # to do each conversion once. Clear the cache to start. This cache is
        # instance state so that self.subscribe can also use it.
        self._content.clear()

        for queue, sub_specs in self._queues.items():
            for data_type in set(ss.data_type for ss in sub_specs):
                # Which (if any) of the sub_specs that want this data_type
                # have a compatible mask?
                eligible = tuple(ss for ss in sub_specs if flags & ss.mask
                                 and ss.data_type == data_type)
                if not eligible:
                    continue
                # There is at least one sub_spec for the queue that will
                # receive this update.
                try:
                    metdata, values = self._content[data_type]
                except KeyError:
                    # Do the expensive data type conversion and cache it in
                    # case another queue or a future subscription wants the
                    # same data type.
                    metadata, values = await self._read(data_type)
                    self._content[data_type] = metadata, values
                await queue.put((eligible, metadata, values))

    def _read_metadata(self, dbr_metadata):
        'Set all metadata fields of a given DBR type instance'
        to_type = ChannelType(dbr_metadata.DBR_ID)
        data = self._data

        if hasattr(dbr_metadata, 'units'):
            units = data.get('units', '')
            if isinstance(units, str):
                units = units.encode(self.string_encoding)
            dbr_metadata.units = units

        if hasattr(dbr_metadata, 'precision'):
            dbr_metadata.precision = data.get('precision', 0)

        if to_type in time_types:
            epics_ts = timestamp_to_epics(data['timestamp'])
            dbr_metadata.secondsSinceEpoch, dbr_metadata.nanoSeconds = epics_ts

        convert_attrs = (GraphicControlBase.control_fields +
                         GraphicControlBase.graphic_fields)

        if any(hasattr(dbr_metadata, attr) for attr in convert_attrs):
            # convert all metadata types to the target type
            values = convert_values(values=[data.get(key, 0)
                                            for key in convert_attrs],
                                    from_dtype=self.data_type,
                                    to_dtype=native_type(to_type),
                                    string_encoding=self.string_encoding)
            if isinstance(values, np.ndarray):
                values = values.tolist()
            for attr, value in zip(convert_attrs, values):
                if hasattr(dbr_metadata, attr):
                    setattr(dbr_metadata, attr, value)

    async def write_metadata(self, publish=True, units=None, precision=None,
                             timestamp=None, upper_disp_limit=None,
                             lower_disp_limit=None, upper_alarm_limit=None,
                             upper_warning_limit=None,
                             lower_warning_limit=None, lower_alarm_limit=None,
                             upper_ctrl_limit=None, lower_ctrl_limit=None,
                             status=None, severity=None):
        '''Write metadata, optionally publishing information to clients'''
        data = self._data
        for kw in ('units', 'precision', 'timestamp', 'upper_disp_limit',
                   'lower_disp_limit', 'upper_alarm_limit',
                   'upper_warning_limit', 'lower_warning_limit',
                   'lower_alarm_limit', 'upper_ctrl_limit',
                   'lower_ctrl_limit'):
            value = locals()[kw]
            if value is not None and kw in data:
                data[kw] = value

        if any(alarm_val is not None
               for alarm_val in (status, severity)):
            await self.alarm.write(status=status, severity=severity)

        if publish:
            await self.publish(SubscriptionType.DBE_PROPERTY)

    @property
    def epics_timestamp(self):
        'EPICS timestamp as (seconds, nanoseconds) since EPICS epoch'
        return timestamp_to_epics(self._data['timestamp'])

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
    data_type = ChannelType.ENUM

    def __init__(self, *, enum_strings=None, **kwargs):
        super().__init__(**kwargs)

        if enum_strings is None:
            enum_strings = []
        self._data['enum_strings'] = enum_strings

    enum_strings = _read_only_property('enum_strings')

    def _read_metadata(self, dbr_metadata):
        if isinstance(dbr_metadata, (DBR_TYPES[ChannelType.GR_ENUM],
                                     DBR_TYPES[ChannelType.CTRL_ENUM])):
            for i, string in enumerate(self.enum_strings):
                bytes_ = bytes(string, self.string_encoding)
                dbr_metadata.strs[i][:] = bytes_.ljust(MAX_ENUM_STRING_SIZE,
                                                       b'\x00')
            dbr_metadata.no_str = len(self.enum_strings)

        return super()._read_metadata(dbr_metadata)


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

    units = _read_only_property('units')
    upper_disp_limit = _read_only_property('upper_disp_limit')
    lower_disp_limit = _read_only_property('lower_disp_limit')
    upper_alarm_limit = _read_only_property('upper_alarm_limit')
    upper_warning_limit = _read_only_property('upper_warning_limit')
    lower_warning_limit = _read_only_property('lower_warning_limit')
    lower_alarm_limit = _read_only_property('lower_alarm_limit')
    upper_ctrl_limit = _read_only_property('upper_ctrl_limit')
    lower_ctrl_limit = _read_only_property('lower_ctrl_limit')


class ChannelInteger(ChannelNumeric):
    data_type = ChannelType.LONG


class ChannelDouble(ChannelNumeric):
    data_type = ChannelType.DOUBLE

    def __init__(self, *, precision=0, **kwargs):
        super().__init__(**kwargs)

        self._data['precision'] = precision

    precision = _read_only_property('precision')


class ChannelChar(ChannelNumeric):
    # 'Limits' on chars do not make much sense and are rarely used.
    data_type = ChannelType.CHAR

    def __init__(self, *, max_length=100, **kwargs):
        super().__init__(**kwargs)
        self.max_length = max_length


class ChannelString(ChannelData):
    data_type = ChannelType.STRING
    # There is no CTRL or GR variant of STRING.

    def __init__(self, *, alarm=None,
                 value=None, timestamp=None,
                 string_encoding='latin-1',
                 reported_record_type='caproto'):
        if isinstance(value, (str, bytes)):
            value = [value]
        super().__init__(alarm=alarm, value=value, timestamp=timestamp,
                         string_encoding=string_encoding,
                         reported_record_type=reported_record_type)
