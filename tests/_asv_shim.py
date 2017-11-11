import os
import asv
import json
import pytest
import logging
import inspect
import pytest_benchmark

from collections import defaultdict

from datetime import datetime, timedelta
from pytest_benchmark.fixture import BenchmarkFixture
from pytest_benchmark.utils import NameWrapper

logger = logging.getLogger(__name__)


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
    logger.debug('Benchmark name is: full=%s short=%s -> %s', fullname,
                 name, name)
    return name


def asv_bench_result(*, fullname, options, stats, extra_info, params, name,
                     **kwargs):
    'Single benchmark result -> asv format'
    asv_metadata = AsvBenchmarkFixture.asv_metadata[name]
    start_dt = asv_metadata['start_dt']
    end_dt = asv_metadata['end_dt']

    return dict(
        name=get_bench_name(fullname, name),
        started_at=asv.util.datetime_to_js_timestamp(start_dt),
        ended_at=asv.util.datetime_to_js_timestamp(end_dt),
        results=dict(stats=dict(min=stats['min'],
                                max=stats['max'],
                                mean=stats['mean'],
                                std=stats['stddev'],
                                n=stats['iterations'],
                                ),
                     result=stats['mean']
                     ),
    )


def pytest_bench_results_to_asv(root):
    'All benchmark results -> asv format'
    benches = defaultdict(lambda: {})
    for bench in root['benchmarks']:
        info = asv_bench_result(**bench)
        name = info.pop('name')
        benches['results'][name] = info.pop('results')
        for key, value in info.items():
            benches[key][name] = value
    return benches


def asv_bench_outline(*, fullname, options, stats, extra_info, params, name,
                      **kwargs):
    'Single pytest benchmark outline -> asv'
    # TODO everything here!
    name = get_bench_name(fullname, name)
    print(name, AsvBenchmarkFixture.asv_metadata.keys())

    return dict(
        code=AsvBenchmarkFixture.asv_metadata[name]['code'],
        goal_time=2.0,
        name=name,
        number=0,
        param_names=[],
        params=[],
        pretty_name=name,
        repeat=stats['iterations'],
        timeout=60.0,
        type='time',
        unit='seconds',
    )


def pytest_bench_outline_to_asv(root):
    'All benchmark outlines -> asv format'
    outlined = {d['pretty_name']: d
                for d in (asv_bench_outline(**bench)
                          for bench in root['benchmarks'])
            }
    outlined.update(version=1)
    return outlined


def pytest_bench_to_asv(root):
    'pytest-benchmark info to asv'
    # root['version']
    # root['datetime']
    commit_info = root['commit_info']

    # TODO git timestamp formatting...
    commit_dt = datetime.strptime(commit_info['time'][:-6],
                                  "%Y-%m-%dT%H:%M:%S")

    machine_info = pytest_bench_machine_to_asv(root, **root['machine_info'])
    params = dict(machine_info)
    # params.update(numpy='')
    params['python'] = '3.5'  # TODO
    del params['version']

    bench_outline = pytest_bench_outline_to_asv(root)

    bench_results = dict(
        commit_hash=commit_info['id'],
        date=asv.util.datetime_to_js_timestamp(commit_dt),
        python=root['machine_info']['python_version'],
        params=params,  # TODO
        profiles={},  # TODO
        requirements={},  # TODO
        env_name=os.environ.get('ASV_ENV_NAME', 'conda-py3.5'),  # TODO
        version=1,
    )

    bench_results.update(**pytest_bench_results_to_asv(root))

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

    results = pytest_bench_to_asv(output_json)
    asv_path = find_asv_root('.')

    logger.info('Saving asv-style JSON to %s', asv_path)
    save_asv_results(asv_path, **results)


class AsvBenchmarkFixture(BenchmarkFixture):
    asv_metadata = {}

    def __call__(self, function_to_benchmark, *args, **kwargs):
        start_dt = datetime.now()
        try:
            ret = super().__call__(function_to_benchmark, *args, **kwargs)
        finally:
            end_dt = datetime.now()

            md = dict(start_dt=start_dt,
                      end_dt=end_dt,
                      code=''.join(inspect.getsourcelines(function_to_benchmark)[0]),
                      )

            AsvBenchmarkFixture.asv_metadata[self.name] = md
        return ret


@pytest.fixture(scope="function")
def asv_bench(request):
    bs = request.config._benchmarksession

    if bs.skip:
        pytest.skip("[asv] Benchmarks are skipped (--benchmark-skip was used).")
    else:
        node = request.node
        marker = node.get_marker("benchmark")
        options = marker.kwargs if marker else {}
        if "timer" in options:
            options["timer"] = NameWrapper(options["timer"])

        # use our subclass here to customize any pytest_benchmark behavior
        logger.debug('Added fixture instance for %s', node.name)

        fixture = AsvBenchmarkFixture(
            node,
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
