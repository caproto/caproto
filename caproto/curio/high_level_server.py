import copy
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
        if pvspec.startup is not None:
            # enable the startup hook for this instance only:
            self.server_startup = self._server_startup
            # bind the startup method to the group (used in server_startup)
            self.startup = MethodType(pvspec.startup, group)

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

    async def _server_startup(self, async_lib):
        return await self.startup(self, async_lib)


class PvpropertyInteger(PvpropertyData, ChannelInteger):
    ...


class PvpropertyDouble(PvpropertyData, ChannelDouble):
    ...


class PvpropertyString(PvpropertyData, ChannelString):
    ...


class PVSpec(namedtuple('PVSpec',
                        'get put startup attr name dtype value '
                        'alarm_group doc')):
    'PV information specification'
    __slots__ = ()
    default_dtype = int

    def __new__(cls, get=None, put=None, startup=None, attr=None, name=None,
                dtype=None, value=None, alarm_group=None, doc=None):
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

        if startup is not None:
            assert inspect.iscoroutinefunction(startup), 'required async def startup'
            sig = inspect.signature(startup)
            try:
                sig.bind('group', 'instance', 'async_library')
            except Exception as ex:
                raise RuntimeError('Invalid signature for startup {}: {}'
                                   ''.format(startup, sig))

        return super().__new__(cls, get, put, startup, attr, name, dtype,
                               value, alarm_group, doc)

    def new_names(self, attr=None, name=None):
        if attr is None:
            attr = self.attr
        if name is None:
            name = self.name
        return PVSpec(self.get, self.put, self.startup, attr, name, self.dtype,
                      self.value, self.alarm_group, self.doc)


class pvproperty:
    'A property-like descriptor for specifying a PV in a group'

    def __init__(self, get=None, put=None, startup=None, *, doc=None,
                 **spec_kw):
        self.attr_name = None  # to be set later
        self.spec_kw = spec_kw

        if doc is None and get is not None:
            doc = get.__doc__

        self.pvspec = PVSpec(get=get, put=put, startup=startup, doc=doc,
                             **spec_kw)
        self.__doc__ = doc

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

    def getter(self, get):
        # update PVSpec with getter
        self.pvspec = PVSpec(get, *self.pvspec[1:])
        return self

    def putter(self, put):
        # update PVSpec with putter
        self.pvspec = PVSpec(self.pvspec.get, put, *self.pvspec[2:])
        return self

    def startup(self, startup):
        # update PVSpec with startup function
        self.pvspec = PVSpec(self.pvspec.get, self.pvspec.put, startup,
                             *self.pvspec[3:])
        return self

    def __call__(self, get, put=None, startup=None):
        # handles case where pvproperty(**spec_kw)(getter, putter, startup) is used
        if get.__doc__:
            if self.__doc__ is None:
                self.__doc__ = get.__doc__
            if 'doc' not in self.spec_kw:
                self.spec_kw['doc'] = get.__doc__

        self.pvspec = PVSpec(get, put, startup, **self.spec_kw)
        return self

    @classmethod
    def from_pvspec(cls, pvspec):
        prop = cls()
        prop.pvspec = pvspec
        return prop


class NestedPvproperty(pvproperty):
    '''Nested pvproperty which allows decorator usage in parent class

    Without using this for the SubGroups, using @subgroup.prop.getter causes
    the parent class to see multiple pvproperties - one defined on the
    subgroup, and one returned from pvproperty.getter. This class fixes that by
    returning the expected class - the parent (i.e., the subgroup)

    Bonus points if you understood all of that.
        ... scratch that, bonus points to me, I think.
    '''

    def getter(self, get):
        super().getter(get)
        return self.parent

    def putter(self, put):
        super().putter(put)
        return self.parent

    def startup(self, startup):
        super().startup(startup)
        return self.parent

    @classmethod
    def from_pvspec(cls, pvspec, parent):
        prop = super().from_pvspec(pvspec)
        prop.parent = parent
        return prop


