import argparse
import sys

import caproto as ca


def template_arg_parser(*, desc, default_prefix, argv=None, macros=None,
                        supported_async_libs=None):
    """
    Construct a template arg parser for starting up an IOC

    Parameters
    ----------
    description : string
        Human-friendly description of what that IOC does.

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
    parser : argparse.ArgumentParser

    split_args : callable[argparse.Namespace, Tuple[dict, dict]]
        A helper function to extract and split the 'standard' CL arguments.
        This function sets the logging level and returns the kwargs for
        constructing the IOC and for the launching the server.
    """
    if argv is None:
        argv = sys.argv
    if macros is None:
        macros = {}
    parser = argparse.ArgumentParser(
        description=desc,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f'caproto version {ca.__version__}')
    parser.add_argument('--prefix', type=str, default=default_prefix)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-q', '--quiet', action='store_true',
                       help=("Suppress INFO log messages. "
                             "(Still show WARNING or higher.)"))
    group.add_argument('-v', '--verbose', action='count',
                       help="Show more log messages. (Use -vvv for even more.)")
    parser.add_argument('--list-pvs', action='store_true',
                        help="At startup, log the list of PV names served.")
    choices = tuple(supported_async_libs or ('asyncio', 'curio', 'trio'))
    parser.add_argument('--async-lib', default=choices[0],
                        choices=choices,
                        help=("Which asynchronous library to use. "
                              "Default is asyncio."))
    default_intf = ca.get_server_address_list(protocol=ca.Protocol.PVAccess)
    if default_intf == ['0.0.0.0']:
        default_msg = '0.0.0.0'
    else:
        default_msg = (f"{' '.join(default_intf)} as specified by environment "
                       f"variable EPICS_PVAS_INTF_ADDR_LIST")
    parser.add_argument('--interfaces', default=default_intf,
                        nargs='+',
                        help=(f"Interfaces to listen on. Default is "
                              f"{default_msg}.  Multiple entries can be "
                              f"given; separate entries by spaces."))
    for name, default_value in macros.items():
        if default_value is None:
            parser.add_argument(f'--{name}', type=str, required=True,
                                help="Macro substitution required by this IOC")
        else:
            parser.add_argument(f'--{name}', type=str, default=default_value,
                                help="Macro substitution, optional")

    def split_args(args):
        """
        Helper function to pull the standard information out of the
        parsed args.

        Returns
        -------
        ioc_options : dict
            kwargs to be handed into the IOC init.

        run_options : dict
            kwargs to be handed to run
        """
        if args.verbose:
            if args.verbose > 1:
                ca.set_handler(level='DEBUG')
            else:
                ca._log._set_handler_with_logger(logger_name='caproto.pva.ctx', level='DEBUG')
                ca._log._set_handler_with_logger(logger_name='caproto.pva.circ', level='INFO')
        elif args.quiet:
            ca.set_handler(level='WARNING')
        else:
            ca._log._set_handler_with_logger(logger_name='caproto.pva.ctx', level='INFO')

        return (
            # IOC options
            dict(prefix=args.prefix,
                 macros={key: getattr(args, key) for key in macros},
                 ),

            # Run options
            dict(
                module_name=f'caproto.pva.{args.async_lib}.server',
                log_pv_names=args.list_pvs,
                interfaces=args.interfaces,
            ),
        )

    return parser, split_args


def ioc_arg_parser(*, desc, default_prefix, argv=None, macros=None,
                   supported_async_libs=None):
    """
    A reusable ArgumentParser for basic example IOCs.

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
    parser, split_args = template_arg_parser(desc=desc, default_prefix=default_prefix,
                                             argv=argv, macros=macros,
                                             supported_async_libs=supported_async_libs)
    return split_args(parser.parse_args())


def run(pvdb, *, module_name, **kwargs):
    from importlib import import_module  # to avoid leaking into module ns
    module = import_module(module_name)
    run = module.run
    return run(pvdb, **kwargs)
