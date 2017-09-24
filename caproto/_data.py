from functools import partial
import time

# TODO: assuming USE_NUMPY for now
import numpy as np

from ._dbr import (DBR_TYPES, ChType, promote_type, native_type,
                   native_float_types, native_int_types, native_types,
                   timestamp_to_epics, time_types, MAX_ENUM_STRING_SIZE,
                   DBR_STSACK_STRING, AccessRights, _numpy_map,
                   SubscriptionType, graphical_types)


class Forbidden(Exception):
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
        """
        Parameters
        ----------
        status : ca.AlarmStatus, optional
            Alarm status
        severity : ca.AlarmSeverity, optional
            Alarm severity
        """
        dbr = DBR_STSACK_STRING()
        self._dbr = dbr
        self._string_encoding = string_encoding
        self._channels = []
        self._update_channel = {}
        self.write(status=status, severity=severity,
                   acknowledge_transient=acknowledge_transient,
                   acknowledge_severity=acknowledge_severity,
                   alarm_string=alarm_string)

    status = property(lambda: self.dbr.status)
    severity = property(lambda: self.dbr.severity)
    acknowledge_transient = property(lambda: self.dbr.acknowledge_transient)
    acknowledge_severity = property(lambda: self.dbr.status)
    alarm_string = property(lambda: self.dbr.alarm_string)

    def __repr__(self):
        # TODO
        ...

    def connect(self, channel_data):
        self._channels.append(channel_data)
        # Obtain from ChannelData a write method that
        # will not propagate the change back to this alarm,
        # avoiding an infinite loop.
        func = channel_data.connect(self)
        self._update_channel[channel_data] = func
        # Hand ChannelData a write method that will skip
        # propagating the change to itself, avoiding an
        # infinite loop.
        return partial(self._write, caller=channel_data)

    def disconnect(self, channel_data):
        self._channels.remove(channel_data)
        self._update_channel.pop(channel_data)

    def acknowledge(self):
        # TODO
        pass

    async def read(self):
       return self._dbr

    async def write(self, status=None, severity=None,
              acknowledge_transient=None,
              acknowledge_severity=None,
              alarm_string=None):
       # Call _write in such a way that all connected channels
       # are updated.
       await self._write(status=status, severity=severity,
                         acknowledge_transient=acknowledge_transient,
                         acknowledge_severity=acknowledge_severity,
                         alarm_string=alarm_string,
                         caller=None)

    async def _write(self, status=None, severity=None,
              acknowledge_transient=None,
              acknowledge_severity=None,
              alarm_string=None, caller=None):
        if status is not None:
            self.dbr.status = status
        if severity is not None:
            self.dbr.severity = severity
        if acknowledge_transient is not None:
            self.dbr.ackt = 1 if acknowledge_transient else 0
        if acknowledge_severity is not None:
            self.dbr.acks = acknowledge_severity
        if alarm_string is not None:
            self.dbr.alarm_string = alarm_string.encode(self.string_encoding)
        for channel in self._channels:
            # Avoid infinite loop.
            if channel is caller:
                continue
            func = self._update_channel[channel]
            await func(status=status, severity=severity,
                       acknowledge_transient=acknowledge_transient,
                       acknowledge_severity=acknowledge_severity,
                       alarm_string=alarm_string)

