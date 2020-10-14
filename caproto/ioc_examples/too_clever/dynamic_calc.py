#!/usr/bin/env python3
import ast

from caproto import ChannelType
from caproto.server import PVGroup, ioc_arg_parser, pvproperty, run


def extract_names(code_string):
    """
    Extract variable names from a given string of code.

    Returns
    -------
    code_object : code
        The compiled code object.

    names : set of str
        Node / variable names.
    """
    ast_node = ast.parse(code_string)
    code_object = compile(code_string, '', 'eval')
    # TODO also skip np namespace
    return code_object, set(node.id for node in ast.walk(ast_node)
                            if isinstance(node, ast.Name))


class DynamicCalc(PVGroup):
    core_attrs = ['formula', 'process', 'output', 'variables']

    formula = pvproperty(value='', report_as_string=True)
    process = pvproperty(value=0, name='formula.PROC')
    output = pvproperty(value=0.0)
    variables = pvproperty(value=['a'], max_length=100,
                           dtype=ChannelType.STRING)

    def reset_pvdb(self):
        """
        Reset the pv database by in-place removing all non-essential entries.
        """
        core_pvs = [
            getattr(self, attr).pvname
            for attr in self.core_attrs
        ]
        for pv in list(self.pvdb):
            if pv not in core_pvs:
                self.pvdb.pop(pv)

    @formula.startup
    async def formula(self, instance, async_lib):
        """
        Startup hook for formula.  Set a default.
        """
        await self.formula.write(value='a + b')

    @formula.putter
    async def formula(self, instance, value):
        # Evaluate the code and grab variables from the formula:
        self.code_object, names = extract_names(value)

        # Tell CA what variables we have:
        await self.variables.write(value=list(sorted(names)))

        # Reset the process variable database to the bare essentials
        self.reset_pvdb()

        # And dynamically create a new set of properties based on the names
        new_pvproperties = {
            name: pvproperty(value=0.0)
            for name in names
        }

        DynamicGroup = type('DynamicGroup', (PVGroup, ), new_pvproperties)
        self.dynamic_group = DynamicGroup(prefix=self.prefix)
        self.pvdb.update(self.dynamic_group.pvdb)

        print('New formula:', value)
        print('pvdb now includes:', list(sorted(self.pvdb)))
        return value

    @process.putter
    async def process(self, instance, value):
        # Gather the current values in a `locals()` dictionary:
        formula_locals = {
            name: getattr(self.dynamic_group, name).value
            for name in self.variables.value
        }

        # Actually run the formula:
        ret = eval(self.code_object, formula_locals)

        print('Evaluating:', self.formula.value, '=', ret)
        print('where:', ', '.join(f'{name}={value}'
                                  for name, value in formula_locals.items()
                                  if not name.startswith('_')))

        # And stash the result in `output`:
        await self.output.write(ret)

        return 0


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='dyncalc:',
        desc="Run an IOC that dynamically adds channels for the formula")
    ioc = DynamicCalc(**ioc_options)
    run(ioc.pvdb, **run_options)
