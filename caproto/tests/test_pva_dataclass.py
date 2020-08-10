import logging
import textwrap
import typing

from caproto import pva
from caproto.pva._fields import FieldArrayType, FieldType  # noqa

logger = logging.getLogger(__name__)


def test_basic():
    @pva.pva_dataclass
    class TimeStamp:
        secondsPastEpoch: FieldType.int64
        nanoseconds: FieldType.int32
        userTag: FieldType.int32

    expected = textwrap.dedent(
        '''\
        struct TimeStamp
            int64 secondsPastEpoch
            int32 nanoseconds
            int32 userTag
        '''.rstrip()
    )

    print('summary')
    print(TimeStamp._pva_struct_.summary())
    print('expected')
    print(expected)

    assert TimeStamp._pva_struct_.summary() == expected
    assert TimeStamp().nanoseconds == 0


def test_basic_array():
    @pva.pva_dataclass
    class TimeStampArray:
        secondsPastEpoch: typing.List[pva.Int64]
        nanoseconds: typing.List[pva.Int32]
        userTag: typing.List[pva.Int32]

    expected = textwrap.dedent(
        '''\
        struct TimeStampArray
            int64[] secondsPastEpoch
            int32[] nanoseconds
            int32[] userTag
        '''.rstrip()
    )

    print('summary')
    print(TimeStampArray._pva_struct_.summary())
    print('expected')
    print(expected)

    assert TimeStampArray._pva_struct_.summary() == expected
    assert TimeStampArray().nanoseconds == []


def test_nesting_dataclasses():
    @pva.pva_dataclass
    class TimeStamp:
        secondsPastEpoch: FieldType.int64
        nanoseconds: FieldType.int32
        userTag: FieldType.int32

    @pva.pva_dataclass
    class Alarm:
        severity: FieldType.int32
        status: FieldType.int32
        message: FieldType.string

    @pva.pva_dataclass
    class exampleStructure:
        value: typing.List[pva.Int32]
        timeStamp: TimeStamp
        alarm: Alarm

    expected = textwrap.dedent(
        '''\
        struct exampleStructure
            int32[] value
            struct TimeStamp timeStamp
                int64 secondsPastEpoch
                int32 nanoseconds
                int32 userTag
            struct Alarm alarm
                int32 severity
                int32 status
                string message
        '''.rstrip()
    )
    # union valueUnion
    #     string stringValue
    #     int32 intValue
    #     float64 doubleValue
    # any variantUnion

    print('summary')
    print(exampleStructure._pva_struct_.summary())
    print('expected')
    print(expected)

    assert exampleStructure._pva_struct_.summary() == expected

    # Check that the defaults actually work:
    assert exampleStructure().timeStamp.nanoseconds == 0
    assert exampleStructure().alarm.message == ''


def test_union():
    @pva.pva_dataclass
    class exampleStructure:
        value: typing.Union[pva.Int32, pva.String]

    expected = textwrap.dedent(
        '''\
        struct exampleStructure
            union value
                int32 Int32
                string String
        '''.rstrip()
    )

    print('summary')
    print(exampleStructure._pva_struct_.summary())
    print('expected')
    print(expected)

    assert exampleStructure._pva_struct_.summary() == expected

    # Check that the defaults actually work:
    assert exampleStructure().value.Int32 is None
    assert exampleStructure().value.String is None