class ChannelData:
    CONVERT_ATTRS = ()
    # subclass must define a `data_type` class attribute, set to a value of the
    # ChType enum

    def __init__(self, *, alarm=None, string_encoding='latin-1',
                 reported_record_type='caproto', **kwargs):
        '''Metadata and Data for a single caproto Channel

        Parameters
        ----------
        alarm : ChannelAlarm, optional
            Optionally specify an allocated alarm, which could be shared
            among several channels. If None (default), a ChannelAllarm
            instance will be created using its default parameters.
        string_encoding : str, optional
            Encoding to use for strings, used both in and out
        reported_record_type : str, optional
            Though this is not a record, the channel access protocol supports
            querying the record type.  This can be set to mimic an actual
            record or be set to something arbitrary.
            Defaults to 'caproto'
        '''
        if alarm is None:
            alarm = ChannelAlarm()
        self.update_alarm = alarm.connect(self)
        self.alarm = alarm
        self.string_encoding = string_encoding
        self.reported_record_type = reported_record_type
        self._subscription_queue = None
        # self.data_type is set as a class attribute on subclasses
        self._dbr = DBR_TYPES[promote_type(self.data_type, use_gr=True)]()
        # cache of DBR_* structs, filled on demand
        self._dbr_variants = {}
        self._stale = {}
        self.write(hostname=None, username=None, **kwargs)

    def subscribe(self, queue, *sub_queue_args):
        '''Set subscription queue'''
        self._subscription_queue = queue
        self._subscription_queue_args = sub_queue_args

    async def read(self, hostname, username, data_type, data_count=None):
        '''Get DBR data and native data, converted to a specific type'''
        access = self.check_access(hostname, username)
        if access not in (AccessRights.READ, AccessRights.READ_WRITE):
            raise Forbidden("Client with hostname {} and username {} "
                            "does not have permission to read."
                            "".format(hostname, username))

        # special cases for alarm strings and class name
        if data_type == ChType.STSACK_STRING:
            ret = await self.alarm.read()
            return (ret, b'')
        elif data_type == ChType.CLASS_NAME:
            class_name = DBR_TYPES[data_type]()
            rtyp = self.reported_record_type.encode(self.string_encoding)
            class_name.value = rtyp
            return class_name, b''

        native_to = native_type(data_type)
        data = convert_values(values=self.data, from_dtype=self.data_type,
                              to_dtype=native_to,
                              string_encoding=self.string_encoding,
                              enum_strings=getattr(self, 'enum_strings', None))

        # TODO Do something with data_count
        if data_count is not None:
            raise NotImplementedError("cannot handle non-default data_count")

        # for native types, there is no dbr metadata - just data
        if data_type in native_types:
            return b'', data

        if data_type in graphical_types:
            return self._dbr, data
        else:
            # Pack the metadata into a different struct.
            try:
                variant = self._dbr_variants[data_type]
            except KeyError:
                # There are two kinds of reuse here. We can reuse the data
                # until the next write makes it stale. We can reuse the
                # struct that holds the data forever.
                variant = DBR_TYPES[data_type]()
                self._dbr_variants[data_type] = variant  # cache for reuse
                self._stale[data_type] = True

            if self._stale[data_type]:
                dbr = self._dbr
                for field in variant._fields_:



        # # convert all metadata types to the target type
        # values = convert_values(values=[getattr(self, key, 0)
        #                                 for key in convert_attrs],
        #                         from_dtype=self.data_type,
        #                         to_dtype=native_type(to_type),
        #                         string_encoding=self.string_encoding)
        # if isinstance(values, np.ndarray):
        #     values = values.tolist()
        # for attr, value in zip(convert_attrs, values):
        #     if hasattr(dbr_metadata, attr):
        #         setattr(dbr_metadata, attr, value)


                    setattr(variant, field, getattr(dbr, field))
                self._stale[data_type] = False
            return variant, data

    def connect(self, alarm):
        return partial(self._write, propagate=False)

    async def write(self, hostname, username, *,
                    data=None, data_type=None, data_count=None,
                    timestamp=None,
                    status=None, severity=None,
                    acknowledge_transient=None,
                    acknowledge_severity=None,
                    alarm_string=None, **kwargs):
        # Call self._write in such a way that the associated
        # alarm is also updated and, subsequently, every other
        # channel connected to the same alarm.
        await self._write(self, propagate=True,
                          hostname=hostname, username=username,
                          data=None, data_type=None, data_count=None,
                          timestamp=None,
                          status=None, severity=None,
                          acknowledge_transient=None,
                          acknowledge_severity=None,
                          alarm_string=None, **kwargs)

    async def _write(self, propagate, hostname, username, *,
                     data=None, data_type=None, data_count=None,
                     timestamp=None, units=None,
                     status=None, severity=None,
                     acknowledge_transient=None,
                     acknowledge_severity=None,
                     alarm_string=None):
        """
        Set data from DBR metadata/values

        Parameters
        ---------
        data : tuple, ``numpy.ndarray``, ``array.array``, or bytes
            Data which has to match with this class's data_type
        data_type : a :class:`DBR_TYPE` or its designation integer ID
        timestamp : float, optional
            Posix timestamp associated with the value
            Defaults to `time.time()`
        """
        if timestamp is None:
            timestamp = time.time()
        access = self.check_access(hostname, username)
        if access not in (AccessRights.WRITE, AccessRights.READ_WRITE):
            raise Forbidden("Client with hostname {} and username {} "
                            "does not have permission to read."
                            "".format(hostname, username))
        for data_type in self._stale:
            self._stale[data_type] = True
        # Has anything to do with the alarm been updated?
        if any(x is not None for x in (status, severity,
                                       acknowledge_transient,
                                       acknowledge_severity,
                                       alarm_string)):
            # Update the alarm, which will in turn write to any
            # other channels with this same alarm and publish
            # the change to any subscriptions they have.
            self.update_alarm(self, status=None, severity=None,
                              acknowledge_transient=None,
                              acknowledge_severity=None,
                              alarm_string=None)
        native_from = native_type(data_type)
        data = convert_values(values=data, from_dtype=native_from,
                              to_dtype=self.data_type,
                              string_encoding=self.string_encoding,
                              enum_strings=getattr(self, 'enum_strings', None))
        dbr = self._dbr
        dbr.value = data
        dbr.secondsSinceEpoch, dbr.nanoSeconds = timestamp_to_epics(timestamp)
        if units is not None:
            dbr.units = units.encode(self.string_encoding)
        
        if self._subscription_queue is not None:
            await self._subscription_queue.put((self,
                                                SubscriptionType.DBE_VALUE,
                                                self.data) +
                                               self._subscription_queue_args)

    def __len__(self):
        try:
            return len(self.data)
        except TypeError:
            return 1

    def check_access(self, hostname, username):
        """
        This always returns AccessRights.READ_WRITE.

        A subclass may override it to return one of
        ``{AccessRights.READ, AccessRights.WRITE, AccessRights.READ_WRITE}``
        based on the given ``hostname`` or ``username``.

        Parameters
        ----------
        hostname : string
            hostname of client requesting to read, subscribe, or write
        username : string
            username of client requesting to read, subscribe, or write

        Returns
        -------
        access : AccessRights.READ_WRITE
        """
        return AccessRights.READ_WRITE

    def __del__(self):
        self.alarm.disconnect(self)


