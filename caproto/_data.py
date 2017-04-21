import time
from ._dbr import (DBR_LONG, DBR_ENUM, DBR_DOUBLE,
                   DBR_TYPES, ChType, promote_type,
                   native_type, native_float_types,
                   native_int_types)

# it's all about data
ENCODING = 'latin-1'


# TODO these aren't really records. what were you thinking?
class DatabaseRecordBase:
    data_type = DBR_LONG.DBR_ID

    def __init__(self, *, timestamp=None, status=0, severity=0, value=None):
        self._dirty = True
        self._dirty_attrs = set()

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
        # TODO it may be wise to rethink the DBR types to store the array of values
        # from the outset

    def convert_to(self, to_dtype):
        # this leaves a lot to be desired
        values = self.value
        from_dtype = self._data_type
        if from_dtype == to_dtype and self.data_type != ChType.ENUM:
            try:
                len(values)
            except TypeError:
                return (values, )
            else:
                return values

        # TODO metadata is expected to be of this type as well!
        native_to = native_type(to_dtype)

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
        if type_ in self._data:
            if self._dirty:
                # for attr in dirty_attrs... do custom dbr updating
                for chtype, dbr_data in self._data.items():
                    if chtype == 'native':
                        # remaining values to ctypes array
                        # self._data[native] = values[1:]
                        pass
                    else:
                        # note that this is too generic to be useful, there
                        # should be custom handling for each dbr field as
                        # necessary
                        for attr, _ in dbr_data._fields_:
                            if hasattr(self, attr):
                                value = getattr(self, attr)
                                if isinstance(value, str):
                                    value = bytes(value, ENCODING)
                                setattr(dbr_data, attr, value)
                            else:
                                print('missing', attr)
            return self._data[type_], self._data['native']
        else:
            # non-standard type request. frequent ones probably should be
            # cached?
            dbr_data = DBR_TYPES[type_]
            for attr, _ in dbr_data._fields_:
                setattr(dbr_data, getattr(self, attr))
            return dbr_data, self.convert_to(type_)

    def __len__(self):
        try:
            return len(self.value)
        except TypeError:
            return 1

    def check_access(self, sender_address):
        print('{} has full access to {}'.format(sender_address, self))
        return 3  # read-write


class DatabaseRecordEnum(DatabaseRecordBase):
    data_type = DBR_ENUM.DBR_ID

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
    data_type = DBR_LONG.DBR_ID


class DatabaseRecordDouble(DatabaseRecordNumeric):
    data_type = DBR_DOUBLE.DBR_ID

    def __init__(self, *, precision=0, **kwargs):
        super().__init__(**kwargs)

        self.precision = precision
