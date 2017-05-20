import time
from ._dbr import (DBR_TYPES, ChType, promote_type, native_type,
                   native_float_types, native_int_types, native_types,
                   timestamp_to_epics, time_types, MAX_ENUM_STRING_SIZE,
                   DBR_STSACK_STRING, AccessRights, _numpy_map)

# TODO: assuming USE_NUMPY for now
import numpy as np


def _convert_enum_values(values, to_dtype, string_encoding, enum_strings):
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
    if to_dtype in native_int_types or to_dtype in native_float_types:
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


class ChannelAlarmStatus:
    def __init__(self, *, channel_data=None, status=0, severity=0,
                 acknowledge_transient=True, acknowledge_severity=0,
                 alarm_string=''):
        self.channel_data = channel_data
        self.status = status
        self.severity = severity
        self.acknowledge_transient = acknowledge_transient
        self.acknowledge_severity = acknowledge_severity
        self.alarm_string = alarm_string

    def acknowledge(self):
        pass

    def _set_instance_from_dbr(self, dbr):
        self.status = dbr.status
        self.severity = dbr.severity
        self.acknowledge_transient = (dbr.ackt != 0)
        self.acknowledge_severity = dbr.acks
        self.alarm_string = dbr.value.decode(self.string_encoding)

    @classmethod
    def _from_dbr(cls, dbr):
        instance = cls()
        instance._set_instance_from_dbr(dbr)

    def get_dbr_data(self, dbr=None):
        if dbr is None:
            dbr = DBR_STSACK_STRING()
        dbr.status = self.status
        dbr.severity = self.severity
        dbr.ackt = 1 if self.acknowledge_transient else 0
        dbr.acks = self.acknowledge_severity
        dbr.value = self.alarm_string.encode(self.string_encoding)
        return dbr

    @property
    def string_encoding(self):
        return self.channel_data.string_encoding


class ChannelData:
    data_type = ChType.LONG

    def __init__(self, *, value=None, timestamp=None, status=0, severity=0,
                 string_encoding='latin-1', alarm_status=None,
                 reported_record_type='caproto'):
        '''Metadata and Data for a single caproto Channel

        Parameters
        ----------
        value :
            Data which has to match with this class's data_type
        timestamp : float, optional
            Posix timestamp associated with the value
            Defaults to `time.time()`
        status : ca.AlarmStatus, optional
            Alarm status
        severity : ca.AlarmSeverity, optional
            Alarm severity
        string_encoding : str, optional
            Encoding to use for strings, used both in and out
        alarm_status : ChannelAlarmStatus, optional
            Optionally specify an allocated alarm status, which could be shared
            among several channels
        reported_record_type : str, optional
            Though this is not a record, the channel access protocol supports
            querying the record type.  This can be set to mimic an actual
            record or be set to something arbitrary.
            Defaults to 'caproto'
        '''
        if timestamp is None:
            timestamp = time.time()
        self.timestamp = timestamp
        if alarm_status is not None:
            self.alarm = alarm_status
            self.alarm.channel_data = self
        else:
            self.alarm = ChannelAlarmStatus(status=status, severity=severity,
                                            channel_data=self)
        self.value = value
        self.string_encoding = string_encoding
        self.reported_record_type = reported_record_type
        self._dbr_metadata = {
            chtype: DBR_TYPES[chtype]()
            for chtype in (promote_type(self.data_type, use_ctrl=True),
                           promote_type(self.data_type, use_time=True),
                           promote_type(self.data_type, use_status=True),
                           promote_type(self.data_type, use_gr=True),
                           )
        }

    def fromtype(self, values, data_type):
        '''Convenience function to convert given values to this data type'''
        native_from = native_type(data_type)
        return convert_values(values=values, from_dtype=native_from,
                              to_dtype=self.data_type,
                              string_encoding=self.string_encoding,
                              enum_strings=getattr(self, 'enum_strings', None))

    def astype(self, to_dtype):
        '''Convenience function: convert stored data to a specific type'''
        native_to = native_type(to_dtype)
        return convert_values(values=self.value, from_dtype=self.data_type,
                              to_dtype=native_to,
                              string_encoding=self.string_encoding,
                              enum_strings=getattr(self, 'enum_strings', None))

    def get_dbr_data(self, type_):
        '''Get DBR data and native data, converted to a specific type'''
        # special cases for alarm strings and class name
        if type_ == ChType.STSACK_STRING:
            return (self.alarm.get_dbr_data(), b'')
        elif type_ == ChType.CLASS_NAME:
            class_name = DBR_TYPES[type_]()
            rtyp = self.reported_record_type.encode(self.string_encoding)
            class_name.value = rtyp
            return class_name, b''

        # for native types, there is no dbr metadata - just data
        native_to = native_type(type_)
        values = self.astype(native_to)

        if type_ in native_types:
            return b'', values

        if type_ in self._dbr_metadata:
            dbr_metadata = self._dbr_metadata[type_]
        else:
            # TODO: non-standard type request. frequent ones probably should be
            # cached?
            dbr_metadata = DBR_TYPES[type_]()

        self._set_dbr_metadata(dbr_metadata)
        return dbr_metadata, values

    def set_dbr_data(self, data, data_type, metadata):
        '''Set data from DBR metadata/values'''
        self.value = self.fromtype(values=data, data_type=data_type)
        return True

    def _set_dbr_metadata(self, dbr_metadata):
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

    @status.setter
    def status(self, status):
        self.alarm.status = status

    @property
    def severity(self):
        '''Alarm severity'''
        return self.alarm.severity

    @severity.setter
    def severity(self, severity):
        self.alarm.severity = severity

    def __len__(self):
        try:
            return len(self.value)
        except TypeError:
            return 1

    def check_access(self, hostname, username):
        print('{!r} from host {!r} has full access to {}'
              ''.format(username, hostname, self))
        return AccessRights.READ_WRITE


class ChannelEnum(ChannelData):
    data_type = ChType.ENUM

    def __init__(self, *, strs=None, **kwargs):
        self.strs = strs

        super().__init__(**kwargs)

    @property
    def enum_strings(self):
        '''List of enum strings for all values'''
        return self.strs

    @property
    def no_str(self):
        return len(self.strs) if self.strs else 0

    def _set_dbr_metadata(self, dbr_metadata):
        if hasattr(dbr_metadata, 'strs') and self.enum_strings:
            for i, string in enumerate(self.enum_strings):
                bytes_ = bytes(string, self.string_encoding)
                dbr_metadata.strs[i][:] = bytes_.ljust(MAX_ENUM_STRING_SIZE,
                                                       b'\x00')
            dbr_metadata.no_str = self.no_str

        return super()._set_dbr_metadata(dbr_metadata)


class ChannelNumeric(ChannelData):
    def __init__(self, *, units='', upper_disp_limit=0, lower_disp_limit=0,
                 upper_alarm_limit=0, upper_warning_limit=0,
                 lower_warning_limit=0, lower_alarm_limit=0,
                 upper_ctrl_limit=0, lower_ctrl_limit=0, **kwargs):

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


class ChannelInteger(ChannelNumeric):
    data_type = ChType.LONG


class ChannelDouble(ChannelNumeric):
    data_type = ChType.DOUBLE

    def __init__(self, *, precision=0, **kwargs):
        super().__init__(**kwargs)

        self.precision = precision


class ChannelChar(ChannelNumeric):
    # 'Limits' on chars do not make much sense and are rarely used.
    data_type = ChType.CHAR


class ChannelString(ChannelData):
    data_type = ChType.STRING
    # There is no CTRL or GR variant of STRING.