class ChannelEnum(ChannelData):
    data_type = ChType.ENUM

    def __init__(self, *, enum_strings=None, **kwargs):
        super().__init__(**kwargs)

        if enum_strings is None:
            enum_strings = []
        self.enum_strings = enum_strings

    def _copy_metadata_to_dbr(self, dbr_metadata):
        if hasattr(dbr_metadata, 'strs') and self.enum_strings:
            for i, string in enumerate(self.enum_strings):
                bytes_ = bytes(string, self.string_encoding)
                dbr_metadata.strs[i][:] = bytes_.ljust(MAX_ENUM_STRING_SIZE,
                                                       b'\x00')
            dbr_metadata.no_str = len(self.enum_strings)

        return super()._copy_metadata_to_dbr(dbr_metadata)


class ChannelNumeric(ChannelData):
    CONVERT_ATTRS = ('upper_disp_limit', 'lower_disp_limit',
                    'upper_alarm_limit', 'upper_warning_limit',
                    'lower_warning_limit', 'lower_alarm_limit',
                    'upper_ctrl_limit', 'lower_ctrl_limit')

    def _write(self, *,
              upper_disp_limit=None, lower_disp_limit=None,
              upper_alarm_limit=None, upper_warning_limit=None,
              lower_warning_limit=None, lower_alarm_limit=None,
              upper_ctrl_limit=None, lower_ctrl_limit=None,
              **kwargs):

        super().write(**kwargs)
        dbr = self._dbr
        for attr in self.CONVERT_ATTRS:
            val = locals()[attr]
            if val is not None:
                setattr(dbr, attr, val)


class ChannelInteger(ChannelNumeric):
    data_type = ChType.LONG


class ChannelDouble(ChannelNumeric):
    data_type = ChType.DOUBLE

    def _write(self, *, precision=None, **kwargs):
        super()._write(**kwargs)
        if precision is not None:
            self._dbr.precision = precision


class ChannelChar(ChannelNumeric):
    data_type = ChType.CHAR
    # 'Limits' on chars do not make much sense and are rarely used.
    def __init__(self, *args, max_length=100, **kwargs):
        self.max_length = max_length
        super().__init__(*args, **kwargs)


class ChannelString(ChannelData):
    data_type = ChType.STRING
