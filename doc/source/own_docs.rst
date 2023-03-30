******************************
Writing Your Own Documentation
******************************


caproto provides some Sphinx and autodoc/autosummary-based helpers to aid users
in the creation of their own (PVGroup-based) IOC documentation.

Sample conf.py
==============

An HTML-centric conf.py may look like the following:

.. literalinclude:: example_conf.py
    :linenos:


Any and all of this can be customized.  Users may also copy the templates
out of caproto, though any improvements to these templates are always welcome
in caproto itself.

Sample requirements-docs.txt
============================

Building your documentation will require extra dependencies that aren't
necessary to run your package, most likely.  The caproto developers recommend
creating a separate requirements file that can be installed by way of ``pip``
or ``conda`` (i.e., ``pip install --requirement requirements-docs.txt`` or
``conda install --file requirements-docs.txt``).

.. literalinclude:: example_requirements-docs.txt

``docs-versions-menu`` is useful for building versioned documentation targeting
GitHub pages using continuous integration.  It is unnecessary if you will only
be building documentation locally or only care about the latest release
documentation.


Using autosummary
=================

.. literalinclude:: example_autosummary.txt
    :linenos:
