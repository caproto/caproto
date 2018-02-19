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
                        'get put startup attr name dtype value alarm_group doc')):
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


class SubGroup:
    'A property-like descriptor for specifying a subgroup in a PVGroup'

    def __init__(self, group_cls=None, *, prefix=None, macros=None,
                 attr_separator=None, doc=None):
        self.attr_name = None  # to be set later
        self.group_cls = group_cls
        self.prefix = prefix
        self.macros = macros if macros is not None else {}
        self.attr_separator = (attr_separator if attr_separator is not None
                               else getattr(group_cls, 'attr_separator', ':'))
        if doc is None and group_cls is not None:
            doc = group_cls.__doc__

        self.__doc__ = doc

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
        if self.__doc__ is None:
            self.__doc__ = group_cls.__doc__

        return self


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
                              default=PVGroupBase.default_values[return_type],
                              annotation=return_type),
        ]

    def _class_from_pvspec(self, pvspec):
        def get_pvproperty(pvspec):
            prop = pvproperty()
            prop.pvspec = pvspec
            return prop

        dct = {
            pvspec.attr: get_pvproperty(pvspec)
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

        return type(self.attr_name, (PVGroupBase, ), dct)

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
        if self.attr_name is not None and self.attr_name != name:
            # TODO: IPython ends up calling this multiple times when
            # introspecting a PVGroup. This should be investigated as I'm
            # likely doing something dumb...
            raise AttributeError('Stop it, IPython')

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
                if value.attr_name is None:
                    # this happens in the case of PVFunctions...
                    value.__set_name__(None, attr)
                subgroup_cls = value.group_cls
                if subgroup_cls is None:
                    raise RuntimeError('Internal error; subgroup class unset?')
                for sub_attr, value in subgroup_cls._pvs_.items():
                    yield '.'.join([attr, sub_attr]), value

    def __new__(metacls, name, bases, dct):
        dct['_subgroups_'] = subgroups = OrderedDict()
        for attr, prop in metacls.find_subgroups(dct):
            logger.debug('class %s attr %s: %r', name, attr, prop)
            subgroups[attr] = prop

            # TODO a bit messy
            # propagate subgroups-of-subgroups to the top
            subgroup_cls = prop.group_cls
            if hasattr(subgroup_cls, '_subgroups_'):
                for subattr, subgroup in subgroup_cls._subgroups_.items():
                    subgroups['.'.join((attr, subattr))] = subgroup

        dct['_pvs_'] = pvs = OrderedDict()
        for attr, prop in metacls.find_pvproperties(dct):
            logger.debug('class %s attr %s: %r', name, attr, prop)
            pvs[attr] = prop

        return super().__new__(metacls, name, bases, dct)


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

            self.groups[attr] = subgroup_cls(prefix=prefix, macros=macros)

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
