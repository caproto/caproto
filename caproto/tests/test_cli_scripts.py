import sys
import pytest
import subprocess
from caproto.sync.client import get, put, monitor, parse_data_type
from caproto import ChannelType

from .conftest import dump_process_output


def escape(pv_name, response):
    raise KeyboardInterrupt


def fix_arg_prefixes(ioc, args):
    'Add prefix to CLI argument pvnames where necessary'
    return [ioc.pvs.get(arg, arg) for arg in args]


@pytest.mark.parametrize('func,args,kwargs',
                         [(get, ('__does_not_exist',), {}),
                          (put, ('__does_not_exist', 5), {}),
                          (monitor, ('__does_not_exist',),
                           {'callback': escape})])
def test_timeout(func, args, kwargs):
    with pytest.raises(TimeoutError):
        func(*args, **kwargs)


def _subprocess_communicate(process, command, timeout=10.0):
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        dump_process_output(command, stdout, stderr)
        raise
    else:
        dump_process_output(command, stdout, stderr)
        assert process.poll() == 0


@pytest.mark.parametrize('more_kwargs,',
                         [{'repeater': False},
                          {'timeout': 3},
                          ]
                         )
@pytest.mark.parametrize('func,args,kwargs',
                         [(get, ('float',), {}),
                          (put, ('float', 5), {}),
                          (monitor, ('float',), {'callback': escape})
                          ])
def test_options(func, args, kwargs, more_kwargs, ioc):
    args = fix_arg_prefixes(ioc, args)
    kwargs.update(more_kwargs)
    func(*args, **kwargs)


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
                          ('caproto-get', ('float', '-d', '5')),
                          ('caproto-get', ('float', '--format', fmt1)),
                          ('caproto-get', ('float', '--format', fmt2)),
                          ('caproto-get', ('enum',)),
                          ('caproto-get', ('enum', '-n')),
                          ('caproto-get', ('float', '-n')),  # no effect
                          ('caproto-get', ('float', '--no-repeater')),
                          ('caproto-get', ('float', '-p', '0')),
                          ('caproto-get', ('float', '-p', '99')),
                          ('caproto-get', ('float', '-t')),
                          ('caproto-get', ('float', '-v')),
                          ('caproto-put', ('float', '5')),
                          ('caproto-put', ('float', '5', '--format', fmt1)),
                          ('caproto-put', ('float', '5', '--format', fmt2)),
                          ('caproto-put', ('float', '5', '--no-repeater')),
                          ('caproto-put', ('float', '5', '-p', '0')),
                          ('caproto-put', ('float', '5', '-p', '99')),
                          ('caproto-put', ('float', '5', '-t')),
                          ('caproto-put', ('float', '5', '-v')),
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


@pytest.mark.parametrize('data_type', ['enum', 'ENUM', '3'])
def test_parse_data_type(data_type):
    assert parse_data_type(data_type) is ChannelType(3)
