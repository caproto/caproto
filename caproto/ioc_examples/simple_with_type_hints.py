#!/usr/bin/env python3
from textwrap import dedent

from caproto.server import PVGroup
from caproto.server import PvpropertyDouble as Double
from caproto.server import PvpropertyDoubleRO as DoubleRO
from caproto.server import PvpropertyInteger as Integer
from caproto.server import ioc_arg_parser, pvproperty, run
from caproto.server.records import AiFields


class SimpleIOC(PVGroup):
    """
    An IOC with three uncoupled read/writable PVs.

    Scalar PVs
    ----------
    A (int)
    B (float)
        Read-only double.

    Array PVs
    ---------
    C (array of int)
    """
    # With support for specifying the dtype directly with the PvpropertyData
    # class type, we can now let our static analyzer help us a bit with
    # making caproto IOCs.  Here's a sample pvproperty that uses
    # PvpropertyInteger instead of the old ``int``:
    A = pvproperty(value=1, dtype=Integer, doc="An integer")

    # Here we have a read-only double type.
    B = pvproperty(
        value=2.0,
        dtype=DoubleRO,
        doc="A read-only floating point value"
    )

    # And an array of Integer:
    C = pvproperty(
        value=[1, 2, 3],
        dtype=Integer,
        doc="An array of integers (max length 3)"
    )

    # If you want to add on fields to make it behave like an EPICS record, use
    # the appropriate Fields class for your record.  Here, for example, we
    # want an "analog input record" (ai) so we choose AiFields.
    # In order to get type annotations working for all field names in the class
    # body and also with the instantiated PVGroup:
    D = pvproperty(
        value=4.5,
        dtype=Double[AiFields],
        record=AiFields,
        doc="A floating point value with ai record fields"
    )

    # With ``record=AiFields`` above, you should be able to use the following
    # syntax here in the class body to add on putter methods for fields:
    # @D.fields.access_security_group.putter

    # If you use mypy, you could use the following in this class definition:
    # reveal_locals()
    # Then running mypy will eventually show - among oa ton of errors -
    # $ mypy simple_with_type_hints.py --follow-imports=silent
    # ...
    # simple_with_type_hints.py:63: note:     A: pvproperty[PvpropertyInteger[Any], Any]
    # simple_with_type_hints.py:63: note:     B: pvproperty[PvpropertyDoubleRO[Any], Any]
    # simple_with_type_hints.py:63: note:     C: pvproperty[PvpropertyInteger[Any], Any]
    # simple_with_type_hints.py:63: note:     D: pvproperty[PvpropertyDouble*[AiFields*], AiFields*]


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='simple:',
        desc=dedent(SimpleIOC.__doc__))

    ioc = SimpleIOC(**ioc_options)
    print("A is", ioc.A.data_type)
    print("B is", ioc.B.data_type)
    print("C is", ioc.C.data_type)

    # With ``dtype=Double[AiFields]`` above, you should be able to infer the
    # correct attributes for the "field instance" on ``ioc.D`` that contains
    # all of the 'ai' record fields:
    print("D is", ioc.D.data_type)
    print("record type", ioc.D.field_inst.record_type.value)
    print("A field from RecordFieldGroup:", ioc.D.field_inst.access_security_group)
    print("A field from AiFields", ioc.D.field_inst.raw_offset)

    run(ioc.pvdb, **run_options)
