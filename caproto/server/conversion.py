import inspect

from .server import pvfunction, PVGroup
from .._data import (ChannelDouble, ChannelEnum, ChannelChar,
                     ChannelInteger, ChannelString, ChannelByte)
from .menus import menus

try:
    # optionally format Python code more nicely
    import yapf
except ImportError:
    yapf = None


def underscore_to_camel_case(s):
    'Convert abc_def_ghi -> AbcDefGhi'
    def capitalize_first(substring):
        return substring[:1].upper() + substring[1:]
    return ''.join(map(capitalize_first, s.split('_')))


def ophyd_component_to_caproto(attr, component, *, depth=0, dev=None):
    import ophyd

    indent = '    ' * depth
    sig = getattr(dev, attr) if dev is not None else None

    if isinstance(component, ophyd.DynamicDeviceComponent):
        to_describe = sig if sig is not None else component

        cpt_dict = ophyd_device_to_caproto_ioc(to_describe, depth=depth)
        cpt_name, = cpt_dict.keys()
        cpt_dict[''] = [
            '',
            f"{indent}{attr} = SubGroup({cpt_name}, prefix='')",
            '',
        ]
        return cpt_dict

    elif issubclass(component.cls, ophyd.Device):
        kwargs = dict()
        if isinstance(component, ophyd.FormattedComponent):
            # TODO Component vs FormattedComponent
            kwargs['name'] = "''"

        to_describe = sig if sig is not None else component.cls

        cpt_dict = ophyd_device_to_caproto_ioc(to_describe, depth=depth)
        cpt_name, = cpt_dict.keys()
        cpt_dict[''] = [
            '',
            (f"{indent}{attr} = SubGroup({cpt_name}, "
             f"prefix='{component.suffix}')"),
            '',
        ]
        return cpt_dict

    kwargs = dict(name=repr(component.suffix))

    if isinstance(component, ophyd.FormattedComponent):
        # TODO Component vs FormattedComponent
        kwargs['name'] = "''"
    else:  # if hasattr(component, 'suffix'):
        kwargs['name'] = repr(component.suffix)

    if sig and sig.connected:
        value = sig.get()

        def array_checker(value):
            try:
                import numpy as np
                return isinstance(value, np.ndarray)
            except ImportError:
                return False

        try:
            # NELM reflects the actual maximum length of the value, as opposed
            # to the current length
            max_length = sig._read_pv.nelm
        except Exception:
            max_length = 1

        if array_checker(value):
            # hack, as value can be a zero-length array
            # FUTURE_TODO: support numpy types directly in pvproperty type map
            import numpy as np
            value = np.zeros(1, dtype=value.dtype).tolist()[0]
        else:
            try:
                value = value[0]
            except (IndexError, TypeError):
                ...

        kwargs['dtype'] = type(value).__name__
        if max_length > 1:
            kwargs['max_length'] = max_length
    else:
        cpt_kwargs = getattr(component, 'kwargs', {})
        is_string = cpt_kwargs.get('string', False)
        if is_string:
            kwargs['dtype'] = 'str'
        else:
            kwargs['dtype'] = 'unknown'

    # if component.__doc__:
    #     kwargs['doc'] = repr(component.__doc__)

    if issubclass(component.cls, ophyd.EpicsSignalRO):
        kwargs['read_only'] = True

    kw_str = ', '.join(f'{key}={value}'
                       for key, value in kwargs.items())

    if issubclass(component.cls, ophyd.EpicsSignalWithRBV):
        line = f"{attr} = pvproperty_with_rbv({kw_str})"
    elif issubclass(component.cls, (ophyd.EpicsSignalRO, ophyd.EpicsSignal)):
        line = f"{attr} = pvproperty({kw_str})"
    else:
        line = f"# {attr} = pvproperty({kw_str})"

    # single line, no new subclass defined
    return {'': list(_format(line, indent=4 * depth))}


def ophyd_device_to_caproto_ioc(dev, *, depth=0):
    import ophyd

    if isinstance(dev, ophyd.DynamicDeviceComponent):
        # DynamicDeviceComponent: attr: (sig_cls, prefix, kwargs)
        # NOTE: cannot inspect types without an instance of the dynamic Device
        # class
        attr_components = {
            attr: ophyd.Component(sig_cls, prefix, **kwargs)
            for attr, (sig_cls, prefix, kwargs) in dev.defn.items()
        }
        dev_name = f'{dev.attr}_group'
        cls, dev = dev, None
    else:
        if inspect.isclass(dev):
            # we can introspect Device directly, but we cannot connect to PVs
            # and tell about their data type
            cls, dev = dev, None
        else:
            # if connected, we can reach out to PVs and determine data types
            cls = dev.__class__
        attr_components = cls._sig_attrs
        dev_name = f'{cls.__name__}_group'

    dev_name = underscore_to_camel_case(dev_name)
    indent = '    ' * depth

    dev_lines = ['',
                 f"{indent}class {dev_name}(PVGroup):"]

    for attr, component in attr_components.items():
        cpt_lines = ophyd_component_to_caproto(attr, component,
                                               depth=depth + 1,
                                               dev=dev)
        if isinstance(cpt_lines, dict):
            # new device/sub-group, for now add it on
            for new_dev, lines in cpt_lines.items():
                dev_lines.extend(lines)
        else:
            dev_lines.extend(cpt_lines)

    return {dev_name: dev_lines}


