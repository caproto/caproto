{{ fullname | escape | underline}}

{%- macro method_info(attr, obj) -%}

    {%- set docstring = inspect.getdoc(obj) or '' %}
    {%- set source_file = inspect.getsourcefile(obj) %}
    {%- set code, start_line = inspect.getsourcelines(obj) %}
    {%- set dedent = path.commonprefix(code)|length %}
    {%- set end_line = start_line + code|length - 1 %}

    {%- set relative_filename = path.join('/', project_root, path.relpath(source_file, start='.')) %}
    {%- if docstring %}
    {{ docstring | indent(8) }}
    {% endif %}

    {% if (code | length) > inline_code_threshold %}
    .. raw:: html

        <details>
        <summary>Source code: {{ attr }}</summary>

    {% endif %}

    {%- if source_file %}
    .. literalinclude:: {{ relative_filename }}
        :language: python
        :linenos:
        :dedent: {{dedent}}
        :lineno-start: {{start_line}}
        :lines: {{start_line}}-{{end_line}}

    {%- endif %}

    {%- if (code | length) > inline_code_threshold %}

    .. raw:: html

        </details>
        <br/>

    {% endif %}

{%- endmacro %}


.. currentmodule:: {{ module }}

.. inheritance-diagram:: {{ objname }}

.. autoclass:: {{ objname }}

    .. if not using autodoc, add this here: automethod:: __init__

    {% set pvgroup_info = get_pvgroup_info(module, objname) %}

    {% if pvgroup_info.record_name %}
    {% if pvgroup_info.record_name == 'base' %}
        This is a PVGroup class used to represent the basic fields from any given
        EPICS record.

        .. note:: The classes shown here are not meant to be instantiated
                  directly, but rather used as a ``record=`` keyword argument
                  in a :class:`pvproperty`.
    {% else %}
        .. note:: To use this, specify
                  ``record="{{pvgroup_info.record_name}}"`` in a
                  :class:`pvproperty`.
    {% endif %}
    {% endif %}

    {% block pvproperties %}
    {% if pvgroup_info.pvproperty %}
    .. list-table:: {{ objname }} pvproperties
        :header-rows: 1
        :widths: auto

        *  - Attribute
           - Suffix
           - Docs
           - Type
           - Notes
           - Alarm Group
    {% for attr, prop in pvgroup_info.pvproperty.items() %}
        *  - {{ attr }}
           - {% if prop.name %}``{{ prop.name }}``{% endif %}
           - {{ prop.doc }}
           - {{ prop.dtype_name }} {% if prop.record_type -%}
             ({{ prop.record_type.cls.link_as(prop.record_type.record_name) }})
             {%- endif %}
           - {% if prop.read_only %}
                 **Read-only**
             {%- endif -%}
             {%- if prop.max_length and prop.max_length > 1 %}
                 Length({{ prop.max_length }})
             {%- endif %}
             {%- if prop.inherited_from %}
                 Inherited from {{ prop.inherited_from.link }}
             {%- endif %}
             {%- if prop.startup %}
                 **Startup**
             {%- endif %}
             {%- if prop.shutdown %}
                 **Shutdown**
             {%- endif %}
             {%- if prop.getter %}
                 **Get**
             {%- endif %}
             {%- if prop.putter %}
                 **Put**
             {%- endif %}
             {%- if prop._call %}
                 **RPC**
             {%- endif %}
           - {% if prop.alarm_group -%}
                 {{ prop.alarm_group }}
             {% endif %}
    {% endfor %}
    {% endif %}

    {% if pvgroup_info.subgroup %}
    .. list-table:: Sub-groups
        :header-rows: 1
        :widths: auto

        *  - Attribute
           - Suffix
           - Class
           - Docs
    {% for attr, sub in pvgroup_info.subgroup.items() %}
        *  -  {{ sub.attr }}
           -  {% if sub.prefix %}``{{ sub.prefix }}``{% endif %}
           -  {{ sub.cls.link }}
           -  {{ sub.doc }}
    {% endfor %}
    {% endif %}
    {% endblock %}

    {% block methods %}
    {% if methods %}
    .. rubric:: {{ _('Methods') }}

    .. autosummary::
    {% for item in methods %}
       ~{{ name }}.{{ item }}
    {%- endfor %}
    {% endif %}
    {% endblock %}

    {% block attributes %}
    {% if attributes %}
    .. rubric:: {{ _('Attributes') }}

    .. autosummary::

    {% for item in attributes %}
       ~{{ name }}.{{ item }}
    {%- endfor %}

    {%- endif %}
    {% endblock %}

    {% block pvprop_methods %}
    {%- if pvgroup_info.pvproperty %}
    .. rubric:: pvproperty methods

    {%- for attr, prop in pvgroup_info.pvproperty.items() %}
    {%- if prop.startup %}
    .. method:: {{ attr }}.startup(self, instance, async_lib)
        {{ method_info(attr + '.startup', prop.startup) }}

    {%- endif %}
    {%- if prop.shutdown %}
    .. method:: {{ attr }}.shutdown(self, instance, async_lib)
        {{ method_info(attr + '.shutdown', prop.shutdown) }}

    {%- endif %}
    {%- if prop.getter %}
    .. method:: {{ attr }}.getter(self, instance)
        {{ method_info(attr + '.getter', prop.getter) }}

    {%- endif %}
    {%- if prop.put %}
    .. method:: {{ attr }}.putter(self, instance, value)
        {{ method_info(attr + '.putter', prop.putter) }}

    {%- endif %}
    {%- if prop.rpc %}
    .. method:: {{ attr }}.call(self, instance, value)
        {{ method_info(attr + '.rpc', prop.rpc) }}

    {%- endif %}
    {%- endfor %}
    {%- endif %}
    {%- endblock %}
