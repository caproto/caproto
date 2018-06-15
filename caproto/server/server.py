'''
caproto IOC "high-level" server framework

This does not define any wire protocol information or have anything specific to
a single asyncio library.

For an example server implementation, see caproto.curio.server
'''
import argparse
import copy
import logging
import inspect
from collections import (namedtuple, OrderedDict, defaultdict)
import sys
from types import MethodType

from .. import (ChannelDouble, ChannelInteger, ChannelString,
                ChannelEnum, ChannelType, ChannelChar, ChannelAlarm,
                AccessRights, get_server_address_list)

module_logger = logging.getLogger(__name__)


__all__ = ['AsyncLibraryLayer',
           'NestedPvproperty', 'PVGroup', 'PVSpec', 'SubGroup',
           'channeldata_from_pvspec', 'data_class_from_pvspec',
           'expand_macros', 'get_pv_pair_wrapper', 'pvfunction', 'pvproperty',

           'PvpropertyData', 'PvpropertyReadOnlyData',
           'PvpropertyChar', 'PvpropertyCharRO',
           'PvpropertyDouble', 'PvpropertyDoubleRO',
           'PvpropertyEnum', 'PvpropertyEnumRO',
           'PvpropertyInteger', 'PvpropertyIntegerRO',
           'PvpropertyString', 'PvpropertyStringRO',

           'ioc_arg_parser', 'template_arg_parser'
           ]


class AsyncLibraryLayer:
    '''Library compatibility layer

    To be subclassed/customized by async library layer for compatibility Then,
    a single IOC written within the high-level server framework can potentially
    use the same code base and still be run on either curio or trio, etc.
    '''
    name = None
    ThreadsafeQueue = None
    library = None


class PvpropertyData:
    def __init__(self, *, pvname, group, pvspec, doc=None, mock_record=None,
                 logger=None, **kwargs):
        self.pvname = pvname  # the full, expanded PV name
        self.name = f'{group.name}.{pvspec.attr}'
        self.group = group
        self.log = group.log
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

        if doc is not None:
            self.__doc__ = doc

        super().__init__(**kwargs)

        if mock_record is not None:
            from .records import records
            field_class = records[mock_record]
            self.field_inst = field_class(
                prefix='', parent=self,
                name=f'{self.name}.fields')
            self.fields = self.field_inst.pvdb
        else:
            self.field_inst = None
            self.fields = {}

    async def read(self, data_type):
        value = await self.getter(self)
        if value is not None:
            if self.pvspec.get is None:
                self.log.debug('group read value for %s updated: %r',
                               self.name, value)
            else:
                self.log.debug('value for %s updated: %r', self.name, value)
            # update the internal state
            await self.write(value)
        return await self._read(data_type)

    async def verify_value(self, value):
        if self.pvspec.put is None:
            self.log.debug('group verify value for %s: %r', self.name, value)
        else:
            self.log.debug('verify value for %s: %r', self.name, value)
        return await self.putter(self, value)

    async def _server_startup(self, async_lib):
        return await self.startup(self, async_lib)

    def get_field(self, field):
        if not field or field == 'VAL':
            return self
        return self.fields[field]

    def filtered(self, filter):
        return self


class PvpropertyChar(PvpropertyData, ChannelChar):
    ...


class PvpropertyInteger(PvpropertyData, ChannelInteger):
    ...


class PvpropertyDouble(PvpropertyData, ChannelDouble):
    ...


class PvpropertyString(PvpropertyData, ChannelString):
    ...


class PvpropertyEnum(PvpropertyData, ChannelEnum):
    ...


class PvpropertyBoolEnum(PvpropertyData, ChannelEnum):
    def __init__(self, *, enum_strings=None, **kwargs):
        if enum_strings is None:
            enum_strings = ['Off', 'On']
        super().__init__(enum_strings=enum_strings, **kwargs)


class PvpropertyReadOnlyData(PvpropertyData):
    def check_access(self, host, user):
        return AccessRights.READ


class PvpropertyCharRO(PvpropertyReadOnlyData, ChannelChar):
    ...


class PvpropertyIntegerRO(PvpropertyReadOnlyData, ChannelInteger):
    ...


class PvpropertyDoubleRO(PvpropertyReadOnlyData, ChannelDouble):
    ...


class PvpropertyStringRO(PvpropertyReadOnlyData, ChannelString):
    ...


