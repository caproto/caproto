#!/use/bin/env python3

import ast
from textwrap import dedent

import numpy as np

from caproto import ChannelType
from caproto.server import PVGroup, pvproperty, run, template_arg_parser

NP_NAMES = frozenset(np.__all__)
NUMPY_NAMESPACE = {k: getattr(np, k) for k in NP_NAMES}


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

    Read-only PVs
    -------------
    {prefix}formula -> the equation computed

    {prefix}out_postfix -> the PV post-fix where the output is available
    {prefix}vars -> the PV post-fixes where the inputs should be posted

    {prefix}{ret_name} -> The result of the computation

    Input PVs
    ---------
    {prefix}{var} -> the value for {var} in the inputs

    See Also
    --------
    `caproto.server.pvfunction`
    """
    proc = pvproperty(value=0, alarm_group='formula')

    @proc.putter
    async def proc(self, instance, value):
        ret = await self.compute(instance)
        await self.output.write(ret)

        return 0

    async def compute(self, instance):
        locals_ = {n: self.pvdb[f'{self.prefix}{n}'].value
                   for n in self.var_names}
        ret = eval(self.code_object, locals_, NUMPY_NAMESPACE)
        return ret


def create_ioc(formula: str) -> type:
    """
    Create an IOC based on the given formula.

    Parameters
    ----------
    formula : str
        The formula to create PVs for.

    Returns
    -------
    cls : type
        Subclass of `FormulaIOC`.
    """
    # parse the input formula
    out_name, expr, code_object, names = extract_names(formula)

    # build the pvpropriety objects for then inputs to the formula
    class_dict = {
        n: pvproperty(value=0.0, alarm_group='formula')
        for n in names
    }

    # build the pvproperty for the output.
    out_pv = pvproperty(
        value=0.0,
        name=out_name,
        read_only=True,
        get=FormulaIOC.compute, record='ai',
        alarm_group='formula'
    )

    @out_pv.scan(period=.1, use_scan_field=True)
    async def out_pv(self, instance, async_lib):
        ret = await self.compute(instance)
        await instance.write(ret)

    class_dict.update({
        # Add read-only informational PVs:
        'output': out_pv,
        'formula': pvproperty(value=f'{out_name} = {expr}', read_only=True,
                              report_as_string=True),
        'out_postfix': pvproperty(value=[out_name], read_only=True,
                                  dtype=ChannelType.STRING),
        'vars': pvproperty(value=sorted(names), read_only=True,
                           dtype=ChannelType.STRING),

        # And information on the formula:
        'var_names': names,
        'code_object': code_object,
    })

    # Dynamically sub-class the FormulaIOC to add the pvproperty
    # objects we built up above.
    return type('CustomFormulaIOC', (FormulaIOC,), class_dict)


def extract_names(code_string):
    """
    Extract variable names from a given string of code.

    Returns
    -------
    output_name : str
        The output variable name.

    expressino : str
        The formula expression.

    code_object : code
        The compiled code object.

    names : set of str
        Node / variable names.
    """
    output_name, _, expr = map(lambda x: x.strip(),
                               code_string.partition('='))

    ast_node = ast.parse(expr)
    code_object = compile(expr, '', 'eval')
    return (
        output_name,
        expr,
        code_object,
        set(node.id for node in ast.walk(ast_node)
            if isinstance(node, ast.Name) and node.id not in NP_NAMES)
    )


if __name__ == '__main__':
    parser, split_args = template_arg_parser(
        default_prefix='Formula:',
        desc=dedent(FormulaIOC.__doc__)
    )

    # add our own CLI argument
    parser.add_argument(
        '--formula',
        help='The formula to evaluate.  Must be a python expression.',
        required=True,
        type=str,
    )

    args = parser.parse_args()
    ioc_options, run_options = split_args(args)

    ioc = create_ioc(args.formula)(**ioc_options)
    run(ioc.pvdb, **run_options)
