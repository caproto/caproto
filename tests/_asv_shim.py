import os
import asv
import json

from collections import defaultdict

from datetime import datetime, timedelta


def pytest_bench_machine_to_asv(root, *, node, machine, system, release, cpu,
                                **kw):
    'Pytest-benchmark machine infomation to asv'
    return dict(arch=machine,
                cpu=cpu['brand'],
                machine=node,
                os='{} {}'.format(system, release),
                ram='TODO',
                version=1,
                )


def get_bench_name(fullname, name):
    return name


def asv_bench_result(*, fullname, options, stats, extra_info, params, name,
                     **kwargs):
    'Single benchmark result -> asv format'
    approx_time = stats['mean']
    end_dt = datetime.now()
    started_dt = end_dt - timedelta(seconds=approx_time)  # TODO
    return dict(
        started_at=asv.util.datetime_to_js_timestamp(started_dt),
        ended_at=asv.util.datetime_to_js_timestamp(end_dt),
        results=approx_time,
        name=get_bench_name(fullname, name),
    )


def pytest_bench_results_to_asv(root):
    'All benchmark results -> asv format'
    benches = defaultdict(lambda: {})
    for bench in root['benchmarks']:
        info = asv_bench_result(**bench)
        name = info.pop('name')
        for key, value in info.items():
            benches[key][name] = value
    return benches


def asv_bench_outline(*, fullname, options, stats, extra_info, params, name,
                      **kwargs):
    'Single pytest benchmark outline -> asv'
    # TODO everything here!
    return dict(
        code='TODO',
        goal_time=2.0,
        name=get_bench_name(fullname, name),
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
    results_path = os.path.join(asv_path, 'results')
    os.makedirs(results_path, exist_ok=True)

    machine_path = os.path.join(results_path, machine_info['machine'])
    os.makedirs(machine_path, exist_ok=True)

    with open(os.path.join(results_path, 'benchmarks.json'), 'wt') as f:
        json.dump(bench_outline, f, sort_keys=True, indent=4)

    with open(os.path.join(machine_path, 'machine.json'), 'wt') as f:
        json.dump(machine_info, f, sort_keys=True, indent=4)

    results_fn = '{}-{}.json'.format(bench_results['commit_hash'][:8],
                                     bench_results['env_name'],
                                     )

    with open(os.path.join(machine_path, results_fn), 'wt') as f:
        json.dump(bench_results, f, sort_keys=True, indent=4)
