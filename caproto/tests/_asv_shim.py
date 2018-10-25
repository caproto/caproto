import os
import json
import pytest
import logging
import inspect

import asv

from collections import OrderedDict, defaultdict

from datetime import datetime
from pytest_benchmark.fixture import BenchmarkFixture
from pytest_benchmark.utils import NameWrapper

logger = logging.getLogger(__name__)

primary_stat_key = 'mean'


def pytest_bench_machine_to_asv(root, *, node, machine, system, release, cpu,
                                **kw):
    'Pytest-benchmark machine infomation to asv'
    asv_defaults = asv.machine.Machine.get_defaults()
    return dict(arch=machine,
                cpu=cpu['brand'],
                machine=node,
                os='{} {}'.format(system, release),
                ram=asv.util.human_file_size(asv_defaults['ram']),
                version=1,
                )


def get_bench_name(fullname, name):
    if name in asv_metadata:
        return name

    name, _, param_string = name.partition('[')
    return name


def single_asv_bench_result(*, start_dt, end_dt, fullname, options, stats,
                            extra_info, params, name, **kwargs):
    'Single benchmark result -> asv format'
    # non-parameterized version
    return dict(
        started_at=asv.util.datetime_to_js_timestamp(start_dt),
        ended_at=asv.util.datetime_to_js_timestamp(end_dt),
        results=dict(stats=dict(min=stats['min'],
                                max=stats['max'],
                                mean=stats['mean'],
                                std=stats['stddev'],
                                n=stats['iterations'],
                                ),
                     result=stats[primary_stat_key]
                     ),
    )


def asv_bench_result(name, md_list):
    'Single normal or parameterized benchmark result -> asv format'
    if not md_list:
        return dict(results=None)

    md0 = md_list[0]
    if len(md_list) == 1:
        return single_asv_bench_result(start_dt=md0['start_dt'],
                                       end_dt=md0['end_dt'],
                                       **md0['pytest_result'])
    else:
        # parameterized version - need to group params
        pytest_results = [md.get('pytest_result', {}) for md in md_list]
        param_names = md0['param_names']
        params = md0['all_params']

        def get_stat_key(key):
            return [res['stats'][key]
                    if res and 'stats' in res
                    else None
                    for res in pytest_results]

        return dict(
            param_names=param_names,
            params=params,
            result=get_stat_key(primary_stat_key),
            number=get_stat_key('iterations'),
        )


def match_asv_metadata(root):
    'Match global asv metadata with json-output pytest metadata'
    for bench in root['benchmarks']:
        bench_name, fullname = bench['name'], bench['fullname']
        name = get_bench_name(fullname, bench_name)
        for md in asv_metadata[name]:
            if md.get('_pytest_name') == bench_name:
                md.pop('_pytest_name')
                md['pytest_result'] = bench
                break


def pytest_bench_results_to_asv():
    'All benchmark results -> asv format'
    benches = defaultdict(lambda: {})

    # ensure at least 'results' key is available, even if all tests are parametrized
    benches['results']

    for name, md_list in asv_metadata.items():
        info = asv_bench_result(name, md_list)
        if 'params' in info:
            # parameterized ones have a dictionary of their own
            benches['results'][name] = info
        else:
            # ... whereas others are just part of general 'results'/etc dicts
            # and keyed by name
            benches['results'][name] = info.pop('results')
            for key, value in info.items():
                benches[key][name] = value
    return benches


def asv_bench_outline(name, md_list):
    'pytest benchmark outline -> asv'
    if not md_list:
        return {}

    md = md_list[0]
    return dict(
        code=md['code'],
        # goal_time=2.0,
        name=name,
        number=0,
        param_names=md['param_names'],
        params=md['all_params'],
        pretty_name=name,
        repeat=1,
        # timeout=60.0,
        type='time',
        unit='seconds',
    )


def pytest_bench_outline_to_asv():
    'All benchmark outlines -> asv format'
    outlined = {name: asv_bench_outline(name, md_list)
                for name, md_list in asv_metadata.items()
                }
    outlined.update(version=1)
    return outlined


def pytest_bench_to_asv(root):
    'pytest-benchmark info to asv'
    commit_info = root['commit_info']

    # TODO git timestamp formatting...
    commit_dt = datetime.strptime(commit_info['time'][:-6],
                                  "%Y-%m-%dT%H:%M:%S")

    machine_info = pytest_bench_machine_to_asv(root, **root['machine_info'])

    # copy over the machine info for the params
    params = dict(machine_info)
    python_version = root['machine_info']['python_version']
    params['python'] = python_version
    # but remove version as it's for the top-level
    del params['version']

    bench_results = dict(
        commit_hash=commit_info['id'],
        date=asv.util.datetime_to_js_timestamp(commit_dt),
        python=python_version,
        params=params,  # TODO
        profiles={},  # TODO
        requirements={},  # TODO
        env_name=os.environ.get('ASV_ENV_NAME', 'conda-py3.5'),  # TODO
        version=1,
    )

    # match asv metadata with pytest results
    match_asv_metadata(root)

    bench_results.update(**pytest_bench_results_to_asv())
    bench_outline = pytest_bench_outline_to_asv()

    return dict(machine_info=machine_info,
                bench_outline=bench_outline,
                bench_results=bench_results)