class PvpropertyEnumRO(PvpropertyReadOnlyData, ChannelEnum):
    ...


class PvpropertyBoolEnumRO(PvpropertyReadOnlyData, ChannelEnum):
    def __init__(self, *, enum_strings=None, **kwargs):
        if enum_strings is None:
            enum_strings = ['Off', 'On']
        super().__init__(enum_strings=enum_strings, **kwargs)


class PVSpec(namedtuple('PVSpec',
                        'get put startup attr name dtype value '
                        'alarm_group read_only doc cls_kwargs')):
    '''PV information specification

    Parameters
    ----------
    get : async callable, optional
        Called when PV is read through channel access
    put : async callable, optional
        Called when PV is written to through channel access
    startup : async callable, optional
        Called at start of server; a hook for initialization and background
        processing
    attr : str, optional
        The attribute name
    name : str, optional
        The PV name
    dtype : ChannelType or builtin type, optional
        The data type
    value : any, optional
        The initial value
    alarm_group : str, optional
        The alarm group the PV should be attached to
    read_only : bool, optional
        Read-only PV over channel access
    doc : str, optional
        Docstring associated with PV
    cls_kwargs : dict, optional
        Keyword arguments for the ChannelData-based class
    '''
    __slots__ = ()
    default_dtype = int

    def __new__(cls, get=None, put=None, startup=None, attr=None, name=None,
                dtype=None, value=None, alarm_group=None, read_only=None,
                doc=None, cls_kwargs=None):
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
            assert not read_only, 'Read-only signal cannot have putter'
            sig = inspect.signature(put)
            try:
                sig.bind('group', 'instance', 'value')
            except Exception as ex:
                raise RuntimeError('Invalid signature for putter {}: {}'
                                   ''.format(put, sig))

        if startup is not None:
            assert inspect.iscoroutinefunction(startup), \
                'required async def startup'
            sig = inspect.signature(startup)
            try:
                sig.bind('group', 'instance', 'async_library')
            except Exception as ex:
                raise RuntimeError('Invalid signature for startup {}: {}'
                                   ''.format(startup, sig))

        return super().__new__(cls, get=get, put=put, startup=startup,
                               attr=attr, name=name, dtype=dtype, value=value,
                               alarm_group=alarm_group, read_only=read_only,
                               doc=doc, cls_kwargs=cls_kwargs)

    def new_names(self, attr=None, name=None):
        if attr is None:
            attr = self.attr
        if name is None:
            name = self.name
        return PVSpec(get=self.get, put=self.put, startup=self.startup,
                      attr=attr, name=name, dtype=self.dtype, value=self.value,
                      alarm_group=self.alarm_group, read_only=self.read_only,
                      doc=self.doc, cls_kwargs=self.cls_kwargs)


