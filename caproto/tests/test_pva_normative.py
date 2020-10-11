import logging

import pytest

pytest.importorskip('caproto.pva')

from caproto import pva  # isort: skip
from caproto.pva._normative import NTScalarBase, alarm_t, nt_name, time_t

logger = logging.getLogger(__name__)


def test_subclasscheck():
    @pva.pva_dataclass(name=nt_name('NTScalar'))
    class NTScalarInt64Test:
        value: pva.Int64
        descriptor: str
        alarm: alarm_t
        timeStamp: time_t

    # While these are not direct subclasses, they are normative type
    # equivalents:
    assert issubclass(NTScalarInt64Test, NTScalarBase)
    assert issubclass(NTScalarInt64Test, pva.NTScalarInt64)

    assert isinstance(NTScalarInt64Test(), NTScalarBase)
    assert isinstance(NTScalarInt64Test(), pva.NTScalarInt64)
