"""
PVAGroup-based server code. It's a big magical - maybe not in a good way...
"""
import contextlib
import copy
import dataclasses
import functools
import inspect
import logging
import types
from contextvars import ContextVar
from typing import Dict, List, Optional, Sequence

from ... import pva
from .._dataclass import get_pv_structure, pva_dataclass
from .._normative import (NTScalarArrayBoolean, NTScalarArrayFloat64,
                          NTScalarArrayInt64, NTScalarArrayString,
                          NTScalarBoolean, NTScalarFloat64, NTScalarInt64,
                          NTScalarString)
from .common import AuthOperation, DataWrapperBase

module_logger = logging.getLogger(__name__)


class AuthenticationError(RuntimeError):
    ...


class DatabaseDefinitionError(RuntimeError):
    ...


class SignatureDefinitionError(DatabaseDefinitionError):
    ...


def expand_macros(pv, macros):
    'Expand a PV name with Python {format-style} macros'
    return pv.format(**macros)


def verify_getter(attr: str, get: callable) -> callable:
    """Verify a getter's call signature."""
    if not inspect.iscoroutinefunction(get):
        raise SignatureDefinitionError('required async def get')

    sig = inspect.signature(get)
    try:
        sig.bind('group', 'instance', 'request')
    except Exception:
        raise SignatureDefinitionError(
            f'{attr}: Invalid signature for getter {get}: {sig}'
        )
    return get


def verify_putter(attr: str,
                  put: callable,
                  *,
                  read_only: bool = False) -> callable:
    """Verify a putter's call signature."""
    if not inspect.iscoroutinefunction(put):
        raise SignatureDefinitionError('required async def put')

    if read_only:
        raise SignatureDefinitionError(
            'Read-only signal cannot have putter'
        )

    sig = inspect.signature(put)
    try:
        sig.bind('group', 'instance', 'write_update')
    except Exception:
        raise SignatureDefinitionError(
            f'{attr}: Invalid signature for putter {put}: {sig}'
        )
    return put


def verify_rpc_call(attr: str,
                    call: callable,
                    *,
                    read_only: bool = False) -> callable:
    """Verify an RPC call handler's signature."""
    if not inspect.iscoroutinefunction(call):
        raise SignatureDefinitionError('required async def call')

    if read_only:
        raise SignatureDefinitionError(
            'Read-only signal cannot have an RPC call'
        )

    sig = inspect.signature(call)
    try:
        sig.bind('group', 'instance', 'data')
    except Exception:
        raise SignatureDefinitionError(
            f'{attr}: Invalid signature for RPC call {call}: {sig}'
        )
    return call


def verify_startup(attr: str, method: callable) -> callable:
    """Verify a startup method's call signature."""
    if not inspect.iscoroutinefunction(method):
        raise SignatureDefinitionError('required async def method')

    sig = inspect.signature(method)
    try:
        sig.bind('group', 'instance', 'async_lib')
    except Exception:
        raise SignatureDefinitionError(
            f'{attr}: Invalid signature for startup {method}: {sig}'
        )
    return method


def verify_shutdown(attr: str, method: callable) -> callable:
    """Verify a shutdown method's call signature."""
    if not inspect.iscoroutinefunction(method):
        raise SignatureDefinitionError('required async def method')

    sig = inspect.signature(method)
    try:
        sig.bind('group', 'instance', 'async_lib')
    except Exception:
        raise SignatureDefinitionError(
            f'{attr}: Invalid signature for shutdown {method}: {sig}'
        )
    return method


