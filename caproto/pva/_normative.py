# TODO: class-based definitions + usual introspection abilities as well?
# TODO: NTValue class which helps handle a structured value of an NTType?

import logging

from ._annotations import Float64, Int32, Int64
from ._dataclass import pva_dataclass

logger = logging.getLogger(__name__)


@pva_dataclass
class time_t:
    secondsPastEpoch: Int64
    nanoseconds: Int32
    userTag: Int32


@pva_dataclass
class alarm_t:
    severity: Int32 = Int32(0)
    status: Int32
    message: str


@pva_dataclass
class display_t:
    limitLow: Float64  # TODO: type depends on value (isnumeric)
    limitHigh: Float64  # TODO: type depends on value
    description: str
    format: str
    units: str


@pva_dataclass
class control_t:
    limitLow: Float64
    limitHigh: Float64
    minStep: Float64


# class combined(metaclass=PvaStruct):
#     time: time_t
#     alarm: alarm_t
#     display: display_t
#     control: control_t


# ? epics:nt/NTScalar:1.0
# ? epics:nt/NTScalarArray:1.0
# value
# alarm_t
# time_t
# display_t
# control_t
# value alarm?
