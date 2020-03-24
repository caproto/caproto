#!/usr/bin/env python3
from caproto import ChannelType
from caproto.server import pvproperty, PVGroup, template_arg_parser, run
from caproto.server.records import records


def start_ioc(record_type, *, ioc_options, run_options):
    record_class = records[record_type]
    val_dtype = record_class._dtype

    default_values = {
        ChannelType.CHAR: 'a',
        ChannelType.DOUBLE: 0.0,
        ChannelType.LONG: 0,
        ChannelType.ENUM: 0,  # TODO
    }
    default_value = default_values[val_dtype]

    class RecordMockingIOC(PVGroup):
        A = pvproperty(
            value=default_value,
            mock_record=record_type,
            dtype=val_dtype,
        )

    ioc = RecordMockingIOC(**ioc_options)

    prefix = ioc_options['prefix']
    print(
        f'{prefix}A is mocking {record_type!r} record with default value '
        f'{default_value!r} ({val_dtype.name}) and fields:',
        ', '.join(ioc.A.fields)
    )
    run(ioc.pvdb, **run_options)


if __name__ == '__main__':
    parser, split_args = template_arg_parser(
        default_prefix='any:record:',
        desc='Run an IOC that mocks an arbitrary record type'
    )

    parser.add_argument(
        '--record-type',
        help='The record type to use for `A`',
        type=str,
        default='ai'
    )

    args = parser.parse_args()
    ioc_options, run_options = split_args(args)
    start_ioc(args.record_type, ioc_options=ioc_options,
              run_options=run_options)
