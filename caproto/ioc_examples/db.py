#!/usr/bin/env python3
import ast
import logging
import os

import recordwhat.parsers.db_parsimonious as _db_parser
import recordwhat.parsers.dbd_parsimonious as _dbd_parser

from caproto.server import pvproperty, PVGroup, template_arg_parser, run


logger = logging.getLogger(__name__)


def load_db(db):
    '''
    Load a an EPICS record database file (.db)

    Parameters
    ----------
    db : str
        The database filename or text
    '''
    if os.path.exists(db):
        with open(db, 'r') as f:
            db_content = f.read()
    else:
        db_content = db
        db = '<string>'

    dw = _db_parser.dbWalker()
    return dw.visit(_db_parser.db_grammar.parse(db_content))


def load_dbd(dbd):
    '''
    Load a an EPICS record database definition file (.dbd)

    Parameters
    ----------
    dbd : str
        The database definition filename or text
    '''
    if os.path.exists(dbd):
        with open(dbd, 'r') as f:
            dbd_content = f.read()
    else:
        dbd_content = dbd
        dbd = '<string>'

    walker = _dbd_parser.RecordWalker()
    return walker.visit(_dbd_parser.dbd_grammar.parse(dbd_content))


def arg_parser(*, desc, default_prefix, argv=None, macros=None,
               supported_async_libs=None):
    """
    A modified version of the built-in ArgumentParser for basic example IOCs.

    Parameters
    ----------
    description : string
        Human-friendly description of what that IOC does
    default_prefix : string
    args : list, optional
        Defaults to sys.argv
    macros : dict, optional
        Maps macro names to default value (string) or None (indicating that
        this macro parameter is required).
    supported_async_libs : list, optional
        "White list" of supported server implementations. The first one will
        be the default. If None specified, the parser will accept all of the
        (hard-coded) choices.

    Returns
    -------
    ioc_options : dict
        kwargs to be handed into the IOC init.

    run_options : dict
        kwargs to be handed to run
    """
    parser, split_args = template_arg_parser(
        desc=desc, default_prefix=default_prefix, argv=argv, macros=macros,
        supported_async_libs=supported_async_libs)

    parser.add_argument('db_file', type=str)
    parser.add_argument('--dbd', type=str)
    args = parser.parse_args()
    ioc_options, run_options = split_args(args)
    db_options = dict(db_file=args.db_file,
                      dbd=args.dbd)
    return db_options, ioc_options, run_options


def field_to_value(field_name, value):
    '''
    String from a database field to a Python type
    '''
    value = value.value.strip('"')
    try:
        return ast.literal_eval(value)
    except Exception:
        ...

    return value


def create_ioc(db_file, dbd, *, default_values=None, class_name='IOCFromDB',
               base_class=None):
    '''
    Create an IOC from a database file

    Parameters
    ----------
    db : str
        The database text or filename
    dbd : str
        The database definition text or filename
    default_values : dict, optional
        A mapping of record_type to default value
    class_name : str, optional
        Class name for the generated class
    base_class : class, optional
        Base for the IOC, defaults to PVGroup
    '''
    logger.info('Loading %s (dbd: %s)', db_file, dbd)
    db_info = load_db(db_file)

    class_dict = {}
    dbd = load_dbd(dbd)

    if default_values is None:
        default_values = {
            'ai': 0.0,
            'ao': 0.0,
            'bi': 0,
            'bo': 0,
            'calc': 0,
            'longin': 0,
            'longout': 0,
        }

    async def startup_hook(group, instance, async_lib):
        '''
        A startup hook which writes all field defaults
        '''
        for attr, fields in group.fields.items():
            prop = getattr(group, attr)
            for field_name, value in fields.items():
                field = prop.get_field(field_name)
                try:
                    await field.write(value)
                except Exception as ex:
                    logger.warning(
                        'Failed to set initial value for: %s.%s => %s (%s)',
                        attr, field_name, value, ex
                    )

    fields = {}
    class_dict['record_0'] = pvproperty(
        name='_startup_hook_',
        value=0,
        startup=startup_hook,
    )

    for idx, record in enumerate(db_info, 1):
        attr = f'record_{idx}'

        fields[attr] = {}
        try:
            value_field = field_to_value('VAL', record.fields['VAL'])
        except KeyError:
            value_field = default_values.get(record.rtype)

        class_dict[attr] = pvproperty(
            name=record.pvname.strip('"'),
            value=value_field,
            mock_record=record.rtype
        )

        for field_name, value in record.fields.items():
            if field_name != 'VAL':
                fields[attr][field_name] = field_to_value(field_name, value)

        for alias_idx, alias in enumerate(record.alias):
            logger.debug('TODO - aliases: %s %s', record, alias)

    if base_class is None:
        base_class = (PVGroup, )

    ioc_class = type(class_name, base_class, class_dict)
    ioc_class.fields = fields
    return ioc_class


if __name__ == '__main__':
    db_options, ioc_options, run_options = arg_parser(
        default_prefix='SIM:',
        desc='IOC from database (and maybe dbd)',
    )

    ioc_class = create_ioc(db_options['db_file'], dbd=db_options['dbd'])
    ioc = ioc_class(**ioc_options)
    run(ioc.pvdb, **run_options)
