import logging

import pytest

pytest.importorskip('caproto.pva')

from caproto import pva  # isort: skip
from caproto.pva._normative import NormativeTypeName, NTScalarBase

logger = logging.getLogger(__name__)


def test_subclasscheck():
    @pva.pva_dataclass(name=NormativeTypeName('NTScalar').struct_name)
    class NTScalarInt64Test:
        value: pva.Int64
        descriptor: str

    # While these are not direct subclasses, they are normative type
    # equivalents:
    assert issubclass(NTScalarInt64Test, NTScalarBase)
    assert issubclass(NTScalarInt64Test, pva.NTScalarInt64)

    assert isinstance(NTScalarInt64Test(), NTScalarBase)
    assert isinstance(NTScalarInt64Test(), pva.NTScalarInt64)
