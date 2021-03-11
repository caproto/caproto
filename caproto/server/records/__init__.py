from . import utils  # isort: skip
from .records import *  # noqa  # isort: skip

# Back-compat:
# The record registry itself:
records = utils.records
register_record = utils.register_record
# Linking tools:
_link_parent_attribute = utils.link_parent_attribute
_link_enum_strings = utils.link_enum_strings

get_record_registry = utils.get_record_registry
summarize = utils.summarize

__all__ = [
    "records",
    "RecordFieldGroup",
    "register_record",
    "get_record_registry",
    "summarize",
] + list(get_record_registry())
