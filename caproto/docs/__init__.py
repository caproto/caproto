"""
Documentation helpers that can be used in packages relying on caproto servers.

Example
-------

.. code::

    import caproto.docs

    def setup(app):
        caproto.docs.setup(app)

    templates_path = [caproto.docs.templates.PATH]

    autosummary_context = {
        **caproto.docs.autosummary_context,
    }
    html_context = {
        'caproto': caproto,
        'records': caproto.docs.get_all_records(),
    }
"""

from . import templates
from .utils import (autodoc_default_options, autosummary_context,
                    get_all_records, get_pvgroup_info, get_record_info, setup)

__all__ = [
    'autosummary_context',
    'autodoc_default_options',
    'get_all_records',
    'get_pvgroup_info',
    'get_record_info',
    'setup',
    'templates',
]
