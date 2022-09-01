import inspect
import os.path
from typing import Any, Dict, List, Optional, Type, Union

import caproto

from ..server import PVGroup, SubGroup, pvproperty
from ..server.records import RecordFieldGroup


def get_class_info(cls: type) -> Optional[Dict[str, Any]]:
    """
    Get class information in a jinja-friendly way.

    Keys for usage include ``name`` (the class name), ``full_name`` (a
    fully-qualified module and class name), ``class`` (the class type itself),
    ``link`` (a link to the class, only showing its name), and ``full_link`` (a
    full link showing the fully-qualified name).

    Parameters
    ----------
    cls : type
        Class type.
    """
    if cls is None:
        return None

    def link_as(text):
        return f':class:`{text} <{full_name}>`'

    full_name = f'{cls.__module__}.{cls.__name__}'
    return {
        'name': cls.__name__,
        'full_name': full_name,
        'class': cls,
        'full_link': f':class:`{full_name}`',
        'link': f':class:`~{full_name}`',
        'link_as': link_as,
    }


def get_subgroup_info(cls: Type[PVGroup],
                      attr: str,
                      subgroup: SubGroup) -> Dict[str, Any]:
    """
    Get information from a SubGroup into an easily-ingestible dictionary.

    Parameters
    ----------
    cls : PVGroup class
    attr : str
        The subgroup attribute.

    subgroup : SubGroup
        The subgroup class itself.

    Returns
    -------
    info : dict
    """
    return dict(
        attr=attr,
        cls=get_class_info(subgroup.group_cls),
        macros=subgroup.macros,
        prefix=subgroup.prefix,
        doc=subgroup.__doc__ or '',
        subgroup=subgroup,
    )


def get_pvproperty_info(cls: Type[PVGroup],
                        prop: pvproperty) -> Dict[str, Any]:
    """
    Get information from a pvproperty into an easily-ingestible dictionary.

    Parameters
    ----------
    cls : PVGroup class
    prop : pvproperty

    Returns
    -------
    info : dict
    """
    pvspec = prop.pvspec
    inherited_from = _follow_inheritance(cls, prop.attr_name)
    if inherited_from is cls:
        inherited_from = None

    return dict(
        prop=prop,
        pvspec=pvspec,
        name=pvspec.name,
        dtype=pvspec.dtype,
        dtype_name=getattr(pvspec.dtype, 'name',
                           getattr(pvspec.dtype, '__name__', str(pvspec.dtype))
                           ),
        inherited_from=get_class_info(inherited_from),
        attr=prop.attr_name,
        cls=get_class_info(type(prop)),
        doc=pvspec.doc or '',
        getter=pvspec.get,
        putter=pvspec.put,
        startup=pvspec.startup,
        shutdown=pvspec.shutdown,
        record_type=get_record_info(prop.record_type),
        read_only=pvspec.read_only,
        max_length=pvspec.max_length,
    )


def _follow_inheritance(cls, attr):
    """Find where an attribute comes from originally."""
    for base in cls.mro()[1:]:
        if hasattr(base, attr):
            return _follow_inheritance(base, attr)

    # Not found in any bases, must be defined here
    return cls


SKIP_ATTRIBUTES = set()


def filter_by_attribute_name(attr) -> bool:
    """A hook for skipping certain attributes."""
    return attr.startswith('_') or attr in SKIP_ATTRIBUTES


def _get_pvgroup_info(cls: Type[PVGroup]) -> dict:
    """
    Get PVGroup information that can be rendered as a table.

    Parameters
    ----------
    cls : PVGroup subclass
    """
    if not issubclass(cls, PVGroup):
        return dict(
            pvproperty=None,
            subgroup=None,
            record_name=None,
            cls=get_class_info(cls),
        )

    properties = {}
    for attr, obj in inspect.getmembers(cls):
        if filter_by_attribute_name(attr):
            continue

        if isinstance(obj, pvproperty):
            properties[attr] = get_pvproperty_info(cls, obj)

    subgroups = {
        attr: get_subgroup_info(cls, attr, subgroup)
        for attr, subgroup in cls._subgroups_.items()
    }

    if cls in caproto.server.records.records.values():
        record_name = cls._record_type
    else:
        record_name = None

    return dict(
        pvproperty=properties,
        subgroup=subgroups,
        record_name=record_name,
        cls=get_class_info(cls),
    )


def get_record_info(
    record_type: Union[str, Type[RecordFieldGroup]]
) -> Optional[Dict[str, Any]]:
    """Get information from a given record type."""
    if record_type is None:
        return None

    if inspect.isclass(record_type):
        cls = record_type
    elif record_type == 'base':
        cls = RecordFieldGroup
    else:
        cls = caproto.server.records.records[record_type]

    return _get_pvgroup_info(cls)


def get_all_records() -> List[Dict[str, Any]]:
    """Get all registered record types."""
    return [
        get_record_info(rec_name)
        for rec_name, cls in caproto.server.records.records.items()
    ]


# NOTE: can't use functools.lru_cache here as it's not picklable
_info_cache = {}


def get_pvgroup_info(module, name) -> List[dict]:
    """
    Get PVGroup information that can be rendered as a table.

    Parameters
    ----------
    module : str
        Module name.

    name : str
        Class name.
    """
    class_name = f'{module}.{name}'
    if class_name not in _info_cache:
        module_name, class_name = class_name.rsplit('.', 1)
        module = __import__(module_name, globals(), locals(), [class_name])
        cls = getattr(module, class_name)
        _info_cache[class_name] = _get_pvgroup_info(cls)

    return _info_cache[class_name]


def rst_with_jinja(app, docname, source):
    """
    Render our pages as a jinja template for fancy templating goodness.

    Usage
    -----

    .. code::

        def setup(app):
            app.connect("source-read", rst_with_jinja)
    """
    # Borrowed from
    # https://www.ericholscher.com/blog/2016/jul/25/integrating-jinja-rst-sphinx/

    # Make sure we're outputting HTML
    if app.builder.format != 'html':
        return

    rendered = app.builder.templates.render_string(
        source[0], app.config.html_context
    )
    source[0] = rendered


def skip_pvproperties(app, what, name, obj, skip, options):
    if isinstance(obj, (pvproperty, SubGroup)):
        return True

    if name.startswith('_'):
        # It's unclear if I broke this or if it's always been broken,
        # but for our use case we never want to document `_` items with
        # autoclass.
        return True

    return skip


def setup(app):
    """
    Setup method to configure caproto sphinx documentation helpers.

    This is a convenience method; advanced users may wish to replicate this
    method on their own.

    Parameters
    ----------
    app : sphinx.Application

    """
    app.connect("source-read", rst_with_jinja)
    app.connect('autodoc-skip-member', skip_pvproperties)


autosummary_context = {
    # Allow autosummary/class.rst to do its magic:
    'caproto': caproto,
    'get_pvgroup_info': get_pvgroup_info,
    'get_all_records': get_all_records,
    'get_record_info': get_record_info,
    'inspect': inspect,
    'path': os.path,
    'inline_code_threshold': 10,
    # Where is your project root, relative to conf.py?
    'project_root': '..',
}

autodoc_default_options = {
    # 'members': '',
    'member-order': 'bysource',
    'special-members': '',
    'undoc-members': False,
    'exclude-members': ''
}
autoclass_content = 'init'  # otherwise duplicates will be generated
