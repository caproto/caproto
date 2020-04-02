'''
This module repurposes the dbd linter from pyPDB (*) to parse EPICS database
definition files and give information about records.

(*) Available on conda-forge as epics-pypdb
'''
import ast
import copy
import pathlib

import caproto
import pytest
import pyPDB.dbd.ast
import pyPDB.dbd.yacc as _yacc
import pyPDB.dbdlint as _dbdlint


class DbdFile:
    '''
    Container for dbdlint results, with easier-to-access attributes

    Extends pyPDB.dbdlint.Results

    Each error or warning has dictionary keys::

        {name, message, file, line, raw_message, format_args}

    Attributes
    ----------
    errors : list
        List of errors found
    warnings : list
        List of warnings found
    '''

    def __init__(self):
        self.whole = True
        self._node = None
        self.stack = []

        # These are set by the dbdlint walk step
        self.rectypes = {}
        self.recdsets = {}
        self.recinst = {}  # {'inst:name':'ao', ...}
        self.extinst = set()
        self.field_metadata = {}

        self.errors = []
        self.warnings = []

    @property
    def node(self):
        'The current node being evaluated'
        return self._node

    @node.setter
    def node(self, node):
        self._node = node

        if getattr(node, 'name', '') == 'field':
            # A hack to aggregate information about fields, using the node
            # setattr as a callback.  If there's an easier way, let me know...
            self._walk_field(node)

    def _walk_field(self, node):
        field_name, field_type = node.args

        def block_value(block):
            if not block.args:
                return None

            try:
                return ast.literal_eval(block.args[0])
            except Exception:
                return block.args[0]

        blocks = {
            child.name: block_value(child)
            for child in node.body
            if isinstance(child, pyPDB.dbd.ast.Block)
        }
        blocks['type'] = field_type
        blocks['field'] = field_name
        if self.stack[-1].name == 'recordtype':
            record_name, = self.stack[-1].args
            if record_name not in self.field_metadata:
                self.field_metadata[record_name] = {}
            self.field_metadata[record_name][field_name] = blocks

    @property
    def all_records(self):
        '''
        A dictionary of record_type to field dictionary, where field dictionary
        is {field: field_type}

        For example::

            {'ao':{'OUT':'DBF_OUTLINK', ...}, ...}
        '''
        return self.rectypes

    @property
    def record_dtypes(self):
        '''
        A dictionary of record_type to a dictionary of dset (device support
        entry table) items.

        For example::

            {'ao':{'Soft Channel':'CONSTANT', ...}, ...}
        '''
        return self.recdsets

    def _record_warning_or_error(self, result_list, name, msg, args):
        result_list.append(
            {'name': name,
             'message': msg % args,
             'file': self.node.fname,
             'line': self.node.lineno,
             'raw_message': msg,
             'format_args': args,
             }
        )

    def err(self, name, msg, *args):
        self._record_warning_or_error(self.errors, name, msg, args)

    def warn(self, name, msg, *args):
        self._record_warning_or_error(self.warnings, name, msg, args)

    @property
    def success(self):
        '''
        Returns
        -------
        success : bool
            True if the linting process succeeded without errors
        '''
        return not len(self.errors)

    @classmethod
    def parse_file(cls, fn):
        '''
        Parse a full EPICS dbd file and return a `DbdFile` instance.

        Parameters
        ----------
        fn : str or file
            dbd filename

        Returns
        ----------
        parsed : list
            pyPDB parsed dbd nodes
        '''
        if hasattr(fn, 'read'):
            contents = fn.read()
        else:
            with open(fn, 'rt') as f:
                contents = f.read()

        parsed = _yacc.parse(contents)
        results = cls()
        tree = copy.deepcopy(_dbdlint.dbdtree)

        # Walk the dbd file, populating the results dictionaries:
        _dbdlint.walk(parsed, tree, results)
        return results


def get_softioc_dbd_path():
    'Get the readily available softIoc.dbd file from EPICS_BASE'
    dbd_path = caproto.benchmarking.find_dbd_path()
    return pathlib.Path(dbd_path) / 'softIoc.dbd'


def get_record_to_field_dictionary(dbd_path, *, include_dollar_fields=True):
    '''
    Return a {record: {field: ftype, ...}, ...} dictionary from a dbd file
    '''
    record_to_fields = DbdFile.parse_file(dbd_path).all_records

    # the record files don't include "RTYP" & ".RTYP$"
    for rdict in record_to_fields.values():
        rdict['RTYP'] = 'DBF_STRING'

        if include_dollar_fields:
            # Add on FTYPE$ entries
            for field, ftype in list(rdict.items()):
                if ftype in {"DBF_STRING", "DBF_FWDLINK", "DBF_INLINK"}:
                    rdict[field + '$'] = 'DBF_CHAR'

    return record_to_fields


def get_record_to_field_metadata(dbd_path):
    '''
    Return a {record: {field: field_info, ...}, ...} dictionary from a dbd file
    '''
    return DbdFile.parse_file(dbd_path).field_metadata


@pytest.fixture(scope='session')
def softioc_dbd_path():
    return get_softioc_dbd_path()


@pytest.fixture(scope='session')
def record_type_to_fields(softioc_dbd_path):
    return get_record_to_field_dictionary(
        softioc_dbd_path, include_dollar_fields=True)
