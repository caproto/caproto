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

See the :ref:`_records_example` example for usage.

{% for item in records | sort(attribute='sort_index') %}
{%- set cls = caproto.server.records.records[item.record_name] -%}
.. class:: {{ item.class_name }}

{% if item.record_name == 'base' %}
    This is a PVGroup class used to represent the basic fields from any given
    EPICS record.

    .. note:: The classes shown here are not meant to be instantiated directly, but
               rather used as a ``record=`` keyword argument in a
               :class:`pvproperty`.
{% else %}
    .. note:: To use this, specify ``record="{{item.record_name}}"`` in a
              :class:`pvproperty`.
{% endif %}
    {{ item.pv_table |indent(4) }}

{% endfor %}