class pvproperty:
    '''A property-like descriptor for specifying a PV in a group

    Parameters
    ----------
    get : async callable, optional
        Called when PV is read through channel access
    put : async callable, optional
        Called when PV is written to through channel access
    startup : async callable, optional
        Called at start of server; a hook for initialization and background
        processing
    name : str, optional
        The PV name (defaults to the attribute name of the pvproperty)
    dtype : ChannelType or builtin type, optional
        The data type
    value : any, optional
        The initial value
    alarm_group : str, optional
        The alarm group the PV should be attached to
    read_only : bool, optional
        Read-only PV over channel access
    doc : str, optional
        Docstring associated with the property
    **cls_kwargs :
        Keyword arguments for the ChannelData-based class
    '''

    def __init__(self, get=None, put=None, startup=None, *, name=None,
                 dtype=None, value=None, alarm_group=None, doc=None,
                 read_only=None,
                 **cls_kwargs):
        self.attr_name = None  # to be set later

        if doc is None and get is not None:
            doc = get.__doc__

        self.pvspec = PVSpec(get=get, put=put, startup=startup, name=name,
                             dtype=dtype, value=value, alarm_group=alarm_group,
                             read_only=read_only, doc=doc,
                             cls_kwargs=cls_kwargs)
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
        # handles case where pvproperty(**spec_kw)(getter, putter, startup) is
        # used
        pvspec = self.pvspec
        spec_kw = dict(name=pvspec.name,
                       dtype=pvspec.dtype,
                       value=pvspec.value,
                       alarm_group=pvspec.alarm_group,
                       doc=pvspec.doc,
                       cls_kwargs=pvspec.cls_kwargs)

        if get.__doc__:
            if self.__doc__ is None:
                self.__doc__ = get.__doc__
            if 'doc' not in self.spec_kw:
                spec_kw['doc'] = get.__doc__

        self.pvspec = PVSpec(get, put, startup, **spec_kw)
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
    '''A property-like descriptor for specifying a subgroup in a PVGroup

    Several methods of generating a SubGroup are possible. For the `group`
    parameter, one can
    1. Pass in a group_dict of {attr: pvspec_or_dict}
    2. Pass in an existing PVGroup class
    3. Use @SubGroup as a decorator on a subsequently-defined PVGroup class
    '''

    # support copy.copy by keeping this here
    _class_dict = None

    def __init__(self, group=None, *, prefix=None, macros=None,
                 attr_separator=None, doc=None, base=None):
        self.attr_name = None  # to be set later

        # group_dict is passed in -> generate class_dict -> generate group_cls
        self._group_dict = None
        self._decorated_items = None
        self.group_cls = None
        self.prefix = prefix
        self.macros = macros if macros is not None else {}
        if not hasattr(self, 'attr_separator') or attr_separator is not None:
            self.attr_separator = attr_separator
        self.base = (PVGroup, ) if base is None else base
        self.__doc__ = doc
        # Set last with setter
        self.group = group

    @property
    def group(self):
        'Property handling either group dict or group class'
        return (self.group_dict, self.group_cls)

    @group.setter
    def group(self, group):
        if isinstance(group, dict):
            # set the group dictionary last:
            self.group_dict = group
        elif group is not None:
            assert inspect.isclass(group), 'Group should be dict or SubGroup'
            assert issubclass(group, PVGroup)
            self.group_cls = group
        else:
            self.group_dict = None
            self.group_cls = None

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
        'Create a PVSpec from an info {dict, PVSpec, pvproperty}'
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
        'Create the class dictionary from all PVSpecs'
        pvspecs = [self._pvspec_from_info(attr, pvspec)
                   for attr, pvspec in self._group_dict.items()]

        return {pvspec.attr: NestedPvproperty.from_pvspec(pvspec, self)
                for pvspec in pvspecs
                }

    @property
    def group_dict(self):
        'The group attribute dictionary'
        return self._group_dict

    @group_dict.setter
    def group_dict(self, group_dict):
        if group_dict is None:
            return

        # Upon setting the group dictionary, generate the class
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

        if group is not None:
            copied.group = group

        if copied.group_cls is not None and copied.attr_separator is None:
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
        'Allow access to class_dict getter/putter/startup through decorators'
        if self._class_dict is not None and attr in self._class_dict:
            return self._class_dict[attr]
        return super().__getattribute__(attr)


