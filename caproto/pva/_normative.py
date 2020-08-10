# TODO: class-based definitions + usual introspection abilities as well?
# TODO: NTValue class which helps handle a structured value of an NTType?

import logging

from ._core import FieldType
from ._dataclass import PvaStruct, pva_dataclass

logger = logging.getLogger(__name__)


@pva_dataclass
class time_t:
    secondsPastEpoch: FieldType.long = 0
    nanoseconds: FieldType.int32 = 0
    userTag: FieldType.int32 = 0


@pva_dataclass
class alarm_t:
    severity: FieldType.int32 = 0
    status: FieldType.int32 = 0
    message: FieldType.string = ''


@pva_dataclass
class display_t:
    limitLow: FieldType.double = 0.0  # TODO: type depends on value (isnumeric)
    limitHigh: FieldType.double = 0.0  # TODO: type depends on value
    description: FieldType.string = ''
    format: FieldType.string = ''
    units: FieldType.string = ''


@pva_dataclass
class control_t:
    limitLow: FieldType.double = 0.0
    limitHigh: FieldType.double = 0.0
    minStep: FieldType.double = 0.0


class combined(metaclass=PvaStruct):
    time: time_t
    alarm: alarm_t
    display: display_t
    control: control_t


# ? epics:nt/NTScalar:1.0
# ? epics:nt/NTScalarArray:1.0
# value
# alarm_t
# time_t
# display_t
# control_t
# value alarm?
