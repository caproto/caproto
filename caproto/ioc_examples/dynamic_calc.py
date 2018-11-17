#!/usr/bin/env python3
from caproto.server import pvproperty, PVGroup, ioc_arg_parser, run
from caproto import ChannelDouble

import ast


def extract_names(code):
    m = ast.parse(code)
    c = compile(code, '', 'eval')
    # TODO also skip np namespace
    return c, set(n.id for n in ast.walk(m)
                  if isinstance(n, ast.Name))


class SmartCalc(PVGroup):
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
        c, names = extract_names(value)

        self.c = c
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
        lcls = {n: self._pvdb[f'{self.prefix}{n}'].value
                for n in self.names}

        ret = eval(self.c, lcls)
        await self.output.write(ret)

        return 0


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='dyncalc:',
        desc="Run an IOC that dynamically adds channels for the formula")
    ioc = SmartCalc(**ioc_options)
    run(ioc.out_db, **run_options)
