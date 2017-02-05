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


def parse_command(h2):
    """
    Parse HTML describing a CA command into a namedtuple.
    """
    raw_desc = h2.find_next(string='Description: ').parent.parent.text
    description = '\n'.join(raw_desc.replace('\t\t\t', '    ').split('\n')[1:])
    table = h2.find_next('table')
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
    input_params = [p for p in params[1:] if p.field != 'reserved']
    struct_args = [p.field
                   if p in input_params else int(p.value)
                   for p in params]
    return Command(name, description, input_params, struct_args)


JINJA_ENV = Environment(loader=FileSystemLoader(getpath('.')))
# JINJA_ENV.filters['repr'] = repr
template = JINJA_ENV.get_template('commands.tpl')


def parse_section(h1):
    """
    Apply ``parse_command`` to each <h2> tag betweeen this <h1> and the next.
    """
    next_h1 = h1.find_next('h1')
    h2s = h1.find_all_next('h2')[:-len(next_h1.find_all_next('h2'))]
    return [parse_command(h2) for h2 in h2s]


def write_commands(path=None):
    """
    Generate commands.py from commands.tpl and CAproto.html
    """
    with open('CAproto.html') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')
    commands = []
    for id in ('secCommandsShared',
               'secCommandsUDP',
               'secCommandsTCP'):
        h1 = soup.find(id=id)
        commands.extend(parse_section(h1))
    if path is None:
        path = getpath('.')
    with open(os.path.join(path, 'commands.py'), 'w') as f:
        f.write(template.render(commands=commands))


if __name__ == '__main__':
    write_commands()
