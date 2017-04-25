import time
from ._dbr import (DBR_TYPES, ChType, promote_type, native_type,
                   native_float_types, native_int_types, native_types,
                   timestamp_to_epics, time_types)
from ._utils import ensure_bytes

# it's all about data
ENCODING = 'latin-1'


# TODO these aren't really records. what were you thinking?
class DatabaseRecordBase:
    data_type = ChType.LONG

    def __init__(self, *, timestamp=None, status=0, severity=0, value=None):
        if timestamp is None:
            timestamp = time.time()
        self.timestamp = timestamp
        self.status = status
        self.severity = severity
        self.value = value

        self._data = {chtype: DBR_TYPES[chtype]()
                      for chtype in
                      (promote_type(self.data_type, use_ctrl=True),
                       promote_type(self.data_type, use_time=True),
                       promote_type(self.data_type, use_status=True),
                       # pending merge of #27 which will have conflicts with
                       # this one now:
                       # promote_type(self.data_type, use_gr=True),
                       )
                      }

        # additional 'array' data not stored in the base DBR types:
        self._data['native'] = []

    def convert_to(self, to_dtype):
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
        elif from_dtype == ChType.ENUM:
            if native_to == ChType.STRING:
                values = [v.encode(ENCODING) for v in values]
            else:
                values = [self.strs.index(v) for v in values]
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
            setattr(dbr_data, attr, value)

        if dbr_data.DBR_ID in time_types:
            epics_ts = self.epics_timestamp
            dbr_data.secondsSinceEpoch, dbr_data.nanoSeconds = epics_ts

    @property
    def epics_timestamp(self):
        'EPICS timestamp as (seconds, nanoseconds) since EPICS epoch'
        return timestamp_to_epics(self.timestamp)

    def __len__(self):
        try:
            return len(self.value)
        except TypeError:
            return 1

    def check_access(self, sender_address):
        print('{} has full access to {}'.format(sender_address, self))
        return 3  # read-write


class DatabaseRecordEnum(DatabaseRecordBase):
    data_type = ChType.ENUM

    def __init__(self, *, strs=None, **kwargs):
        self.strs = strs

        super().__init__(**kwargs)

    @property
    def no_str(self):
        return len(self.strs) if self.strs else 0

    def convert_to(self, to_dtype):
        if native_type(to_dtype) == ChType.STRING:
            return [bytes(str(self.value), ENCODING)]
        else:
            return [self.strs.index(self.value)]


class DatabaseRecordNumeric(DatabaseRecordBase):
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


class DatabaseRecordInteger(DatabaseRecordNumeric):
    data_type = ChType.LONG


class DatabaseRecordDouble(DatabaseRecordNumeric):
    data_type = ChType.DOUBLE

    def __init__(self, *, precision=0, **kwargs):
        super().__init__(**kwargs)

        self.precision = precision
