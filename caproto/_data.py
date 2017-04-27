import time
from ._dbr import (DBR_TYPES, ChType, promote_type, native_type,
                   native_float_types, native_int_types, native_types,
                   timestamp_to_epics, time_types, MAX_ENUM_STRING_SIZE,
                   DBR_STSACK_STRING)
from ._utils import ensure_bytes

# it's all about data
ENCODING = 'latin-1'


# TODO these aren't really records. what were you thinking?
class DatabaseAlarmStatus:
    def __init__(self, *, status=0, severity=0, acknowledge_transient=False,
                 acknowledge_severity=0, alarm_string=''):
        self.status = status
        self.severity = severity
        self.acknowledge_transient = acknowledge_transient
        self.acknowledge_severity = acknowledge_severity
        self.alarm_string = ''

    def acknowledge(self):
        pass

    def _set_instance_from_dbr(self, dbr):
        self.status = dbr.status
        self.severity = dbr.severity
        self.acknowledge_transient = (dbr.ackt != 0)
        self.acknowledge_severity = dbr.acks
        self.alarm_string = dbr.value.decode(ENCODING)

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
        dbr.value = self.alarm_string.encode(ENCODING)
        return dbr


class ChannelData:
    data_type = ChType.LONG

    def __init__(self, *, timestamp=None, status=0, severity=0, value=None):
        if timestamp is None:
            timestamp = time.time()
        self.timestamp = timestamp
        self.alarm = DatabaseAlarmStatus(status=status, severity=severity)
        self.value = value

        self._data = {chtype: DBR_TYPES[chtype]()
                      for chtype in
                      (promote_type(self.data_type, use_ctrl=True),
                       promote_type(self.data_type, use_time=True),
                       promote_type(self.data_type, use_status=True),
                       promote_type(self.data_type, use_gr=True),
                       )
                      }

        # additional 'array' data not stored in the base DBR types:
        self._data['native'] = []

    def convert_to(self, to_dtype):
        if to_dtype in (ChType.STSACK_STRING, ChType.CLASS_NAME):
            return None

        # this leaves a lot to be desired
        from_dtype = self.data_type
        native_to = native_type(to_dtype)

        # TODO metadata is expected to be of this type as well!
        no_conversion_necessary = (
            from_dtype == native_to or
            (from_dtype in native_float_types and native_to in
             native_float_types) or
            (from_dtype in native_int_types and native_to in native_int_types)
        )

        try:
            len(self.value)
        except TypeError:
            values = (self.value, )
        else:
            values = self.value

        if no_conversion_necessary:
            return values

        if from_dtype in native_float_types and native_to in native_int_types:
            values = [int(v) for v in values]
        elif native_to == ChType.STRING:
            if self.data_type in (ChType.STRING, ChType.ENUM):
                values = [v.encode(ENCODING) for v in values]
            else:
                values = [bytes(str(v), ENCODING) for v in values]
        return values

    def get_dbr_data(self, type_):
        if type_ in self._data and self.data_type != ChType.ENUM:
            dbr_data = self._data[type_]
            self._set_dbr_metadata(dbr_data)
            return dbr_data, self._data['native']
        elif type_ in native_types:
            return None, self.convert_to(type_)

        # non-standard type request. frequent ones probably should be
        # cached?
        dbr_data = DBR_TYPES[type_]()
        self._set_dbr_metadata(dbr_data)
        return dbr_data, self.convert_to(type_)

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
                value = bytes(value, ENCODING)
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

    def check_access(self, sender_address):
        print('{} has full access to {}'.format(sender_address, self))
        return 3  # read-write


class ChannelEnum(ChannelData):
    data_type = ChType.ENUM

    def __init__(self, *, strs=None, **kwargs):
        self.strs = strs

        super().__init__(**kwargs)

    @property
    def no_str(self):
        return len(self.strs) if self.strs else 0

    def _set_dbr_metadata(self, dbr_data):
        if hasattr(dbr_data, 'strs'):
            for i, string in enumerate(self.strs):
                bytes_ = bytes(string, ENCODING)
                dbr_data.strs[i][:] = bytes_.ljust(MAX_ENUM_STRING_SIZE, b'\x00')

        return super()._set_dbr_metadata(dbr_data)

    def convert_to(self, to_dtype):
        if native_type(to_dtype) == ChType.STRING:
            return [bytes(str(self.value), ENCODING)]
        else:
            return [self.strs.index(self.value)]


class ChannelNumeric(ChannelData):
    def __init__(self, *, units='', upper_disp_limit=0.0,
                 lower_disp_limit=0.0, upper_alarm_limit=0.0,
                 upper_warning_limit=0.0, lower_warning_limit=0.0,
                 lower_alarm_limit=0.0, upper_ctrl_limit=0.0,
                 lower_ctrl_limit=0.0, **kwargs):

        super().__init__(**kwargs)
        self.units = ensure_bytes(units)
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