class DataclassOverlayInstance:
    _reserved = (
        '_struct_', '_instance_', '_children_', '_root_', '_changes_',
        '_prefix_', '_owner_',
    )
    _changes_ = None
    _children_ = None
    _instance_ = None
    _prefix_ = None
    _root_ = None
    _struct_ = None
    _owner_ = None

    def __init__(self, instance, *, attr=None, parent=None,
                 owner=None, changes=None):
        self._struct_ = get_pv_structure(instance)
        self._instance_ = instance
        self._children_ = self._struct_.children
        self._owner_ = owner
        self._changes_ = changes if changes is not None else {}

        if parent is not None:
            self._root_ = parent._root_ or parent
            self._prefix_ = parent._prefix_ + [attr]
        else:
            self._root_ = self
            self._prefix_ = []

    def __repr__(self):
        return repr(self._instance_)

    def __dir__(self):
        return dir(self._instance_)

    def __getattr__(self, attr):
        try:
            return self._changes_[attr]
        except KeyError:
            ...

        value = getattr(self._instance_, attr)
        if hasattr(value, '_pva_struct_'):
            if attr not in self._changes_:
                self._changes_[attr] = {}
            sub_overlay = DataclassOverlayInstance(
                value, attr=attr, parent=self, owner=self._owner_,
                changes=self._changes_[attr],
            )
            self.__dict__[attr] = sub_overlay
            return sub_overlay

        return value

    def __setattr__(self, attr, value):
        if attr in self._reserved:
            # For initialization-related things
            self.__dict__[attr] = value
            return

        if attr in self._children_:
            self._changes_[attr] = value
        else:
            setattr(self._instance_, attr, value)

    def __delattr__(self, attr):
        if attr in self._reserved:
            return

        # with self._change_lock_:
            # TODO fix rejection of entire sub-structure
            # this breaks it entirely
        assert not isinstance(self._changes_.pop(attr, None), dict)


class WriteUpdate:
    def __init__(self,
                 owner,
                 overlay: DataclassOverlayInstance,
                 changes: dict):
        self._cls = type(owner.data)
        self._owner = owner
        self.instance = overlay
        self._changes = changes  # overlay._changes_

    def __repr__(self):
        return (
            f'<WriteUpdate for {self._cls} changes={self._changes}>'
        )

    @property
    def changes(self):
        # TODO: deep copy would be appropriate; or just trust the caller :(
        return dict(self._changes)

    def __contains__(self, attr):
        changes = self._changes
        try:
            for part in attr.split('.'):
                changes = changes[part]
        except KeyError:
            return False

        return True

    def accept(self, *keys):
        """
        Accept only the provided keys.
        """
        if not keys:
            # accept() -> reject
            self.reject()
            return

        def add_accepted(changes, accepted, parts):
            part, *parts = parts
            if part not in changes:
                # warn? error?
                return

            if len(parts):
                if part not in accepted:
                    accepted[part] = {}
                return add_accepted(changes[part], accepted[part], parts)
            accepted[part] = changes[part]

        accepted_changes = {}
        for key in keys:
            add_accepted(self._changes, accepted_changes, key.split('.'))

        # TODO: this is pretty inefficient and bad
        # TODO: accessing the overlay after this can fail in nested structs
        self.instance._changes_ = accepted_changes
        self._changes = accepted_changes

    def reject(self, *keys):
        """
        Reject the provided keys, accepting the remainder.
        """
        if not keys:
            # reject() -> reject all
            self._changes.clear()
            self.instance._changes_ = self._changes
            return

        def remove_rejected(changes, parts):
            part, *parts = parts
            if part not in changes:
                # warn? error?
                return

            if len(parts):
                return remove_rejected(changes[part], parts)

            changes.pop(part, None)

        for key in keys:
            remove_rejected(self._changes, key.split('.'))

        self.instance._changes_ = self._changes


def _method_or_fallback(group: 'PVAGroup',
                        user_specified_method: Optional[callable],
                        fallback: Optional[callable]):
    if user_specified_method is not None:
        return types.MethodType(user_specified_method, group)
    return fallback


# These context variables are pretty magical in their own right:
#   * The following context variable holds a DataclassOverlayInstance in each
#     "context"
#   * The context is defined below in `GroupDataWrapper`
#   * When one uses `async with GroupDataWrapper()`, it calls `__aenter__` and
#     generates a new context and context variable
#   * When that context exits, `__aexit__` is called, and `GroupDataWrapper`
#     can find the correct overlay that relates to the given context by way of
#     retrieving the context variable.
# More here: https://docs.python.org/3/library/contextvars.html
_overlays_context_var = ContextVar('overlays')
_overlays_context_var: ContextVar[Dict[str, DataclassOverlayInstance]]