def get_pv_pair_wrapper(setpoint_suffix='', readback_suffix='_RBV'):
    'Generates a Subgroup class for a pair of PVs (setpoint and readback)'
    def wrapped(*, name=None, dtype=int, doc=None, **kwargs):
        return SubGroup(
            {'setpoint': dict(dtype=dtype, name=setpoint_suffix, doc=doc,
                              **kwargs),
             'readback': dict(dtype=dtype, name=readback_suffix, doc=doc,
                              read_only=True, **kwargs),
             },
            attr_separator='',
            doc=doc,
            prefix=name,
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

        super().__init__(group=None, prefix=prefix, macros=macros,
                         attr_separator=attr_separator, doc=doc)
        self.default_retval = default
        self.func = func
        self.alarm_group = alarm_group
        if names is None:
            names = self.default_names
        self.names = {k: names.get(k, self.default_names[k])
                      for k in self.default_names}
        self.pvspec = []
        self.__doc__ = doc

    def __call__(self, func=None, *, prefix=None, macros=None, doc=None):
        # handles case where pvfunction()(func) is used
        copied = super().__call__(prefix=prefix, macros=macros, doc=doc)

        if func is not None:
            copied.func = func
            copied.group = copied._generate_class_dict()
        return copied

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
            # the pvname defaults to the parameter name, but can be remapped
            # with the 'names' dictionary
            name=self.names.get(param.name, param.name),
            dtype=dtype,
            value=default, alarm_group=self.alarm_group,
            read_only=param.name in ['retval', 'status'],
            doc=doc if doc is not None else f'Parameter {dtype} {param.name}'
        )

    def get_additional_parameters(self):
        sig = inspect.signature(self.func)
        return_type = sig.return_annotation
        assert return_type, 'Return value must have a type annotation'

        return [
            inspect.Parameter('status', kind=0, default=['Init'],
                              annotation=str),
            inspect.Parameter('retval', kind=0,
                              # TODO?
                              default=PVGroup.default_values[return_type],
                              annotation=return_type),
        ]

    def _class_dict_from_pvspec(self, pvspec):
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
                await group.retval.write(value)
                await group.status.write(f'Success')
            except Exception as ex:
                await group.status.write(f'{ex.__class__.__name__}: {ex}')
                raise

        process_prop.pvspec = PVSpec(None, do_process, *process_pvspec[2:])
        return dct

    def _generate_class_dict(self):
        if self.func is None:
            return {}

        if self.alarm_group is None:
            self.alarm_group = self.func.__name__

        if self.__doc__ is None:
            self.__doc__ = self.func.__doc__

        sig = inspect.signature(self.func)
        parameters = list(sig.parameters.values())[1:]  # skip 'self'
        parameters.extend(self.get_additional_parameters())
        self.pvspec = [self.pvspec_from_parameter(param)
                       for param in parameters]
        return self._class_dict_from_pvspec(self.pvspec)

    def __set_name__(self, owner, name):
        self.group_dict = self._generate_class_dict()
        super().__set_name__(owner, name)


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

        # Propagate any subgroups/PVs from base classes
        for base in bases:
            if hasattr(base, '_subgroups_'):
                dct['_subgroups_'].update(**base._subgroups_)
            if hasattr(base, '_pvs_'):
                dct['_pvs_'].update(**base._pvs_)

        for attr, prop in metacls.find_subgroups(dct):
            module_logger.debug('class %s subgroup attr %s: %r', name, attr,
                                prop)
            subgroups[attr] = prop

            # TODO a bit messy
            # propagate subgroups-of-subgroups to the top
            subgroup_cls = prop.group_cls
            if hasattr(subgroup_cls, '_subgroups_'):
                for subattr, subgroup in subgroup_cls._subgroups_.items():
                    subgroups['.'.join((attr, subattr))] = subgroup

        for attr, prop in metacls.find_pvproperties(dct):
            pvspec = prop.pvspec
            module_logger.debug('class %s pvproperty attr %s: %r', name, attr,
                                pvspec)
            pvs[attr] = prop

            if pvspec.cls_kwargs:
                # Ensure all passed class kwargs are valid for the specific
                # class, so it doesn't bite us on instantiation

                prop_cls = data_class_from_pvspec(group=cls, pvspec=pvspec)
                if not hasattr(prop_cls, '_valid_init_kw'):
                    # TODO this should be generated elsewhere
                    prop_cls._valid_init_kw = {
                        key
                        for cls in inspect.getmro(prop_cls)
                        for key in inspect.signature(cls).parameters.keys()
                    }

                bad_kw = set(pvspec.cls_kwargs) - prop_cls._valid_init_kw
                if bad_kw:
                    raise ValueError(f'Bad kw for class {prop_cls}: {bad_kw}')

        return cls


def data_class_from_pvspec(group, pvspec):
    'Return the data class for a given PVSpec in a group'
    if pvspec.read_only:
        return group.type_map_read_only[pvspec.dtype]
    return group.type_map[pvspec.dtype]


def channeldata_from_pvspec(group, pvspec):
    'Create a ChannelData instance based on a PVSpec'
    full_pvname = expand_macros(group.prefix + pvspec.name, group.macros)
    value = (pvspec.value
             if pvspec.value is not None
             else group.default_values[pvspec.dtype]
             )

    cls = data_class_from_pvspec(group, pvspec)
    kw = dict(pvspec.cls_kwargs) if pvspec.cls_kwargs is not None else {}

    inst = cls(group=group, pvspec=pvspec, value=value,
               alarm=group.alarms[pvspec.alarm_group], pvname=full_pvname,
               **kw)
    inst.__doc__ = pvspec.doc
    return (full_pvname, inst)