class SubGroup:
    'A property-like descriptor for specifying a subgroup in a PVGroup'

    # support copy.copy by keeping this here
    _class_dict = None

    def __init__(self, group=None, *, prefix=None, macros=None,
                 attr_separator=None, doc=None, base=None):
        self.attr_name = None  # to be set later
        self._class_dict = None
        self._decorated_items = None
        self.group_cls = None
        self.prefix = prefix
        self.macros = macros if macros is not None else {}
        self.attr_separator = attr_separator
        self.base = (PVGroup, ) if base is None else base
        self.__doc__ = doc

        if isinstance(group, dict):
            # set the group dictionary last:
            self.group_dict = group
        elif group is not None:
            self.group_cls = group

    def __get__(self, instance, owner):
        if instance is None:
            return self
        return instance.groups[self.attr_name]

    def __set__(self, instance, value):
        instance.groups[self.attr_name] = value

    def __delete__(self, instance):
        del instance.groups[self.attr_name]

    @staticmethod
    def _pvspec_from_info(attr, info):
        if isinstance(info, dict):
            if 'attr' not in info:
                info['attr'] = attr
            return PVSpec(**info)
        elif isinstance(info, PVSpec):
            return info
        elif isinstance(info, pvproperty):
            return info.pvspec
        else:
            raise TypeError(f'Unknown type for pvspec: {info!r}')

    def _generate_class_dict(self):
        pvspecs = [self._pvspec_from_info(attr, pvspec)
                   for attr, pvspec in self._group_dict.items()]

        return {pvspec.attr: NestedPvproperty.from_pvspec(pvspec, self)
                for pvspec in pvspecs
                }

    @property
    def group_dict(self):
        return self._group_dict

    @group_dict.setter
    def group_dict(self, group_dict):
        if group_dict is None:
            return

        self._group_dict = group_dict
        self._class_dict = self._generate_class_dict()

        bad_items = set(group_dict).intersection(set(dir(self)))
        if bad_items:
            raise ValueError(f'Cannot use these attribute names: {bad_items}')

    def __call__(self, group=None, *, prefix=None, macros=None, doc=None):
        # handles case where a single definition is used multiple times
        # as in SubGroup(**kw)(group_cls_or_dict) is used
        copied = copy.copy(self)

        # TODO verify the following works (or even makes sense)
        if prefix is not None:
            copied.prefix = prefix

        if macros is not None:
            copied.macros = macros

        if doc is not None:
            copied.__doc__ = doc

        if isinstance(group, dict):
            copied.group_dict = group
        elif group is not None:
            copied.group_cls = group

        if copied.attr_separator is None:
            copied.attr_separator = getattr(copied.group_cls,
                                            'attr_separator', ':')

        return copied

    def __set_name__(self, owner, name):
        self.attr_name = name
        if self.group_cls is None:
            # generate the group class, in the case of a dict-based subgroup
            self.group_cls = type(self.attr_name, self.base, self._class_dict)

            if self.__doc__ is None:
                self.__doc__ = self.group_cls.__doc__

        attr_separator = getattr(self.group_cls, 'attr_separator', ':')
        if attr_separator is not None and self.attr_separator is None:
            self.attr_separator = attr_separator

        if self.prefix is None:
            self.prefix = name + self.attr_separator

    def __getattr__(self, attr):
        if self._class_dict is not None and attr in self._class_dict:
            return self._class_dict[attr]
        return super().__getattribute__(attr)


def get_pv_pair_wrapper(setpoint_suffix='', readback_suffix='_RBV'):
    'Generates a Subgroup class for a pair of PVs (setpoint and readback)'
    def wrapped(dtype=int, doc=None, **kwargs):
        return SubGroup(
            {'setpoint': dict(dtype=dtype, name=setpoint_suffix, doc=doc),
             'readback': dict(dtype=dtype, name=readback_suffix, doc=doc),
             },
            attr_separator='',
            doc=doc,
        )
    return wrapped


