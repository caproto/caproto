'''
This module repurposes the dbd linter from pyPDB (*) to parse EPICS database
definition files and give information about records.

(*) Available on conda-forge as epics-pypdb
'''
import copy
import pathlib

import caproto
import pytest
import pyPDB.dbd.yacc as _yacc
import pyPDB.dbdlint as _dbdlint


class Results:
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
        self.node = None
        self.stack = []

        # These are set by the dbdlint walk step
        self.rectypes = {}
        self.recdsets = {}
        self.recinst = {}  # {'inst:name':'ao', ...}
        self.extinst = set()

        self.errors = []
        self.warnings = []

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


def parse_dbd(fn):
    '''
    Parse a full EPICS dbd file

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

    return _yacc.parse(contents)


def dbd_to_fields(fn):
    '''
    Parse a dbd file and return a dictionary of record_type to field
    dictionary, where field dictionary is {field: field_type}

    For example::

        {'ao':{'OUT':'DBF_OUTLINK', ...}, ...}

    Parameters
    ----------
    fn : str or file
        dbd filename
    '''

    parsed = parse_dbd(fn)
    results = Results()
    tree = copy.deepcopy(_dbdlint.dbdtree)

    # Walk the dbd file, populating the results dictionaries:
    _dbdlint.walk(parsed, tree, results)
    return results.all_records


@pytest.fixture(scope='session')
def softioc_dbd_path():
    dbd_path = caproto.benchmarking.find_dbd_path()
    print(dbd_path)
    return pathlib.Path(dbd_path) / 'softIoc.dbd'


@pytest.fixture(scope='session')
def record_type_to_fields(softioc_dbd_path):
    record_to_fields = dbd_to_fields(softioc_dbd_path)

    # the record files don't include "RTYP" & ".RTYP$"
    for rdict in record_to_fields.values():
        rdict['RTYP'] = 'DBF_STRING'

        # Add on FTYPE$ entries
        for field, ftype in list(rdict.items()):
            if ftype in {"DBF_STRING", "DBF_FWDLINK", "DBF_INLINK"}:
                rdict[ftype + '$'] = 'DBF_CHAR'

    return record_to_fields
