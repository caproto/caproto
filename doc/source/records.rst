*******
Records
*******

.. currentmodule:: caproto.server.records

These Python classes make it easy to run IOCs that have the record and field
layout and linking of common EPICS database records. The source code of these
"mock records" was auto-generated from the reference implementations. See the
:ref:`mocking_records_example` example for usage.

{% for item in mocked_records | sort(attribute='sort_index') %}
{%- set cls = caproto.server.records.records[item.record_name] -%}
.. class:: {{ item.class_name }}

{% if item.record_name == 'base' %}
    This is a PVGroup class used to represent the basic fields from any given
    EPICS record.  It does not implement the full functionality of that record,
    but effectively "mocks" up all of the fields for availability over channel
    access.

    .. note:: The classes shown here are not meant to be instantiated directly, but
               rather used as a ``mock_record=`` keyword argument in a
               :class:`pvproperty`.
{% else %}
    .. note:: To use this, specify ``mock_record="{{item.record_name}}"`` in a
              :class:`pvproperty`.
{% endif %}
    {{ item.pv_table |indent(4) }}

{% endfor %}
