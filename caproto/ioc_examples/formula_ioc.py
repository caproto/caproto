#!/use/bin/env python3
from caproto.server import pvproperty, PVGroup, template_arg_parser, run
from caproto import ChannelType
import numpy as np
from textwrap import dedent
import ast

np_names = set(np.__all__)
np_ns = {k: getattr(np, k) for k in np_names}


def extract_names(code_string):
    output_name, _, expr = map(lambda x: x.strip(),
                               code_string.partition('='))

    ast_node = ast.parse(expr)
    code_object = compile(expr, '', 'eval')
    return (output_name,
            expr,
            code_object,
            set(node.id for node in ast.walk(ast_node)
                if (isinstance(node, ast.Name) and
                    node.id not in np_names)))


class FormulaIOC(PVGroup):
    """
    An IOC that computes a formula.

    The equation is specified as a python assignment statement an IOC
    boot.  It must be of the form::

       ret_name = <expr>

    The expression will be evaluated in a namespace with numpy's top-level
    namespace available.

    Any free-variables will be identified and used as the PV names of
    the form `{prefix}{var}`.  The output will be published to
    `{prefix}{ret_name}`


    Readonly PVs
    ------------
    {prefix}formula -> the equation computed

    {prefix}out_postfix -> the PV post-fix where the output is available
    {prefix}vars -> the PV post-fixes where the inputs should be posted

    {prefix}{ret_name} -> The result of the computation

    Input PVs
    ---------
    {prefix}{var} -> the value for {var} in the inputs
    """
    proc = pvproperty(value=0, alarm_group='formula')

    def __init__(self, *args, code_object, var_names, **kwargs):
        super().__init__(*args, **kwargs)
        self.code_object = code_object
        self.var_names = var_names

    @proc.putter
    async def proc(self, instance, value):
        ret = await self.compute(instance)
        await self.output.write(ret)

        return 0

    async def compute(self, instance):
        locals_ = {n: self.pvdb[f'{self.prefix}{n}'].value
                   for n in self.var_names}
        ret = eval(self.code_object, locals_, np_ns)
        return ret


if __name__ == '__main__':
    parser, split_args = template_arg_parser(
        default_prefix='SmartCalc:',
        desc=dedent(FormulaIOC.__doc__)
    )
    # add our own CLI arguments
    parser.add_argument('--formula',
                        help=('The formula to evaluate.  ' +
                              'Must be a python expression.'),
                        required=True, type=str)

    args = parser.parse_args()
    ioc_options, run_options = split_args(args)

    # parse the input formula
    out_name, expr, code_object, names = extract_names(args.formula)

    # build the pvpropriety objects for then inputs to the formula
    dyn_pvs = {n: pvproperty(value=0.0, alarm_group='formula')
               for n in names}

    # build the pvproperty for the output.
    out_pv = pvproperty(
        value=0.0,
        name=out_name, read_only=True,
        get=FormulaIOC.compute, mock_record='ai',
        alarm_group='formula')

    @out_pv.scan(period=.1, use_scan_field=True)
    async def out_pv(self, instance, async_lib):
        ret = await self.compute(instance)
        await instance.write(ret)

    dyn_pvs['output'] = out_pv

    # add read-only informational PVs
    dyn_pvs['formula'] = pvproperty(
        value=f'{out_name} = {expr}',
        read_only=True)
    dyn_pvs['out_postfix'] = pvproperty(
        value=[out_name], read_only=True, dtype=ChannelType.STRING)
    dyn_pvs['vars'] = pvproperty(
        value=sorted(names), read_only=True, dtype=ChannelType.STRING)

    # dynamically sub-class the FormulaIOC to add the pvproperty
    # objects we built up above.
    MyIOC = type('MyIOC', (FormulaIOC,), dyn_pvs)

    # instantiate the IOC
    ioc = MyIOC(code_object=code_object,
                var_names=names,
                **ioc_options)

    # and run it!
    run(ioc.pvdb, **run_options)