class GroupDataWrapper(DataWrapperBase):
    """
    A base class to wrap dataclasses and support caproto-pva's server API.

    Two easy methods are provided for writing multiple changes to a data
    structure in one block.

    .. code::

        async with group.prop as prop:
            prop.attr1 = 1
            prop.attr2 = 2

    .. code::

        async with group.prop(changes={'attr1': 1}) as prop:
            prop.attr2 = 2

    When the context manager exits, the values written will be committed
    and sent out over pvAccess.

    Parameters
    ----------
    name : str
        The associated name of the data.

    data : PvaStruct
        The dataclass holding the data.

    group : PVAGroup
        The group associated with the data.

    prop : pvaproperty
        The group's property which help in binding user hooks.
    """

    write_update_class = WriteUpdate

    def __init__(self,
                 name: str,
                 data,
                 *,
                 group: 'PVAGroup',
                 prop: 'pvaproperty',
                 ):
        super().__init__(name=name, data=data)
        self.prop = prop

        self.user_read = _method_or_fallback(
            group, prop._get, fallback=group.group_read
        )

        self.user_write = _method_or_fallback(
            group, prop._put, fallback=group.group_write
        )

        self.user_call = _method_or_fallback(group, prop._call, fallback=None)

        if prop._startup is not None:
            self.server_startup = functools.partial(
                types.MethodType(prop._startup, group),
                self,
            )

        if prop._shutdown is not None:
            self.server_shutdown = functools.partial(
                types.MethodType(prop._shutdown, group),
                self,
            )

    @contextlib.asynccontextmanager
    async def __call__(self, *, changes=None):
        overlay = DataclassOverlayInstance(self.data, owner=self,
                                           changes=changes)
        yield overlay
        await self.commit(overlay._changes_)

    async def __aenter__(self):
        # For more information on this, see `_overlays_context_var` above.
        overlays = _overlays_context_var.get({})
        _overlays_context_var.set(overlays)

        # Nesting of these blocks is not yet supported
        overlay = DataclassOverlayInstance(self.data, owner=self)
        overlays[self.name] = overlay
        return overlay

    async def __aexit__(self, exc_type, exc_value, traceback):
        overlays = _overlays_context_var.get()
        overlay: DataclassOverlayInstance = overlays.pop(self.name)
        if exc_type is None:
            await self.commit(overlay._changes_)

    async def authorize(self,
                        operation: AuthOperation, *,
                        authorization,
                        request=None):
        """
        Authenticate `operation`, given `authorization` information.

        In the event of successful authorization, a dataclass defining the data
        contained here must be returned.

        In the event of a failed authorization, `AuthenticationError` or
        similar should be raised.

        Returns
        -------
        data

        Raises
        ------
        AuthenticationError
        """
        if authorization['method'] == 'ca':
            # user = authorization['data'].user
            # if user != 'klauer':
            #     raise AuthenticationError(f'No, {user}.')
            ...
        elif authorization['method'] in {'anonymous', ''}:
            ...

        return self.data

    async def read(self, request):
        """A read request."""
        async with self() as overlay:
            await self.user_read(overlay, request)
        return self.data

    async def write(self, update: pva.DataWithBitSet):
        """A write request."""
        async with self(changes=update.data) as overlay:
            write_update = self.write_update_class(
                owner=self, overlay=overlay, changes=update.data)
            await self.user_write(overlay, write_update)

    async def call(self, request: pva.PVRequest, data: pva.FieldDescAndData):
        """An rpc-call request."""
        async with self() as overlay:
            # TODO: update state or not?
            # is_nturi = type(data).__name__.startswith('epics:nt/NTURI:')
            return await self.user_call(overlay, data.data)


@dataclasses.dataclass
class PvapropertyHooks:
    get: Optional[callable]
    put: Optional[callable]
    startup: Optional[callable]
    shutdown: Optional[callable]
    call: Optional[callable]


