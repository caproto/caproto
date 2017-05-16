import time
from ._dbr import (DBR_TYPES, ChType, promote_type, native_type,
                   native_float_types, native_int_types, native_types,
                   timestamp_to_epics, time_types, MAX_ENUM_STRING_SIZE,
                   DBR_STSACK_STRING, AccessRights)


def _ensure_iterable(value):
    try:
        len(value)
    except TypeError:
        return (value, )
    else:
        return value


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

    def to_dbr(self, dbr=None):
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
    _has_custom_convert = False

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
            querying the record type.  This can be set to mimic an actual record
            or be set to something arbitrary.
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
        self._data = {chtype: DBR_TYPES[chtype]()
                      for chtype in
                      (promote_type(self.data_type, use_ctrl=True),
                       promote_type(self.data_type, use_time=True),
                       promote_type(self.data_type, use_status=True),
                       promote_type(self.data_type, use_gr=True),
                       )
                      }

    def convert_to(self, to_dtype):
        '''Convert values to another native type

        Parameters
        ----------
        to_dtype : ca.ChType
        '''
        if to_dtype not in native_types:
            raise ValueError('Expecting a native type')

        if to_dtype in (ChType.STSACK_STRING, ChType.CLASS_NAME):
            return None

        from_dtype = self.data_type

        no_conversion_necessary = (
            from_dtype == to_dtype or
            (from_dtype in native_float_types and to_dtype in
             native_float_types) or
            (from_dtype in native_int_types and to_dtype in native_int_types)
        )

        values = _ensure_iterable(self.value)

        if no_conversion_necessary:
            return values

        if from_dtype in native_float_types and to_dtype in native_int_types:
            values = [int(v) for v in values]
        elif to_dtype == ChType.STRING:
            values = [str(v).encode(self.string_encoding) for v in values]
        return values

    def get_dbr_data(self, type_):
        if type_ == ChType.STSACK_STRING:
            return (self.alarm.to_dbr(), b'')
        elif type_ == ChType.CLASS_NAME:
            class_name = DBR_TYPES[type_]()
            rtyp = self.reported_record_type.encode(self.string_encoding)
            class_name.value = rtyp
            return class_name, b''

        native_to = native_type(type_)
        if type_ in self._data:
            dbr_data = self._data[type_]
            self._set_dbr_metadata(dbr_data)

            if self._has_custom_convert:
                value = self.convert_to(native_to)
            else:
                value = _ensure_iterable(self.value)

            return dbr_data, value
        elif type_ in native_types:
            return b'', self.convert_to(native_to)

        # non-standard type request. frequent ones probably should be cached?
        dbr_data = DBR_TYPES[type_]()
        self._set_dbr_metadata(dbr_data)
        return dbr_data, self.convert_to(native_to)

    def set_dbr_data(self, data):
        return True

    def _set_dbr_metadata(self, dbr_data):
        'Set all metadata fields of a given DBR type instance'
        # note that this is too generic to be useful, there probably should be
        # custom handling for each dbr field as necessary
        ts_sec, ts_ns = self.epics_timestamp
        other_values = {
            'secondsSinceEpoch': ts_sec,
            'nanoSeconds': ts_ns,
            'RISC_Pad': 0,
            'RISC_pad': 0,
            'RISC_pad0': 0,
            'RISC_pad1': 0,
            'ackt': 0,  # TODO from #27
            'acks': 0,  # TODO from #27
            'no_strs': 0,  # if not enum type
            'strs': [],  # if not enum type
        }

        to_type = ChType(dbr_data.DBR_ID)
        for attr, _ in dbr_data._fields_:
            if hasattr(self, attr):
                value = getattr(self, attr)
            elif attr in other_values:
                value = other_values[attr]
            else:
                print('missing', attr)
                continue

            if isinstance(value, str):
                value = bytes(value, self.string_encoding)
            try:
                setattr(dbr_data, attr, value)
            except TypeError as ex:
                if to_type in native_int_types:
                    # you probably want to kill me at this point
                    setattr(dbr_data, attr, int(value))

        if dbr_data.DBR_ID in time_types:
            epics_ts = self.epics_timestamp
            dbr_data.secondsSinceEpoch, dbr_data.nanoSeconds = epics_ts

    @property
    def epics_timestamp(self):
        'EPICS timestamp as (seconds, nanoseconds) since EPICS epoch'
        return timestamp_to_epics(self.timestamp)

    @property
    def status(self):
        return self.alarm.status

    @status.setter
    def status(self, status):
        self.alarm.status = status

    @property
    def severity(self):
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
    _has_custom_convert = True

    def __init__(self, *, strs=None, **kwargs):
        self.strs = strs

        super().__init__(**kwargs)

    @property
    def no_str(self):
        return len(self.strs) if self.strs else 0

    def _set_dbr_metadata(self, dbr_data):
        if hasattr(dbr_data, 'strs'):
            for i, string in enumerate(self.strs):
                bytes_ = bytes(string, self.string_encoding)
                dbr_data.strs[i][:] = bytes_.ljust(MAX_ENUM_STRING_SIZE, b'\x00')

        return super()._set_dbr_metadata(dbr_data)

    def convert_to(self, to_dtype):
        if native_type(to_dtype) == ChType.STRING:
            return [self.value.encode(self.string_encoding)]
        else:
            return [self.strs.index(self.value)]


class ChannelNumeric(ChannelData):
    def __init__(self, *, units='', upper_disp_limit=0.0,
                 lower_disp_limit=0.0, upper_alarm_limit=0.0,
                 upper_warning_limit=0.0, lower_warning_limit=0.0,
                 lower_alarm_limit=0.0, upper_ctrl_limit=0.0,
                 lower_ctrl_limit=0.0, **kwargs):

        super().__init__(**kwargs)
        self.units = units.encode(self.string_encoding)
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
    _has_custom_convert = True

    def convert_to(self, to_dtype):
        # if to_dtype == ChType.STRING:
        #     return self.value.encode(self.string_encoding)
        # else:
        if isinstance(self.value, str):
            return self.value.encode(self.string_encoding)
        elif isinstance(self.value, bytes):
            return self.value
        else:
            return [self.value]


class ChannelString(ChannelData):
    data_type = ChType.STRING
    _has_custom_convert = True
    # There is no CTRL or GR variant of STRING.

    def convert_to(self, to_dtype):
        if to_dtype != ChType.STRING:
            # TODO does this actually respond with an error?
            return b''

        if isinstance(self.value, str):
            # single string
            return [self.value.encode(self.string_encoding)]
        elif isinstance(self.value, bytes):
            # single bytestring
            return [self.value]
        else:
            # array of strings/bytestrings
            return [v.encode(self.string_encoding)
                    if isinstance(v, str)
                    else v
                    for v in self.value]
