*******
Records
*******

.. currentmodule:: caproto.server.records

These Python classes make it easy to run IOCs that have the record and field
layout and linking of common EPICS database records. The source code of these
"records" was auto-generated from a reference implementation available `here
<https://github.com/caproto/reference-dbd>`_.

Please note that none of the classes listed here implement the full
functionality of the corresponding record, but make available over Channel
Access all of the fields one would normally expect from that record.

See the :ref:`records_example` example for usage.

.. autosummary::
    :toctree: generated

    register_record
    RecordFieldGroup
    AiFields
    AsubFields
    AaiFields
    AaoFields
    AoFields
    AsynFields
    BiFields
    BoFields
    CalcFields
    CalcoutFields
    CompressFields
    DfanoutFields
    EventFields
    FanoutFields
    HistogramFields
    LonginFields
    LongoutFields
    MbbiFields
    MbbidirectFields
    MbboFields
    MbbodirectFields
    MotorFields
    PermissiveFields
    SelFields
    SeqFields
    StateFields
    StringinFields
    StringoutFields
    SubFields
    SubarrayFields
    WaveformFields
    Int64inFields
    Int64outFields
    LsiFields
    LsoFields
    PrintfFields
    summarize
