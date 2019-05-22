#!/usr/bin/env python3
from caproto.server import pvproperty, PVGroup, template_arg_parser, run
import json


def ingest_pv_dict(inp):
    type_map = {'float': float,
                'int': int}
    body = {}
    for (i, (k, (dtype, rec_type))) in enumerate(inp.items()):
        body[str(i)] = pvproperty(name=k,
                                  dtype=type_map[dtype],
                                  mock_record=rec_type)

    return type('BucketOPVs', (PVGroup,), body)


if __name__ == '__main__':
    parser, split_args = template_arg_parser(
        default_prefix='',
        desc='An IOC that servers a bucket of disconnected PVs.')

    parser.add_argument('--json',
                        help='The file to read the PVs from',
                        required=True, type=str)
    args = parser.parse_args()
    ioc_options, run_options = split_args(args)

    with open(args.json, 'r') as fin:
        inp = json.load(fin)
    klass = ingest_pv_dict(inp)

    ioc = klass(**ioc_options)
    run(ioc.pvdb, **run_options)
