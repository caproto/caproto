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
    formula = pvproperty(value='', report_as_string=True)
    process = pvproperty(value=0, name='formula.PROC')
    output = pvproperty(value=0.0)
    variables = pvproperty(value=['a'], max_length=100,
                           dtype=ChannelType.STRING)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._all_variables = {}

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

        # And dynamically create a new set of properties based on the names
        new_pvproperties = {
            name: pvproperty(value=0.0)
            for name in names if name not in self._all_variables
        }

        DynamicGroup = type('DynamicGroup', (PVGroup, ), new_pvproperties)
        dynamic_group = DynamicGroup(prefix=self.prefix)

        print('New formula:', value)
        print('New PVs:', list(sorted(dynamic_group.pvdb)))

        self._all_variables.update(
            {
                attr: getattr(dynamic_group, attr)
                for attr in new_pvproperties
            }
        )

        self.pvdb.update(dynamic_group.pvdb)
        return value

    @process.putter
    async def process(self, instance, value):
        # Gather the current values in a `locals()` dictionary:
        formula_locals = {
            name: self._all_variables[name].value
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
