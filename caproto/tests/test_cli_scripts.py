import sys
import pytest
import subprocess
from caproto.sync.client import read, write, subscribe, block

from .conftest import dump_process_output


def escape(pv_name, response):
    raise KeyboardInterrupt


def fix_arg_prefixes(ioc, args):
    'Add prefix to CLI argument pvnames where necessary'
    return [ioc.pvs.get(arg, arg) for arg in args]


@pytest.mark.parametrize('func,args,kwargs',
                         [(read, ('__does_not_exist',), {}),
                          (write, ('__does_not_exist', 5), {}),
                          ])
def test_timeout(func, args, kwargs):
    with pytest.raises(TimeoutError):
        func(*args, **kwargs)


def test_subscribe_timeout():
    with pytest.raises(TimeoutError):
        sub = subscribe('__does_not_exit')
        sub.block()
    with pytest.raises(TimeoutError):
        sub = subscribe('__does_not_exit')
        block(sub)


def _subprocess_communicate(process, command, timeout=10.0):
    stdout, stderr = process.communicate(timeout=timeout)
    dump_process_output(command, stdout, stderr)
    assert process.poll() == 0


@pytest.mark.parametrize('more_kwargs,',
                         [{'repeater': False},
                          {'timeout': 3},
                          {'notify': True},
                          ]
                         )
@pytest.mark.parametrize('func,args,kwargs',
                         [(read, ('float',), {}),
                          (write, ('float', 3.16), {}),
                          (write, ('float', '3.16'), {'data_type': 0}),
                          ])
def test_options(func, args, kwargs, more_kwargs, ioc):
    args = fix_arg_prefixes(ioc, args)
    kwargs.update(more_kwargs)
    func(*args, **kwargs)


@pytest.mark.parametrize('more_kwargs,',
                         [{'repeater': False},
                          {'timeout': 3},
                          ]
                         )
def test_subscribe_options(more_kwargs, ioc):
    args = ('float',)
    args = fix_arg_prefixes(ioc, args)
    sub = subscribe(*args)
    block(sub, duration=0.5, **more_kwargs)


fmt1 = '{response.data[0]}'
fmt2 = '{timestamp:%%H:%%M}'


# Skip the long-running ones.
@pytest.mark.parametrize('command,args',
                         [('caproto-get', ('-h',)),
                          ('caproto-put', ('-h',)),
                          ('caproto-monitor', ('-h',)),
                          ('caproto-get', ('--list-types',)),
                          ('caproto-get', ('float',)),
                          ('caproto-get', ('float', 'str')),
                          # data_type as int, enum name, class on type
                          ('caproto-get', ('float', '-d', '0')),
                          ('caproto-get', ('float', '-d', 'STRING')),
                          ('caproto-get', ('float', '-d', 'string')),
                          ('caproto-get', ('float', '-d', 'CONTROL')),
                          ('caproto-get', ('float', '-d', 'control')),
                          ('caproto-get', ('float', '--format', fmt1)),
                          ('caproto-get', ('float', '--format', fmt2)),
                          ('caproto-get', ('enum',)),
                          ('caproto-get', ('enum', '-n')),
                          ('caproto-get', ('float', '-n')),  # no effect
                          ('caproto-get', ('float', '--no-repeater')),
                          ('caproto-get', ('float', '-p', '0')),
                          ('caproto-get', ('float', '-p', '99')),
                          ('caproto-get', ('float', '-t')),
                          ('caproto-get', ('float', '-l')),
                          ('caproto-get', ('float', '-v')),
                          ('caproto-get', ('float', '-vvv')),
                          ('caproto-put', ('float', '3.16')),
                          ('caproto-put', ('float', '3.16', '--format', fmt1)),
                          ('caproto-put', ('float', '3.16', '--format', fmt2)),
                          ('caproto-put', ('float', '3.16', '--no-repeater')),
                          ('caproto-put', ('float', '3.16', '-p', '0')),
                          ('caproto-put', ('float', '3.16', '-p', '99')),
                          ('caproto-put', ('float', '3.16', '-t')),
                          ('caproto-put', ('float', '3.16', '-l')),
                          ('caproto-put', ('float', '3.16', '-v')),
                          ('caproto-put', ('float', '3.16', '-vvv')),
                          ])
def test_cli(command, args, ioc):
    args = fix_arg_prefixes(ioc, args)
    p = subprocess.Popen([sys.executable, '-um', 'caproto.tests.example_runner',
                          '--script', command] + list(args),
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE
                         )

    _subprocess_communicate(p, command, timeout=10.0)


@pytest.mark.parametrize('args',
                         [('float', '--format', fmt1),
                          ('float', '--format', fmt2),
                          ('float', '--format', '{timedelta}'),
                          ('float', '-m va'),
                          ('float', '-m valp'),
                          ('float', '-m v'),
                          ('enum',),
                          ('enum', '-n'),
                          ('float', '-n'),  # should have no effect
                          ('float', '--no-repeater'),
                          ('float', '-p', '0'),
                          ('float', '-p', '99'),
                          ('float', '-w', '2'),
                          ])
def test_monitor(args, ioc):
    args = fix_arg_prefixes(ioc, args)

    if sys.platform == 'win32':
        si = subprocess.STARTUPINFO()
        si.dwFlags = (subprocess.STARTF_USESTDHANDLES |
                      subprocess.CREATE_NEW_PROCESS_GROUP)
        os_kwargs = dict(startupinfo=si)
    else:
        os_kwargs = {}

    # For the purposes of this test, one monitor output is sufficient
    args += ['--maximum', '1']

    p = subprocess.Popen([sys.executable, '-um', 'caproto.tests.example_runner',
                          '--script', 'caproto-monitor'] + list(args),
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         **os_kwargs)

    _subprocess_communicate(p, 'camonitor', timeout=2.0)
