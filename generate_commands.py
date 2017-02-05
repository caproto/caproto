# Parse excerpts from
# http://www.aps.anl.gov/epics/docs/CAproto.html#secVirtualCircuitLifeCycle
# and generate Python functions that return bytestrings.

import re
import os
from collections import namedtuple
from jinja2 import Environment, FileSystemLoader
import xml.etree.ElementTree as ET


def getpath(*args):
    """Get absolute path of joined directories relative to this file"""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), *args))


EXAMPLE = """<table class="table" cellspacing="0"><tr class="odd"><th>Field</th><th>Value</th><th>Description</th></tr><tr class="even"><td><tt class="identifier">Command</tt></td><td><tt class="identifier">10</tt></td><td>Command identifier for CA_PROTO_READ_SYNC.</td></tr><tr class="odd"><td><tt class="identifier">Reserved</tt></td><td><tt class="identifier">0</tt></td><td>Must be 0.</td></tr><tr class="even"><td><tt class="identifier">Reserved</tt></td><td><tt class="identifier">0</tt></td><td>Must be 0.</td></tr><tr class="odd"><td><tt class="identifier">Reserved</tt></td><td><tt class="identifier">0</tt></td><td>Must be 0.</td></tr><tr class="even"><td><tt class="identifier">Reserved</tt></td><td><tt class="identifier">0</tt></td><td>Must be 0.</td></tr><tr class="odd"><td><tt class="identifier">Reserved</tt></td><td><tt class="identifier">0</tt></td><td>Must be 0.</td></tr></table>"""


Param = namedtuple('Param', ['field', 'value', 'description'])
Command = namedtuple('Command', ['name', 'input_params', 'struct_args'])

COMMAND_NAME_PATTERN = re.compile("Command identifier for ([A-Z_]+)\.?")


def validate(params):
    if not params[0].field == 'Command':
        raise ValueError("first cell of table should be 'Command'")
    if not len(params) == 6:
        raise ValueError("table should have six rows")


def generate(table):
    root = ET.fromstring(table)
    rows = root.iter(tag='tr')
    next(rows)  # discard the header row
    params = []
    for row in rows:
        field_td, val_td, desc_td = row.iter(tag='td')
        field = field_td.find('tt').text
        val = val_td.find('tt').text
        desc = desc_td.text
        params.append(Param(field, val, desc))
    validate(params)
    name = COMMAND_NAME_PATTERN.match(params[0].description).group(1)
    input_params = [p for p in params[1:] if p.field != 'Reserved']
    struct_args = [p.field
                   if p in input_params else int(p.value)
                   for p in params]
    print(', '.join(map(repr, struct_args)))
    return Command(name, input_params, struct_args)


JINJA_ENV = Environment(loader=FileSystemLoader(getpath('.')))
JINJA_ENV.filters['repr'] = repr
template = JINJA_ENV.get_template('command.tpl')
res = template.render(commands=[generate(EXAMPLE)])
print(res)
