import logging
import inspect
from collections import (namedtuple, OrderedDict, defaultdict)
from types import MethodType

from .. import (ChannelDouble, ChannelInteger, ChannelString,
                ChannelAlarm)


logger = logging.getLogger(__name__)


class PvpropertyData:
    def __init__(self, *, group, pvspec, **kwargs):
        self.group = group
        self.pvspec = pvspec
        self.getter = (MethodType(pvspec.get, group)
                       if pvspec.get is not None
                       else group.group_read)
        self.putter = (MethodType(pvspec.put, group)
                       if pvspec.put is not None
                       else group.group_write)
        super().__init__(**kwargs)

    async def read(self, data_type):
        value = await self.getter(self)
        if value is not None:
            if self.pvspec.get is None:
                logger.debug('group read value for %s updated: %r',
                             self.pvspec, value)
            else:
                logger.debug('value for %s updated: %r', self.pvspec, value)
            # update the internal state
            await self.write(value)
        return await self._read(data_type)

    async def verify_value(self, value):
        if self.pvspec.put is None:
            logger.debug('group verify value for %s: %r', self.pvspec, value)
        else:
            logger.debug('verify value for %s: %r', self.pvspec, value)
        return await self.putter(self, value)


class PvpropertyInteger(PvpropertyData, ChannelInteger):
    ...


class PvpropertyDouble(PvpropertyData, ChannelDouble):
    ...


class PvpropertyString(PvpropertyData, ChannelString):
    ...


class PVSpec(namedtuple('PVSpec',
                        'get put attr name dtype value alarm_group')):
    'PV information specification'
    __slots__ = ()
    default_dtype = int

    def __new__(cls, get=None, put=None, attr=None, name=None, dtype=None,
                value=None, alarm_group=None):
        if dtype is None:
            dtype = (type(value[0]) if value is not None
                     else cls.default_dtype)

        if get is not None:
            assert inspect.iscoroutinefunction(get), 'required async def get'
            sig = inspect.signature(get)
            try:
                sig.bind('group', 'instance')
            except Exception as ex:
                raise RuntimeError('Invalid signature for getter {}: {}'
                                   ''.format(get, sig))

        if put is not None:
            assert inspect.iscoroutinefunction(put), 'required async def put'
            sig = inspect.signature(put)
            try:
                sig.bind('group', 'instance', 'value')
            except Exception as ex:
                raise RuntimeError('Invalid signature for putter {}: {}'
                                   ''.format(put, sig))

        return super().__new__(cls, get, put, attr, name, dtype, value,
                               alarm_group)

    def new_names(self, attr=None, name=None):
        if attr is None:
            attr = self.attr
        if name is None:
            name = self.name
        return PVSpec(self.get, self.put, attr, name, self.dtype, self.value,
                      self.alarm_group)


class pvproperty:
    'A property-like descriptor for specifying a PV in a group'

    def __init__(self, get=None, put=None, **spec_kw):
        self.attr_name = None  # to be set later
        self.spec_kw = spec_kw
        self.pvspec = PVSpec(get=get, put=put, **spec_kw)

    def __get__(self, instance, owner):
        if instance is None:
            return self.pvspec
        return instance.attr_pvdb[self.attr_name]

    def __set__(self, instance, value):
        instance.attr_pvdb[self.attr_name] = value

    def __delete__(self, instance):
        del instance.attr_pvdb[self.attr_name]

    def __set_name__(self, owner, name):
        self.attr_name = name
        # update the PV specification with the attribute name
        self.pvspec = self.pvspec.new_names(
            self.attr_name,
            self.pvspec.name
            if self.pvspec.name is not None
            else self.attr_name)

    def putter(self, put):
        # update PVSpec with putter
        self.pvspec = PVSpec(self.pvspec.get, put, *self.pvspec[2:])
        return self

    def __call__(self, get, put=None):
        # handles case where pvproperty(**spec_kw)(getter, putter) is used
        self.pvspec = PVSpec(get, put, **self.spec_kw)
        return self


class SubGroup:
    'A property-like descriptor for specifying a subgroup in a PVGroup'

    def __init__(self, group_cls=None, prefix=None, macros=None,
                 attr_separator=None):
        self.attr_name = None  # to be set later
        self.group_cls = group_cls
        self.prefix = prefix
        self.macros = macros if macros is not None else {}
        self.attr_separator = (attr_separator if attr_separator is not None
                               else getattr(group_cls, 'attr_separator', ':'))

    def __get__(self, instance, owner):
        if instance is None:
            return self
        return instance.groups[self.attr_name]

    def __set__(self, instance, value):
        instance.groups[self.attr_name] = value

    def __delete__(self, instance):
        del instance.groups[self.attr_name]

    def __set_name__(self, owner, name):
        self.attr_name = name
        if self.prefix is None:
            self.prefix = name + self.attr_separator

    def __call__(self, group_cls):
        # handles case where SubGroup(**kw)(group_cls) is used
        self.group_cls = group_cls
        return self