class pvaproperty:
    """
    A property-like descriptor for specifying a PV in a `PVGroup`.

    Parameters
    ----------
    get : async callable, optional
        Called when PV is read through channel access

    put : async callable, optional
        Called when PV is written to through channel access

    startup : async callable, optional
        Called at start of server; a hook for initialization and background
        processing

    shutdown : async callable, optional
        Called at shutdown of server; a hook for cleanup

    value : pva dataclass or instance
        The initial value - either an instantiated pva dataclass.

    name : str, optional
        The PV name (defaults to the attribute name of the pvaproperty)

    alarm_group : str, optional
        The alarm group the PV should be attached to

    read_only : bool, optional
        Read-only PV over channel access

    doc : str, optional
        Docstring associated with the property

    **cls_kwargs :
        Keyword arguments for the dataclass.

    Attributes
    ----------
    attr : str
        The attribute name of the pvaproperty.
    """

    def __init__(self,
                 get=None, put=None, startup=None, shutdown=None, call=None,
                 *,
                 value, name=None, alarm_group=None, doc=None, read_only=None,
                 **cls_kwargs):
        self.attr = None  # to be set later

        if doc is None and get is not None:
            doc = get.__doc__

        self.__doc__ = doc
        self._get = get
        self._put = put
        self._startup = startup
        self._shutdown = shutdown
        self._call = call
        self._name = name
        self._value = value
        self._alarm_group = alarm_group
        self._read_only = read_only
        self._cls_kwargs = cls_kwargs

    def __get__(self, instance, owner):
        """Descriptor method: get the pvaproperty instance from a group."""
        if instance is None:
            # `class.pvaproperty`
            return self

        return instance.attr_pvdb[self.attr]

    def __set__(self, instance, value):
        """Descriptor method: set the pvaproperty instance in a group."""
        instance.attr_pvdb[self.attr] = value

    def __delete__(self, instance):
        """Descriptor method: delete the pvaproperty instance from a group."""
        del instance.attr_pvdb[self.attr]

    def __set_name__(self, owner, name):
        """Descriptor method: auto-called to set the attribute name."""
        self.attr = name
        if self._name is None:
            self._name = name

    @property
    def name(self):
        """The pvname suffix."""
        return self._name

    @property
    def read_only(self):
        """Is the pvaproperty read-only?"""
        return self._read_only

    @property
    def cls_kwargs(self):
        """Keyword arguments to use on creation of the value instance."""
        return dict(self._cls_kwargs)

    @property
    def value(self):
        """The default value."""
        return self._value

    def getter(self, get):
        """
        Usually used as a decorator, this sets the ``getter`` method.
        """
        self._get = verify_getter(self.attr, get=get)
        return self

    def putter(self, put):
        """
        Usually used as a decorator, this sets the ``putter`` method.
        """
        self._put = verify_putter(self.attr, put=put,
                                  read_only=self._read_only)
        return self

    def startup(self, startup):
        """
        Usually used as a decorator, this sets ``startup`` method.
        """
        self._startup = verify_startup(self.attr, startup)
        return self

    def shutdown(self, shutdown):
        """
        Usually used as a decorator, this sets ``shutdown`` method.
        """
        self._shutdown = verify_shutdown(self.attr, shutdown)
        return self

    def call(self, call):
        """
        Usually used as a decorator, this sets the RPC ``call`` method.
        """
        self._call = verify_rpc_call(
            self.attr, call=call, read_only=self._read_only)
        return self

    @property
    def hooks(self):
        """All user-defined hooks."""
        return PvapropertyHooks(
            get=self._get,
            put=self._put,
            startup=self._startup,
            shutdown=self._shutdown,
            call=self._call,
        )

    def __call__(self, get, put=None, startup=None, shutdown=None):
        # Handles use case: pvaproperty(**info)(getter, putter, startup).
        raise NotImplementedError('TODO')


class PVAGroupMeta(type):
    'Metaclass that finds all pvaproperties'
    @staticmethod
    def find_pvaproperties(dct):
        for attr, value in dct.items():
            if attr.startswith('_'):
                continue

            if isinstance(value, pvaproperty):
                yield attr, value

    def __new__(metacls, name, bases, dct):
        dct['_pvs_'] = pvs = {}

        cls = super().__new__(metacls, name, bases, dct)

        # Propagate any PVs from base classes
        for base in bases:
            if hasattr(base, '_pvs_'):
                dct['_pvs_'].update(**base._pvs_)

        for attr, prop in metacls.find_pvaproperties(dct):
            module_logger.debug(
                'class %s pvaproperty attr %s: %r', name, attr, prop
            )
            pvs[attr] = prop

        # Ensure group_read/group_write are valid before proceeding:
        verify_getter('group_read', cls.group_read)
        verify_putter('group_write', cls.group_write, read_only=False)
        return cls