class pvfunction(SubGroup):
    default_names = dict(process='Process',
                         retval='Retval',
                         status='Status',
                         )

    def __init__(self, func=None, default=None, names=None, alarm_group=None,
                 prefix=None, macros=None, attr_separator=None, doc=None):

        '''
        A descriptor for making an RPC-like function

        Note: Requires Python type hinting for all arguments to the function
        and its return value. These are used to generate the PVs.

        Parameters
        ----------
        func : async callable, optional
            The function to wrap
        default : any, optional
            Default value for the return value
        names : dict, optional
            Valid keys include {'process', 'retval', 'status'} and also any
            function argument names. This will map attributes of the
            dynamically-generated PVGroup that this pvfunction represents to
            EPICS PV names.
        alarm_group : str, optional
            The alarm group name this group should be associated with
        prefix : str, optional
            The prefix for all PVs
        macros : dict, optional
            Macro dictionary for PVs
        attr_separator : str, optional
            String separator between {prefix} and {attribute} for generated PV
            names.
        doc : str, optional
            Docstring
        '''

        super().__init__(group_cls=None,
                         prefix=prefix, macros=macros,
                         attr_separator=attr_separator,
                         doc=doc)
        self.default_retval = default
        self.func = func
        self.alarm_group = alarm_group
        if names is None:
            names = self.default_names
        self.names = {k: names.get(k, self.default_names[k])
                      for k in self.default_names}
        self.pvspec = []
        self.__doc__ = doc

    def __call__(self, func):
        # handles case where pvfunction()(func) is used
        self.func = func
        self._regenerate()
        return self

    def pvspec_from_parameter(self, param, doc=None):
        dtype = param.annotation
        default = param.default

        try:
            default[0]
        except TypeError:
            default = [default]
        except Exception:
            raise ValueError(f'Invalid default value for parameter {param}')
        else:
            # ensure we copy any arrays as default parameters, lest we give
            # some developers a heart attack
            default = list(default)

        return PVSpec(
            get=None, put=None, attr=param.name,
            # the name defaults to the parameter name, but can be remapped with
            # the 'names' dictionary
            name=self.names.get(param.name, param.name),
            dtype=dtype,
            value=default, alarm_group=self.alarm_group,
            doc=doc if doc is not None else f'Parameter {dtype} {param.name}'
        )

    def get_additional_parameters(self):
        sig = inspect.signature(self.func)
        return_type = sig.return_annotation
        assert return_type, 'Return value must have a type annotation'

        return [
            inspect.Parameter(self.names['status'], kind=0, default=['Init'],
                              annotation=str),
            inspect.Parameter(self.names['retval'], kind=0,
                              # TODO?
                              default=PVGroup.default_values[return_type],
                              annotation=return_type),
        ]

    def _class_from_pvspec(self, pvspec):
        dct = {
            pvspec.attr: pvproperty.from_pvspec(pvspec)
            for pvspec in self.pvspec
        }

        # handle process specially
        process_pvspec = self.pvspec_from_parameter(
            inspect.Parameter(self.names['process'], kind=0, default=0,
                              annotation=int)
        )

        dct[process_pvspec.attr] = process_prop = pvproperty()

        async def do_process(group, instance, value):
            try:
                sig = inspect.signature(self.func)
                kwargs = {sig.name: getattr(group, sig.name).value
                          for sig in list(sig.parameters.values())[1:]
                          }
                value = await self.func(group, **kwargs)
                await group.Retval.write(value)
                await group.Status.write(f'Success')
            except Exception as ex:
                await group.Status.write(f'{ex.__class__.__name__}: {ex}')
                raise

        process_prop.pvspec = PVSpec(None, do_process, *process_pvspec[2:])
        return type(self.attr_name, (PVGroup, ), dct)

    def _regenerate(self):
        if self.func is None or self.attr_name is None:
            return []

        if self.alarm_group is None:
            self.alarm_group = self.func.__name__

        if self.__doc__ is None:
            self.__doc__ = self.func.__doc__

        sig = inspect.signature(self.func)
        parameters = list(sig.parameters.values())[1:]  # skip 'self'
        parameters.extend(self.get_additional_parameters())
        self.pvspec = [self.pvspec_from_parameter(param)
                       for param in parameters]

        # how about an auto-generated meta-class subclass in your subgroup
        # descriptor? (cc @tacaswell)
        self.group_cls = self._class_from_pvspec(self.pvspec)

    def __set_name__(self, owner, name):
        self.attr_name = name
        if self.prefix is None:
            self.prefix = name + self.attr_separator
        self._regenerate()


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
                if subgroup_cls is None:
                    raise RuntimeError('Internal error; subgroup class unset?')
                for sub_attr, value in subgroup_cls._pvs_.items():
                    yield '.'.join([attr, sub_attr]), value

    def __new__(metacls, name, bases, dct):
        dct['_subgroups_'] = subgroups = OrderedDict()
        dct['_pvs_'] = pvs = OrderedDict()

        cls = super().__new__(metacls, name, bases, dct)

        for attr, prop in metacls.find_subgroups(dct):
            logger.debug('class %s subgroup attr %s: %r', name, attr, prop)
            subgroups[attr] = prop

            # TODO a bit messy
            # propagate subgroups-of-subgroups to the top
            subgroup_cls = prop.group_cls
            if hasattr(subgroup_cls, '_subgroups_'):
                for subattr, subgroup in subgroup_cls._subgroups_.items():
                    subgroups['.'.join((attr, subattr))] = subgroup

        for attr, prop in metacls.find_pvproperties(dct):
            logger.debug('class %s pvproperty attr %s: %r', name, attr, prop.pvspec)
            pvs[attr] = prop

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
    inst.__doc__ = pvspec.doc
    return (full_pvname, inst)