def expand_macros(pv, macros):
    'Expand a PV name with Python {format-style} macros'
    return pv.format(**macros)


class PVGroupMeta(type):
    'Metaclass that finds all pvproperties'
    @classmethod
    def __prepare__(self, name, bases):
        # keep class dictionary items in order
        return OrderedDict()

    @staticmethod
    def find_subgroups(dct):
        for attr, value in dct.items():
            if attr.startswith('_'):
                continue

            if isinstance(value, SubGroup):
                yield attr, value

    @staticmethod
    def find_pvproperties(dct):
        for attr, value in dct.items():
            if attr.startswith('_'):
                continue

            if isinstance(value, pvproperty):
                yield attr, value
            elif isinstance(value, SubGroup):
                subgroup_cls = value.group_cls
                for sub_attr, value in subgroup_cls.__pvs__.items():
                    yield '.'.join([attr, sub_attr]), value

    def __new__(metacls, name, bases, dct):
        dct['__subgroups__'] = subgroups = OrderedDict()
        for attr, prop in metacls.find_subgroups(dct):
            logger.debug('class %s attr %s: %r', name, attr, prop)
            subgroups[attr] = prop

            # TODO a bit messy
            # propagate subgroups-of-subgroups to the top
            subgroup_cls = prop.group_cls
            if hasattr(subgroup_cls, '__subgroups__'):
                for subattr, subgroup in subgroup_cls.__subgroups__.items():
                    subgroups['.'.join((attr, subattr))] = subgroup

        dct['__pvs__'] = pvs = OrderedDict()
        for attr, prop in metacls.find_pvproperties(dct):
            logger.debug('class %s attr %s: %r', name, attr, prop)
            pvs[attr] = prop

        cls = super().__new__(metacls, name, bases, dct)

        for attr, prop in metacls.find_subgroups(dct):
            if prop.attr_name is None:
                # note: for python < 3.6
                subgroups[attr].__set_name__(attr, cls)
        for attr, prop in metacls.find_pvproperties(dct):
            if prop.attr_name is None:
                # note: for python < 3.6
                pvs[attr].__set_name__(attr, cls)

        return cls


def channeldata_from_pvspec(group, pvspec):
    'Create a ChannelData instance based on a PVSpec'
    full_pvname = expand_macros(group.prefix + pvspec.name, group.macros)
    value = (pvspec.value
             if pvspec.value is not None
             else group.default_values[pvspec.dtype]
             )

    cls = group.type_map[pvspec.dtype]
    inst = cls(group=group, pvspec=pvspec,
               value=value, alarm=group.alarms[pvspec.alarm_group])
    return (full_pvname, inst)


class PVGroupBase(metaclass=PVGroupMeta):
    'Base class for a group of PVs'
    type_map = {
        str: PvpropertyString,
        int: PvpropertyInteger,
        float: PvpropertyDouble,
    }

    default_values = {
        str: '-',
        int: 0,
        float: 0.0,
    }

    def __init__(self, prefix, macros=None):
        self.macros = macros if macros is not None else {}
        self.prefix = expand_macros(prefix, self.macros)
        self.alarms = defaultdict(lambda: ChannelAlarm())
        self.pvdb = OrderedDict()
        self.attr_pvdb = OrderedDict()
        self.groups = OrderedDict()
        self._create_pvdb()

    def _create_pvdb(self):
        'Create the PV database for all subgroups and pvproperties'
        for attr, subgroup in self.__subgroups__.items():
            subgroup_cls = subgroup.group_cls

            prefix = (subgroup.prefix if subgroup.prefix is not None
                      else subgroup.prefix)
            prefix = self.prefix + prefix

            macros = dict(self.macros)
            macros.update(subgroup.macros)

            self.groups[attr] = subgroup_cls(prefix=prefix, macros=macros)

        for attr, pvprop in self.__pvs__.items():
            if '.' in attr:
                group_attr, _ = attr.rsplit('.', 1)
                group = self.groups[group_attr]
            else:
                group = self

            pvname, channeldata = channeldata_from_pvspec(group, pvprop.pvspec)

            # full pvname -> ChannelData instance
            self.pvdb[pvname] = channeldata

            # attribute -> PV instance mapping for quick access by pvproperty
            self.attr_pvdb[attr] = channeldata

    async def group_read(self, instance):
        'Generic read called for channels without `get` defined'
        logger.debug('no-op group read of %s', instance.pvspec.attr)

    async def group_write(self, instance, value):
        'Generic write called for channels without `put` defined'
        logger.debug('group write of %s = %s', instance.pvspec.attr, value)
        return value
