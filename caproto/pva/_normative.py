import dataclasses
import logging
from typing import List, Optional, Tuple, Type

from ._annotations import Int32, Int64, type_to_annotation
from ._dataclass import (get_pv_structure, is_pva_dataclass,
                         is_pva_dataclass_instance, pva_dataclass)
from ._fields import FieldType

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class NormativeTypeName:
    type_name: str
    namespace: str = 'epics:nt'
    version: str = '1.0'

    @property
    def struct_name(self):
        """The packed, single-string name."""
        return f'{self.namespace}/{self.type_name}:{self.version}'

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
            nt_name = NormativeTypeName.from_struct_name(st.struct_name)
            if nt_name.type_name != cls._base_type_name_:
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


class NTScalarArrayBase(metaclass=_NTMeta):
    _base_type_name_ = 'NTScalarArray'
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


def _create_nt(name: str,
               field_type: FieldType,
               array: Optional[bool] = False,
               ) -> Tuple[Type[NTScalarBase], Type[NTScalarBase]]:
    """
    Creates two classes - a base normative scalar type and a "full" one.

    Parameters
    ----------
    name : str
        The "full" class name.

    field_type : FieldType
        The primitive type for "value" to hold.

    array : bool, optional
        Create an array type?

    Example
    -------

    Example return value, based on a name of "NTScalarInt64", and a field_type
    of FieldType.int64:

        @pva_dataclass(name='epics:nt/NTScalar:1.0')
        class NTScalarInt64Base(NTScalarBase):
            value: int64

        @pva_dataclass(name='epics:nt/NTScalar:1.0')
        class NTScalarInt64(NTScalarInt64Base):
            descriptor: str
            alarm: NTAlarm
            timeStamp: NTTimestamp
            display: generated_display_t
            control: generated_control_t

    """

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

    base_dict = {
        '_value_type_': field_type,
        '__annotations__': {
            'value': List[type_to_annotation[field_type]] if array else field_type,
        }
    }

    wrapper = pva_dataclass(
        name=NormativeTypeName('NTScalarArray' if array else 'NTScalar').struct_name
    )
    bases = (NTScalarBase if not array else NTScalarArrayBase, )
    base_cls = wrapper(type(f'{name}Base', bases, base_dict))

    full_dict = {
        '__annotations__': {
            **base_dict['__annotations__'],
            'descriptor': str,
            'alarm': NTAlarm,
            'timeStamp': NTTimestamp,
            'display': DisplayStruct,
            'control': ControlStruct,
            'valueAlarm': ValueAlarmStruct,
        },
    }

    if not field_type.is_numeric:
        full_dict['__annotations__'].pop('control')

    full_cls = wrapper(type(name, (base_cls, ), full_dict))
    return base_cls, full_cls


# Create these explicitly for easy grepping:
NTScalarBooleanBase, NTScalarBoolean = _create_nt('NTScalarBoolean', FieldType.boolean)
NTScalarFloat128Base, NTScalarFloat128 = _create_nt('NTScalarFloat128', FieldType.float128)
NTScalarFloat16Base, NTScalarFloat16 = _create_nt('NTScalarFloat16', FieldType.float16)
NTScalarFloat32Base, NTScalarFloat32 = _create_nt('NTScalarFloat32', FieldType.float32)
NTScalarFloat64Base, NTScalarFloat64 = _create_nt('NTScalarFloat64', FieldType.float64)
NTScalarInt16Base, NTScalarInt16 = _create_nt('NTScalarInt16', FieldType.int16)
NTScalarInt32Base, NTScalarInt32 = _create_nt('NTScalarInt32', FieldType.int32)
NTScalarInt64Base, NTScalarInt64 = _create_nt('NTScalarInt64', FieldType.int64)
NTScalarInt64Base, NTScalarInt64 = _create_nt('NTScalarInt64', FieldType.int64)
NTScalarInt8Base, NTScalarInt8 = _create_nt('NTScalarInt8', FieldType.int8)
NTScalarStringBase, NTScalarString = _create_nt('NTScalarString', FieldType.string)
NTScalarUInt16Base, NTScalarUInt16 = _create_nt('NTScalarUInt16', FieldType.uint16)
NTScalarUInt32Base, NTScalarUInt32 = _create_nt('NTScalarUInt32', FieldType.uint32)
NTScalarUInt64Base, NTScalarUInt64 = _create_nt('NTScalarUInt64', FieldType.uint64)
NTScalarUInt8Base, NTScalarUInt8 = _create_nt('NTScalarUInt8', FieldType.uint8)

NTScalarArrayBooleanBase, NTScalarArrayBoolean = _create_nt(
    'NTScalarArrayBoolean', FieldType.boolean, array=True)
NTScalarArrayFloat128Base, NTScalarArrayFloat128 = _create_nt(
    'NTScalarArrayFloat128', FieldType.float128, array=True)
NTScalarArrayFloat16Base, NTScalarArrayFloat16 = _create_nt(
    'NTScalarArrayFloat16', FieldType.float16, array=True)
NTScalarArrayFloat32Base, NTScalarArrayFloat32 = _create_nt(
    'NTScalarArrayFloat32', FieldType.float32, array=True)
NTScalarArrayFloat64Base, NTScalarArrayFloat64 = _create_nt(
    'NTScalarArrayFloat64', FieldType.float64, array=True)
NTScalarArrayInt16Base, NTScalarArrayInt16 = _create_nt(
    'NTScalarArrayInt16', FieldType.int16, array=True)
NTScalarArrayInt32Base, NTScalarArrayInt32 = _create_nt(
    'NTScalarArrayInt32', FieldType.int32, array=True)
NTScalarArrayInt64Base, NTScalarArrayInt64 = _create_nt(
    'NTScalarArrayInt64', FieldType.int64, array=True)
NTScalarArrayInt64Base, NTScalarArrayInt64 = _create_nt(
    'NTScalarArrayInt64', FieldType.int64, array=True)
NTScalarArrayInt8Base, NTScalarArrayInt8 = _create_nt(
    'NTScalarArrayInt8', FieldType.int8, array=True)
NTScalarArrayStringBase, NTScalarArrayString = _create_nt(
    'NTScalarArrayString', FieldType.string, array=True)
NTScalarArrayUInt16Base, NTScalarArrayUInt16 = _create_nt(
    'NTScalarArrayUInt16', FieldType.uint16, array=True)
NTScalarArrayUInt32Base, NTScalarArrayUInt32 = _create_nt(
    'NTScalarArrayUInt32', FieldType.uint32, array=True)
NTScalarArrayUInt64Base, NTScalarArrayUInt64 = _create_nt(
    'NTScalarArrayUInt64', FieldType.uint64, array=True)
NTScalarArrayUInt8Base, NTScalarArrayUInt8 = _create_nt(
    'NTScalarArrayUInt8', FieldType.uint8, array=True)