def pvfunction_to_device_function(name, pvf, *, indent='    '):
    'pvfunction -> Device method'
    def format_arg(pvspec):
        value = pvspec.value
        if isinstance(value, (list, tuple)) and len(value) == 1:
            value = value[0]
        value = f'={value}' if value else ''
        return f"{pvspec.attr}: {pvspec.dtype.__name__}{value}"

    skip_attrs = ('status', 'retval')
    args = ', '.join(format_arg(spec) for spec in pvf.pvspec
                     if spec.attr not in skip_attrs)
    yield f"{indent}def call(self, {args}):"
    if pvf.__doc__:
        yield f"{indent*2}'{pvf.__doc__}'"
    for pvspec in pvf.pvspec:
        if pvspec.attr not in skip_attrs:
            yield (f"{indent*2}self.{pvspec.attr}.put({pvspec.attr}, "
                   "wait=True)")

    yield f"{indent*2}self.process.put(1, wait=True)"
    yield f"{indent*2}status = self.status.get(use_monitor=False)"
    yield f"{indent*2}retval = self.retval.get(use_monitor=False)"
    yield f"{indent*2}if status != 'Success':"
    yield f"{indent*3}raise RuntimeError(f'RPC function failed: {{status}}')"
    yield f"{indent*2}return retval"


def group_to_device(group):
    'Make an ophyd device from a high-level server PVGroup'
    # TODO subgroups are weak and need rethinking (generic comment deux)

    for name, subgroup in group._subgroups_.items():
        yield from group_to_device(subgroup.group_cls)

        if isinstance(subgroup, pvfunction):
            yield f''
            yield from pvfunction_to_device_function(name, subgroup)

        yield f''
        yield f''

    if isinstance(group, PVGroup):
        group = group.__class__

    yield f"class {group.__name__}Device(ophyd.Device):"

    for name, subgroup in group._subgroups_.items():
        doc = f', doc={subgroup.__doc__!r}' if subgroup.__doc__ else ''
        yield from _format(f"{name.lower()} = Cpt({name}Device, "
                           f"'{subgroup.prefix}'{doc})", indent=4)

    if not group._pvs_:
        yield f'    ...'

    for name, prop in group._pvs_.items():
        if '.' in name:
            # Skipping, part of subgroup handled above
            continue

        pvspec = prop.pvspec
        doc = f', doc={pvspec.doc!r}' if pvspec.doc else ''
        string = f', string=True' if pvspec.dtype == str else ''
        cls = 'EpicsSignalRO' if pvspec.read_only else 'EpicsSignal'
        yield from _format(f"{name.lower()} = Cpt({cls}, '{pvspec.name}'"
                           f"{string}{doc})", indent=4)
        # TODO will break when full/macro-ified PVs is specified

    # lower_name = group.__name__.lower()
    # yield f"# {lower_name} = {group.__name__}Device(my_prefix)"


def record_to_field_info(record_type):
    import recordwhat

    base = recordwhat.RecordBase

    if record_type == 'base':
        cls = recordwhat.RecordBase
    else:
        cls = recordwhat.get_record_class(record_type)

    base_metadata = dict(base.field_metadata())
    field_dict = dict(cls.field_metadata())

    type_info = {
        'DBF_DEVICE': ChannelString,  # DTYP
        'DBF_FLOAT': ChannelDouble,
        'DBF_DOUBLE': ChannelDouble,
        'DBF_FWDLINK': ChannelString,
        'DBF_INLINK': ChannelString,
        'DBF_LONG': ChannelInteger,
        'DBF_MENU': ChannelEnum,
        'DBF_ENUM': ChannelEnum,
        'DBF_OUTLINK': ChannelString,
        'DBF_SHORT': ChannelInteger,
        'DBF_STRING': ChannelString,
        'DBF_CHAR': ChannelChar,

        # unsigned types which don't actually have ChannelType equivalents:
        'DBF_UCHAR': ChannelByte,
        'DBF_ULONG': ChannelInteger,
        'DBF_USHORT': ChannelInteger,
    }

    for name, field_info in field_dict.items():
        if cls is not base and name in base_metadata:
            if base_metadata[name] == field_info:
                # Skip base attrs
                continue

        type_ = field_info.type
        size = field_info.size
        prompt = field_info.prompt

        # alarm = parent.alarm
        kwargs = {}

        if type_ == 'DBF_STRING' and size > 0:
            type_ = 'DBF_UCHAR'
            kwargs['max_length'] = size
        elif size > 1:
            kwargs['max_length'] = size

        if type_ == 'DBF_MENU':
            # note: ordered key assumption here (py3.6+)
            kwargs['enum_strings'] = (f'menus.{field_info.menu}'
                                      '.get_string_tuple()')

        if prompt:
            kwargs['doc'] = repr(prompt)

        if field_info.special == 'SPC_NOMOD':
            kwargs['read_only'] = True

        type_class = type_info[type_]

        yield name, type_class, kwargs, field_info


