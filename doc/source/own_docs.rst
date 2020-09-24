******************************
Writing Your Own Documentation
******************************


caproto provides some Sphinx and autodoc/autosummary-based helpers to aid users
in the creation of their own (PVGroup-based) IOC documentation.

Sample conf.py
==============

An HTML-centric conf.py may look like the following:

.. literalinclude:: example_conf.py

Any and all of this can be customized.  Users may also copy the templates
out of caproto, though any improvements to these templates are always welcome
in caproto itself.


Using autosummary
=================

.. literalinclude:: example_autosummary.txt