def save_asv_results(asv_path, *, machine_info, bench_outline, bench_results):
    results_top = os.path.join(asv_path, 'results')
    logger.debug('Saving results to %s', results_top)
    os.makedirs(results_top, exist_ok=True)

    machine_top = os.path.join(results_top, machine_info['machine'])
    machine_path = os.path.join(machine_top, 'machine.json')
    logger.debug('Saving machine info to %s', machine_path)
    os.makedirs(machine_top, exist_ok=True)

    with open(os.path.join(results_top, 'benchmarks.json'), 'wt') as f:
        json.dump(bench_outline, f, sort_keys=True, indent=4)

    with open(machine_path, 'wt') as f:
        json.dump(machine_info, f, sort_keys=True, indent=4)

    results_fn = '{}-{}.json'.format(bench_results['commit_hash'][:8],
                                     bench_results['env_name'],
                                     )
    bench_path = os.path.join(machine_top, results_fn)
    logger.debug('Saving benchmark results to %s', bench_path)

    with open(bench_path, 'wt') as f:
        json.dump(bench_results, f, sort_keys=True, indent=4)


def find_asv_root(path, *, asv_conf_filename='asv.conf.json',
                  asv_subdir='.asv'):
    test_path = os.path.join(path, asv_conf_filename)
    if os.path.exists(test_path):
        return os.path.join(path, asv_subdir)

    parent = os.path.join(*os.path.split(path)[:-1])
    if not parent:
        raise RuntimeError('Unable to find asv root path')

    return find_asv_root(parent)


@pytest.mark.hookwrapper(trylast=True)
def pytest_benchmark_update_json(config, benchmarks, output_json):
    yield

    try:
        results = pytest_bench_to_asv(output_json)
        asv_path = find_asv_root('.')

        logger.info('Saving asv-style JSON to %s', asv_path)
        save_asv_results(asv_path, **results)
    except Exception:
        logger.exception('Failed to update pytest benchmark json; '
                         'asv results not saved')


def get_all_params_from_marked_test(node_or_func):
    'Returns (all_param_names, all_param_values)'
    # TODO: important - verify ordering of kwargs
    decorated_test = getattr(node_or_func, 'obj', node_or_func)
    pinfo = decorated_test.parametrize

    arg_names, arg_values = pinfo.args[::2], pinfo.args[1::2]
    kwarg_names = list(sorted(pinfo.kwargs.keys()))
    kwarg_values = [pinfo.kwargs[key] for key in kwarg_names]

    return (list(arg_names) + kwarg_names,
            [[repr(arg) for arg in arg_list]
             for arg_list in list(arg_values) + kwarg_values]
            )


asv_metadata = {}


class AsvBenchmarkFixture(BenchmarkFixture):
    def __init__(self, *, node, **kwargs):
        self.node = node
        super().__init__(node=node, **kwargs)

    def generate_asv_metadata(self, function_to_benchmark, start_dt, end_dt):
        'Generate metadata for asv from pytest_benchmark information'
        callspec = self.node.callspec
        params = OrderedDict(
            (arg, callspec.params[arg])
            for arg in callspec.metafunc.funcargnames
            if arg in callspec.params
        )

        code = ''.join(inspect.getsourcelines(function_to_benchmark)[0])

        if params:
            name, _, param_string = self.name.partition('[')
            param_string = param_string.rstrip(']')
        else:
            name, param_string = self.name, ''

        return dict(start_dt=start_dt,
                    end_dt=end_dt,
                    code=code,
                    params=params,
                    name=name,
                    param_string=param_string,
                    )

    def __call__(self, function_to_benchmark, *args, **kwargs):
        start_dt = datetime.now()
        try:
            ret = super().__call__(function_to_benchmark, *args, **kwargs)
        finally:
            end_dt = datetime.now()

            md = self.generate_asv_metadata(function_to_benchmark, start_dt,
                                            end_dt)
            name = md['name']
            if name not in asv_metadata:
                asv_metadata[name] = []

            param_names, param_values = get_all_params_from_marked_test(self.node)
            md['param_names'] = param_names
            md['all_params'] = param_values

            md['_pytest_name'] = self.node.name
            logger.debug('md generated: name=%s md=%s', name, md)
            asv_metadata[name].append(md)

        return ret


@pytest.fixture(scope="function")
def asv_bench(request):
    bs = request.config._benchmarksession

    if bs.skip:
        pytest.skip("[asv] Benchmarks are skipped (--benchmark-skip was "
                    "used).")
    else:
        node = request.node
        marker = node.get_marker("benchmark")
        options = marker.kwargs if marker else {}
        if "timer" in options:
            options["timer"] = NameWrapper(options["timer"])

        # use our subclass here to customize any pytest_benchmark behavior
        logger.debug('Added fixture instance for %s', node.name)

        fixture = AsvBenchmarkFixture(
            node=node,
            add_stats=bs.benchmarks.append,
            logger=bs.logger,
            warner=request.node.warn,
            disabled=bs.disabled,
            **dict(bs.options, **options)
        )
        request.addfinalizer(fixture._cleanup)
        return fixture


def get_conftest_globals():
    'Globals to be in conftest for this shim to work'
    return dict(pytest_benchmark_update_json=pytest_benchmark_update_json,
                benchmark=asv_bench,
                )
