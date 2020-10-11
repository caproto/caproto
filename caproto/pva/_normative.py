# TODO: class-based definitions + usual introspection abilities as well?
# TODO: NTValue class which helps handle a structured value of an NTType?

import dataclasses
import logging
from typing import Tuple, Type

from ._annotations import Int32, Int64
from ._dataclass import (get_pv_structure, is_pva_dataclass,
                         is_pva_dataclass_instance, pva_dataclass)
from ._fields import FieldType

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class NormativeTypeName:
    type_name: str
    namespace: str = 'epics:nt'
    version_number: str = '1.0'

    @property
    def struct_name(self):
        """The packed, single-string name."""
        return f'{self.namespace}/{self.type_name}:{self.version_number}'

    @classmethod
    def from_struct_name(cls, struct_name) -> 'NormativeTypeName':
        """Split a normative type struct_name into its parts."""
        namespace, type_and_version = struct_name.split('/', 1)
        type_name, version = type_and_version.rsplit(':', 1)
        return NormativeTypeName(
            namespace=namespace,
            type_name=type_name,
            version=version,
        )


class _NTMeta(type):
    def __instancecheck__(cls, instance):
        if not is_pva_dataclass_instance(instance):
            return False

        return issubclass(type(instance), cls)

    def __subclasscheck__(cls, subclass):
        # 1. Ensure it's a dataclass
        if not is_pva_dataclass(subclass):
            return False

        # 2. Ensure it's an epics:nt/...:1.0
        try:
            st = get_pv_structure(subclass)
            type_name = NormativeTypeName.from_struct_name(st.struct_name)['type_name']
            if type_name != cls._base_type_name_:
                return False
        except Exception:
            return False

        # 3. Check the value type
        value_type = cls._value_type_
        if value_type is None:
            # Checking against NTScalarBase
            return 'value' in st.children

        try:
            return value_type == st.children['value'].field_type
        except Exception:
            return False


class NTScalarBase(metaclass=_NTMeta):
    _base_type_name_ = 'NTScalar'
    _value_type_ = None


@pva_dataclass(name='time_t')
class NTTimestamp:
    secondsPastEpoch: Int64
    nanoseconds: Int32
    userTag: Int32


@pva_dataclass(name='alarm_t')
class NTAlarm:
    severity: Int32
    status: Int32
    message: str


def _create_nt_scalar(name: str,
                      field_type: FieldType
                      ) -> Tuple[Type[NTScalarBase], Type[NTScalarBase]]:
    """
    Creates two classes - a base normative scalar type and a "full" one.

    Parameters
    ----------
    name : str
        The "full" class name.

    field_type : FieldType
        The primitive type for "value" to hold.

    Example
    -------

    Example return value, based on a name of "NTScalarInt64", and a field_type
    of FieldType.int64:

        @pva_dataclass(name='epics:nt/NTScalar:1.0')
        class NTScalarInt64Base(NTScalarInt64Base):
            value: int64

        @pva_dataclass(name='epics:nt/NTScalar:1.0')
        class NTScalarInt64(NTScalarInt64Base):
            descriptor: str
            alarm: NTAlarm
            timeStamp: NTTimestamp
            display: generated_display_t
            control: generated_control_t

    """

    base_dict = {
        '_value_type_': field_type,
        '__annotations__': {
            'value': field_type,
        }
    }

    wrapper = pva_dataclass(name=NormativeTypeName('NTScalar').struct_name)
    base_cls = wrapper(type(f'{name}Base', (NTScalarBase, ), base_dict))

    if field_type.is_numeric:
        @pva_dataclass(name='display_t')
        class DisplayStruct:
            limitLow: field_type
            limitHigh: field_type
            description: str
            format: str
            units: str
    else:
        @pva_dataclass(name='display_t')
        class DisplayStruct:
            # limitLow: field_type
            # limitHigh: field_type
            description: str
            format: str
            units: str

    @pva_dataclass(name='control_t')
    class ControlStruct:
        limitLow: field_type
        limitHigh: field_type
        minStep: field_type

    @pva_dataclass(name='valueAlarm_t')
    class ValueAlarmStruct:
        active: FieldType.boolean
        lowAlarmLimit: field_type
        lowWarningLimit: field_type
        highWarningLimit: field_type
        highAlarmLimit: field_type
        lowAlarmSeverity: FieldType.int32
        lowWarningSeverity: FieldType.int32
        highWarningSeverity: FieldType.int32
        highAlarmSeverity: FieldType.int32
        hysteresis: FieldType.float64

    annotations = {
        # 'value': field_type,
        'descriptor': str,
        'alarm': NTAlarm,
        'timeStamp': NTTimestamp,
        'display': DisplayStruct,
        'control': ControlStruct,
        'valueAlarm': ValueAlarmStruct,
    }

    if not field_type.is_numeric:
        annotations.pop('control')

    full_dict = {
        '__annotations__': annotations,
    }

    full_cls = wrapper(type(name, (base_cls, ), full_dict))
    return base_cls, full_cls


NTScalarInt64Base, NTScalarInt64 = _create_nt_scalar('NTScalarInt64', FieldType.int64)
