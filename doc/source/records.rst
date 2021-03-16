.. _records_section:

*******
Records
*******

.. currentmodule:: caproto.server.records

These Python classes make it easy to run IOCs that have the record and field
layout of common EPICS database records. The source code of these "records" was
auto-generated from a reference implementation available `here
<https://github.com/caproto/reference-dbd>`_.

Please note that none of the classes listed here implement the full
functionality of the corresponding record, but make available over Channel
Access all of the fields one would normally expect from that record.

See the :ref:`records_example` example for usage.


.. list-table:: Records
   :header-rows: 1

   * - Record type
     - Field Class
   * - aSub
     - :class:`.AsubFields`
   * - aai
     - :class:`.AaiFields`
   * - aao
     - :class:`.AaoFields`
   * - ai
     - :class:`.AiFields`
   * - ao
     - :class:`.AoFields`
   * - asyn
     - :class:`.AsynFields`
   * - bi
     - :class:`.BiFields`
   * - bo
     - :class:`.BoFields`
   * - calc
     - :class:`.CalcFields`
   * - calcout
     - :class:`.CalcoutFields`
   * - compress
     - :class:`.CompressFields`
   * - dfanout
     - :class:`.DfanoutFields`
   * - event
     - :class:`.EventFields`
   * - fanout
     - :class:`.FanoutFields`
   * - histogram
     - :class:`.HistogramFields`
   * - int64in
     - :class:`.Int64inFields`
   * - int64out
     - :class:`.Int64outFields`
   * - longin
     - :class:`.LonginFields`
   * - longout
     - :class:`.LongoutFields`
   * - lsi
     - :class:`.LsiFields`
   * - lso
     - :class:`.LsoFields`
   * - mbbi
     - :class:`.MbbiFields`
   * - mbbiDirect
     - :class:`.MbbidirectFields`
   * - mbbo
     - :class:`.MbboFields`
   * - mbboDirect
     - :class:`.MbbodirectFields`
   * - motor
     - :class:`.MotorFields`
   * - permissive
     - :class:`.PermissiveFields`
   * - printf
     - :class:`.PrintfFields`
   * - sel
     - :class:`.SelFields`
   * - seq
     - :class:`.SeqFields`
   * - state
     - :class:`.StateFields`
   * - stringin
     - :class:`.StringinFields`
   * - stringout
     - :class:`.StringoutFields`
   * - sub
     - :class:`.SubFields`
   * - subArray
     - :class:`.SubarrayFields`
   * - waveform
     - :class:`.WaveformFields`

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