class PVAGroup(metaclass=PVAGroupMeta):
    """
    Class which groups a set of PVs for a high-level caproto server

    Parameters
    ----------
    prefix : str
        Prefix for all PVs in the group.

    macros : dict, optional
        Dictionary of macro name to value.

    parent : PVGroup, optional
        Parent PVGroup.

    name : str, optional
        Name for the group, defaults to the class name.
    """

    _wrapper_class_ = GroupDataWrapper

    type_map = {
        int: NTScalarInt64,
        float: NTScalarFloat64,
        str: NTScalarString,
        bool: NTScalarBoolean,
    }

    array_type_map = {
        int: NTScalarArrayInt64,
        float: NTScalarArrayFloat64,
        str: NTScalarArrayString,
        bool: NTScalarArrayBoolean,
    }

    def __init__(self, prefix, *, macros=None, parent=None, name=None):
        self.parent = parent
        self.macros = macros if macros is not None else {}
        self.prefix = prefix  # expand_macros(prefix, self.macros)
        self.pvdb = {}
        self.attr_pvdb = {}
        self.attr_to_pvname = {}
        self.groups = {}

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

    def _instantiate_value_from_pvaproperty(self, attr, prop):
        if pva.is_pva_dataclass_instance(prop.value):
            return copy.deepcopy(prop.value)

        if pva.is_pva_dataclass(prop.value):
            # TODO: not sure i like this: may be removed
            return prop.value(**prop.cls_kwargs)

        # Also preliminary array/scalar checks:
        if isinstance(prop.value, Sequence) and not isinstance(prop.value, str):
            dtype = self.array_type_map[type(prop.value[0])]
            return dtype(value=copy.copy(prop.value), **prop.cls_kwargs)

        dtype = self.type_map[type(prop.value)]
        return dtype(value=prop.value, **prop.cls_kwargs)

    def _create_pv(self, attr: str, prop: pvaproperty):
        value = self._instantiate_value_from_pvaproperty(attr, prop)
        pvname = expand_macros(self.prefix + prop.name, self.macros)
        wrapped_data = self._wrapper_class_(
            name=pvname, data=value, group=self, prop=prop)

        previous_definition = self.pvdb.get(pvname, None)
        if previous_definition is not None:
            raise DatabaseDefinitionError(
                f'{pvname} defined multiple times: now in attr: {attr} '
                f'originally: {previous_definition}'
            )

        # full pvname -> wrapped data instance
        self.pvdb[pvname] = wrapped_data

        # attribute -> PV instance mapping for quick access by pvaproperty
        self.attr_pvdb[attr] = wrapped_data

        # and a convenient map of attr -> pvname
        self.attr_to_pvname[attr] = pvname
        return wrapped_data

    def _create_pvdb(self):
        'Create the PV database for all pvaproperties'
        for attr, prop in self._pvs_.items():
            self._create_pv(attr, prop)

    async def group_read(self, instance, request):
        'Generic read called for channels without `get` defined'

    async def group_write(self, instance, update: WriteUpdate):
        'Generic write called for channels without `put` defined'
        self.log.debug('group_write: %s = %s', instance, update)


class ServerRPC(PVAGroup):
    """
    Helper group for supporting ``pvlist`` and other introspection tools.
    """

    @pva_dataclass
    class HelpInfo:
        # TODO: technically epics:nt/NTScalar
        value: str

    @pva_dataclass
    class ChannelListing:
        # TODO: technically epics:nt/NTScalarArray
        value: List[str]

    @pva_dataclass
    class ServerInfo:
        # responseHandlers.cpp
        version: str
        implLang: str
        host: str
        process: str
        startTime: str

    # This is the special
    server = pvaproperty(value=ServerInfo(), name='server')

    def __init__(self, *args, server_instance, **kwargs):
        super().__init__(*args, **kwargs)
        self.server_instance = server_instance

    @server.call
    async def server(self, instance, data):
        # Some awf... nice normative type stuff comes through here (NTURI):
        self.log.debug('RPC call data is: %s', data)
        self.log.debug('Scheme: %s', data.scheme)
        self.log.debug('Query: %s', data.query)
        self.log.debug('Path: %s', data.path)

        # Echo back the query value, if available:
        try:
            operation = data.query.op
        except AttributeError:
            raise ValueError('Malformed request (expected .query.op)')

        if operation == 'help':
            return self.HelpInfo(value='Me too')

        if operation == 'info':
            return self.ServerInfo()

        if operation == 'channels':
            pvnames = list(sorted(self.server_instance.pvdb))
            pvnames.remove(self.server.name)
            return self.ChannelListing(value=pvnames)
