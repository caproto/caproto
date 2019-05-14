#!/usr/bin/env python3
from caproto.server import pvproperty, PVGroup, ioc_arg_parser, run
from caproto import ChannelType
from textwrap import dedent


class EnumIOC(PVGroup):
    """
    An IOC with some enums

    Each mock actual EPICS record fields and link the ZNAM and ONAM fields
    appropriately.

    Scalar PVs
    ----------
    bo (enum) - a mocked binary output record
    bi (enum) - a mocked binary input record
    """
    bo = pvproperty(value='One Value',
                    enum_strings=['Zero Value', 'One Value'],
                    mock_record='bo',
                    dtype=ChannelType.ENUM)
    bi = pvproperty(value='a',
                    enum_strings=['a', 'b'],
                    mock_record='bi',
                    dtype=ChannelType.ENUM)


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='enum:',
        desc=dedent(EnumIOC.__doc__))
    ioc = EnumIOC(**ioc_options)
    run(ioc.pvdb, **run_options)
