# Parse excerpts from
# http://www.aps.anl.gov/epics/docs/CAproto.html#secVirtualCircuitLifeCycle
# and generate Python functions that return bytestrings.
import re
import string
import os
from collections import namedtuple
from jinja2 import Environment, FileSystemLoader
import requests
from bs4 import BeautifulSoup


def getpath(*args):
    """Get absolute path of joined directories relative to this file"""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), *args))


Param = namedtuple('Param', ['field', 'value', 'description'])
Command = namedtuple('Command', ['name', 'description',
                                 'input_params', 'struct_args'])

COMMAND_NAME_PATTERN = re.compile("Command identifier for ([A-Z_]+)\.?")


def validate(params):
    if not params[0].field == 'command':
        raise ValueError("first cell of table should be 'Command', "
                         "not %s" % params[0].field)
    if not len(params) == 6:
        raise ValueError("table should have six rows")


def is_reserved(param):
    return param.field == 'reserved' or param.description == 'Must be 0.' 


def parse_commands(h2):
    """
    Parse HTML describing CA request/response spec into namedtuples.
    """
    # Grab the description under the h2 heading for use in the docstring.
    raw_desc = h2.find_next(string='Description: ').parent.parent.text
    description = '\n'.join(raw_desc.replace('\t\t\t', '    ').split('\n')[1:])

    # Select the <table> tags between this <h2> and the next </h2>.
    next_h2 = h2.find_next('h2')
    tables = h2.find_all_next('table')[:-len(next_h2.find_all_next('table'))]

    # Figure out which tables are associated with 'Request' vs 'Response'.
    # Ignore tables about 'Compatibility' with various versions of EPICS.
    request_spec = []
    response_spec = []
    for table in tables:
        table_title = table.previous_sibling.find('span').text
        if table_title == 'Compatibility':
            continue
        h3_text = table.find_previous('h3').text
        if 'Request' in h3_text:
            request_spec.append(table)
        elif 'Response' in h3_text:
            response_spec.append(table)
        else:
            raise ValueError("expected 'Request' or 'Response' in h3text")

    # Prase the tables under the headings 'Request' and 'Response' into
    # namedtuples. Some have only one of these headings, or neither, so this
    # may result in a list of 0, 1, or 2 commands.
    commands = []
    for suffix, tables in (('REQ', request_spec), ('RESP', response_spec)):
        if not tables:
            continue
        table = tables[0]  # Ignore Payload table for now.
        rows = table.find_all('tr')
        params = []
        for row in rows[1:]:  # exclude header row
            field_td, val_td, desc_td = row.find_all('td')
            field = field_td.find('tt').text.replace(' ', '_').lower()
            val = val_td.find('tt').text
            desc = desc_td.text
            params.append(Param(field, val, desc))
        validate(params)
        name = COMMAND_NAME_PATTERN.match(params[0].description).group(1)
        input_params = [p for p in params[1:] if not is_reserved(p)]
        struct_args = [p.field
                       if p in input_params else int(p.value)
                       for p in params]
        command = Command('{}_{}'.format(name, suffix),
                          description, input_params, struct_args)
        commands.append(command)
    return commands


JINJA_ENV = Environment(loader=FileSystemLoader(getpath('.')))
# JINJA_ENV.filters['repr'] = repr
template = JINJA_ENV.get_template('commands.tpl')


def parse_section(h1):
    """
    Apply ``parse_command`` to each <h2> tag betweeen this <h1> and the next.
    """
    next_h1 = h1.find_next('h1')
    h2s = h1.find_all_next('h2')[:-len(next_h1.find_all_next('h2'))]
    commands = []
    for h2 in h2s:
        commands.extend(parse_commands(h2))
    return commands


def write_commands(path=None):
    """
    Generate commands.py from commands.tpl and CAproto.html
    """
    with open('CAproto.html') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')
    commands = []
    for _id in ('secCommandsShared',
                'secCommandsUDP',
                'secCommandsTCP'):
        h1 = soup.find(id=_id)
        commands.extend(parse_section(h1))
    if path is None:
        path = getpath('.')
    with open(os.path.join(path, 'commands.py'), 'w') as f:
        f.write(template.render(commands=commands))


if __name__ == '__main__':
    write_commands()
