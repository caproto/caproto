#!/usr/bin/env python3
from caproto.server import pvproperty, PVGroup, ioc_arg_parser, run
from caproto import ChannelDouble

import ast


def extract_names(code_string):
    ast_node = ast.parse(code_string)
    code_object = compile(code_string, '', 'eval')
    # TODO also skip np namespace
    return code_object, set(node.id for node in ast.walk(ast_node)
                            if isinstance(node, ast.Name))


class DynamicCalc(PVGroup):
    formula = pvproperty(value='')
    proc = pvproperty(value=0)
    output = pvproperty(value=0.0)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pvdb = {}
        self.out_db = {}
        self.out_db.update(self.pvdb)

    @formula.putter
    async def formula(self, instance, value):
        code_object, names = extract_names(value)

        self.code_object = code_object
        self.names = names

        self._pvdb.clear()
        self._pvdb.update({f'{self.prefix}{n}': ChannelDouble(value=0)
                           for n in names})
        self.out_db.clear()
        self.out_db.update(self.pvdb)
        self.out_db.update(self._pvdb)
        return value

    @proc.putter
    async def proc(self, instance, value):
        locals_ = {n: self._pvdb[f'{self.prefix}{n}'].value
                  for n in self.names}

        ret = eval(self.code_object, locals_)
        await self.output.write(ret)

        return 0


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='dyncalc:',
        desc="Run an IOC that dynamically adds channels for the formula")
    ioc = DynamicCalc(**ioc_options)
    run(ioc.out_db, **run_options)