class PVGroup(metaclass=PVGroupMeta):
    '''
    Class which groups a set of PVs for a high-level caproto server

    Parameters
    ----------
    prefix : str
        Prefix for all PVs in the group
    macros : dict, optional
        Dictionary of macro name to value
    parent : PVGroup, optional
        Parent PVGroup
    name : str, optional
        Name for the group, defaults to the class name
    states : dict, optional
        A dictionary of states used for channel filtering. See
        https://epics.anl.gov/base/R3-15/5-docs/filters.html
    '''

    type_map = {
        str: PvpropertyString,
        int: PvpropertyInteger,
        float: PvpropertyDouble,
        bool: PvpropertyBoolEnum,

        ChannelType.STRING: PvpropertyString,
        ChannelType.LONG: PvpropertyInteger,
        ChannelType.DOUBLE: PvpropertyDouble,
        ChannelType.ENUM: PvpropertyEnum,
        ChannelType.CHAR: PvpropertyChar,
    }

    # Auto-generate the read-only class specification:
    type_map_read_only = {
        dtype: globals()[f'{cls.__name__}RO']
        for dtype, cls in type_map.items()
    }

    default_values = {
        str: '',
        int: 0,
        float: 0.0,
        bool: False,

        ChannelType.STRING: '',
        ChannelType.LONG: 0,
        ChannelType.DOUBLE: 0.0,
        ChannelType.ENUM: 0,
        ChannelType.CHAR: '',
    }

    def __init__(self, prefix, *, macros=None, parent=None, name=None):
        self.parent = parent
        self.macros = macros if macros is not None else {}
        self.prefix = expand_macros(prefix, self.macros)
        self.alarms = defaultdict(ChannelAlarm)
        self.pvdb = OrderedDict()
        self.attr_pvdb = OrderedDict()
        self.attr_to_pvname = OrderedDict()
        self.groups = OrderedDict()

        if not hasattr(self, 'states'):
            if hasattr(self.parent, 'states'):
                self.states = self.parent.states
            else:
                self.states = {}

        pv_group = self

        class StateUpdateContext:
            def __init__(self, state, value):
                self.pv_group = pv_group
                self.state = state
                self.value = value

            async def __aenter__(self):
                for attr in pv_group.attr_pvdb.values():
                    attr.pre_state_change(self.state, self.value)
                pv_group.states[self.state] = self.value
                return self

            async def __aexit__(self, exc_type, exc_value, traceback):
                for attr in pv_group.attr_pvdb.values():
                    attr.post_state_change(self.state, self.value)

        self.update_state = StateUpdateContext

        # Create logger name from parent or from module class
        self.name = (self.__class__.__name__
                     if name is None
                     else name)
        log_name = type(self).__name__
        if self.parent is not None:
            base = self.parent.log.name
            parent_log_prefix = f'{base}.'
            if log_name.startswith(parent_log_prefix):
                log_name = log_name[parent_log_prefix:]
        else:
            base = self.__class__.__module__

        # Instantiate the logger
        self.log = logging.getLogger(f'{base}.{log_name}')
        self._create_pvdb()

        # Prime the snapshots to the current state.
        for key, val in self.states.items():
            for attr in pv_group.attr_pvdb.values():
                attr.pre_state_change(key, val)
                attr.post_state_change(key, val)

    def _create_pvdb(self):
        'Create the PV database for all subgroups and pvproperties'
        for attr, subgroup in self._subgroups_.items():
            if attr in self.groups:
                # already created as part of a sub-subgroup
                continue

            subgroup_cls = subgroup.group_cls

            prefix = (subgroup.prefix if subgroup.prefix is not None
                      else subgroup.attr_name)
            prefix = self.prefix + prefix

            macros = dict(self.macros)
            macros.update(subgroup.macros)

            # instantiate the subgroup
            inst = subgroup_cls(prefix=prefix, macros=macros, parent=self,
                                name=f'{self.name}.{attr}')
            self.groups[attr] = inst

            # find all sub-subgroups, giving direct access to them
            for sub_attr, sub_subgroup in inst.groups.items():
                full_attr = '.'.join((attr, sub_attr))
                self.groups[full_attr] = sub_subgroup

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

    async def group_read(self, instance):
        'Generic read called for channels without `get` defined'
        self.log.debug('no-op group read of %s', instance.pvspec.attr)

    async def group_write(self, instance, value):
        'Generic write called for channels without `put` defined'
        self.log.debug('group write of %s = %s', instance.pvspec.attr, value)
        return value


