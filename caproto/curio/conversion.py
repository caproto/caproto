import inspect
import ophyd
from .high_level_server import pvfunction, PVGroup


def underscore_to_camel_case(s):
    'Convert abc_def_ghi -> AbcDefGhi'
    def capitalize_first(substring):
        return substring[:1].upper() + substring[1:]
    return ''.join(map(capitalize_first, s.split('_')))


def ophyd_component_to_caproto(attr, component, *, depth=0, dev=None):
    indent = '    ' * depth
    sig = getattr(dev, attr) if dev is not None else None

    if isinstance(component, ophyd.DynamicDeviceComponent):
        cpt_dict = ophyd_device_to_caproto_ioc(component, depth=depth)
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
            f"{indent}{attr} = caproto.SubGroup({cpt_name}, prefix='')",
            ''
        ]
        return cpt_dict

    kwargs = dict(name=repr(component.suffix))

    if isinstance(component, ophyd.FormattedComponent):
        # TODO Component vs FormattedComponent
        kwargs['name'] = "''"
    else:  # if hasattr(component, 'suffix'):
        kwargs['name'] = repr(component.suffix)

    if sig and sig.connected:
        value = component.get()
        try:
            value = value[0]
        except TypeError:
            ...
        kwargs['dtype'] = str(type(value))
    else:
        cpt_kwargs = getattr(component, 'kwargs', {})
        is_string = cpt_kwargs.get('string', False)
        if is_string:
            kwargs['dtype'] = 'str'
        else:
            kwargs['dtype'] = 'unknown'

    # if component.__doc__:
    #     kwargs['doc'] = repr(component.__doc__)

    kw_str = ', '.join(f'{key}={value}'
                       for key, value in kwargs.items())

    if issubclass(component.cls, ophyd.EpicsSignalWithRBV):
        line = f"{indent}{attr} = pvproperty_with_rbv({kw_str})"
    elif issubclass(component.cls, ophyd.EpicsSignalRO):
        line = f"{indent}{attr} = pvproperty({kw_str})"
    elif issubclass(component.cls, ophyd.EpicsSignal):
        line = f"{indent}{attr} = pvproperty({kw_str})"
    else:
        line = f"{indent}# {attr} = pvproperty({kw_str})"

    # single line, no new subclass defined
    return {'': [line]}


def ophyd_device_to_caproto_ioc(dev, *, depth=0):
    if isinstance(dev, ophyd.DynamicDeviceComponent):
        # DynamicDeviceComponent: attr: (sig_cls, prefix, kwargs)
        attr_components = {
            attr: ophyd.Component(sig_cls, prefix, **kwargs)
            for attr, (sig_cls, prefix, kwargs) in dev.defn.items()
        }
        dev_name = f'{dev.attr}_group'
        # TODO can't inspect
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

    dev_lines = [f"{indent}class {dev_name}(PVGroup):"]

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

    skip_attrs = ('Status', 'Retval')
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
        yield (f"    {name.lower()} = Cpt({name}Device, "
               f"'{subgroup.prefix}'{doc})")

    if not group._pvs_:
        yield f'    ...'

    for name, prop in group._pvs_.items():
        if '.' in name:
            # Skipping, part of subgroup handled above
            continue

        pvspec = prop.pvspec
        doc = f', doc={pvspec.doc!r}' if pvspec.doc else ''
        string = f', string=True' if pvspec.dtype == str else ''
        yield (f"    {name.lower()} = Cpt(EpicsSignal, '{pvspec.name}'"
               f"{string}{doc})")
        # TODO will break when full/macro-ified PVs is specified

    # lower_name = group.__name__.lower()
    # yield f"# {lower_name} = {group.__name__}Device(my_prefix)"