class PVGroup(metaclass=PVGroupMeta):
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

    def __init__(self, prefix, *, macros=None, parent=None):
        self.parent = parent
        self.macros = macros if macros is not None else {}
        self.prefix = expand_macros(prefix, self.macros)
        self.alarms = defaultdict(lambda: ChannelAlarm())
        self.pvdb = OrderedDict()
        self.attr_pvdb = OrderedDict()
        self.attr_to_pvname = OrderedDict()
        self.groups = OrderedDict()
        self._create_pvdb()

    def _create_pvdb(self):
        'Create the PV database for all subgroups and pvproperties'
        for attr, subgroup in self._subgroups_.items():
            subgroup_cls = subgroup.group_cls

            prefix = (subgroup.prefix if subgroup.prefix is not None
                      else subgroup.attr_name)
            prefix = self.prefix + prefix

            macros = dict(self.macros)
            macros.update(subgroup.macros)

            self.groups[attr] = subgroup_cls(prefix=prefix, macros=macros,
                                             parent=self)

        for attr, pvprop in self._pvs_.items():
            if '.' in attr:
                group_attr, sub_attr = attr.rsplit('.', 1)
                group = self.groups[group_attr]
                channeldata = group.attr_pvdb[sub_attr]
                pvname = group.attr_to_pvname[sub_attr]
            else:
                group = self
                pvname, channeldata = channeldata_from_pvspec(group,
                                                              pvprop.pvspec)

            if pvname in self.pvdb:
                first_seen = self.pvdb[pvname]
                if hasattr(first_seen, 'pvspec'):
                    first_seen = first_seen.pvspec.attr
                raise RuntimeError(f'{pvname} defined multiple times: '
                                   f'now in attr: {attr} '
                                   f'originally: {first_seen}')

            # full pvname -> ChannelData instance
            self.pvdb[pvname] = channeldata

            # attribute -> PV instance mapping for quick access by pvproperty
            self.attr_pvdb[attr] = channeldata

            # and a convenient map of attr -> pvname
            self.attr_to_pvname[attr] = pvname
            # TODO maybe this could all be simplified?

    async def group_read(self, instance):
        'Generic read called for channels without `get` defined'
        logger.debug('no-op group read of %s', instance.pvspec.attr)

    async def group_write(self, instance, value):
        'Generic write called for channels without `put` defined'
        logger.debug('group write of %s = %s', instance.pvspec.attr, value)
        return value