def template_arg_parser(*, desc, default_prefix, argv=None, macros=None,
                        supported_async_libs=None):
    """
    Construct a template arg parser for starting up an IOC

    Parameters
    ----------
    description : string
        Human-friendly description of what that IOC does
    default_prefix : string
    args : list, optional
        Defaults to sys.argv
    macros : dict, optional
        Maps macro names to default value (string) or None (indicating that
        this macro parameter is required).
    supported_async_libs : list, optional
        "White list" of supported server implementations. The first one will
        be the default. If None specified, the parser will accept all of the
        (hard-coded) choices.

    Returns
    -------
    parser : argparse.ArguementParser
    split_args : callable[argparse.Namespace, Tuple[dict, dict]]
        A helper function to extract and split the 'standard' CL arguments.
        This function sets the logging level and returns the kwargs for
        constructing the IOC and for the launching the server.
    """
    if argv is None:
        argv = sys.argv
    if macros is None:
        macros = {}
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument('--prefix', type=str, default=default_prefix)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-q', '--quiet', action='store_true',
                       help=("Suppress INFO log messages. "
                             "(Still show WARNING or higher.)"))
    group.add_argument('-v', '--verbose', action='store_true',
                       help="Verbose mode. (Use -vvv for more.)")
    group.add_argument('-vvv', action='store_true',
                       help=argparse.SUPPRESS)
    parser.add_argument('--list-pvs', action='store_true',
                        help="At startup, log the list of PV names served.")
    choices = tuple(supported_async_libs or ('asyncio', 'curio', 'trio'))
    parser.add_argument('--async-lib', default=choices[0],
                        choices=choices,
                        help=("Which asynchronous library to use. "
                              "Default is curio."))
    default_intf = get_server_address_list()
    if default_intf == ['0.0.0.0']:
        default_msg = '0.0.0.0'
    else:
        default_msg = (f"{' '.join(default_intf)} as specified by environment "
                       f"variable EPICS_CAS_INTF_ADDR_LIST")
    parser.add_argument('--interfaces', default=default_intf,
                        nargs='+',
                        help=(f"Interfaces to listen on. Default is "
                              f"{default_msg}.  Multiple entries can be "
                              f"given; separate entries by spaces."))
    for name, default_value in macros.items():
        if default_value is None:
            parser.add_argument(f'--{name}', type=str, required=True,
                                help="Macro substitution required by this IOC")
        else:
            parser.add_argument(f'--{name}', type=str, default=default_value,
                                help="Macro substitution, optional")

    def split_args(args):
        """
        Helper function to pull the standard information out of the
        parsed args.

        Returns
        -------
        ioc_options : dict
            kwargs to be handed into the IOC init.

        run_options : dict
            kwargs to be handed to run
        """
        if args.vvv:
            logging.getLogger('caproto').setLevel('DEBUG')
        else:
            if args.verbose:
                level = 'DEBUG'
            elif args.quiet:
                level = 'WARNING'
            else:
                level = 'INFO'
            logging.getLogger('caproto.ctx').setLevel(level)

        return ({'prefix': args.prefix,
                 'macros': {key: getattr(args, key) for key in macros}},

                {'module_name': f'caproto.{args.async_lib}.server',
                 'log_pv_names': args.list_pvs,
                 'interfaces': args.interfaces})

    return parser, split_args


def ioc_arg_parser(*, desc, default_prefix, argv=None, macros=None,
                   supported_async_libs=None):
    """
    A reusable ArgumentParser for basic example IOCs.

    Parameters
    ----------
    description : string
        Human-friendly description of what that IOC does
    default_prefix : string
    args : list, optional
        Defaults to sys.argv
    macros : dict, optional
        Maps macro names to default value (string) or None (indicating that
        this macro parameter is required).
    supported_async_libs : list, optional
        "White list" of supported server implementations. The first one will
        be the default. If None specified, the parser will accept all of the
        (hard-coded) choices.

    Returns
    -------
    ioc_options : dict
        kwargs to be handed into the IOC init.

    run_options : dict
        kwargs to be handed to run
    """
    parser, split_args = template_arg_parser(desc=desc, default_prefix=default_prefix,
                                             argv=argv, macros=macros,
                                             supported_async_libs=supported_async_libs)
    return split_args(parser.parse_args())
