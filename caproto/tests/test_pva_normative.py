import logging
import typing

import pytest

pytest.importorskip('caproto.pva')

from caproto import pva  # isort: skip
from caproto.pva._normative import (NormativeTypeName, NTScalarArrayBase,
                                    NTScalarBase)

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


def test_subclasscheck_array():
    @pva.pva_dataclass(name=NormativeTypeName('NTScalarArray').struct_name)
    class NTScalarArrayInt64Test:
        value: typing.List[pva.Int64]
        descriptor: str

    # While these are not direct subclasses, they are normative type
    # equivalents:
    assert issubclass(NTScalarArrayInt64Test, NTScalarArrayBase)
    assert issubclass(NTScalarArrayInt64Test, pva.NTScalarArrayInt64)

    assert isinstance(NTScalarArrayInt64Test(), NTScalarArrayBase)
    assert isinstance(NTScalarArrayInt64Test(), pva.NTScalarArrayInt64)
