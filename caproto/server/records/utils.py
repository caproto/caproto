import copy
import logging
import sys
from typing import Dict, Type

from ..._constants import MAX_ENUM_STRING_SIZE
from ..server import PVGroup, pvproperty

logger = logging.getLogger(__name__)
records = {}


def register_record(cls: Type[PVGroup]) -> Type[PVGroup]:
    """Register a record type to be used with pvproperty mock_record."""
    if not issubclass(cls, PVGroup):
        raise ValueError(f"Class {cls.__name__} must subclass from PVGroup.")

    records[cls._record_type] = cls
    logger.debug("Registered record type %r", cls._record_type)
    return cls


def get_record_registry() -> Dict[str, Type[PVGroup]]:
    """Get a shallow-copy of the record registry dictionary."""
    return dict(records)


def link_parent_attribute(
    pvprop: pvproperty,
    parent_attr_name: str,
    *,
    read_only: bool = False,
    use_setattr: bool = False,
    default=0,
):
    """Take a pvproperty and link its getter/putter to a parent attribute."""

    @pvprop.getter
    async def getter(self, instance):
        return getattr(self.parent, parent_attr_name, default)

    if not read_only:
        if use_setattr:

            @pvprop.putter
            async def putter(self, instance, value):
                if hasattr(self.parent, parent_attr_name):
                    setattr(self.parent, parent_attr_name, value)

        else:

            @pvprop.putter
            async def putter(self, instance, value):
                kw = {parent_attr_name: value}
                await self.parent.write_metadata(**kw)

    return pvprop


def link_enum_strings(pvprop: pvproperty, index: int):
    """Take a pvproperty and link its parent enum_strings[index]."""

    @pvprop.getter
    async def getter(self, instance):
        try:
            return self.parent.enum_strings[index]
        except IndexError:
            return ""

    @pvprop.putter
    async def putter(self, instance, value):
        enum_strings = list(self.parent.enum_strings)

        if index >= len(enum_strings):
            missing_count = index - len(enum_strings) + 1
            enum_strings = enum_strings + [""] * missing_count

        old_enum = enum_strings[index]
        enum_strings[index] = str(value)[: MAX_ENUM_STRING_SIZE - 1]

        await self.parent.write_metadata(enum_strings=enum_strings)
        if self.parent.value in (old_enum, index):
            await self.parent.write(value=index)

    return pvprop


def summarize(file=sys.stdout):
    """Summarize all supported records and their fields to a file."""
    from .base import RecordFieldGroup

    all_records = [("base", RecordFieldGroup)] + list(records.items())

    def to_string(s):
        if callable(s):
            return "callable/" + s.__name__
        return repr(s)

    base_fields = {
        pvprop.pvspec.name for attr, pvprop in RecordFieldGroup._pvs_.items()
    }

    for record, rclass in all_records:
        info = [record, [cls.__name__ for cls in rclass.mro()]]
        print("\t".join(to_string(s) for s in info), file=file)
        for attr, pvprop in rclass._pvs_.items():
            if record != "base" and pvprop.pvspec.name in base_fields:
                continue

            kwargs = (
                f"{key}={value}".format(key, value)
                for key, value in sorted(pvprop.pvspec.cls_kwargs.items())
            )
            info = [attr] + list(pvprop.pvspec) + list(kwargs)
            print("\t".join(to_string(s) for s in info), file=file)
        print(file=file)


def copy_pvproperties(locals_dict, *classes):
    """Copy pvproperties from the given classes into the locals() namespace."""
    locals_dict.update({
        attr: copy.copy(pvprop)
        for cls in classes
        for attr, pvprop in cls._pvs_.items()
    })


__all__ = [
    "copy_pvproperties",
    "get_record_registry",
    "link_enum_strings",
    "link_parent_attribute",
    "records",
    "register_record",
    "summarize",
]
