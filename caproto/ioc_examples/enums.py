#!/usr/bin/env python3
from caproto.server import pvproperty, PVGroup, ioc_arg_parser, run
from caproto import ChannelType
from textwrap import dedent


class EnumIOC(PVGroup):
    """
    An IOC with some enums.

    Each property here presents itself as a record with the expected fields
    over Channel Access.

    For ``bi`` and ``bo``, the ZNAM and ONAM fields hold the string equivalent
    values for 0 and 1.  These are derived from the ``enum_strings`` keyword
    argument.

    That is, ``bo.ZNAM`` is "Zero Value", ``bo.ONAM`` is ``"One Value"``, such
    that ``caput bo 1`` would show it being set to ``"One Value"``.

    For the mbbi record, the ``ZRST`` (zero string) field, ``ONST`` (one
    string) field, and so on (up to 15), are similarly respected and mapped
    from the ``enum_strings`` keyword argument.

    Scalar PVs
    ----------
    bo (enum) - a binary output (bo) record
    bi (enum) - a binary input (bi) record
    mbbi (enum) - a multi-bit binary input (mbbi) record
    """

    bo = pvproperty(value='One Value',
                    enum_strings=['Zero Value', 'One Value'],
                    record='bo',
                    dtype=ChannelType.ENUM)
    bi = pvproperty(value='a',
                    enum_strings=['a', 'b'],
                    record='bi',
                    dtype=ChannelType.ENUM)
    mbbi = pvproperty(value='one',
                      enum_strings=['zero',
                                    'one',
                                    'two',
                                    'three',
                                    'four'],
                      record='mbbi',
                      dtype=ChannelType.ENUM
                      )


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='enum:',
        desc=dedent(EnumIOC.__doc__))
    ioc = EnumIOC(**ioc_options)
    run(ioc.pvdb, **run_options)