def _format(line, *, indent=0):
    '''Format Python code lines, with a specific indent

    NOTE: Uses yapf if available
    '''
    prefix = ' ' * indent
    if yapf is None:
        yield prefix + line
    else:
        from yapf.yapflib.yapf_api import FormatCode
        from yapf.yapflib.style import _style

        # TODO study awkward yapf api more closely
        _style['COLUMN_LIMIT'] = 79 - indent
        for formatted_line in FormatCode(line)[0].split('\n'):
            if formatted_line:
                yield prefix + formatted_line.rstrip()


def record_to_field_dict_code(record_type, *, skip_fields=None):
    'Record name -> yields code to create {field: ChannelData(), ...}'
    if skip_fields is None:
        skip_fields = ['VAL']
    yield f"def create_{record_type}_dict(alarm_group, **kw):"
    yield f"    kw['reported_record_type'] = '{record_type}'"
    yield f"    kw['alarm_group'] = alarm_group"
    yield '    return {'
    for name, cls, kwargs, finfo in record_to_field_info(record_type):
        kwarg_string = ', '.join(
            list(f'{k}={v}' for k, v in kwargs.items()) + ['**kw'])
        yield f"        '{finfo.field}': {cls.__name__}({kwarg_string}),"
    yield '    }'


dtype_overrides = {
    # DBF_FLOAT is ChannelDouble -> DOUBLE; override with FLOAT
    'DBF_FLOAT': 'FLOAT',
    # DBF_SHORT is ChannelInteger -> LONG; override with SHORT
    'DBF_SHORT': 'SHORT',
    'DBF_USHORT': 'SHORT',
}


def record_to_high_level_group_code(record_type, *, skip_fields=None):
    'Record name -> yields code to create a PVGroup for all fields'
    if skip_fields is None:
        skip_fields = ['VAL']

    if record_type == 'base':
        name = 'RecordFieldGroup'
        base_class = 'PVGroup'
    else:
        name = f'{record_type.capitalize()}Fields'
        base_class = 'RecordFieldGroup'

    yield f"class {name}({base_class}):"
    if record_type != 'base':
        yield f"    _record_type = '{record_type}'"

    fields = {}

    for name, cls, kwargs, finfo in record_to_field_info(record_type):
        fields[name] = (cls, kwargs, finfo)
        kwarg_string = ', '.join(f'{k}={v}' for k, v in kwargs.items())
        dtype = dtype_overrides.get(cls.data_type.name, cls.data_type.name)
        comment = False
        if finfo.field in skip_fields:
            comment = True
        elif finfo.menu and finfo.menu not in menus:
            comment = True

        lines = _format(f"{name} = pvproperty(name="
                        f"'{finfo.field}', "
                        f"dtype=ChannelType.{dtype}, "
                        f"{kwarg_string})", indent=4)

        if comment:
            for line in lines:
                indent = len(line) - len(line.lstrip())
                if indent >= 4:
                    yield f'    # {line[4:]}'
                else:
                    yield f'# {line}'
        else:
            yield from lines

    linkable = {
        'display_precision': 'precision',
        'hihi_alarm_limit': 'upper_alarm_limit',
        'high_alarm_limit': 'upper_warning_limit',
        'low_alarm_limit': 'lower_warning_limit',
        'lolo_alarm_limit': 'lower_alarm_limit',
        'high_operating_range': 'upper_ctrl_limit',
        'low_operating_range': 'lower_ctrl_limit',
        # 'alarm_deadband': '',
        'archive_deadband': 'log_atol',
        'monitor_deadband': 'value_atol',
    }

    for field_attr, channeldata_attr in linkable.items():
        if field_attr not in fields:
            continue
        yield f"    _link_parent_attribute({field_attr}, '{channeldata_attr}')"
